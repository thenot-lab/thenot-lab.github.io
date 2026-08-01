# Eli OS — Survivable Instance (OneDrive-resident)

A full working instance whose durable core lives **inside OneDrive**, so the
instance survives anything that kills a machine: reinstall, disk loss, a
reclaimed cloud container, or a wiped `.claude` folder. Any machine that can
sign in to OneDrive can rebuild the running instance from the synced folder
alone.

The design splits the instance into two halves:

| Half | Lives | Property |
|---|---|---|
| **Durable core** | `<OneDrive>\DominionLabs\eli-instance\` | Only atomic, whole-file artifacts: state snapshots, a repo bundle, handoffs, config. Survives everything. |
| **Local runtime** | `%LOCALAPPDATA%\EliOS\` (never synced) | Hot SQLite DBs, telemetry JSONL, the running gateway. Disposable — rebuilt from the core by `bootstrap.ps1`. |

## The two rules

1. **Nothing hot in the synced folder.** OneDrive syncs files while they are
   being written; a live SQLite DB (or its `-wal`) synced mid-transaction
   produces torn copies and `-conflict` files. Databases and telemetry run in
   the local runtime dir and reach OneDrive only as **snapshots** — single
   consistent files produced by `VACUUM INTO` and moved into place with an
   atomic rename.
2. **Everything in the synced folder is atomic and stamped.** Writes go to a
   temp name then `os.replace()` — OneDrive never sees a half-written file.
   Snapshot names carry `<host>-<utc-timestamp>` so two machines can never
   collide on the same filename; last-N are kept per host, and OneDrive's own
   30-day version history backs even that.

## Layout of the durable core

```text
<OneDrive>\DominionLabs\eli-instance\
├── state\        state-<host>-<ts>.db      ← VACUUM INTO snapshots (memory stores)
├── telemetry\    telemetry-<host>-<ts>.jsonl  ← rotated telemetry copies
├── repo\         eli.bundle                ← git bundle: the whole repo, one file
├── handoffs\     next_session_handoff_<date>.md  ← session handoffs (newest wins)
└── instance.json                            ← manifest: ports, paths, versions
```

## Lifecycle

```text
snapshot.py snapshot   local runtime ──VACUUM INTO / bundle / rename──▶ OneDrive core
bootstrap.ps1          OneDrive core ──unbundle / restore newest ─────▶ fresh machine
snapshot.py handoff    writes handoffs\next_session_handoff_<date>.md (+ git dual-write)
```

- **`snapshot.py`** (stdlib-only) does every write into the core:
  `snapshot` (DBs + telemetry + repo bundle, with per-host pruning),
  `restore` (newest snapshot → local runtime), `handoff` (write/read
  handoffs). Run it from a scheduled task, a BRA.Y.AI service hook, or by
  hand.
- **`bootstrap.ps1`** is the survivability proof: on a brand-new Windows
  machine with OneDrive signed in and Python installed, it locates the core
  (`$env:OneDrive`), clones the repo from `repo\eli.bundle` (GitHub is the
  fallback, not the requirement), restores the newest state snapshot into
  `%LOCALAPPDATA%\EliOS\`, and starts the gateway on `127.0.0.1:8484`. One
  script, zero other prerequisites.

## The handoff loop (why this exists)

A session handoff written only to `C:\Users\<user>\.claude\projects\...` is
invisible to every other machine and every cloud session — it dies with the
box. Written to `handoffs\` in the core it syncs to every machine; and
because cloud containers can't mount OneDrive, `snapshot.py handoff --push`
**dual-writes** the same file to a git branch, which cloud sessions *can*
read. Durable on both transports; either one alone survives.

## Acceptance (survivability check)

- Wipe test: on a machine that has never seen the project, sign in to
  OneDrive → run `bootstrap.ps1` → `curl 127.0.0.1:8484/healthz` returns the
  policy version, and the memory store contains the last snapshot's data.
- Conflict test: snapshot from two hosts in the same minute → two distinct
  files, no `-conflict` copies, `restore` picks the newest by timestamp.
- Handoff test: `snapshot.py handoff --read` on machine B returns what
  machine A wrote, byte-identical.

## Headless / Linux transport: rclone

On machines without the OneDrive client (VPS, Termux, the home box running
headless), the same core is reachable via rclone — and this matches the
transport the ecosystem's existing continuance automation already uses
(`rclone` → an `onedrive:` remote). After `rclone config` once:

```sh
rclone copy "$ELI_RUNTIME_SNAPSHOTS" onedrive:DominionLabs/eli-instance/state
rclone copy onedrive:DominionLabs/eli-instance/handoffs /tmp/handoffs
```

`snapshot.py` doesn't care how the core folder syncs — client, rclone, or
both — because every artifact is a whole, stamped, atomically-renamed file.

## Explicit non-goals

- OneDrive does not run anything; there is no "execution in the cloud drive."
- No secrets in the core: `ANTHROPIC_API_KEY` and keystores stay in local env
  files / OS keychains. The core must be safe if the OneDrive account is
  shared or synced to a family PC.
