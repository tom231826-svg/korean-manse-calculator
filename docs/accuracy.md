# Accuracy and Data Integrity

Korean Manse Calculator is a calculation-only engine. It is designed to make the calendar calculation layer reproducible so downstream agents or applications do not ask an LLM to infer pillars directly.

## Validation Coverage

The bundled v0.8 data covers solar dates from 1950-01-01 through 2030-12-31.

Current validation expectations:

| Dataset | Coverage | Expected total | Validation expectation |
|---|---:|---:|---|
| Day ganzhi lookup | 1950-2030 | 29,585 dates | missing 0, mismatch 0 |
| Solar-term references | 1950-2030 | 1,944 entries | 81 years x 24 entries |
| Runtime solar-term cache | 1950-2030 | 1,944 entries | 81 years x 24 entries |
| Lunar-to-solar conversion cache | solar 1950-2030 | 29,585 dates | every solar date reverse-indexed once |

Run:

```bash
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

## Source Strategy

- 2000-2027 solar-term references can be regenerated from KASI / data.go.kr `SpcdeInfoService/get24DivisionsInfo`.
- 1950-1999 and 2028-2030 references use Skyfield with NASA JPL DE421 ephemeris methodology.
- Day ganzhi data is generated and cross-checked as a lookup table for deterministic runtime use.
- Lunar input is resolved through an offline lunar-to-solar reverse index before any pillar calculation runs.
- The preferred lunar conversion regeneration source is KASI / data.go.kr `LrsrCldInfoService/getLunCalInfo`.
- The bundled v0.8 lunar conversion cache was generated from KASI / data.go.kr `LrsrCldInfoService/getLunCalInfo`.
- Downloaded ephemeris files and API keys are not committed.

See [`../DATA_SOURCES.md`](../DATA_SOURCES.md) for source notes and regeneration commands.

## Known Corrections

The reference data includes documented corrections for source-label or source-time inconsistencies:

- 2007-12-07: KASI/distbe label corrected from `대서` to `대설` using `sunLongitude=255`.
- 2019-01-20: abnormal KASI time `17:60` normalized to `18:00`.
- 2011-01-21 대한: suspected one-day typo replaced with Skyfield result `2011-01-20 19:18`.
- 2011-11-08 입동: KASI/Skyfield six-hour disagreement replaced with Skyfield result `2011-11-08 03:34`.
- 2015 하지: KASI retained despite a 20-minute Skyfield disagreement, with review note.
- 2000 입춘/우수: missing/corrupted reference entries repaired using solar-longitude fallback.

## Calculation Policy

- LLM calculation is forbidden. Callers should use `scripts/calculate_manse.py` output as the source of truth.
- LLM lunar conversion is forbidden. Lunar dates must be converted by the cache or rejected with a structured error.
- The engine preserves the input solar date for the day pillar even if corrected time crosses midnight.
- For lunar input, the converted solar date becomes the preserved day-pillar date.
- Late-night `子` hour never shifts the day pillar to the next day.
- v0.8 uses a fixed Seoul longitude correction of -32 minutes and does not apply apparent solar time, true solar time, or equation-of-time correction.
