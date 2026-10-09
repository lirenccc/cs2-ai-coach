# P0.5 NetCon Real-CS2 Spike — Status

Date: 2026-10-10  
Host OS: Windows 10/11 (`win32`)  
Private fixture: `9208210907649202700_0` (zip/dem **not** committed)

## CS2 build tested

| Field | Value |
| --- | --- |
| Product | Counter-Strike 2 (`appID=730`) |
| `steam.inf` PatchVersion | `1.41.9.0` |
| `steam.inf` ClientVersion / ServerVersion | `2000930` |
| `steam.inf` VersionDate | `Oct 08 2026` |
| Steam `buildid` | `25815307` |
| Binary | `game\bin\win64\cs2.exe` |

## Process launch result

Typed argv (via `steam.exe`, never a concatenated shell string):

```text
steam.exe -applaunch 730 -netconport <ephemeral> -tools
```

Observed child process command line (redacted host paths unchanged; no password used):

```text
cs2.exe -steam -netconport <PORT> -tools
```

| Attempt | Result |
| --- | --- |
| `-netconport` **without** `-tools` | Process starts; **no TCP listener** on the requested port (`CS2_START_TIMEOUT`) |
| `-netconport` **with** `-tools` | TCP listen on `0.0.0.0:<PORT>` **and** VConsole-related `0.0.0.0:29000` |
| CS2 already running without this session’s NetCon | Typed error `CS2_ALREADY_RUNNING_WITHOUT_NETCON` (no silent kill) |

