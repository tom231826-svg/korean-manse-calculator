# Korean Manse Calculator

[![CI](https://github.com/tom231826-svg/korean-manse-calculator/actions/workflows/ci.yml/badge.svg)](https://github.com/tom231826-svg/korean-manse-calculator/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/tom231826-svg/korean-manse-calculator?sort=semver)](https://github.com/tom231826-svg/korean-manse-calculator/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)

Deterministic, calculation-only, reproducible Korean manse / Four Pillars engine for solar birth dates. It returns structured year, month, day, and hour pillars without generating fortune-telling interpretations, counseling copy, compatibility readings, or predictions.

## Why This Exists

LLMs are good at explaining results, but they should not improvise calendar arithmetic. Four Pillars calculation depends on historical Korean legal time, solar-term boundaries, day ganzhi lookup data, and explicit midnight policies. This repository separates that deterministic calculation layer from any interpretation layer so agents and applications can depend on a repeatable engine result.

## What It Does

- Calculates year, month, day, and hour pillars for solar birth dates from 1950 through 2030.
- Uses Korea legal time and historical daylight-saving handling through `Asia/Seoul`.
- Applies a fixed Seoul longitude correction of -32 minutes.
- Preserves the input solar date for the day pillar, including late-night `子` hour cases.
- Ships bundled reference data, validation scripts, smoke tests, and a JSON output schema.

## Quick Start

```bash
python3 scripts/calculate_manse.py --date 1990-01-01 --time 23:30 --format json
python3 scripts/calculate_manse.py --date 1990-01-02 --time 00:30 --format json
python3 scripts/calculate_manse.py --date 1965-07-07 --time 16:00 --format md
```

Validate bundled data:

```bash
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

## Output At A Glance

Example summary:

```text
己巳년 丙子월 丙寅일 己亥시
```

Short JSON shape:

```json
{
  "status": "ok",
  "summary": "己巳년 丙子월 丙寅일 己亥시",
  "pillars": {
    "year": {"ganzhi": "己巳", "ko": "기사"},
    "month": {"ganzhi": "丙子", "ko": "병자"},
    "day": {"ganzhi": "丙寅", "ko": "병인"},
    "hour": {"ganzhi": "己亥", "ko": "기해"}
  }
}
```

See [`examples/sample-output.json`](examples/sample-output.json) for a full JSON output example.

## Accuracy & Data Integrity

- Day ganzhi lookup covers 29,585 solar dates from 1950-01-01 through 2030-12-31 with validation mismatch count 0.
- Solar-term references cover 81 years x 24 entries = 1,944 entries.
- Runtime solar-term cache also validates to 1,944 entries.
- CI runs compile checks, bundled cache validation, and smoke tests on every push and pull request.
- LLM calculation is forbidden by policy; callers should use the engine output as the source of truth.

For details, see [`docs/accuracy.md`](docs/accuracy.md).

## Limitations

- Lunar calendar and leap-month conversion are not supported in v0.7.
- Overseas births and user-provided birthplace correction are not supported.
- Apparent solar time, true solar time, and equation-of-time correction are not applied.
- The project is an early public release and currently focuses on a source-run CLI rather than package distribution.

## Data Sources

The bundled cache is enough for normal calculation over 1950-2030. KASI / data.go.kr keys are only needed if you want to regenerate references from upstream APIs.

No API keys are included in this repository. Create a local `.env` file from `.env.example` if needed, but never commit real keys:

```bash
cp .env.example .env
```

Regenerate from bundled references:

```bash
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references
```

Regenerate from KASI + Skyfield:

```bash
KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
```

More source notes are in [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Roadmap

The current priority is #2: add JSON schema validation to CI and expand regression cases near solar-term and corrected-time boundaries.

Other planned work:

- #1: add Python package and CLI distribution workflow.
- #3: add lunar calendar and leap-month conversion support.

## Contributing

Contributions should keep calculation deterministic and interpretation-free. Please run validation before opening a pull request:

```bash
python3 -m json.tool examples/sample-output.json >/dev/null
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CHANGELOG.md`](CHANGELOG.md), and [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

MIT. See [LICENSE](LICENSE).
