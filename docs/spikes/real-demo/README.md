# Real-demo spike

This folder holds research and validation notes from parsing a **private**
competitive CS2 demo. The `.dem` itself is not in git.

## Fixture identity

- Filename: `9208210907649202700_0.dem`
- SHA-256: `d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec`
- Golden redacted summary: `fixtures/real-demo/expected/9208210907649202700_0.redacted-summary.json`

## Cross-check sources

1. Independent `structural_probe` (no demoparser2 dependency)
2. Host-installed `demoparser2` via `DemoParser.parse_event`

Verified event counts for this fixture:

| Event | Count |
| --- | ---: |
| `player_death` | 128 |
| `player_hurt` | 444 |
| `weapon_fire` | 2894 |

## Local regression

```powershell
$env:CS2_COACH_REAL_DEMO = "C:\path\to\9208210907649202700_0.dem"
python -m pytest services\analyzer\tests\test_structural_probe_real_demo.py -q
```
