from __future__ import annotations

from .awpy_adapter import AwpyAdapter
from .composite import CompositeDemoParser
from .demoparser2_adapter import Demoparser2Adapter
from .ports import DemoParserAdapter


def create_demo_parser() -> DemoParserAdapter:
    """Default strategy from docs/02_DEMO_PIPELINE.md."""
    return CompositeDemoParser(
        primary=AwpyAdapter(),
        fallback=Demoparser2Adapter(),
    )
