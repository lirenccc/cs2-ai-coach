"""Build a RuleContext from a normalized ParsedDemo (offline, no AI/NetCon)."""

from __future__ import annotations

from collections import defaultdict

from ..demo.models import ParsedDemo
from ..demo.team_codes import normalize_team_code
from ..domain.evidence import EvidenceCertainty, ROUND_SIDE_CONTRACT_VERSION, RoundPlayerState
from .context import LifeEndingEvent, RoundSnapshot, RuleContext
from .thresholds import RuleThresholds


def rule_context_from_parsed(
    parsed: ParsedDemo,
    *,
    match_id: str,
    thresholds: RuleThresholds | None = None,
) -> RuleContext:
    """Map parser-normalized facts into the pure rule context.

    Side / initial alive provenance prefers ``selected_ticks`` at
    ``round_freeze_end`` (P0.6A authoritative source). Roster team is never used
    as a permanent side assignment.
    """

    ticks_by_freeze: dict[int, list] = defaultdict(list)
    for row in parsed.selected_ticks:
        if row.selection_reason != "round_freeze_end":
            continue
        ticks_by_freeze[row.demo_tick].append(row)

    rounds: list[RoundSnapshot] = []
    round_states: list[RoundPlayerState] = []

    for row in parsed.rounds:
        freeze = row.freeze_end_tick
        freeze_rows = ticks_by_freeze.get(freeze or -1, [])
        player_sides: dict[str, str] = {}
        alive: set[str] = set()
        complete = True

        if not freeze_rows:
            complete = False
            side_source = "missing_freeze_end_selected_ticks"
        else:
            side_source = "selected_ticks.team@round_freeze_end"
            for tick_row in freeze_rows:
                team = normalize_team_code(tick_row.team) if tick_row.team else None
                if team not in {"ct", "t"}:
                    continue
                player_sides[tick_row.player_id] = team
                if tick_row.is_alive is True:
                    alive.add(tick_row.player_id)
                elif tick_row.is_alive is None:
                    complete = False
            if len(player_sides) < 2:
                complete = False

        for identity, side in sorted(player_sides.items()):
            round_states.append(
                RoundPlayerState(
                    round_id=row.round_number,
                    player_identity_id=identity,
                    side=side,
                    team_identity=None,
                    source=side_source,
                    contract_version=ROUND_SIDE_CONTRACT_VERSION,
                )
            )

        winner = normalize_team_code(row.winner) if row.winner else None
        rounds.append(
            RoundSnapshot(
                round_id=f"r{row.round_number}",
                round_no=row.round_number,
                freeze_end_demo_tick=row.freeze_end_tick,
                end_demo_tick=row.end_tick,
                winner=winner if winner in {"ct", "t"} else None,
                win_reason=row.win_reason,
                player_sides=player_sides,
                side_source=side_source,
                initial_alive_identity_ids=frozenset(alive),
                alive_provenance_complete=complete and bool(alive),
            )
        )

    side_by_round_player = {
        (state.round_id, state.player_identity_id): state.side for state in round_states
    }

    life_events: list[LifeEndingEvent] = []
    for kill in parsed.kills:
        if kill.round_number is None:
            continue
        victim = kill.victim_id
        attacker = kill.attacker_id
        victim_side = side_by_round_player.get((kill.round_number, victim))
        attacker_side = (
            side_by_round_player.get((kill.round_number, attacker)) if attacker else None
        )
        extras = kill.extras or {}
        if victim_side is None:
            victim_side = normalize_team_code(extras.get("victim_team"))
        if attacker_side is None:
            attacker_side = normalize_team_code(extras.get("attacker_team"))

        is_suicide = (not attacker) or attacker == victim
        is_teamkill = (
            (not is_suicide)
            and victim_side in {"ct", "t"}
            and attacker_side == victim_side
        )
        life_events.append(
            LifeEndingEvent(
                event_id=kill.event_id,
                demo_tick=kill.demo_tick if kill.demo_tick is not None else kill.tick,
                round_no=kill.round_number,
                victim_identity_id=victim,
                attacker_identity_id=attacker,
                victim_side=victim_side if victim_side in {"ct", "t"} else None,
                attacker_side=attacker_side if attacker_side in {"ct", "t"} else None,
                certainty=EvidenceCertainty.DERIVED,
                is_suicide=is_suicide,
                is_teamkill=is_teamkill,
                crosses_unresolved_takeover=bool(
                    extras.get("crosses_unresolved_takeover")
                ),
            )
        )

    life_events.sort(key=lambda item: (item.round_no, item.demo_tick, item.event_id))
    return RuleContext(
        match_id=match_id,
        rounds=tuple(rounds),
        life_ending_events=tuple(life_events),
        thresholds=thresholds or RuleThresholds(),
        round_player_states=tuple(round_states),
    )
