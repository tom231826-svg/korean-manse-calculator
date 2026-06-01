#!/usr/bin/env python3
"""
Korean Manse Calculator v0.8.0

국내/서울 기준 생년월일로 사주 만세력의 연주/월주/일주/시주를 산출한다.
- v0.8.0은 양력 입력과 오프라인 cache 기반 음력/윤달 입력을 지원한다.
- 출생지는 사용자에게 받지 않고 서울을 기본값으로 둔다.
- 대한민국 법정시/서머타임을 fixed KST(+09:00)로 정규화한 뒤 서울 기준 경도 보정 -32분을 적용한다.
- 진태양시/시태양시(균시차) 보정은 지원하지 않는다.
- 절기는 KASI 특일정보 API dateKind=03의 kst 시각 또는 사전 생성 캐시를 사용한다.
- 음력 입력은 먼저 양력으로 변환한 뒤 기존 양력 기반 계산 흐름을 그대로 사용한다.
- 일주는 보정시각으로 날짜를 바꾸지 않고 계산 기준 양력 날짜의 일진을 그대로 사용한다.
  KASI 음양력 API lunIljin 또는 양력 날짜 캐시를 우선 사용하고, 없으면 JDN 공식 fallback을 사용한다.

CLI examples:
  python3 scripts/calculate_manse.py --date 2001-11-19 --time 14:30 --gender male
  python3 scripts/calculate_manse.py --date 1988-07-01 --time 00:30 --gender female
  python3 scripts/calculate_manse.py --calendar lunar --date 2001-08-14 --lunar-leap false --time 12:00
  KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" KASI_LRSR_SERVICE_KEY="<your-data-go-kr-service-key>" python3 scripts/calculate_manse.py --date 2001-11-19 --time 14:30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

PROFILE_NAME = "seoul_corrected_manse_v0.8"
PROFILE_VERSION = "0.8.0"
KASI_BASE = "http://apis.data.go.kr/B090041/openapi/service"
KST_FIXED = timezone(timedelta(hours=9), name="KST")

DEFAULT_BIRTHPLACE = {
    "name": "서울특별시",
    "latitude": 37.5665,
    "longitude": 126.9780,
    "standard_meridian": 135.0,
}
# 서울 경도 126.978E와 한국 표준자오선 135E의 차이: 약 -32.088분.
# v0.8.0 정책상 분 단위 정밀도에 맞춰 -32분을 고정 적용한다.
SEOUL_LONGITUDE_CORRECTION_MINUTES = -32

STEMS_HAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
STEMS_KO = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"]
BRANCHES_HAN = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
BRANCHES_KO = ["자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해"]

STEM_KO_TO_HAN = dict(zip(STEMS_KO, STEMS_HAN))
BRANCH_KO_TO_HAN = dict(zip(BRANCHES_KO, BRANCHES_HAN))
STEM_HAN_TO_KO = dict(zip(STEMS_HAN, STEMS_KO))
BRANCH_HAN_TO_KO = dict(zip(BRANCHES_HAN, BRANCHES_KO))

# 월주 경계에 직접 쓰는 12절기. 중기(우수, 춘분 등)는 월주 경계에는 쓰지 않는다.
MONTH_BOUNDARY_TERM_TO_BRANCH = {
    "입춘": "寅",
    "경칩": "卯",
    "청명": "辰",
    "입하": "巳",
    "망종": "午",
    "소서": "未",
    "입추": "申",
    "백로": "酉",
    "한로": "戌",
    "입동": "亥",
    "대설": "子",
    "소한": "丑",
}

# 24절기 태양황경 대응표. 데이터 라벨과 sunLongitude가 충돌하면 v0.8 정책상 sunLongitude를 우선 신뢰한다.
SOLAR_TERM_BY_LONGITUDE = {
    0: "춘분", 15: "청명", 30: "곡우", 45: "입하", 60: "소만", 75: "망종",
    90: "하지", 105: "소서", 120: "대서", 135: "입추", 150: "처서", 165: "백로",
    180: "추분", 195: "한로", 210: "상강", 225: "입동", 240: "소설", 255: "대설",
    270: "동지", 285: "소한", 300: "대한", 315: "입춘", 330: "우수", 345: "경칩",
}
SOLAR_TERM_LONGITUDE_BY_NAME = {v: k for k, v in SOLAR_TERM_BY_LONGITUDE.items()}

MONTH_BRANCH_TO_OFFSET_FROM_IN = {
    "寅": 0,
    "卯": 1,
    "辰": 2,
    "巳": 3,
    "午": 4,
    "未": 5,
    "申": 6,
    "酉": 7,
    "戌": 8,
    "亥": 9,
    "子": 10,
    "丑": 11,
}
# 연간별 寅월 시작 천간: 甲/己=丙, 乙/庚=戊, 丙/辛=庚, 丁/壬=壬, 戊/癸=甲
MONTH_START_STEM_FOR_YEAR_STEM_INDEX = {
    0: 2,  # 甲 -> 丙寅
    5: 2,  # 己 -> 丙寅
    1: 4,  # 乙 -> 戊寅
    6: 4,  # 庚 -> 戊寅
    2: 6,  # 丙 -> 庚寅
    7: 6,  # 辛 -> 庚寅
    3: 8,  # 丁 -> 壬寅
    8: 8,  # 壬 -> 壬寅
    4: 0,  # 戊 -> 甲寅
    9: 0,  # 癸 -> 甲寅
}
# 일간별 子시 시작 천간: 甲/己=甲, 乙/庚=丙, 丙/辛=戊, 丁/壬=庚, 戊/癸=壬
HOUR_START_STEM_FOR_DAY_STEM_INDEX = {
    0: 0,
    5: 0,
    1: 2,
    6: 2,
    2: 4,
    7: 4,
    3: 6,
    8: 6,
    4: 8,
    9: 8,
}


class ManseError(Exception):
    pass


class MissingSolarTermsError(ManseError):
    pass


def warning_obj(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def normalize_warnings(warnings: List[Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for w in warnings:
        if isinstance(w, dict) and "code" in w and "message" in w:
            out.append({"code": str(w["code"]), "message": str(w["message"])})
        elif isinstance(w, str):
            code = "notice"
            if "서머타임" in w:
                code = "summer_time_period"
            elif "출생시간 미상" in w:
                code = "hour_unknown"
            elif "입춘" in w:
                code = "near_ipchun_boundary"
            elif "절입" in w or "절기" in w:
                code = "near_jeolgi_boundary"
            elif "시간 전환" in w or "표준시" in w:
                code = "standard_time_change_period"
            out.append({"code": code, "message": w})
        else:
            out.append({"code": "notice", "message": str(w)})
    # De-duplicate while preserving order.
    seen = set()
    deduped: List[Dict[str, str]] = []
    for item in out:
        key = (item["code"], item["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


@dataclass
class GanZhi:
    stem: str
    branch: str

    @property
    def han(self) -> str:
        return f"{self.stem}{self.branch}"

    @property
    def ko(self) -> str:
        return f"{STEM_HAN_TO_KO.get(self.stem, self.stem)}{BRANCH_HAN_TO_KO.get(self.branch, self.branch)}"

    @property
    def stem_index(self) -> int:
        return STEMS_HAN.index(self.stem)

    @property
    def branch_index(self) -> int:
        return BRANCHES_HAN.index(self.branch)


@dataclass(frozen=True)
class LunarInputDate:
    year: int
    month: int
    day: int

    def isoformat(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_path(name: str) -> Path:
    return package_root() / "data" / name


def parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ManseError("date는 YYYY-MM-DD 형식이어야 합니다.") from exc


def parse_lunar_date(s: str) -> LunarInputDate:
    parts = s.split("-")
    if len(parts) != 3:
        raise ManseError("음력 date는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        y, m, d = (int(part) for part in parts)
    except ValueError as exc:
        raise ManseError("음력 date는 YYYY-MM-DD 형식이어야 합니다.") from exc
    if y < 1 or not (1 <= m <= 12) or not (1 <= d <= 30):
        raise ManseError("음력 date의 월/일 범위가 올바르지 않습니다.")
    return LunarInputDate(y, m, d)


def parse_time_or_unknown(s: Optional[str]) -> Optional[time]:
    if not s or s.lower() in {"unknown", "none", "null", "미상", "모름", "시간모름"}:
        return None
    try:
        return datetime.strptime(s, "%H:%M").time()
    except ValueError as exc:
        raise ManseError("time은 HH:mm 형식이어야 합니다. 시간 미상은 unknown을 사용하세요.") from exc


def normalize_lunar_leap_arg(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    raw = "auto" if value is None else str(value).strip().lower()
    aliases = {
        "auto": "auto",
        "unknown": "auto",
        "true": "true",
        "1": "true",
        "yes": "true",
        "y": "true",
        "leap": "true",
        "윤": "true",
        "윤달": "true",
        "false": "false",
        "0": "false",
        "no": "false",
        "n": "false",
        "regular": "false",
        "평": "false",
        "평달": "false",
    }
    if raw not in aliases:
        raise ManseError("lunar_leap은 auto, true, false 중 하나여야 합니다.")
    return aliases[raw]


def lunar_cache_key(lunar_date: LunarInputDate, leap: bool) -> str:
    return f"{lunar_date.isoformat()}:{'leap' if leap else 'regular'}"


def _lunar_entry_solar_date(entry: Any) -> Optional[str]:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        raw = entry.get("solar_date") or entry.get("solarDate") or entry.get("date")
        return str(raw) if raw else None
    return None


def load_lunar_conversion_year(cache_dir: Path, lunar_year: int) -> Optional[Dict[str, Any]]:
    path = cache_dir / "lunar_to_solar_by_year" / f"{lunar_year}.json"
    if not path.exists():
        return None
    obj = load_json_file(path, {})
    if isinstance(obj, dict) and "entries" not in obj:
        obj = {"meta": {}, "entries": obj}
    if not isinstance(obj, dict):
        return {"meta": {}, "entries": {}}
    obj.setdefault("meta", {})
    obj.setdefault("entries", {})
    return obj


def resolve_lunar_to_solar(lunar_date: LunarInputDate, lunar_leap: Any, cache_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Resolve a Korean lunar date to a solar date from the bundled offline cache.

    Returns (conversion, error). The error object is already shaped for JSON output.
    """
    leap_mode = normalize_lunar_leap_arg(lunar_leap)
    if not (1 <= lunar_date.month <= 12 and 1 <= lunar_date.day <= 30):
        return None, {
            "status": "invalid_lunar_date",
            "reason": "invalid_lunar_date",
            "message": f"음력 날짜 범위가 올바르지 않습니다: {lunar_date.isoformat()}",
            "user_action_hint": "check_lunar_month_day",
        }

    cache_obj = load_lunar_conversion_year(cache_dir, lunar_date.year)
    if cache_obj is None:
        return None, {
            "status": "lunar_conversion_missing",
            "reason": "lunar_conversion_missing",
            "message": f"{lunar_date.year}년 음력→양력 변환 cache가 없습니다.",
            "user_action_hint": "run_build_kasi_cache_include_lunar_conversion",
        }
    entries = cache_obj.get("entries") or {}
    if not isinstance(entries, dict):
        entries = {}

    candidates: List[Tuple[bool, Any]] = []
    if leap_mode in {"auto", "false"}:
        regular = entries.get(lunar_cache_key(lunar_date, False))
        if regular is not None:
            candidates.append((False, regular))
    if leap_mode in {"auto", "true"}:
        leap = entries.get(lunar_cache_key(lunar_date, True))
        if leap is not None:
            candidates.append((True, leap))

    if leap_mode == "auto" and len(candidates) > 1:
        return None, {
            "status": "ambiguous_lunar_date",
            "reason": "ambiguous_lunar_date",
            "message": f"{lunar_date.isoformat()} 음력 날짜는 평달/윤달 후보가 모두 있습니다. --lunar-leap true 또는 false를 지정하세요.",
            "user_action_hint": "set_lunar_leap_true_or_false",
        }
    if not candidates:
        return None, {
            "status": "invalid_lunar_date",
            "reason": "invalid_lunar_date",
            "message": f"음력 {lunar_date.isoformat()} ({'윤달' if leap_mode == 'true' else '평달' if leap_mode == 'false' else 'auto'})을 변환 cache에서 찾지 못했습니다.",
            "user_action_hint": "check_lunar_date_and_leap_month",
        }

    selected_leap, selected_entry = candidates[0]
    solar_raw = _lunar_entry_solar_date(selected_entry)
    if not solar_raw:
        return None, {
            "status": "lunar_conversion_missing",
            "reason": "lunar_conversion_missing",
            "message": f"음력 {lunar_date.isoformat()} cache entry에 solar_date가 없습니다.",
            "user_action_hint": "regenerate_lunar_conversion_cache",
        }
    try:
        solar_date = parse_date(solar_raw)
    except ManseError:
        return None, {
            "status": "lunar_conversion_missing",
            "reason": "lunar_conversion_missing",
            "message": f"음력 {lunar_date.isoformat()} cache entry의 solar_date 형식이 올바르지 않습니다.",
            "user_action_hint": "regenerate_lunar_conversion_cache",
        }

    conversion = {
        "input_calendar": "lunar",
        "input_lunar_date": lunar_date.isoformat(),
        "input_lunar_leap": selected_leap,
        "requested_lunar_leap": leap_mode,
        "converted_solar_date": solar_date.isoformat(),
        "conversion_source": cache_obj.get("meta", {}).get("source", "offline_lunar_to_solar_cache"),
        "cache_key": lunar_cache_key(lunar_date, selected_leap),
    }
    return conversion, None


