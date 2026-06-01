# Contributing

Thanks for helping improve Korean Manse Calculator.

## Development Checks

Run these before opening a pull request:

```bash
python3 -S -m py_compile scripts/calculate_manse.py scripts/build_kasi_cache.py scripts/validate_caches.py
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

## Data Changes

When changing reference data, include:

- the source used,
- the exact year/date range,
- validation output,
- any correction notes for KASI/Skyfield disagreement.

Do not commit API keys, downloaded ephemeris files, `.env` files, or local cache directories.
