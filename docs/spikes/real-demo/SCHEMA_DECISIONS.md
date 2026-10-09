# Real-Demo Schema Decisions

These decisions are based on the verified P0.2 private fixture.

## Identity

### `player_identity`
Stable identity when known.

- `id`
- `steamid64`
- `display_name_latest`

### `controller_session`
A demo-local controller/userid binding.

- `id`
- `match_id`
- `userid`
- `player_identity_id?`
- `connected_demo_tick?`
- `disconnected_demo_tick?`
- `is_bot`
- `is_hltv`

### `pawn_life`
One in-world pawn/life.

- `id`
- `match_id`
- `controller_session_id?`
- `pawn_handle`
- `spawn_demo_tick?`
- `death_demo_tick?`

Do not assume one pawn per player per round.

## Event clocks

Every normalized event should support:

- `demo_tick` — PBDEMS2 outer frame tick
- `server_tick` — embedded event tick when present
- `server_start_tick` — match/header reference
- `demo_time_seconds?` — derived only when validated timing exists
- `round_relative_seconds?` — derived presentation field

Never overwrite raw tick fields with derived clocks.

## Kill event

Recommended columns:

- `event_id`
- `match_id`
- `round_id?`
- `demo_tick`
- `server_tick?`
- `victim_userid`
- `victim_pawn_handle?`
- `attacker_userid?`
- `attacker_pawn_handle?`
- `assister_userid?`
- `assister_pawn_handle?`
- `weapon`
- `headshot`
- `penetrated`
- `through_smoke`
- `attacker_blind`
- `attacker_in_air`
- `distance`
- `hp_damage`
- `armor_damage`
- `hitgroup`
- `source_event_id`
- `source_parser`

`event_id` is the unique identity. Do not create a uniqueness constraint on player+round.

## Round construction

Use a round state machine rather than only one event name.

Observed real fixture:

```text
round_freeze_end x18
round_officially_ended x17
cs_win_panel_match x1
```

MVP state machine:

1. open competitive round at `round_freeze_end`;
2. close at next `round_officially_ended` when present;
3. final fallback: `cs_win_panel_match`;
4. retain the raw marker events as evidence;
5. later cross-check against parser/score state.

## Team truth

The event-only structural probe does not authoritatively expose every player's team.

Do not persist inferred team grouping as fact.

Full parser should obtain authoritative team/entity state from player-controller/entity properties.