def make_error_result(
    status: str,
    reason: str,
    message: str,
    input_data: Dict[str, Any],
    user_action_hint: str,
) -> Dict[str, Any]:
    return {
        "status": status,
        "version": PROFILE_VERSION,
        "profile": {"name": PROFILE_NAME, "version": PROFILE_VERSION},
        "message": message,
        "error": {"reason": reason, "message": message, "user_action_hint": user_action_hint},
        "input": input_data,
    }


def gregorian_jdn(y: int, m: int, d: int) -> int:
    # Gregorian calendar JDN for civil date at noon. Sexagenary day fallback uses (JDN + 49) % 60.
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def ganzhi_from_index(index: int) -> GanZhi:
    i = index % 60
    return GanZhi(STEMS_HAN[i % 10], BRANCHES_HAN[i % 12])


def sexagenary_year_ganzhi(year: int) -> GanZhi:
    # 1984년은 甲子년. 연도 경계는 호출부에서 입춘으로 결정한다.
    return ganzhi_from_index(year - 1984)


def day_ganzhi_by_formula(day: date) -> Tuple[GanZhi, Dict[str, Any]]:
    jdn = gregorian_jdn(day.year, day.month, day.day)
    index = (jdn + 49) % 60
    return ganzhi_from_index(index), {"source": "formula_fallback", "julian_day_number": jdn, "formula": "(JDN + 49) mod 60"}


