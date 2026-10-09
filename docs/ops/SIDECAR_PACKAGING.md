# Sidecar Packaging Plan

Development starts the Python analyzer separately so the repository works
before a packaged executable exists.

P0.3 should switch production startup to a Tauri-managed external binary.

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
