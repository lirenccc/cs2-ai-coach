"""Authoritative alive-count reconstruction for a single round.

Same-tick policy
----------------
All life-ending events that share a DemoTick are applied as one batch.
Parser/list order inside that tick must not change the resulting alive counts.
Within a tick, victims are collected as a set; evidence listing sorts by
``event_id`` for stable serialization only.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.evidence import EvidenceCertainty
from .context import LifeEndingEvent, RoundSnapshot


@dataclass(frozen=True, slots=True)
class AliveCountState:
    demo_tick: int
    ct_alive: int
    t_alive: int
    ct_identities: frozenset[str]
    t_identities: frozenset[str]
    provenance: str


@dataclass(frozen=True, slots=True)
class AliveReconstruction:
    states: tuple[AliveCountState, ...]
    unresolved_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.unresolved_reason is None


def _side_sets(
    round_snap: RoundSnapshot,
) -> tuple[dict[str, str], set[str], set[str]] | str:
    sides = {
        identity: side
        for identity, side in round_snap.player_sides.items()
        if side in {"ct", "t"}
    }
    if not sides:
        return "missing_round_side_state"
    if not round_snap.alive_provenance_complete:
        return "incomplete_alive_provenance"

    ct: set[str] = set()
    t: set[str] = set()
    for identity in round_snap.initial_alive_identity_ids:
        side = sides.get(identity)
        if side is None:
            return f"alive_identity_missing_side:{identity}"
        if side == "ct":
            ct.add(identity)
        else:
            t.add(identity)
    return sides, ct, t


def reconstruct_alive_states(
    round_snap: RoundSnapshot,
    events: tuple[LifeEndingEvent, ...] | list[LifeEndingEvent],
) -> AliveReconstruction:
    """Build the DemoTick-ordered alive-count sequence for one round."""

    prepared = _side_sets(round_snap)
    if isinstance(prepared, str):
        return AliveReconstruction(states=(), unresolved_reason=prepared)

    sides, ct_alive, t_alive = prepared
    start_tick = round_snap.freeze_end_demo_tick
    if start_tick is None:
        start_tick = min((event.demo_tick for event in events), default=0)

    states: list[AliveCountState] = [
        AliveCountState(
            demo_tick=start_tick,
            ct_alive=len(ct_alive),
            t_alive=len(t_alive),
            ct_identities=frozenset(ct_alive),
            t_identities=frozenset(t_alive),
            provenance=round_snap.side_source,
        )
    ]

    # Batch by demo_tick; ignore input list order within a tick.
    by_tick: dict[int, list[LifeEndingEvent]] = {}
    for event in events:
        by_tick.setdefault(event.demo_tick, []).append(event)

    for tick in sorted(by_tick):
        batch = sorted(by_tick[tick], key=lambda item: item.event_id)
        victims: set[str] = set()
        for event in batch:
            if event.certainty == EvidenceCertainty.UNRESOLVED:
                return AliveReconstruction(
                    states=tuple(states),
                    unresolved_reason=(
                        f"life_ending_certainty_unresolved:{event.event_id}"
                    ),
                )
            if event.crosses_unresolved_takeover:
                return AliveReconstruction(
                    states=tuple(states),
                    unresolved_reason=(
                        f"unresolved_takeover_attribution:{event.event_id}"
                    ),
                )
            if not event.victim_identity_id:
                return AliveReconstruction(
                    states=tuple(states),
                    unresolved_reason=f"missing_victim_identity:{event.event_id}",
                )
            victim = event.victim_identity_id
            expected_side = sides.get(victim)
            event_side = event.victim_side
            if victim not in ct_alive and victim not in t_alive:
                # Not part of the authoritative alive set (already dead, spectator,
                # or absent from freeze_end snapshot). Do not invent a side or
                # fabricate an alive-count change.
                continue
            if expected_side is None:
                # Currently counted alive but missing side provenance.
                return AliveReconstruction(
                    states=tuple(states),
                    unresolved_reason=f"victim_side_unknown:{victim}",
                )
            if event_side is not None and event_side in {"ct", "t"}:
                if event_side != expected_side:
                    return AliveReconstruction(
                        states=tuple(states),
                        unresolved_reason=(
                            f"victim_side_conflict:{victim}:{expected_side}:{event_side}"
                        ),
                    )
            victims.add(victim)

        if not victims:
            continue

        for victim in sorted(victims):
            if victim in ct_alive:
                ct_alive.remove(victim)
            elif victim in t_alive:
                t_alive.remove(victim)

        states.append(
            AliveCountState(
                demo_tick=tick,
                ct_alive=len(ct_alive),
                t_alive=len(t_alive),
                ct_identities=frozenset(ct_alive),
                t_identities=frozenset(t_alive),
                provenance="life_ending_batch",
            )
        )

    return AliveReconstruction(states=tuple(states))


def advantage_for_side(state: AliveCountState, side: str) -> int:
    if side == "ct":
        return state.ct_alive - state.t_alive
    if side == "t":
        return state.t_alive - state.ct_alive
    raise ValueError(f"unsupported side: {side}")
