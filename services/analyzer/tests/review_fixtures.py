"""CI-safe synthetic ParsedDemo covering Match Review scenarios."""

from __future__ import annotations

from app.demo.models import (
    NORMALIZATION_SCHEMA_VERSION,
    KillRow,
    MatchHeader,
    ParsedDemo,
    PlayerRosterEntry,
    RoundRow,
    SelectedTickRow,
)
from app.storage.match_repository import MatchRecord


CT = [f"pid_ct{i}" for i in range(1, 6)]
T = [f"pid_t{i}" for i in range(1, 6)]


def _freeze_ticks(round_no: int, identities: list[tuple[str, str]]) -> list[SelectedTickRow]:
    freeze = {1: 100, 2: 1000, 3: 2000, 13: 9000}[round_no]
    return [
        SelectedTickRow(
            demo_tick=freeze,
            player_id=identity,
            steamid64=None,
            x=0.0,
            y=0.0,
            z=0.0,
            health=100.0,
            team=team.upper(),
            is_alive=True,
            selection_reason="round_freeze_end",
        )
        for identity, team in identities
    ]


def synthetic_review_parsed() -> ParsedDemo:
    """Fixture covering R001/R002/R003, same-tick, halftime, zero-incident, unresolved."""

    pre_sides = [(p, "ct") for p in CT] + [(p, "t") for p in T]
    # Post-halftime: former CT players are now T.
    post_sides = [(p, "t") for p in CT] + [(p, "ct") for p in T]

    roster = [
        PlayerRosterEntry(
            player_id=pid,
            steamid64=None,
            display_name=f"Player_{pid[-2:]}",
            team="CT" if pid.startswith("pid_ct") else "T",
            is_bot=False,
        )
        for pid in CT + T
    ]

    rounds = [
        RoundRow(
            round_number=1,
            freeze_end_tick=100,
            end_tick=500,
            winner="t",
            win_reason="elimination",
        ),
        RoundRow(
            round_number=2,
            freeze_end_tick=1000,
            end_tick=1500,
            winner="ct",
            win_reason="bomb_defused",
        ),
        RoundRow(
            round_number=3,
            freeze_end_tick=2000,
            end_tick=2500,
            winner="ct",
            win_reason="elimination",
        ),
        RoundRow(
            round_number=13,
            freeze_end_tick=9000,
            end_tick=9500,
            winner="ct",
            win_reason="target_bombed",
        ),
    ]

    # Round 1: same-tick opening deaths (CT1+CT2), untraded chain, then CT collapses from 5v3.
    # Peak CT advantage 2 after two T deaths, then CT wiped → R003 for CT.
    kills = [
        KillRow(
            event_id="kill:r1:a",
            tick=200,
            demo_tick=200,
            attacker_id=T[0],
            victim_id=CT[0],
            round_number=1,
            weapon="ak47",
        ),
        KillRow(
            event_id="kill:r1:b",
            tick=200,
            demo_tick=200,
            attacker_id=T[1],
            victim_id=CT[1],
            round_number=1,
            weapon="ak47",
        ),
        KillRow(
            event_id="kill:r1:c",
            tick=260,
            demo_tick=260,
            attacker_id=CT[2],
            victim_id=T[0],
            round_number=1,
            weapon="m4a1",
        ),
        KillRow(
            event_id="kill:r1:d",
            tick=270,
            demo_tick=270,
            attacker_id=CT[2],
            victim_id=T[1],
            round_number=1,
            weapon="m4a1",
        ),
        # CT now 3v3 after two openings died — need more for advantage.
        # Kill two more T → CT 3v1 advantage 2, then CT lose remaining.
        KillRow(
            event_id="kill:r1:e",
            tick=300,
            demo_tick=300,
            attacker_id=CT[3],
            victim_id=T[2],
            round_number=1,
            weapon="m4a1",
        ),
        KillRow(
            event_id="kill:r1:f",
            tick=310,
            demo_tick=310,
            attacker_id=CT[3],
            victim_id=T[3],
            round_number=1,
            weapon="m4a1",
        ),
        # 3v1 CT advantage. Now T wins by wiping CT.
        KillRow(
            event_id="kill:r1:g",
            tick=400,
            demo_tick=400,
            attacker_id=T[4],
            victim_id=CT[2],
            round_number=1,
            weapon="awp",
        ),
        KillRow(
            event_id="kill:r1:h",
            tick=410,
            demo_tick=410,
            attacker_id=T[4],
            victim_id=CT[3],
            round_number=1,
            weapon="awp",
        ),
        KillRow(
            event_id="kill:r1:i",
            tick=420,
            demo_tick=420,
            attacker_id=T[4],
            victim_id=CT[4],
            round_number=1,
            weapon="awp",
        ),
        # Round 2: traded opening — should produce fewer / zero untraded for victim.
        KillRow(
            event_id="kill:r2:a",
            tick=1100,
            demo_tick=1100,
            attacker_id=T[0],
            victim_id=CT[0],
            round_number=2,
            weapon="ak47",
        ),
        KillRow(
            event_id="kill:r2:b",
            tick=1110,
            demo_tick=1110,
            attacker_id=CT[1],
            victim_id=T[0],
            round_number=2,
            weapon="m4a1",
        ),
        # Round 3: unresolved takeover opening — UNRESOLVED, not an incident.
        KillRow(
            event_id="kill:r3:a",
            tick=2100,
            demo_tick=2100,
            attacker_id=T[0],
            victim_id=CT[0],
            round_number=3,
            weapon="ak47",
            extras={"crosses_unresolved_takeover": True},
        ),
        # Round 13 post-halftime: pid_ct1 is now on T side.
        KillRow(
            event_id="kill:r13:a",
            tick=9100,
            demo_tick=9100,
            attacker_id=T[0],  # former T now CT
            victim_id=CT[0],  # former CT now T
            round_number=13,
            weapon="ak47",
        ),
    ]

    selected = (
        _freeze_ticks(1, pre_sides)
        + _freeze_ticks(2, pre_sides)
        + _freeze_ticks(3, pre_sides)
        + _freeze_ticks(13, post_sides)
    )

    return ParsedDemo(
        parser_name="synthetic-review",
        parser_version="1.0.0",
        normalization_schema_version=NORMALIZATION_SCHEMA_VERSION,
        header=MatchHeader(
            map_name="de_dust2",
            tick_rate=128.0,
            build_num="test-build",
        ),
        roster=roster,
        rounds=rounds,
        kills=kills,
        damages=[],
        selected_ticks=selected,
        event_counts={"player_death": len(kills), "round_freeze_end": 4},
        source_path="C:/private/should-not-leak.dem",
    )


def synthetic_match_record(match_id: str = "match_review_synth") -> MatchRecord:
    parsed = synthetic_review_parsed()
    return MatchRecord(
        id=match_id,
        demo_id="demo_review_synth",
        map_name=parsed.header.map_name,
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        normalization_schema_version=parsed.normalization_schema_version,
        parse_status="completed",
        roster_count=len(parsed.roster),
        round_count=len(parsed.rounds),
        kill_count=len(parsed.kills),
        damage_count=0,
    )
