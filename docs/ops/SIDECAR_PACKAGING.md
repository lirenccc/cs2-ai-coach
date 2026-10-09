# Sidecar Packaging Plan

Development: Tauri spawns `.venv` Python (`python -m app`) with a random
loopback port and per-session token. Set `CS2_COACH_ANALYZER_PYTHON` /
`CS2_COACH_DB_PATH` via `scripts/dev.ps1` if needed.

Production: switch startup to a Tauri-managed external binary.

Target:

```text
apps/desktop/src-tauri/binaries/
  analyzer-sidecar-x86_64-pc-windows-msvc.exe
```

Tauri config then adds:

```json
{
  "bundle": {
    "externalBin": ["binaries/analyzer-sidecar"]
  }
}
```

Rust lifecycle should use the Tauri shell sidecar API and retain `CommandChild`
in managed state.

Production:
1. choose unused loopback port,
2. generate random high-entropy token,
3. spawn sidecar,
4. health probe,
5. renderer invokes Tauri only,
6. Tauri authenticates analyzer requests,
7. kill child on desktop exit.
