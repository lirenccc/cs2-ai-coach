# Cursor Prompt — P0.2 Full Parser

Paste this into Cursor after opening this repository:

> Read `AGENTS.md`, `.cursor/rules/*`, `docs/spikes/real-demo/P0_2_REPORT.md`,
> `docs/spikes/real-demo/SCHEMA_DECISIONS.md`, `docs/01_SYSTEM_ARCHITECTURE.md`,
> `docs/02_DEMO_PIPELINE.md`, and `TASKS.md`.
>
> First run all existing checks. Do not modify code until they pass.
>
> Then implement only the full `demoparser2` P0.2 adapter against my local private Demo.
> The private Demo path will be supplied by me and must not be committed.
>
> Requirements:
> 1. Run `structural_probe.py` first and save its summary in test output.
> 2. Run current `demoparser2` against the same file.
> 3. Normalize roster, kills, damage, grenade events, round markers, and a minimal selected tick set.
> 4. Preserve raw `demo_tick`, raw event/server tick when available, controller userid, and pawn handles.
> 5. Do not assume 64 tick globally; use the fixture's verified footer timing only for this file.
> 6. Do not assume one death per player per round.
> 7. Compare full-parser event counts to the independent structural probe.
> 8. If `demoparser2` throws or produces suspiciously empty data, return a typed parser-compatibility error; do not silently create a 0-0 match.
> 9. Do not infer authoritative team from kill relationships; read team state from parser/entity data.
> 10. Add golden normalized JSON for this fixture but do not commit the `.dem`.
>
> Acceptance for this private fixture:
> - map = `de_dust2`
> - patch_version = `14189`
> - build_num = `10924`
> - verified playback tick rate = `64.0`
> - structural probe sees 18 `round_freeze_end`
> - structural probe sees 128 `player_death`
> - structural probe sees 444 `player_hurt`
> - structural probe sees 2,894 `weapon_fire`
> - initial userinfo contains 10 human players plus CSTV
>
> Finish by reporting:
> - verified fields
> - parser-specific fields that were unstable
> - exact files changed
> - tests run
> - differences between structural-probe counts and demoparser2 counts
> - assumptions that still require CS2 replay verification
