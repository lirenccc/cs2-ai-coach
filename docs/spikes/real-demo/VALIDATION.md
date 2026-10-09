# Validation Report — v0.2 Real Demo

Baseline date: 2026-10-09

## Automated validation

- Scaffold validator: PASS
- Default test suite: **39 passed, 1 skipped in 0.32s**
- Private real-demo regression: **40 passed in 2.66s**
- Structural probe CLI: PASS
- Golden fixture comparisons: PASS (17/17)
- Node workspace smoke: PASS
- Process-memory/injection API marker hits: 0
- ZIP CRC/integrity: PASS

The private real-demo regression is skipped by default and runs only when
`CS2_COACH_REAL_DEMO` points to the private `.dem`.

## Real Demo regression verifies

The private fixture is not bundled. Its SHA-256 is used to make accidental fixture drift detectable.

Verified values:
- SHA-256: `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec`
- PBDEMS2 map: `de_dust2`
- patch version: `14189`
- build number: `10924`
- playback time: `1803.40625` seconds
- playback ticks: `115418`
- reverse-verified tick rate for this fixture: `64.0`
- initial roster: 10 humans + CSTV
- `round_freeze_end`: 18
- `player_death`: 128
- `player_hurt`: 444
- `weapon_fire`: 2894
- legacy event count: 17432

## Still unverified in this sandbox

This Linux sandbox has no Rust toolchain and no Windows/CS2 runtime. Therefore these remain local Windows gates:

1. `npm install`
2. `npm run check:web`
3. `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`
4. `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml`
5. current `demoparser2` full entity/tick normalization against this same private Demo
6. CS2 `-netconport` real-game smoke test
7. `playdemo` / pause / seek real-game smoke test
8. Windows.Graphics.Capture smoke test

The repository intentionally reports these as unverified rather than claiming success.

## Environment note

The generation environment emits an unrelated `artifact_tool` spreadsheet warmup warning on
Python process shutdown. It appears on stderr after successful Python commands. Test status/counts
above are parsed from pytest stdout and verified by return code.