def parse_ganzhi_text(value: str) -> Optional[GanZhi]:
    if not value:
        return None
    value = str(value).strip()
    if len(value) < 2:
        return None
    a, b = value[0], value[1]
    if a in STEMS_HAN and b in BRANCHES_HAN:
        return GanZhi(a, b)
    if a in STEM_KO_TO_HAN and b in BRANCH_KO_TO_HAN:
        return GanZhi(STEM_KO_TO_HAN[a], BRANCH_KO_TO_HAN[b])
    return None


def request_kasi_json_or_xml(path: str, params: Dict[str, Any], service_key: str, timeout: int = 20) -> Any:
    if not service_key:
        raise ManseError("KASI_SERVICE_KEY가 설정되지 않았습니다.")
    base_url = f"{KASI_BASE}/{path}"
    query_params = {k: str(v) for k, v in params.items() if v is not None}
    query_params.setdefault("_type", "json")
    query = urllib.parse.urlencode(query_params)
    # 공공데이터포털 키는 인코딩된 키/디코딩된 키가 섞여 들어올 수 있다.
    # '%'가 있으면 이미 인코딩된 것으로 보고 그대로 붙인다.
    key_part = service_key if "%" in service_key else urllib.parse.quote(service_key, safe="")
    url = f"{base_url}?ServiceKey={key_part}&{query}"
    req = urllib.request.Request(url, headers={"User-Agent": f"korean-manse-calculator/{PROFILE_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    if not raw:
        raise ManseError("KASI API 응답이 비어 있습니다.")
    if raw.startswith("{") or raw.startswith("["):
        return json.loads(raw)
    return parse_xml_response(raw)


def parse_xml_response(raw: str) -> Dict[str, Any]:
    root = ET.fromstring(raw)
    result: Dict[str, Any] = {"response": {"body": {"items": {"item": []}}}}
    header = root.find("header")
    if header is not None:
        result["response"]["header"] = {child.tag: child.text for child in header}
    items = []
    for item_el in root.findall(".//item"):
        item: Dict[str, Any] = {}
        for child in item_el:
            item[child.tag] = child.text
        items.append(item)
    result["response"]["body"]["items"]["item"] = items
    return result


def extract_items(api_response: Any) -> List[Dict[str, Any]]:
    if isinstance(api_response, list):
        return [x for x in api_response if isinstance(x, dict)]
    if not isinstance(api_response, dict):
        return []
    body = api_response.get("response", {}).get("body", {})
    items_obj = body.get("items", {})
    if items_obj is None or items_obj == "":
        return []
    if isinstance(items_obj, list):
        return [x for x in items_obj if isinstance(x, dict)]
    if isinstance(items_obj, dict):
        item = items_obj.get("item", [])
        if isinstance(item, list):
            return [x for x in item if isinstance(x, dict)]
        if isinstance(item, dict):
            return [item]
    return []



def canonical_solar_term_name(term: Dict[str, Any]) -> str:
    """Return the canonical solar-term name, preferring sunLongitude over label.

    KASI/distbe data has had rare label/time defects. For 24절기, the solar longitude is the
    mathematically identifying value, so v0.8 uses it as the authoritative fallback.
    """
    lon = term.get("sunLongitude", term.get("sun_longitude"))
    if lon is not None and lon != "":
        try:
            key = int(round(float(lon))) % 360
            if key in SOLAR_TERM_BY_LONGITUDE:
                return SOLAR_TERM_BY_LONGITUDE[key]
        except Exception:
            pass
    return str(term.get("name") or term.get("dateName") or "").strip()


def normalize_solar_term_label_by_longitude(term: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(term)
    canonical = canonical_solar_term_name(out)
    original = str(out.get("name") or "").strip()
    if canonical and original and canonical != original:
        out.setdefault("label_correction_note", f"name '{original}' corrected to '{canonical}' by sunLongitude fallback")
        out["original_name"] = original
        out["name"] = canonical
    elif canonical and not original:
        out["name"] = canonical
    return out


def normalize_kst_hhmm(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    s = str(value).strip()
    if ":" in s:
        hh, mm = s.split(":", 1)
        return f"{int(hh):02d}:{int(mm):02d}"
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    digits = digits.zfill(4)[-4:]
    hh, mm = int(digits[:2]), int(digits[2:])
    # KASI 특일정보에서 2019-01-20 대한이 17:60으로 표기된 사례가 있어 18:00으로 정규화한다.
    if mm == 60:
        hh += 1
        mm = 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return f"{hh:02d}:{mm:02d}"


def normalize_solar_term_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # KASI 특일정보 24절기: dateKind='03', dateName, locdate, kst, sunLongitude.
    date_kind = str(item.get("dateKind") or item.get("datekind") or "").strip()
    name = str(item.get("dateName") or item.get("datename") or item.get("name") or "").strip()
    # dateKind가 없더라도 kst/sunLongitude가 있으면 24절기 item으로 간주한다.
    if date_kind and date_kind != "03":
        return None
    if not name:
        return None
    locdate_raw = item.get("locdate") or item.get("locDate") or item.get("date")
    if locdate_raw is None:
        return None
    locdate = str(locdate_raw).strip()
    if len(locdate) != 8 or not locdate.isdigit():
        return None
    kst = normalize_kst_hhmm(item.get("kst"))
    if not kst:
        return None
    y, m, d = int(locdate[:4]), int(locdate[4:6]), int(locdate[6:8])
    dt = datetime(y, m, d, int(kst[:2]), int(kst[3:5]), tzinfo=KST_FIXED)
    sun_long_raw = item.get("sunLongitude") or item.get("sunlongitude")
    try:
        sun_longitude = float(sun_long_raw) if sun_long_raw is not None and sun_long_raw != "" else None
    except Exception:
        sun_longitude = None
    out = {
        "name": name,
        "dateKind": "03",
        "locdate": locdate,
        "kst": kst.replace(":", ""),
        "time": kst,
        "sunLongitude": sun_longitude,
        "datetime_kst": dt.isoformat(),
        "source": item.get("source") or "KASI_SpcdeInfoService_get24DivisionsInfo",
    }
    return normalize_solar_term_label_by_longitude(out)


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def load_solar_terms_cache(cache_path: Path) -> Dict[str, Any]:
    obj = load_json_file(cache_path, {"years": {}})
    if "years" not in obj:
        # 옛 형식: {'2001': [...]}도 허용
        obj = {"years": obj}
    obj.setdefault("years", {})
    return obj



def load_reference_jeolgi_year(year: int) -> Optional[List[Dict[str, Any]]]:
    """Load reference generation-style references/jeolgi/{YYYY}.json and convert to engine format."""
    path = package_root() / "references" / "jeolgi" / f"{year}.json"
    if not path.exists():
        return None
    raw = load_json_file(path, {})
    entries = raw.get("jeolgi", [])
    converted: List[Dict[str, Any]] = []
    for entry in entries:
        kst_text = str(entry.get("kst") or "").strip()
        if not kst_text:
            continue
        try:
            dt = datetime.strptime(kst_text, "%Y-%m-%d %H:%M").replace(tzinfo=KST_FIXED)
        except ValueError:
            continue
        out = {
            "name": entry.get("name"),
            "hanja": entry.get("hanja"),
            "dateKind": "03",
            "locdate": dt.strftime("%Y%m%d"),
            "date": entry.get("date") or dt.strftime("%Y-%m-%d"),
            "kst": dt.strftime("%H%M"),
            "time": dt.strftime("%H:%M"),
            "sunLongitude": entry.get("sun_longitude"),
            "datetime_kst": dt.isoformat(),
            "source": entry.get("source"),
        }
        for key in ("correction_note", "fixed_note", "review_note", "label_correction_note"):
            if key in entry:
                out[key] = entry[key]
        converted.append(normalize_solar_term_label_by_longitude(out))
    converted.sort(key=lambda x: x["datetime_kst"])
    return converted


def fetch_solar_terms_year(year: int, service_key: str) -> List[Dict[str, Any]]:
    terms: List[Dict[str, Any]] = []
    for month in range(1, 13):
        resp = request_kasi_json_or_xml(
            "SpcdeInfoService/get24DivisionsInfo",
            {"solYear": year, "solMonth": f"{month:02d}"},
            service_key,
        )
        for item in extract_items(resp):
            norm = normalize_solar_term_item(item)
            if norm:
                terms.append(norm)
    # 중복 제거
    unique: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for term in terms:
        unique[(term["name"], term["locdate"])] = term
    return sorted(unique.values(), key=lambda x: x["datetime_kst"])


def get_solar_terms_year(year: int, cache: Dict[str, Any], cache_path: Path, service_key: Optional[str]) -> Tuple[List[Dict[str, Any]], str]:
    years = cache.setdefault("years", {})
    if str(year) in years and years[str(year)]:
        return [normalize_solar_term_label_by_longitude(t) for t in years[str(year)]], "cache"
    ref_terms = load_reference_jeolgi_year(year)
    if ref_terms:
        years[str(year)] = ref_terms
        return ref_terms, "references/jeolgi"
    if not service_key:
        raise MissingSolarTermsError(
            f"{year}년 24절기 캐시가 없습니다. references/jeolgi/{year}.json 또는 KASI_SPCDE_SERVICE_KEY/KASI_SERVICE_KEY가 필요합니다."
        )
    terms = fetch_solar_terms_year(year, service_key)
    if len(terms) < 20:
        raise ManseError(f"{year}년 24절기 데이터가 부족합니다. 수집 건수: {len(terms)}")
    terms = [normalize_solar_term_label_by_longitude(t) for t in terms]
    years[str(year)] = terms
    cache.setdefault("meta", {})["updated_at"] = datetime.now(tz=KST_FIXED).isoformat()
    save_json_file(cache_path, cache)
    return terms, "api"


def term_dt(term: Dict[str, Any]) -> datetime:
    return datetime.fromisoformat(term["datetime_kst"])


def find_term(terms: Iterable[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for term in terms:
        if canonical_solar_term_name(term) == name:
            return normalize_solar_term_label_by_longitude(term)
    return None


def normalize_legal_time_to_fixed_kst(input_date: date, input_time: time) -> Dict[str, Any]:
    naive = datetime.combine(input_date, input_time)
    warnings: List[str] = []
    if ZoneInfo is None:
        # 매우 드문 fallback. 1987/1988 DST는 이 fallback에서 보정하지 못한다.
        aware = naive.replace(tzinfo=KST_FIXED)
        return {
            "legal_local_time": aware.isoformat(),
            "basis_time_kst": aware.isoformat(),
            "basis_date": aware.date().isoformat(),
            "offset_minutes_at_birth": 540,
            "basis_adjustment_minutes": 0,
            "dst_applied": False,
            "timezone_source": "fixed_KST_fallback",
            "warnings": ["Python zoneinfo를 사용할 수 없어 대한민국 과거 시간대/서머타임 보정을 적용하지 못했습니다."],
        }
    seoul = ZoneInfo("Asia/Seoul")
    legal = naive.replace(tzinfo=seoul)
    fixed = legal.astimezone(KST_FIXED)
    offset = legal.utcoffset() or timedelta(hours=9)
    dst = legal.dst() or timedelta(0)
    adjustment_minutes = int((fixed.replace(tzinfo=None) - naive).total_seconds() // 60)
    # 전환일 근처에서는 zoneinfo의 fold/nonexistent 처리 한계가 있으므로 경고를 남긴다.
    fold0 = naive.replace(tzinfo=seoul, fold=0)
    fold1 = naive.replace(tzinfo=seoul, fold=1)
    if fold0.utcoffset() != fold1.utcoffset():
        warnings.append("대한민국 시간 전환 구간과 겹칠 수 있어, 입력 시각이 모호하거나 존재하지 않는 시각일 수 있습니다.")
    return {
        "legal_local_time": legal.isoformat(),
        "basis_time_kst": fixed.isoformat(),
        "basis_date": fixed.date().isoformat(),
        "offset_minutes_at_birth": int(offset.total_seconds() // 60),
        "basis_adjustment_minutes": adjustment_minutes,
        "dst_applied": bool(dst.total_seconds()),
        "timezone_source": "zoneinfo:Asia/Seoul -> fixed KST(+09:00)",
        "warnings": warnings,
    }




def apply_default_seoul_longitude_correction(time_norm: Dict[str, Any]) -> Dict[str, Any]:
    """Apply fixed Seoul longitude/local-mean-time correction after legal-time/DST normalization.

    Input birth time is treated as official Korean clock time at birth. First zoneinfo converts
    legal time to fixed KST(+09:00), handling historical Korean DST and UTC+08:30 periods.
    Then v0.8.0 applies Seoul's fixed longitude correction of -32 minutes.
    This is not apparent/true solar time; equation of time is intentionally not applied.
    """
    base_iso = time_norm.get("basis_time_kst")
    if not base_iso:
        return time_norm
    standard_dt = datetime.fromisoformat(base_iso)
    corrected_dt = standard_dt + timedelta(minutes=SEOUL_LONGITUDE_CORRECTION_MINUTES)
    out = dict(time_norm)
    out["standard_time_kst_before_longitude_correction"] = standard_dt.isoformat()
    out["basis_time_kst"] = corrected_dt.isoformat()
    out["calculation_time"] = corrected_dt.isoformat()
    out["basis_date"] = corrected_dt.date().isoformat()
    out["longitude_correction"] = {
        "applied": True,
        "type": "default_seoul_longitude_local_mean_time",
        "birthplace_default": DEFAULT_BIRTHPLACE,
        "minutes": SEOUL_LONGITUDE_CORRECTION_MINUTES,
        "exact_minutes_from_longitude": round((DEFAULT_BIRTHPLACE["longitude"] - DEFAULT_BIRTHPLACE["standard_meridian"]) * 4, 3),
        "apparent_or_true_solar_time": False,
        "equation_of_time_applied": False,
        "note": "출생지는 입력받지 않고 서울 기준 -32분 경도 보정을 고정 적용합니다.",
    }
    prev = out.get("basis_adjustment_minutes")
    out["total_adjustment_minutes"] = (prev if isinstance(prev, int) else 0) + SEOUL_LONGITUDE_CORRECTION_MINUTES
    return out


def _parse_day_cache_value(val: Any, key: str) -> Optional[Tuple[GanZhi, Dict[str, Any]]]:
    if isinstance(val, str):
        gz = parse_ganzhi_text(val)
        if gz:
            return gz, {"source": "day_ganzhi_cache", "cache_key": key}
    elif isinstance(val, dict):
        raw = val.get("day_ganzhi") or val.get("lunIljin") or val.get("ganzhi") or val.get("han")
        gz = parse_ganzhi_text(str(raw)) if raw else None
        if gz:
            info = {"source": val.get("source", "day_ganzhi_cache"), "cache_key": key}
            if "solJd" in val:
                info["solJd"] = val["solJd"]
            return gz, info
    return None

def get_day_ganzhi_from_cache(day: date, cache_path: Path) -> Optional[Tuple[GanZhi, Dict[str, Any]]]:
    key = day.isoformat()
    # Fast path: v0.8.0 stores imported ilju data by year to avoid loading a multi-MB JSON on every call.
    year_path = cache_path.parent / "day_ganzhi_by_year" / f"{day.year}.json"
    if year_path.exists():
        year_cache = load_json_file(year_path, {})
        if isinstance(year_cache, dict) and key in year_cache:
            parsed = _parse_day_cache_value(year_cache[key], key)
            if parsed:
                return parsed
    # Backward-compatible monolithic cache.
    cache = load_json_file(cache_path, {})
    if isinstance(cache, dict) and key in cache:
        return _parse_day_cache_value(cache[key], key)
    return None


def fetch_day_ganzhi_from_kasi(day: date, service_key: str) -> Tuple[Optional[GanZhi], Dict[str, Any]]:
    resp = request_kasi_json_or_xml(
        "LrsrCldInfoService/getLunCalInfo",
        {"solYear": day.year, "solMonth": f"{day.month:02d}", "solDay": f"{day.day:02d}"},
        service_key,
    )
    items = extract_items(resp)
    if not items:
        return None, {"source": "KASI_LrsrCldInfoService_getLunCalInfo", "error": "empty_items"}
    item = items[0]
    raw = item.get("lunIljin") or item.get("luniljin")
    gz = parse_ganzhi_text(str(raw)) if raw else None
    info = {
        "source": "KASI_LrsrCldInfoService_getLunCalInfo",
        "raw_lunIljin": raw,
        "solJd": item.get("solJd") or item.get("soljd"),
        "lunar": {
            "lunYear": item.get("lunYear") or item.get("lunyear"),
            "lunMonth": item.get("lunMonth") or item.get("lunmonth"),
            "lunDay": item.get("lunDay") or item.get("lunday"),
            "lunLeapmonth": item.get("lunLeapmonth") or item.get("lunleapmonth"),
        },
    }
    return gz, info


def get_day_ganzhi(day: date, service_key: Optional[str], cache_path: Path) -> Tuple[GanZhi, Dict[str, Any]]:
    cached = get_day_ganzhi_from_cache(day, cache_path)
    if cached:
        return cached
    if service_key:
        try:
            gz, info = fetch_day_ganzhi_from_kasi(day, service_key)
            if gz:
                return gz, info
        except Exception as exc:
            # API 실패 시 fallback. 결과 로그에 남긴다.
            fallback_gz, fallback_info = day_ganzhi_by_formula(day)
            fallback_info["api_error"] = str(exc)
            return fallback_gz, fallback_info
    return day_ganzhi_by_formula(day)


def determine_year_pillar(calc_date: date, calc_dt: Optional[datetime], terms_for_year: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], GanZhi, List[str]]:
    warnings: List[str] = []
    ipchun = find_term(terms_for_year, "입춘")
    if not ipchun:
        raise ManseError(f"{calc_date.year}년 입춘 데이터를 찾을 수 없습니다.")
    ipchun_dt = term_dt(ipchun)
    ambiguous = False
    possible: List[str] = []
    if calc_dt is not None:
        year_basis = calc_date.year if calc_dt >= ipchun_dt else calc_date.year - 1
        after = calc_dt >= ipchun_dt
    else:
        if calc_date < ipchun_dt.date():
            year_basis = calc_date.year - 1
            after = False
        elif calc_date > ipchun_dt.date():
            year_basis = calc_date.year
            after = True
        else:
            ambiguous = True
            warnings.append("출생시간 미상이고 입춘 당일이므로 연주가 절입시각 전후에 따라 달라질 수 있습니다.")
            prev_gz = sexagenary_year_ganzhi(calc_date.year - 1)
            curr_gz = sexagenary_year_ganzhi(calc_date.year)
            possible = [prev_gz.han, curr_gz.han]
            # 기본 표시는 정오 기준으로 한다. 확정값으로 쓰지 말 것.
            noon = datetime.combine(calc_date, time(12, 0), tzinfo=KST_FIXED)
            year_basis = calc_date.year if noon >= ipchun_dt else calc_date.year - 1
            after = noon >= ipchun_dt
    gz = sexagenary_year_ganzhi(year_basis)
    detail = {
        "ganzhi": gz.han,
        "ko": gz.ko,
        "stem": gz.stem,
        "branch": gz.branch,
        "basis": "ipchun_exact_kst",
        "year_basis": year_basis,
        "ipchun": ipchun,
        "birth_after_ipchun": after,
        "ambiguous": ambiguous,
    }
    if possible:
        detail["possible"] = possible
    return detail, gz, warnings


def determine_month_pillar(
    calc_date: date,
    calc_dt: Optional[datetime],
    all_terms: List[Dict[str, Any]],
    year_gz: GanZhi,
) -> Tuple[Dict[str, Any], GanZhi, List[str]]:
    warnings: List[str] = []
    boundaries = []
    for term in all_terms:
        canonical_name = canonical_solar_term_name(term)
        branch = MONTH_BOUNDARY_TERM_TO_BRANCH.get(canonical_name)
        if branch:
            boundaries.append({**normalize_solar_term_label_by_longitude(term), "month_branch": branch, "canonical_name": canonical_name})
    boundaries.sort(key=lambda x: x["datetime_kst"])
    if not boundaries:
        raise ManseError("월주 계산용 절기 경계 데이터가 없습니다.")

    ambiguous = False
    target_dt: datetime
    if calc_dt is not None:
        target_dt = calc_dt
    else:
        # 시간 미상은 정오 기준으로 대표 계산하되, 절기 당일이면 경고한다.
        target_dt = datetime.combine(calc_date, time(12, 0), tzinfo=KST_FIXED)
        for b in boundaries:
            if calc_date == term_dt(b).date():
                ambiguous = True
                warnings.append(f"출생시간 미상이고 {b['name']} 절입일이므로 월주가 절입시각 전후에 따라 달라질 수 있습니다.")
                break

    previous = None
    next_b = None
    for b in boundaries:
        if term_dt(b) <= target_dt:
            previous = b
        elif term_dt(b) > target_dt and next_b is None:
            next_b = b
            break
    if previous is None:
        # Supported reference range starts at 1950. For the first days of 1950 before 소한,
        # the actual previous boundary is 1949 대설. Branch-wise this is still 子월.
        previous = {
            "name": "대설",
            "month_branch": "子",
            "canonical_name": "대설",
            "datetime_kst": None,
            "source": "synthetic_previous_boundary_for_range_start",
            "note": "이전년도 대설 데이터가 범위 밖이라 子월 경계로 합성 처리했습니다.",
        }
        warnings.append("이전년도 대설 데이터가 지원 범위 밖이라 子월 경계로 합성 처리했습니다.")
    if next_b is None:
        # 통상 연말 대설 이후에는 다음 해 소한이 필요하다.
        future = [b for b in boundaries if term_dt(b) > target_dt]
        next_b = future[0] if future else None

    branch = previous["month_branch"]
    year_stem_idx = year_gz.stem_index
    start_stem_idx = MONTH_START_STEM_FOR_YEAR_STEM_INDEX[year_stem_idx]
    month_offset = MONTH_BRANCH_TO_OFFSET_FROM_IN[branch]
    stem = STEMS_HAN[(start_stem_idx + month_offset) % 10]
    gz = GanZhi(stem, branch)
    detail = {
        "ganzhi": gz.han,
        "ko": gz.ko,
        "stem": gz.stem,
        "branch": gz.branch,
        "basis": "solar_term_exact_kst",
        "month_boundary_term": previous,
        "next_boundary_term": next_b,
        "year_stem_used": year_gz.stem,
        "ambiguous": ambiguous,
    }
    return detail, gz, warnings


def hour_branch_index_from_time(t: time) -> int:
    # 자시: 23:00~00:59. 이후 2시간 단위.
    h = t.hour
    if h == 23 or h == 0:
        return 0  # 子
    return ((h + 1) // 2) % 12


def determine_hour_pillar(calc_dt: Optional[datetime], day_gz: GanZhi) -> Optional[Dict[str, Any]]:
    if calc_dt is None:
        return None
    t = calc_dt.timetz().replace(tzinfo=None)
    b_idx = hour_branch_index_from_time(t)
    start_stem_idx = HOUR_START_STEM_FOR_DAY_STEM_INDEX[day_gz.stem_index]
    stem = STEMS_HAN[(start_stem_idx + b_idx) % 10]
    branch = BRANCHES_HAN[b_idx]
    gz = GanZhi(stem, branch)
    return {
        "ganzhi": gz.han,
        "ko": gz.ko,
        "stem": gz.stem,
        "branch": gz.branch,
        "basis": "fixed_kst_after_dst_and_default_seoul_longitude_correction",
        "hour_branch_policy": "23:00-00:59=子 after time correction; day stem uses input solar date; zi-hour never shifts day pillar",
        "calculation_time": calc_dt.isoformat(),
    }


def collect_terms_for_context(calc_year: int, cache: Dict[str, Any], cache_path: Path, service_key: Optional[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sources: Dict[str, str] = {}
    all_terms: List[Dict[str, Any]] = []
    # Current year is mandatory. Previous/next year is useful near Jan/Dec boundaries, but a provisional cache may not contain it.
    for y in [calc_year - 1, calc_year, calc_year + 1]:
        try:
            terms, src = get_solar_terms_year(y, cache, cache_path, service_key)
            sources[str(y)] = src
            all_terms.extend(terms)
        except MissingSolarTermsError:
            sources[str(y)] = "missing_cache_optional" if y != calc_year else "missing_cache_required"
            if y == calc_year:
                raise
    all_terms.sort(key=lambda x: x["datetime_kst"])
    return all_terms, sources


def calculate_manse(
    birth_date: Any,
    birth_time: Optional[time],
    gender: Optional[str] = None,
    calendar: str = "solar",
    lunar_leap: Any = "auto",
    spcde_service_key: Optional[str] = None,
    lrsr_service_key: Optional[str] = None,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    cache_dir = cache_dir or package_root() / "data"
    calendar = str(calendar or "solar").strip().lower()
    input_date = birth_date
    input_data: Dict[str, Any] = {
        "calendar": calendar,
        "date": input_date.isoformat(),
        "time": birth_time.strftime("%H:%M") if birth_time else "unknown",
        "gender": gender or "unknown",
    }
    if calendar == "lunar":
        input_data["lunar_leap"] = normalize_lunar_leap_arg(lunar_leap)
    if calendar not in {"solar", "lunar"}:
        return make_error_result(
            "unsupported_calendar",
            "unsupported_calendar",
            f"지원하지 않는 calendar 값입니다: {calendar}. solar 또는 lunar를 사용하세요.",
            input_data,
            "use_calendar_solar_or_lunar",
        )

    lunar_conversion: Optional[Dict[str, Any]] = None
    if calendar == "lunar":
        if not isinstance(input_date, LunarInputDate):
            input_date = parse_lunar_date(input_date.isoformat() if hasattr(input_date, "isoformat") else str(input_date))
        lunar_conversion, lunar_error = resolve_lunar_to_solar(input_date, lunar_leap, cache_dir)
        if lunar_error:
            return make_error_result(
                lunar_error["status"],
                lunar_error["reason"],
                lunar_error["message"],
                input_data,
                lunar_error["user_action_hint"],
            )
        assert lunar_conversion is not None
        birth_date = parse_date(lunar_conversion["converted_solar_date"])
        input_data["lunar_leap"] = bool(lunar_conversion["input_lunar_leap"])
    elif not isinstance(birth_date, date):
        birth_date = parse_date(birth_date.isoformat() if hasattr(birth_date, "isoformat") else str(birth_date))

    if birth_date.year < 1950 or birth_date.year > 2030:
        return make_error_result(
            "error",
            "year_out_of_range",
            f"Year {birth_date.year} out of supported range 1950-2030",
            input_data,
            "out_of_range_no_action",
        )

    solar_terms_cache_path = cache_dir / "solar_terms_cache.json"
    day_cache_path = cache_dir / "day_ganzhi_cache.json"
    cache = load_solar_terms_cache(solar_terms_cache_path)

    warnings: List[str] = []
    if birth_time is not None:
        norm = normalize_legal_time_to_fixed_kst(birth_date, birth_time)
        norm = apply_default_seoul_longitude_correction(norm)
        warnings.extend(norm.get("warnings", []))
        calc_dt = datetime.fromisoformat(norm["basis_time_kst"])
        calc_date = calc_dt.date()
    else:
        norm = {
            "legal_local_time": f"{birth_date.isoformat()}Tunknown",
            "basis_time_kst": None,
            "calculation_time": None,
            "basis_date": birth_date.isoformat(),
            "offset_minutes_at_birth": None,
            "basis_adjustment_minutes": None,
            "total_adjustment_minutes": None,
            "dst_applied": None,
            "timezone_source": "date_only_no_time_normalization",
            "longitude_correction": {"applied": False, "reason": "출생시간 미상으로 -32분 시간 보정을 적용하지 않았습니다."},
            "warnings": ["출생시간 미상으로 시주는 산출하지 않습니다."],
        }
        warnings.extend(norm["warnings"])
        calc_dt = None
        calc_date = birth_date

    # 절기 데이터는 계산 기준일의 연도를 중심으로 전/후년도까지 필요하다.
    all_terms, term_sources = collect_terms_for_context(calc_date.year, cache, solar_terms_cache_path, spcde_service_key)
    terms_for_calc_year = [t for t in all_terms if str(t.get("locdate", ""))[:4] == str(calc_date.year)]

    year_detail, year_gz, year_warnings = determine_year_pillar(calc_date, calc_dt, terms_for_calc_year)
    warnings.extend(year_warnings)
    month_detail, month_gz, month_warnings = determine_month_pillar(calc_date, calc_dt, all_terms, year_gz)
    warnings.extend(month_warnings)

    day_gz, day_info = get_day_ganzhi(birth_date, lrsr_service_key, day_cache_path)
    day_info = dict(day_info)
    day_info["policy"] = "input_solar_date_preserved"
    day_info["input_solar_date"] = birth_date.isoformat()
    if lunar_conversion:
        day_info["input_lunar_date"] = input_date.isoformat()
        day_info["input_lunar_leap"] = lunar_conversion["input_lunar_leap"]
        day_info["lunar_conversion_cache_key"] = lunar_conversion["cache_key"]
    day_info["time_corrected_date_not_used_for_day_pillar"] = calc_date.isoformat()
    hour_detail = determine_hour_pillar(calc_dt, day_gz)

    calendar_data: Dict[str, Any] = {
        "input_calendar": calendar,
        "solar_date_for_day_pillar": birth_date.isoformat(),
        "time_corrected_date_for_year_month_and_hour": calc_date.isoformat(),
        "day_pillar_policy": "input_solar_date_preserved_even_if_corrected_time_crosses_midnight",
        "day_ganzhi_source": day_info,
    }
    if lunar_conversion:
        calendar_data.update({
            "input_lunar_date": lunar_conversion["input_lunar_date"],
            "input_lunar_leap": lunar_conversion["input_lunar_leap"],
            "requested_lunar_leap": lunar_conversion["requested_lunar_leap"],
            "converted_solar_date": lunar_conversion["converted_solar_date"],
            "conversion_source": lunar_conversion["conversion_source"],
            "conversion_cache_key": lunar_conversion["cache_key"],
        })
    else:
        calendar_data["input_solar_date"] = input_date.isoformat()

    result_input: Dict[str, Any] = {
        "calendar": calendar,
        "date": input_date.isoformat(),
        "time": birth_time.strftime("%H:%M") if birth_time else "unknown",
        "gender": gender or "unknown",
        "birthplace": {"input_collected": False, "default_used": DEFAULT_BIRTHPLACE},
    }
    if lunar_conversion:
        result_input["lunar_leap"] = bool(lunar_conversion["input_lunar_leap"])

    result: Dict[str, Any] = {
        "status": "ok",
        "version": PROFILE_VERSION,
        "profile": {
            "name": PROFILE_NAME,
            "version": PROFILE_VERSION,
            "purpose": "manse_calculation_only_for_saju_agent",
        },
        "input": result_input,
        "policies": {
            "country_scope": "KR_only",
            "timezone": "Asia/Seoul legal time normalized to fixed KST(+09:00)",
            "birthplace_input": False,
            "default_birthplace": DEFAULT_BIRTHPLACE,
            "longitude_correction": "fixed Seoul correction -32 minutes",
            "apparent_solar_time": False,
            "true_solar_time": False,
            "overseas_birth": False,
            "lunar_calendar": "supported_by_offline_lunar_to_solar_cache_v0.8",
            "dst": "auto_by_zoneinfo_Asia/Seoul before Seoul longitude correction",
            "year_boundary": "ipchun_exact_kst",
            "month_boundary": "12_solar_term_boundaries_exact_kst",
            "day_pillar_policy": "input_solar_date_preserved; corrected time never changes day pillar date; reference cases-compatible midnight boundary verified",
            "day_boundary": "input_solar_date_preserved / reference cases midnight boundary",
            "zi_hour": "23:00-00:59",
            "llm_calculation": "forbidden; use engine result only",
        },
        "normalized_time": norm,
        "calendar_data": calendar_data,
        "solar_terms": {
            "sources_by_year": term_sources,
            "year_boundary_ipchun": year_detail.get("ipchun"),
            "month_boundary": month_detail.get("month_boundary_term"),
            "next_month_boundary": month_detail.get("next_boundary_term"),
        },
        "pillars": {
            "year": {k: v for k, v in year_detail.items() if k not in {"ipchun"}},
            "month": {k: v for k, v in month_detail.items() if k not in {"month_boundary_term", "next_boundary_term"}},
            "day": {
                "ganzhi": day_gz.han,
                "ko": day_gz.ko,
                "stem": day_gz.stem,
                "branch": day_gz.branch,
                "basis": "input_solar_date_preserved; KASI/cache preferred; not shifted by zi-hour or longitude correction",
            },
            "hour": hour_detail,
        },
        "warnings": normalize_warnings(warnings),
    }
    result["summary"] = make_summary(result)
    return result


def make_summary(result: Dict[str, Any]) -> str:
    if result.get("status") != "ok":
        return result.get("message", "계산 불가")
    p = result["pillars"]
    if p.get("hour"):
        return f"{p['year']['ganzhi']}년 {p['month']['ganzhi']}월 {p['day']['ganzhi']}일 {p['hour']['ganzhi']}시"
    return f"{p['year']['ganzhi']}년 {p['month']['ganzhi']}월 {p['day']['ganzhi']}일 시주 미상"


def make_markdown(result: Dict[str, Any]) -> str:
    if result.get("status") != "ok":
        return result.get("message", "계산 불가")
    p = result["pillars"]
    nt = result["normalized_time"]
    lines = []
    lines.append(f"계산 결과: **{result['summary']}**")
    lines.append("")
    lines.append("| 기둥 | 결과 | 기준 |")
    lines.append("|---|---:|---|")
    lines.append(f"| 년주 | {p['year']['ganzhi']} ({p['year']['ko']}) | 입춘 절입시각 기준 |")
    lines.append(f"| 월주 | {p['month']['ganzhi']} ({p['month']['ko']}) | 24절기 절입시각 기준 |")
    lines.append(f"| 일주 | {p['day']['ganzhi']} ({p['day']['ko']}) | 양력 날짜 기준 |")
    if p.get("hour"):
        lines.append(f"| 시주 | {p['hour']['ganzhi']} ({p['hour']['ko']}) | 보정 후 한국표준시 기준 |")
    else:
        lines.append("| 시주 | 미상 | 출생시간 미상 |")
    lines.append("")
    lines.append("계산 기준: 국내 출생, 서울 기본값 기준. 대한민국 법정시/서머타임 보정 후 서울 경도 보정 -32분을 적용했습니다. 진태양시/시태양시(균시차)는 적용하지 않았습니다.")
    if nt.get("standard_time_kst_before_longitude_correction"):
        lines.append(f"한국 표준시 환산 시각: `{nt['standard_time_kst_before_longitude_correction']}`")
    if nt.get("basis_time_kst"):
        lines.append(f"최종 계산 기준 시각: `{nt['basis_time_kst']}`")
    if nt.get("basis_adjustment_minutes") not in (None, 0):
        lines.append(f"대한민국 시간대/서머타임 보정: {nt['basis_adjustment_minutes']}분")
    if nt.get("longitude_correction", {}).get("applied"):
        lines.append(f"서울 경도 보정: {nt['longitude_correction']['minutes']}분")
    if result.get("warnings"):
        lines.append("")
        lines.append("주의:")
        for w in result["warnings"]:
            if isinstance(w, dict):
                lines.append(f"- [{w.get('code', 'notice')}] {w.get('message', '')}")
            else:
                lines.append(f"- {w}")
    return "\n".join(lines)


def resolve_api_keys(args: argparse.Namespace) -> Tuple[Optional[str], Optional[str]]:
    """Return (spcde_key, lrsr_key).

    KASI_SERVICE_KEY is a backward-compatible/common fallback.
    Prefer the explicit env vars when 특일정보 and 음양력정보 have different data.go.kr ServiceKeys.
    """
    common = args.api_key or os.getenv("KASI_SERVICE_KEY")
    spcde = args.spcde_api_key or os.getenv("KASI_SPCDE_SERVICE_KEY") or common
    lrsr = args.lrsr_api_key or os.getenv("KASI_LRSR_SERVICE_KEY") or common
    return spcde, lrsr


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="사주/Four Pillars 에이전트용 만세력 계산 스킬 v0.8.0")
    parser.add_argument("--date", required=True, help="생년월일 YYYY-MM-DD. --calendar lunar이면 음력 날짜로 해석")
    parser.add_argument("--time", default="unknown", help="출생시간 HH:mm 또는 unknown")
    parser.add_argument("--gender", default="unknown", choices=["male", "female", "unknown", "남", "여"], help="성별. 4기둥 계산에는 직접 사용하지 않지만 에이전트 전달용으로 보존")
    parser.add_argument("--calendar", default="solar", choices=["solar", "lunar"], help="입력 달력: solar 또는 lunar")
    parser.add_argument("--lunar-leap", default="auto", choices=["auto", "true", "false"], help="--calendar lunar일 때 윤달 여부. auto는 단일 후보만 자동 선택")
    parser.add_argument("--format", default="json", choices=["json", "md"], help="출력 형식")
    parser.add_argument("--cache-dir", default=None, help="캐시 디렉터리. 기본값은 패키지 data/")
    parser.add_argument("--api-key", default=None, help="공통 KASI 서비스키 fallback. 없으면 KASI_SERVICE_KEY 환경변수 사용")
    parser.add_argument("--spcde-api-key", default=None, help="특일정보 API 서비스키. 없으면 KASI_SPCDE_SERVICE_KEY 또는 공통 키 사용")
    parser.add_argument("--lrsr-api-key", default=None, help="음양력정보 API 서비스키. 없으면 KASI_LRSR_SERVICE_KEY 또는 공통 키 사용")
    args = parser.parse_args(argv)

    try:
        bdate = parse_lunar_date(args.date) if args.calendar == "lunar" else parse_date(args.date)
        btime = parse_time_or_unknown(args.time)
        gender = {"남": "male", "여": "female"}.get(args.gender, args.gender)
        spcde_key, lrsr_key = resolve_api_keys(args)
        cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None
        result = calculate_manse(
            bdate,
            btime,
            gender=gender,
            calendar=args.calendar,
            lunar_leap=args.lunar_leap,
            spcde_service_key=spcde_key,
            lrsr_service_key=lrsr_key,
            cache_dir=cache_dir,
        )
        if args.format == "md":
            print(make_markdown(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False))
        return 0 if result.get("status") == "ok" else 2
    except MissingSolarTermsError as exc:
        error = {
            "status": "missing_solar_terms_cache",
            "version": PROFILE_VERSION,
            "profile": {"name": PROFILE_NAME, "version": PROFILE_VERSION},
            "message": str(exc),
            "next_action": "KASI_SPCDE_SERVICE_KEY 또는 KASI_SERVICE_KEY를 설정하거나 references/jeolgi/{YYYY}.json을 확인하거나 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 을 실행하세요.",
        }
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stdout)
        return 3
    except Exception as exc:
        error = {"status": "error", "version": PROFILE_VERSION, "profile": {"name": PROFILE_NAME, "version": PROFILE_VERSION}, "message": str(exc)}
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
