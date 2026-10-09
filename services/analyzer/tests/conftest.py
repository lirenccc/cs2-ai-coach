from __future__ import annotations

from pathlib import Path
import sys

ANALYZER_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYZER_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYZER_ROOT))
