# Korean Manse Calculator

[![CI](https://github.com/tom231826-svg/korean-manse-calculator/actions/workflows/ci.yml/badge.svg)](https://github.com/tom231826-svg/korean-manse-calculator/actions/workflows/ci.yml)

Deterministic Korean manse / Four Pillars calculation engine for solar birth dates.

This project provides a calculation-only layer for agents and applications that need reproducible year, month, day, and hour pillars. It does not generate fortune-telling interpretations, counseling copy, compatibility readings, or predictions.

## Features

- Solar-date only calculation for 1950-2030
- Year, month, day, and hour pillar output as JSON or Markdown
- Korea legal time and historical daylight-saving handling via `Asia/Seoul`
- Fixed Seoul longitude correction of -32 minutes
- 1950-2030 solar-term references: 81 years, 1,944 entries
- 1950-2030 day ganzhi lookup: 29,585 days
- KASI-backed reference workflow for 2000-2027
- Skyfield / NASA JPL DE421 fallback methodology for 1950-1999 and 2028-2030
- Validation scripts, smoke tests, and a JSON output schema

## Limitations

- Lunar calendar and leap-month conversion are not supported in v0.7.
- Overseas births and user-provided birthplace correction are not supported.
- Apparent solar time, true solar time, and equation-of-time correction are not applied.
- The day pillar intentionally follows the input solar date, including late-night `子` hour cases.

## Quick Start

```bash
python3 scripts/calculate_manse.py --date 1990-01-01 --time 23:30 --format json
python3 scripts/calculate_manse.py --date 1990-01-02 --time 00:30 --format json
python3 scripts/calculate_manse.py --date 1965-07-07 --time 16:00 --format md
```

Example summary:

```text
己巳년 丙子월 丙寅일 己亥시
```

See [`examples/sample-output.json`](examples/sample-output.json) for a full JSON output example.

Validate bundled data:

```bash
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

Expected validation totals:

- Day ganzhi: 29,585 days, mismatch count 0
- Solar-term references: 81 years x 24 entries = 1,944 entries
- Runtime solar-term cache: 81 years x 24 entries = 1,944 entries

## API Keys

No API keys are included in this repository.

The bundled cache is enough for normal calculation over 1950-2030. KASI / data.go.kr keys are only needed if you want to regenerate references from upstream APIs.

Create a local `.env` file from `.env.example` if needed, but never commit real keys:

```bash
cp .env.example .env
```

Example regeneration command:

```bash
KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
```

## Cache Regeneration

Regenerate from bundled references:

```bash
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references
```

Regenerate from KASI + Skyfield:

```bash
KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
```

When using Skyfield, `ecliptic_latlon('date')` is required. The default J2000 frame can produce materially wrong solar-term transition times.

## Repository Layout

| Path | Purpose |
|---|---|
| `scripts/calculate_manse.py` | Deterministic calculation engine |
| `scripts/build_kasi_cache.py` | Cache/reference builder |
| `scripts/validate_caches.py` | Data integrity validation |
| `data/solar_terms_cache.json` | Runtime 24 solar-term cache |
| `data/day_ganzhi_by_year/{YYYY}.json` | Runtime day ganzhi lookup |
| `references/jeolgi/{YYYY}.json` | Solar-term reference files |
| `references/ilju/{YYYY}.json` | Day ganzhi reference files |
| `schemas/manse-output.schema.json` | Output JSON schema |
| `examples/sample-output.json` | Example JSON output |
| `tests/smoke_test.sh` | Smoke test suite |

## License

MIT. See [LICENSE](LICENSE).
