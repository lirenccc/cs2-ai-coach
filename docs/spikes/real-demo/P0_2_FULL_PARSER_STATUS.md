# P0.2 Full demoparser2 Adapter — Status

Date: 2026-10-09

Private fixture: `9208210907649202700_0` (zip/dem not committed).

## Verified fields

| Field | Source | Value |
|---|---|---|
| map_name | demoparser2 header | `de_dust2` |
| patch_version | demoparser2 header | `14189` |
| build_num | structural_probe file header | `10924` |
| tick_rate | probe `DEM_FileInfo` for this fixture only | `64.0` |
| playback_ticks | probe file info | `115418` |
| server_start_tick | probe file header | `3779` |
| player_death / hurt / weapon_fire | demoparser2 == probe | 128 / 444 / 2894 |
| round_freeze_end | demoparser2 == probe | 18 |
| grenade detonates | demoparser2 == probe | flash 64, HE 18, smoke 56, inferno 20, decoy 7 |
| roster humans + CSTV | demoparser2 player_info + probe userinfo | 10 + 1 |
| team | demoparser2 `team_number` / tick `team_num` | T/CT entity state |
| demo_tick | demoparser2 `tick` column | preserved on all combat events |
| server_tick | structural_probe legacy event field | joined by event index |
| userid / pawn | structural_probe event values | joined by event index |
| selected ticks | demoparser2 `parse_ticks` at freeze_end | 18 ticks × roster rows |

## Unstable / parser-specific

- demoparser2 0.42 `other=` does **not** expose `userid` / `*_pawn` columns.
- demoparser2 header omits `build_num`, footer timing, `server_start_tick`.
- demoparser2 `player_info` omits CSTV/HLTV and may emit a non-Steam64 placeholder (`steamid=13`).
- demoparser2 `tick` is the outer demo tick (aligned with probe `demo_tick`), not server tick.
- `parse_grenades()` returns full trajectories (hundreds of thousands of rows); P0.2 stores detonate/startburn events only.

## Golden artifacts (no `.dem`)

- `fixtures/real-demo/expected/9208210907649202700_0.redacted-summary.json` (probe)
- `fixtures/real-demo/expected/9208210907649202700_0.redacted-normalized.json` (full parser)

## Still needs CS2 replay verification

- Whether NetCon/GOTV seek by demo tick vs server tick for coach overlays.
- Pawn handle lifetime across respawn / bot_takeover.
- Whether entity `team_num` at freeze_end is sufficient for half-time swaps without round-scoped team history.
