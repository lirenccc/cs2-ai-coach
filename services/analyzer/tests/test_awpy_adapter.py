from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.demo.archive import resolve_demo_file
from app.demo.awpy_adapter import AwpyAdapter
from app.demo.factory import create_demo_parser


def test_awpy_is_installed_and_available() -> None:
    adapter = AwpyAdapter()
    assert adapter.available() is True
    assert adapter.version() is not None
    assert adapter.version().startswith("2.")


@pytest.mark.skipif(
    not os.environ.get("CS2_COACH_REAL_DEMO"),
    reason="set CS2_COACH_REAL_DEMO to exercise Awpy on a private demo/zip",
)
def test_awpy_parses_real_demo_tables(tmp_path: Path) -> None:
    source = Path(os.environ["CS2_COACH_REAL_DEMO"])
    resolved = resolve_demo_file(source, extract_root=tmp_path / "extracted")
    parsed = AwpyAdapter().parse(resolved.demo_path)

    assert parsed.parser_name == "awpy"
    assert parsed.header.map_name == "de_dust2"
    assert parsed.header.patch_version == "14189"
    assert len(parsed.rounds) == 18
    assert len(parsed.damages) == 444
    assert len(parsed.kills) >= 125
    assert len(parsed.roster) >= 10
    assert all(row.event_id for row in parsed.kills)
    assert "DataFrame" not in repr(parsed.to_dict())


@pytest.mark.skipif(
    not os.environ.get("CS2_COACH_REAL_DEMO"),
    reason="set CS2_COACH_REAL_DEMO to exercise composite awpy+demoparser2 fill",
)
def test_composite_prefers_denser_kill_table(tmp_path: Path) -> None:
    source = Path(os.environ["CS2_COACH_REAL_DEMO"])
    resolved = resolve_demo_file(source, extract_root=tmp_path / "extracted")
    parsed = create_demo_parser().parse(resolved.demo_path)

    assert "awpy" in parsed.parser_name
    assert len(parsed.damages) == 444
    assert len(parsed.kills) == 128
    assert len(parsed.rounds) == 18
