from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "services" / "analyzer"
if str(ANALYZER) not in sys.path:
    sys.path.insert(0, str(ANALYZER))

from app.demo.archive import resolve_demo_file
from app.demo.structural_probe import probe_demo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("demo", help="Path to a .dem or a .zip containing one .dem")
    parser.add_argument("--events", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--extract-root",
        type=Path,
        default=ROOT / "runtime" / "extracted",
    )
    args = parser.parse_args()

    resolved = resolve_demo_file(args.demo, extract_root=args.extract_root)
    summary, events = probe_demo(resolved.demo_path, include_events=args.events)
    payload = {
        "source_path": str(resolved.source_path),
        "demo_path": str(resolved.demo_path),
        "from_archive": resolved.from_archive,
        "archive_member": resolved.archive_member,
        "summary": summary.to_dict(),
    }
    if args.events:
        payload["events"] = events

    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
