#!/usr/bin/env python3
"""
Korean Manse Calculator 만세력 v0.7 24절기/일진 캐시 생성 스크립트.

핵심 정책:
- 24절기 runtime cache는 data/solar_terms_cache.json에 저장한다.
- KASI 특일정보 API(get24DivisionsInfo)는 실제 확인 기준 2000~2027 구간을 직접 소스로 사용한다.
- 1950~1999, 2028~2030은 skyfield + NASA/JPL DE421 보완 계산을 사용한다.
- skyfield 계산 시 반드시 ecliptic_latlon('date')를 사용한다. J2000 기본값은 평균분점 기준이라 큰 오차가 난다.
- 번들된 references/jeolgi/{YYYY}.json이 있으면 --from-bundled-references로 즉시 data cache를 재생성할 수 있다.

사용 예:
  # 번들 reference에서 data/solar_terms_cache.json 재생성
  python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references

  # KASI + skyfield로 재현 생성. skyfield/de421 필요.
  KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_manse import (  # type: ignore
    KST_FIXED,
    canonical_solar_term_name,
    day_ganzhi_by_formula,
    fetch_solar_terms_year,
    load_json_file,
    load_reference_jeolgi_year,
    normalize_solar_term_label_by_longitude,
    package_root,
    save_json_file,
)

TERM_ORDER_BY_YEAR = [
    (285, "소한", "小寒", (1, 6)), (300, "대한", "大寒", (1, 20)),
    (315, "입춘", "立春", (2, 4)), (330, "우수", "雨水", (2, 19)),
    (345, "경칩", "驚蟄", (3, 6)), (0, "춘분", "春分", (3, 21)),
    (15, "청명", "淸明", (4, 5)), (30, "곡우", "穀雨", (4, 20)),
    (45, "입하", "立夏", (5, 6)), (60, "소만", "小滿", (5, 21)),
    (75, "망종", "芒種", (6, 6)), (90, "하지", "夏至", (6, 21)),
    (105, "소서", "小暑", (7, 7)), (120, "대서", "大暑", (7, 23)),
    (135, "입추", "立秋", (8, 8)), (150, "처서", "處暑", (8, 23)),
    (165, "백로", "白露", (9, 8)), (180, "추분", "秋分", (9, 23)),
    (195, "한로", "寒露", (10, 8)), (210, "상강", "霜降", (10, 23)),
    (225, "입동", "立冬", (11, 7)), (240, "소설", "小雪", (11, 22)),
    (255, "대설", "大雪", (12, 7)), (270, "동지", "冬至", (12, 22)),
]
HANJA_BY_NAME = {name: hanja for _, name, hanja, _ in TERM_ORDER_BY_YEAR}
EXPECTED_LONGITUDE_BY_NAME = {name: lon for lon, name, _, _ in TERM_ORDER_BY_YEAR}

# KASI/distbe 원본 정정 이력. v0.7 데이터 재현 시 동일 적용.
MANUAL_REPLACEMENTS: Dict[tuple[int, str], Dict[str, Any]] = {
    (2011, "대한"): {
        "name": "대한", "hanja": "大寒", "date": "2011-01-20", "kst": "2011-01-20 19:18",
        "sunLongitude": 300, "source": "skyfield_de421", "correction_note": "KASI 원본 1일 typo 의심 → skyfield 교체",
    },
    (2011, "입동"): {
        "name": "입동", "hanja": "立冬", "date": "2011-11-08", "kst": "2011-11-08 03:34",
        "sunLongitude": 225, "source": "skyfield_de421", "correction_note": "KASI vs skyfield 6시간 차이 → skyfield 교체",
    },
}
REVIEW_NOTES: Dict[tuple[int, str], str] = {
    (2015, "하지"): "KASI vs skyfield 차이 20분; KASI 채택",
}


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _engine_term_from_kst_text(name: str, hanja: str, kst_text: str, lon: int, source: str, **extra: Any) -> Dict[str, Any]:
    dt = datetime.strptime(kst_text, "%Y-%m-%d %H:%M").replace(tzinfo=KST_FIXED)
    out = {
        "name": name,
        "hanja": hanja,
        "dateKind": "03",
        "locdate": dt.strftime("%Y%m%d"),
        "date": dt.strftime("%Y-%m-%d"),
        "kst": dt.strftime("%H%M"),
        "time": dt.strftime("%H:%M"),
        "sunLongitude": lon,
        "datetime_kst": dt.isoformat(),
        "source": source,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return normalize_solar_term_label_by_longitude(out)


def reference_year_to_engine(year: int) -> List[Dict[str, Any]]:
    terms = load_reference_jeolgi_year(year)
    if not terms:
        raise RuntimeError(f"references/jeolgi/{year}.json을 찾지 못했습니다.")
    return normalize_and_validate_year(year, terms, allow_repair=True)


def _to_dt(term: Dict[str, Any]) -> datetime:
    return datetime.fromisoformat(term["datetime_kst"])


def normalize_and_validate_year(year: int, terms: List[Dict[str, Any]], allow_repair: bool = True) -> List[Dict[str, Any]]:
    # 1) 황경 fallback으로 라벨 정규화.
    fixed = [normalize_solar_term_label_by_longitude(t) for t in terms]

    # 2) 2007 대서/대설 같은 라벨 오류는 위 fallback으로 처리된다.
    # 3) 2011 대한/입동은 KASI 원본 의심 건이므로 수동 교체.
    by_name: Dict[str, Dict[str, Any]] = {canonical_solar_term_name(t): t for t in fixed}
    for (yy, name), replacement in MANUAL_REPLACEMENTS.items():
        if yy == year:
            by_name[name] = _engine_term_from_kst_text(
                replacement["name"], replacement["hanja"], replacement["kst"], int(replacement["sunLongitude"]),
                replacement["source"], correction_note=replacement.get("correction_note")
            )

    # 4) 2015 하지 review note는 KASI 유지, 검토 표시만 추가.
    for (yy, name), note in REVIEW_NOTES.items():
        if yy == year and name in by_name:
            by_name[name]["review_note"] = note

    # 5) 2000 v1.0 reference에서 우수 누락/입춘 날짜 오염을 방어적으로 보정.
    #    실제 v0.7 reference에는 이미 교정되어 있어 보통 실행되지 않는다.
    if allow_repair and year == 2000 and "우수" not in by_name:
        suspect = by_name.get("입춘")
        if suspect and str(suspect.get("locdate", "")).startswith("20000219"):
            by_name["우수"] = dict(suspect)
            by_name["우수"].update({"name": "우수", "hanja": "雨水", "sunLongitude": 330, "fixed_note": "입춘으로 잘못 들어온 2000-02-19 항목을 우수로 정정"})
            by_name["입춘"] = _engine_term_from_kst_text(
                "입춘", "立春", "2000-02-04 21:40", 315, "skyfield_de421",
                correction_note="2000 입춘/우수 누락 방어 보정"
            )

    # 6) 필수 24개 점검.
    missing = [name for _, name, _, _ in TERM_ORDER_BY_YEAR if name not in by_name]
    if missing:
        raise RuntimeError(f"{year}년 절기 누락: {missing}")
    result = []
    for lon, name, hanja, _ in TERM_ORDER_BY_YEAR:
        t = dict(by_name[name])
        t["name"] = name
        t["hanja"] = t.get("hanja") or hanja
        t["sunLongitude"] = int(t.get("sunLongitude", lon))
        if int(t["sunLongitude"]) % 360 != lon:
            raise RuntimeError(f"{year} {name}: sunLongitude {t['sunLongitude']} != {lon}")
        result.append(t)
    result.sort(key=_to_dt)
    return result


def fetch_kasi_year_corrected(year: int, service_key: str) -> List[Dict[str, Any]]:
    terms = fetch_solar_terms_year(year, service_key)
    if not terms:
        raise RuntimeError(f"{year}년 KASI 응답이 비어 있습니다.")
    return normalize_and_validate_year(year, terms, allow_repair=True)


def _angle_diff(lon: float, target: float) -> float:
    return (lon - target + 180.0) % 360.0 - 180.0


def skyfield_year(year: int, data_dir: Optional[Path] = None, ephemeris: str = "de421.bsp") -> List[Dict[str, Any]]:
    """Compute 24 solar terms with skyfield + DE421.

    Implementation note: apparent().ecliptic_latlon('date') is required. Do not use the
    default J2000 ecliptic frame for 절기 시각; it causes large errors.
    """
    try:
        from skyfield.api import Loader  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("skyfield가 설치되어 있지 않습니다. pip install skyfield 후 다시 실행하세요.") from exc

    load = Loader(str(data_dir or (package_root() / "data" / "skyfield")))
    eph = load(ephemeris)
    ts = load.timescale()
    earth = eph["earth"]
    sun = eph["sun"]

    def lon_at(dt_utc: datetime) -> float:
        t = ts.utc(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute, dt_utc.second)
        astrometric = earth.at(t).observe(sun).apparent()
        lat, lon, distance = astrometric.ecliptic_latlon("date")  # IMPORTANT: date, not J2000
        return lon.degrees % 360.0

    def find_cross(target: int, guess_kst: datetime) -> datetime:
        lo = (guess_kst - timedelta(days=4)).astimezone(timezone.utc)
        hi = (guess_kst + timedelta(days=4)).astimezone(timezone.utc)
        # Assume Sun longitude is monotonic in this short bracket.
        for _ in range(50):
            mid = lo + (hi - lo) / 2
            if _angle_diff(lon_at(mid), target) < 0:
                lo = mid
            else:
                hi = mid
        return hi.astimezone(KST_FIXED).replace(second=0, microsecond=0)

    out: List[Dict[str, Any]] = []
    for lon, name, hanja, (month, day) in TERM_ORDER_BY_YEAR:
        guess = datetime(year, month, day, 12, 0, tzinfo=KST_FIXED)
        dt = find_cross(lon, guess)
        out.append(_engine_term_from_kst_text(name, hanja, dt.strftime("%Y-%m-%d %H:%M"), lon, "skyfield_de421"))
    return normalize_and_validate_year(year, out, allow_repair=False)


def build_solar_terms(start_year: int, end_year: int, out_path: Path, service_key: Optional[str], from_bundled_references: bool, skyfield_data_dir: Optional[Path]) -> Dict[str, Any]:
    years: Dict[str, List[Dict[str, Any]]] = {}
    for year in range(start_year, end_year + 1):
        print(f"[solar-terms] building {year}...", file=sys.stderr)
        if from_bundled_references:
            terms = reference_year_to_engine(year)
        elif 2000 <= year <= 2027:
            if not service_key:
                raise RuntimeError("2000~2027 KASI 구간 생성에는 KASI_SPCDE_SERVICE_KEY 또는 --api-key가 필요합니다.")
            terms = fetch_kasi_year_corrected(year, service_key)
        else:
            terms = skyfield_year(year, data_dir=skyfield_data_dir)
        years[str(year)] = terms

    meta = {
        "version": "0.7.0",
        "source": "KASI SpcdeInfoService/get24DivisionsInfo for 2000~2027; skyfield_de421 for 1950~1999 and 2028~2030; or bundled references if --from-bundled-references",
        "generated_at": datetime.now(tz=KST_FIXED).isoformat(),
        "coverage": {"start_year": start_year, "end_year": end_year, "years": end_year - start_year + 1, "entries": sum(len(v) for v in years.values())},
        "skyfield_method_note": "skyfield must use ecliptic_latlon('date'), not J2000.",
        "correction_history": [
            "2007-12-07: 대서 라벨 오류를 대설로 정정 by sunLongitude 255°",
            "2019-01-20: 17:60 표기를 18:00으로 정규화",
            "2011-01-21 대한: KASI 1일 typo 의심 → skyfield 2011-01-20 19:18로 교체",
            "2011-11-08 입동: KASI와 skyfield 6시간 차이 → skyfield 2011-11-08 03:34로 교체",
            "2015 하지: KASI와 skyfield 20분 차이, KASI 채택 및 review_note 표기",
            "2000 입춘/우수: v0.7 reference validation 중 발견된 우수 누락/입춘 날짜 오염 방어 보정",
        ],
        "validation": "reference generation methodology: KASI ground truth 615개와 cross-validation 99.5% (612개) 1분 이내 일치.",
    }
    obj = {"meta": meta, "years": years}
    save_json_file(out_path, obj)
    return obj


def build_day_ganzhi_formula_cache(start_year: int, end_year: int, out_path: Path) -> Dict[str, Any]:
    cache: Dict[str, Any] = load_json_file(out_path, {})
    for d in daterange(date(start_year, 1, 1), date(end_year, 12, 31)):
        gz, info = day_ganzhi_by_formula(d)
        cache[d.isoformat()] = {
            "day_ganzhi": gz.han,
            "ko": gz.ko,
            "source": "formula_fallback_generated_cache",
            "julian_day_number": info["julian_day_number"],
            "formula": info["formula"],
        }
    save_json_file(out_path, cache)
    return cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Korean Manse Calculator 만세력 v0.7 24절기 캐시 생성")
    parser.add_argument("--start-year", type=int, default=1950)
    parser.add_argument("--end-year", type=int, default=2030)
    parser.add_argument("--out-dir", default=str(package_root() / "data"))
    parser.add_argument("--api-key", default=None, help="특일정보 API ServiceKey. 없으면 KASI_SPCDE_SERVICE_KEY 또는 KASI_SERVICE_KEY 사용")
    parser.add_argument("--from-bundled-references", action="store_true", help="references/jeolgi/{YYYY}.json에서 data cache를 생성")
    parser.add_argument("--skyfield-data-dir", default=None, help="skyfield Loader data dir. DE421 ephemeris 저장 위치")
    parser.add_argument("--include-day-ganzhi-formula", action="store_true", help="JDN 공식 기반 일진 cache도 생성")
    args = parser.parse_args()

    if args.start_year > args.end_year:
        raise SystemExit("start-year는 end-year보다 작거나 같아야 합니다.")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    service_key = args.api_key or os.getenv("KASI_SPCDE_SERVICE_KEY") or os.getenv("KASI_SERVICE_KEY")
    skyfield_dir = Path(args.skyfield_data_dir).resolve() if args.skyfield_data_dir else None

    obj = build_solar_terms(
        args.start_year,
        args.end_year,
        out_dir / "solar_terms_cache.json",
        service_key,
        from_bundled_references=args.from_bundled_references,
        skyfield_data_dir=skyfield_dir,
    )
    print(f"wrote {out_dir / 'solar_terms_cache.json'} ({obj['meta']['coverage']['entries']} entries)", file=sys.stderr)

    if args.include_day_ganzhi_formula:
        build_day_ganzhi_formula_cache(args.start_year, args.end_year, out_dir / "day_ganzhi_cache.json")
        print(f"wrote {out_dir / 'day_ganzhi_cache.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
