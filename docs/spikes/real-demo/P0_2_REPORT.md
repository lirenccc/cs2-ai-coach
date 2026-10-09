# P0.2 Real Demo Parser Spike Report

Baseline date: 2026-10-09

Private fixture used during generation:
`9208210907649202700_0.dem`

The Demo itself is **not bundled** in this repository. Only a redacted golden summary/hash is retained.

## Verified from the actual bytes

### Container

- Format magic: `PBDEMS2\0`
- SHA-256: `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec`
- Size: 76,882,362 bytes
- Outer command frames: 115,484
- `DEM_Packet`: 115,419
- `DEM_FullPacket`: 31

### File header protobuf

- Map: `de_dust2`
- Patch version: `14189`
- Build number: `10924`
- Demo version: `valve_demo_2`
- Server start tick: `3779`
- Client: `SourceTV Demo`
- Server: Perfect World competitive platform ladder server

### Footer / timing

`DEM_FileInfo` contains:

- playback time: `1803.40625` seconds
- playback ticks: `115418`
- playback frames: `115419`

Reverse check:

```text
1803.40625 * 64 = 115418
115418 / 1803.40625 = 64
```

So this fixture's verified demo tick rate is exactly **64 Hz**.

Do not generalize that into a global fixed tick-rate assumption.

### Initial roster

The `DEM_StringTables` snapshot contains a `userinfo` table.

Verified:
- 10 human player entries
- 1 CSTV/HLTV entry

`CMsgPlayerInfo` values provide:
- player name
- SteamID64
- userid/controller slot
- fake-player flag
- HLTV flag

Raw player names and Steam IDs are deliberately not copied into this report.

### Source 1 legacy event bridge

The signon packet contains one `GE_Source1LegacyGameEventList` message.

Verified:
- 271 registered event schemas
- 17,432 emitted legacy events
- 47 event types actually emitted

Selected counts:

| Event | Count |
|---|---:|
| `round_freeze_end` | 18 |
| `player_death` | 128 |
| `player_hurt` | 444 |
| `weapon_fire` | 2,894 |
| `flashbang_detonate` | 64 |
| `smokegrenade_detonate` | 56 |
| `hegrenade_detonate` | 18 |
| `bomb_planted` | 10 |
| `bomb_exploded` | 4 |
| `bomb_defused` | 1 |

Round marker sequence:
- 18 `round_freeze_end`
- 17 `round_officially_ended`
- final `cs_win_panel_match`

This means the final competitive round needs an end-marker fallback instead of assuming every round has `round_officially_ended`.

## Critical schema findings

### 1. Preserve both demo tick and server tick

Across legacy events, the observed histogram for:

```text
server_tick - demo_tick
```

was:

```text
3778 -> 4,002 events
3779 -> 13,068 events
```

Therefore:

- store raw `demo_tick`
- store raw `server_tick` when present
- store `server_start_tick`
- do not replace one tick domain with the other
- do not assume a single constant offset can reconstruct every event

### 2. Controller userid is not the same thing as pawn identity

`player_death` carries both:

- `userid` / `attacker` / `assister`
- `userid_pawn` / `attacker_pawn` / `assister_pawn`

The first group identifies player-controller userids.
The pawn fields identify the in-world pawn/entity handle.

Both must be preserved.

### 3. One controller can die more than once in a round

This fixture contains 12 `bot_takeover` events.

At least 8 round/userid pairs contain multiple `player_death` events for the same controller userid in one competitive round.

Therefore this is invalid:

```text
UNIQUE(match_id, round_no, player_id, death)
```

A death needs its own event ID and pawn identity.

### 4. The initial userinfo snapshot is useful but not sufficient for the whole match

The fixture has:
- player disconnect events
- a later BOT `player_connect`
- bot takeovers

Roster state is temporal.

Recommended model:

```text
PlayerIdentity       stable person / Steam identity
ControllerSession    demo-local userid/controller interval
PawnLife             pawn/entity life interval
Event                immutable event record
```

Do not collapse all four into a single `Player` row.

## What the new structural probe does

`services/analyzer/app/demo/structural_probe.py` is a dependency-free compatibility/preflight parser.

It handles:

- PBDEMS2 16-byte fixed header
- outer command framing
- raw Snappy outer-frame decompression
- `CDemoFileHeader`
- `CDemoFileInfo`
- `CDemoStringTables` userinfo snapshot
- Source 2 bit-level packet-message framing / `ubitvar`
- Source1 legacy event descriptor list
- Source1 legacy event values

It intentionally does **not** implement:
- entity serializer decoding
- player positions
- team/entity state
- view angles
- inventory state
- nav/visibility

Those remain the job of `demoparser2`/Awpy or a future full parser adapter.

## Why keep this probe even after demoparser2 works

It gives the application an independent preflight layer that can answer:

- is the file structurally valid PBDEMS2?
- what patch/build/map is it?
- does the footer/timing make sense?
- can we read the initial roster?
- is the event bridge present?
- did a parser update silently return zero events?

This is valuable for detecting parser compatibility regressions after CS2 updates.

## Next implementation gate

On the Windows/Cursor development machine:

1. install `demoparser2` current supported version,
2. run it against this same Demo,
3. normalize:
   - player info
   - rounds
   - kills
   - damage
   - grenade events
   - selected tick properties
4. compare its event counts with the structural probe,
5. fail closed if the full parser produces suspiciously empty output.

For this fixture, a full parser result reporting zero `player_death` is definitely invalid because the independent event stream contains 128 such events.