Root cause for Windows without `-tools`: Valve issue [csgo-osx-linux#3603](https://github.com/ValveSoftware/csgo-osx-linux/issues/3603) (`WSANOTINITIALISED` during early netconsole socket create). `-tools` is Workshop Tools, **not** `-insecure` / injection / VAC bypass.

### Post-spike regression: missing `assetsystem` / error 126

On a later cold start, CS2 failed with:

```text
FATAL ERROR: CAppSystemDict:Unable to load module assetsystem
(Dependency of ToolFramework2_002), error 126
```

plus Steam’s “game files missing or damaged” dialog.

Local check: `game\bin\win64\toolframework2.dll` exists, but **`assetsystem.dll` is absent**. Verifying CS2 local files did not restore it. Coach launch now **gates** `-tools` on `assetsystem.dll` + `toolframework2.dll` presence (`CS2_TOOLS_UNAVAILABLE` otherwise). To play CS2 normally: start from Steam **without** `-tools`.

## NetCon connection behavior

- Client connects only to `127.0.0.1:<port>` (renderer cannot supply host).
- With `-tools`, connect succeeds within seconds of process ready.
- Engine listens on **`0.0.0.0`**, not loopback-only → treat as LAN-reachable console; firewall guidance is mandatory for production.
- Console traffic is **plain line-oriented text** on `-netconport` (not the binary VConsole framing used by some third-party clients on `:29000`).
- Responses are **irregular**: startup/engine noise is interleaved; many commands return **empty** best-effort reads (no structured ACK). Product code must keep **raw + best-effort** status.
- Disconnect/reconnect: works on a fresh session with short backoff. If the engine leaves sockets in `CLOSE_WAIT`, new accepts can fail until CS2 restart — surfaced as typed `NETCON_CONNECT_FAILED`, not an infinite retry.

## Commands tested

| Command | Issued via typed API | Observed |
| --- | --- | --- |
| `demo_info` | `ReplayCommand::DemoInfo` | Returns console noise before demo load (Steam activate lines). After load, often empty within idle window. |
| `playdemo <staged>` | `PlayStagedDemo` | Accepted; demo staging name used; load progresses (render-device lines appear). |
| `demo_pause` | `Pause` | Issued OK; response often unrelated engine noise or empty. |
| `demo_resume` | `Resume` | Issued OK; empty response common. |
| `demo_timescale` | `Timescale` | Issued OK (`0.5` then `1.0`); empty response common. |
| `demo_gototick` | `GoToTick(ReplayTick::demo(..))` | Issued OK; empty response common; **playback moved** (manual/integration smoke). Tick **domain UNVERIFIED**. |
| `demo_togglepause` | Serialized in unit tests | Not separately smoked on live build this run. |
| `demo_pauseatservertick` | — | **Not depended on**; not verified this spike. |

## Raw / normalized response examples (redacted)

PII redacted: SteamID / account path segments → `<STEAMID3>` / `<STEAMID64>` / `<ACCOUNT>`.

### `demo_info` before `playdemo` (raw excerpt)

```text
ResetBreakpadAppId: Universe is 1 (k_EUniversePublic)
ResetBreakpadAppId: Setting non standard break pad app id: 2347779
CSteam3Client::Activate succeeded.
SteamID is [U:1:<STEAMID3>] (<STEAMID64>), AppID is 730
Steam text filteri…
```

### `playdemo` / load window (raw excerpt)

```text
Visibility enabled.
USRLOCAL path using Steam profile data folder:
C:\Program Files (x86)\Steam\userdata\<ACCOUNT>\730\local
Determined driver version for graphics adapter 0 …
```

### `demo_pause` window (raw excerpt)

```text
Creating render device for graphics adapter 0 'NVIDIA GeForce RTX …'
Setting setting.cpu_level to 3
Setting setting.gpu_mem_level to 3
Video Card dxsupport …
```

### Later commands (`resume` / `timescale` / `demo_info` / `demo_gototick`)

```text
(raw empty within idle/timeout window — command write succeeded; no reliable ACK)
```

Normalized status policy for this spike:

```text
{ "command": "<typed>", "write_ok": true, "raw_text": "<maybe empty>", "parsed": null }
```

## Demo staging behavior

| Check | Result |
| --- | --- |
| Private zip → SHA-256 `.dem` name | `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec.dem` |
| Matches P0.2 fixture digest | Yes |
| Idempotent re-stage | Yes (unit + probe) |
| Zip-slip rejected | Yes (unit) |
| Ambiguous multi-`.dem` zip rejected | Yes (unit) |
| Original demo unmodified | Yes (copy/extract only) |
| Publish into CS2 `game/csgo/` under safe name | Yes (for `playdemo`) |

## NetCon password investigation

| Evidence | Status |
| --- | --- |
| `engine2.dll` strings: `Bad password attempt from net console`, `Must send PASS command` | Password auth **exists** in engine |
| Cleartext launch option `-netconpassword` in local binaries | **Not found** as a plain string |
| Community / historical docs describe `-netconpassword` + `PASS <pw>` | Documented elsewhere; **not verified** on this build’s launch path |
| This spike’s successful run | **No password** launch arg; connect without `PASS` |

Conclusion: do **not** assume `-netconpassword` works until an explicit opt-in probe (`CS2_COACH_ATTEMPT_NETCON_PASSWORD=1`) succeeds on the target build. Client supports sending `PASS` when enabled.

## Security assumptions

1. `-netconport` creates a **remotely reachable** console (observed bind `0.0.0.0`).
2. Mitigations: random high port, short session lifetime, typed allowlist only, no renderer raw console, no port/password at info logs, Windows Firewall block inbound on that port for production.
3. Normal product path: **no** `-insecure`; Trusted Mode / VAC untouched.
4. Windows product path currently requires `-tools` for NetCon listen (engine bug workaround).
5. No DLL injection, no process-memory game APIs, no binary patching in this spike.

## Failure cases observed

| Case | Code / behavior |
| --- | --- |
| NetCon without `-tools` on Windows | `CS2_START_TIMEOUT` |
| Second launch while CS2 already up on another config | `CS2_ALREADY_RUNNING_WITHOUT_NETCON` |
| Peer TCP close with no prior bytes | `NETCON_CONNECTION_LOST` |
| Illegal session transition | `REPLAY_INVALID_TRANSITION` |
| Reconnect beyond cap | `NETCON_RECONNECT_EXHAUSTED` |
| Command responses empty | Not a hard failure; preserve raw emptiness |

## Remaining unknowns

### Most important (explicitly deferred to P0.5A)

**What tick domain does `demo_gototick` consume for this Demo / current CS2 build?**

**Resolved in P0.5A** for this build + fixture: **DemoTick** (engine “demo tick”; “game tick” aligns with parser `server_tick`). See `docs/spikes/replay/P0_5A_TICK_CALIBRATION.md`. Production `GoToTick` accepts only calibrated `DemoTick` and never translates clocks.

### Other unknowns

- Whether `-netconpassword` launch option is accepted on this Windows build without regressions.
- Whether NetCon can eventually listen without `-tools` after a Valve fix.
- Reliable parse of `demo_info` / seek settle signals from noisy console output.
- Behavior of `demo_pauseatservertick` (intentionally unused).
- Whether `playdemo` of absolute paths (vs csgo-staged names) is stable.

## Test entry points

```powershell
# CI-safe unit tests
cargo test

# Real CS2 (ignored)
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.zip"
cargo test -p cs2-ai-coach --lib probe_ -- --ignored --nocapture --test-threads=1
```

## Parser / storage confirmation

This spike did **not** behaviorally change the Python parser, storage v2 schema, or sidecar HTTP contracts. Only desktop Rust CS2/NetCon/staging/session code and milestone docs were touched.
