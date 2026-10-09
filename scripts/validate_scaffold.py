from __future__ import annotations

import compileall
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "AGENTS.md",
    "TASKS.md",
    "docs/README.md",
    "docs/01_SYSTEM_ARCHITECTURE.md",
    "docs/spikes/real-demo/P0_2_REPORT.md",
    "docs/prompts/P0_2_FULL_PARSER.md",
    "apps/desktop/package.json",
    "apps/desktop/src/App.tsx",
    "apps/desktop/src-tauri/Cargo.toml",
    "apps/desktop/src-tauri/tauri.conf.json",
    "services/analyzer/pyproject.toml",
    "services/analyzer/app/main.py",
    "services/analyzer/migrations/001_init.sql",
    "packages/contracts/schemas/coach_incident_analysis.schema.json",
    "fixtures/real-demo/expected/9208210907649202700_0.redacted-summary.json",
]

for rel in REQUIRED:
    if not (ROOT / rel).exists():
        raise SystemExit(f"missing required file: {rel}")

SKIP_DIRS = {
    "node_modules",
    "target",
    ".venv",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".git",
}
for path in ROOT.rglob("*.json"):
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    # TypeScript configs are JSONC and are checked by tsc, not this parser.
    if path.name == "tsconfig.json" or path.name.startswith("tsconfig."):
        continue
    json.loads(path.read_text(encoding="utf-8"))

for path in [
    ROOT / "services/analyzer/pyproject.toml",
    ROOT / "apps/desktop/src-tauri/Cargo.toml",
]:
    with path.open("rb") as f:
        tomllib.load(f)

if not compileall.compile_dir(ROOT / "services/analyzer/app", quiet=1):
    raise SystemExit("python compileall failed")

code_roots = [
    ROOT / "apps/desktop/src",
    ROOT / "apps/desktop/src-tauri/src",
    ROOT / "services/analyzer/app",
]
forbidden = [
    "ReadProcessMemory",
    "WriteProcessMemory",
    "CreateRemoteThread",
    "VirtualAllocEx",
]
for base in code_roots:
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".rs", ".ts", ".tsx"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                if marker in text:
                    raise SystemExit(f"forbidden API marker {marker!r} in {path}")

print("scaffold validation: OK")
