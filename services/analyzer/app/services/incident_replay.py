"""Authoritative IncidentReplayPlan for Click-to-CS2 (native consumer).

The renderer never computes seek ticks. Pre-roll uses match timing metadata
and never hard-codes 64 Hz. Production seek domain is DemoTick only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..demo.structural_probe import probe_demo
from ..domain.timing import pre_roll_tick
from ..errors import AppError
from ..storage.demo_repository import DemoRepository
from ..storage.match_repository import MatchRepository
from .match_review import MatchNotFoundError, MatchNotParsedError, MatchReviewService

INCIDENT_REPLAY_PLAN_VERSION = "1.0.0"
REPLAY_SEMANTICS_VERSION = "p0.5a-2026-10-10"
REPLAY_TICK_DOMAIN = "DemoTick"
DEFAULT_PRE_ROLL_SECONDS = 5.0
DEFAULT_TIMESCALE = 0.5
DEFAULT_SETTLE_DEBOUNCE_MS = 2000
SETTLE_POLICY = "fixed_debounce_ms"


class IncidentNotFoundError(AppError):
    def __init__(self, match_id: str, incident_id: str):
        super().__init__(
            "INCIDENT_NOT_FOUND",
            f"Incident {incident_id} was not found in the current deterministic review",
            False,
            {"match_id": match_id, "incident_id": incident_id},
        )


class DemoSourceMissingError(AppError):
    def __init__(self, match_id: str, demo_sha256: str):
        super().__init__(
            "REPLAY_SOURCE_MISSING",
            "Imported Demo source is missing and no safe managed copy is available",
            False,
            {"match_id": match_id, "demo_sha256": demo_sha256},
        )


def resolve_ticks_per_second(
    match_tick_rate: float | None,
    demo_source_path: str | None,
) -> tuple[float | None, str]:
    """Resolve timing metadata without inventing a global 64 Hz rate."""

    if match_tick_rate is not None and match_tick_rate > 0:
        return float(match_tick_rate), "match.tick_rate"
    if demo_source_path and Path(demo_source_path).is_file():
        try:
            summary, _events = probe_demo(demo_source_path, include_events=False)
            derived = summary.playback.get("derived_tick_rate")
            if isinstance(derived, (int, float)) and float(derived) > 0:
                return float(derived), "structural_probe.derived_tick_rate"
        except Exception:  # noqa: BLE001 — probe is best-effort timing recovery
            pass
    return None, "incident_start_demo_tick"


def compute_seek_demo_tick(
    *,
    anchor_demo_tick: int,
    start_demo_tick: int,
    round_start_demo_tick: int | None,
    tick_rate: float | None,
    timing_source: str = "match.tick_rate",
    pre_roll_seconds: float = DEFAULT_PRE_ROLL_SECONDS,
) -> tuple[int, str, float | None, bool]:
    """Return (seek, timing_source, verified_tick_rate, timing_degraded)."""

    clamp_start = (
        int(round_start_demo_tick)
        if round_start_demo_tick is not None
        else int(start_demo_tick)
    )
    if tick_rate is not None and tick_rate > 0:
        seek = pre_roll_tick(
            int(anchor_demo_tick),
            clamp_start,
            float(pre_roll_seconds),
            float(tick_rate),
        )
        return seek, timing_source, float(tick_rate), False

    # Timing metadata unavailable: never invent 64 Hz; land at authoritative start.
    return int(start_demo_tick), "incident_start_demo_tick", None, True


def build_incident_replay_plan(
    *,
    review: dict[str, Any],
    incident_id: str,
    demo_sha256: str,
    demo_source_path: str | None,
    pre_roll_seconds: float = DEFAULT_PRE_ROLL_SECONDS,
) -> dict[str, Any]:
    match = review["match"]
    match_id = str(match["match_id"])
    incident = next(
        (item for item in review["incidents"] if item["incident_id"] == incident_id),
        None,
    )
    if incident is None:
        raise IncidentNotFoundError(match_id, incident_id)

    round_row = next(
        (
            item
            for item in review["rounds"]
            if item["round_id"] == incident["round_id"]
            or int(item["round_number"]) == int(incident["round_number"])
        ),
        None,
    )
    round_start = None
    if round_row is not None:
        round_start = round_row.get("start_demo_tick")
        if round_start is None:
            round_start = round_row.get("freeze_end_demo_tick")

    tick_rate, timing_label = resolve_ticks_per_second(
        match.get("tick_rate"), demo_source_path
    )
    seek, timing_source, verified_tick_rate, timing_degraded = compute_seek_demo_tick(
        anchor_demo_tick=int(incident["anchor_demo_tick"]),
        start_demo_tick=int(incident["start_demo_tick"]),
        round_start_demo_tick=int(round_start) if round_start is not None else None,
        tick_rate=tick_rate,
        timing_source=timing_label,
        pre_roll_seconds=pre_roll_seconds,
    )

    source_available = bool(
        demo_source_path and Path(demo_source_path).is_file()
    )

    plan: dict[str, Any] = {
        "version": INCIDENT_REPLAY_PLAN_VERSION,
        "match_id": match_id,
        "incident_id": str(incident["incident_id"]),
        "rule_id": str(incident["rule_id"]),
        "round_id": str(incident["round_id"]),
        "round_number": int(incident["round_number"]),
        "start_demo_tick": int(incident["start_demo_tick"]),
        "anchor_demo_tick": int(incident["anchor_demo_tick"]),
        "end_demo_tick": int(incident["end_demo_tick"]),
        "seek_demo_tick": int(seek),
        "replay_tick_domain": REPLAY_TICK_DOMAIN,
        "replay_semantics_version": REPLAY_SEMANTICS_VERSION,
        "timing_source": timing_source,
        "verified_tick_rate": verified_tick_rate,
        "timing_degraded": timing_degraded,
        "pre_roll_seconds": float(pre_roll_seconds),
        "settle_policy": SETTLE_POLICY,
        "settle_debounce_ms": DEFAULT_SETTLE_DEBOUNCE_MS,
        "timescale": DEFAULT_TIMESCALE,
        "auto_resume": True,
        "pov_auto_selected": False,
        "demo_sha256": demo_sha256,
        "demo_source_available": source_available,
        # Native-only field. Never mirrored into the renderer TypeScript contract.
        "demo_source_path": demo_source_path,
    }
    # Hard invariant: production plans never carry server_tick for seek.
    assert "server_tick" not in plan
    assert "seek_server_tick" not in plan
    assert plan["replay_tick_domain"] == REPLAY_TICK_DOMAIN
    return plan


def renderer_safe_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Drop absolute paths / secrets for any renderer-facing serialization."""

    safe = {
        key: value
        for key, value in plan.items()
        if key not in {"demo_source_path", "session_token", "netcon_port"}
    }
    assert "demo_source_path" not in safe
    assert "original_path" not in safe
    return safe


class IncidentReplayService:
    def __init__(
        self,
        match_repo: MatchRepository,
        demo_repo: DemoRepository,
        review_service: MatchReviewService | None = None,
    ):
        self.match_repo = match_repo
        self.demo_repo = demo_repo
        self.review_service = review_service or MatchReviewService(match_repo)

    def get_replay_plan(self, match_id: str, incident_id: str) -> dict[str, Any]:
        match = self.match_repo.get(match_id)
        if match is None:
            raise MatchNotFoundError(match_id)
        if self.match_repo.load_parsed_json(match_id) is None:
            raise MatchNotParsedError(match_id, match.parse_status)

        demo = self.demo_repo.get(match.demo_id)
        if demo is None:
            raise DemoSourceMissingError(match_id, "")

        review = self.review_service.get_review(match_id)
        return build_incident_replay_plan(
            review=review,
            incident_id=incident_id,
            demo_sha256=demo.sha256,
            demo_source_path=demo.original_path,
        )
