#!/usr/bin/env python3
"""Survivable-instance snapshots: local runtime <-> OneDrive durable core.

Every write into the synced folder is a whole file moved into place with an
atomic rename, stamped <host>-<utc-ts> so concurrent machines never collide.
Hot files (live SQLite, telemetry being appended) never live in the core.

Usage:
    python3 snapshot.py snapshot [--repo DIR]      # DBs + telemetry + bundle -> core
    python3 snapshot.py restore                    # newest state snapshot -> local runtime
    python3 snapshot.py handoff --write FILE [--push BRANCH]   # publish a handoff
    python3 snapshot.py handoff --read             # print newest handoff
    python3 snapshot.py status                     # core + runtime inventory

Paths (all overridable by env):
    ONEDRIVE_DIR   OneDrive root      (default: %OneDrive%)
    ELI_CORE       durable core       (default: <OneDrive>/DominionLabs/eli-instance)
    ELI_RUNTIME    local runtime dir  (default: %LOCALAPPDATA%/EliOS, else ~/.eli-os)
"""

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KEEP_PER_HOST = 5  # snapshots retained per host per kind; OneDrive history backs the rest


def onedrive_root():
    for var in ("ONEDRIVE_DIR", "OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(var)
        if v and Path(v).is_dir():
            return Path(v)
    raise SystemExit("error: OneDrive root not found — set ONEDRIVE_DIR or sign in to OneDrive")


def core_dir():
    c = Path(os.environ.get("ELI_CORE") or onedrive_root() / "DominionLabs" / "eli-instance")
    for sub in ("state", "telemetry", "repo", "handoffs"):
        (c / sub).mkdir(parents=True, exist_ok=True)
    return c


def runtime_dir():
    r = os.environ.get("ELI_RUNTIME")
    if r:
        p = Path(r)
    elif os.environ.get("LOCALAPPDATA"):
        p = Path(os.environ["LOCALAPPDATA"]) / "EliOS"
    else:
        p = Path.home() / ".eli-os"
    p.mkdir(parents=True, exist_ok=True)
    return p


def stamp():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def host():
    # single token: no dashes/dots, so snapshot names split unambiguously
    h = socket.gethostname().split(".")[0].lower().replace("-", "").replace("_", "")
    return h or "host"


def atomic_publish(tmp_path, dest):
    """Move a fully-written temp file into the core in one rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp_path, dest)
    return dest


def prune(directory, prefix, keep=KEEP_PER_HOST):
    mine = sorted(p for p in directory.glob(prefix + "*") if p.is_file())
    for old in mine[:-keep]:
        old.unlink()


def snapshot_dbs(core, runtime):
    out = []
    for db in sorted(runtime.glob("*.db")):
        tag = f"state-{db.stem}-{host()}-"
        fd, tmp = tempfile.mkstemp(dir=core / "state", suffix=".part")
        os.close(fd)
        os.unlink(tmp)  # VACUUM INTO refuses an existing file
        con = sqlite3.connect(db)
        try:
            con.execute("VACUUM INTO ?", (str(tmp),))
        finally:
            con.close()
        dest = atomic_publish(tmp, core / "state" / f"{tag}{stamp()}.db")
        prune(core / "state", tag)
        out.append(dest.name)
    return out


def snapshot_telemetry(core, runtime):
    out = []
    for jl in sorted(runtime.glob("*.jsonl")):
        tag = f"telemetry-{jl.stem}-{host()}-"
        fd, tmp = tempfile.mkstemp(dir=core / "telemetry", suffix=".part")
        os.close(fd)
        shutil.copyfile(jl, tmp)  # append-only source: a plain copy is prefix-consistent
        dest = atomic_publish(tmp, core / "telemetry" / f"{tag}{stamp()}.jsonl")
        prune(core / "telemetry", tag)
        out.append(dest.name)
    return out


def snapshot_repo(core, repo):
    if not (Path(repo) / ".git").exists():
        return None
    fd, tmp = tempfile.mkstemp(dir=core / "repo", suffix=".part")
    os.close(fd)
    r = subprocess.run(["git", "-C", str(repo), "bundle", "create", tmp, "--all"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp)
        print(f"warn: repo bundle failed: {r.stderr.strip()}", file=sys.stderr)
        return None
    return atomic_publish(tmp, core / "repo" / "eli.bundle").name


def restore_state(core, runtime):
    restored = []
    # group snapshots by db stem: state-<stem>-<host>-<ts>.db ; newest ts wins across hosts
    groups = {}
    for p in (core / "state").glob("state-*.db"):
        parts = p.stem.split("-")
        if len(parts) < 4:
            continue
        db_stem = "-".join(parts[1:-2])
        groups.setdefault(db_stem, []).append(p)
    for db_stem, snaps in groups.items():
        newest = max(snaps, key=lambda p: p.stem.rsplit("-", 1)[-1])
        fd, tmp = tempfile.mkstemp(dir=runtime, suffix=".part")
        os.close(fd)
        shutil.copyfile(newest, tmp)
        os.replace(tmp, runtime / f"{db_stem}.db")
        restored.append(f"{newest.name} -> {db_stem}.db")
    return restored


def write_manifest(core, extra):
    manifest = {"updated_utc": stamp(), "host": host(),
                "gateway": {"bind": "127.0.0.1", "port": 8484, "health": "/healthz"},
                **extra}
    fd, tmp = tempfile.mkstemp(dir=core, suffix=".part")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    atomic_publish(tmp, core / "instance.json")


def handoff_write(core, src, push_branch=None):
    text = Path(src).read_text(encoding="utf-8")
    name = f"next_session_handoff_{time.strftime('%Y_%m_%d', time.gmtime())}.md"
    fd, tmp = tempfile.mkstemp(dir=core / "handoffs", suffix=".part")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    dest = atomic_publish(tmp, core / "handoffs" / name)
    if push_branch:  # dual-write: cloud sessions can't mount OneDrive, but they can read git
        repo = Path(__file__).resolve().parents[2]
        for cmd in (["git", "-C", str(repo), "checkout", "-B", push_branch],
                    ["git", "-C", str(repo), "add", "-A"],
                    ["git", "-C", str(repo), "commit", "-m", f"handoff: {name}", "--allow-empty"],
                    ["git", "-C", str(repo), "push", "-u", "origin", push_branch]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"warn: dual-write step failed: {' '.join(cmd[3:])}: {r.stderr.strip()}",
                      file=sys.stderr)
                break
    return dest


def handoff_read(core):
    snaps = sorted((core / "handoffs").glob("next_session_handoff_*.md"))
    if not snaps:
        raise SystemExit("no handoffs in core")
    return snaps[-1]


def status(core, runtime):
    def listing(d, pat):
        return sorted(p.name for p in d.glob(pat))
    return {
        "core": str(core),
        "runtime": str(runtime),
        "state_snapshots": listing(core / "state", "state-*.db"),
        "telemetry_snapshots": listing(core / "telemetry", "telemetry-*.jsonl"),
        "repo_bundle": listing(core / "repo", "*.bundle"),
        "handoffs": listing(core / "handoffs", "*.md"),
        "runtime_dbs": listing(runtime, "*.db"),
    }


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    core, runtime = core_dir(), runtime_dir()

    if cmd == "snapshot":
        repo = argv[argv.index("--repo") + 1] if "--repo" in argv else Path(__file__).resolve().parents[2]
        dbs = snapshot_dbs(core, runtime)
        tel = snapshot_telemetry(core, runtime)
        bundle = snapshot_repo(core, repo)
        write_manifest(core, {"last_snapshot": {"dbs": dbs, "telemetry": tel, "bundle": bundle}})
        print(json.dumps({"dbs": dbs, "telemetry": tel, "bundle": bundle}, indent=2))
    elif cmd == "restore":
        print(json.dumps({"restored": restore_state(core, runtime)}, indent=2))
    elif cmd == "handoff" and "--write" in argv:
        src = argv[argv.index("--write") + 1]
        branch = argv[argv.index("--push") + 1] if "--push" in argv else None
        print(handoff_write(core, src, branch))
    elif cmd == "handoff" and "--read" in argv:
        print(handoff_read(core).read_text(encoding="utf-8"))
    elif cmd == "status":
        print(json.dumps(status(core, runtime), indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
