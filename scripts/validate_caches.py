#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_manse import day_ganzhi_by_formula, load_reference_jeolgi_year, package_root, canonical_solar_term_name  # type: ignore

EXPECTED = {
    '춘분':0,'청명':15,'곡우':30,'입하':45,'소만':60,'망종':75,'하지':90,'소서':105,
    '대서':120,'입추':135,'처서':150,'백로':165,'추분':180,'한로':195,'상강':210,
    '입동':225,'소설':240,'대설':255,'동지':270,'소한':285,'대한':300,'입춘':315,'우수':330,'경칩':345,
}
ALLOWED_SOURCES = {'kasi', 'skyfield_de421', 'KASI_SpcdeInfoService_get24DivisionsInfo', 'cache', None}


def load(path: Path):
    return json.load(open(path, encoding='utf-8'))


def daterange(a: date, b: date):
    cur = a
    while cur <= b:
        yield cur
        cur += timedelta(days=1)


def validate_day(data_dir: Path, start: int, end: int) -> Dict[str, Any]:
    missing=[]; mismatch=[]; total=0
    ydir=data_dir/'day_ganzhi_by_year'
    year_cache={}
    for y in range(start,end+1):
        f=ydir/f'{y}.json'
        year_cache[y]=load(f) if f.exists() else None
    for day in daterange(date(start,1,1), date(end,12,31)):
        total += 1
        key=day.isoformat()
        obj=year_cache.get(day.year)
        if obj is None:
            missing.append(key); continue
        val=obj.get(key)
        if not val:
            missing.append(key); continue
        raw=(val.get('day_ganzhi') or val.get('han') or val.get('ganzhi')) if isinstance(val,dict) else val
        gz,_=day_ganzhi_by_formula(day)
        if raw != gz.han:
            mismatch.append((key, raw, gz.han))
    return {'total_expected':total,'missing_count':len(missing),'missing':missing[:20],'mismatch_count':len(mismatch),'mismatch':mismatch[:20]}


def _validate_term_list(year: int, terms: List[Dict[str, Any]], label: str) -> List[str]:
    problems=[]
    if len(terms) != 24:
        problems.append(f'{label} {year}: expected 24 terms, got {len(terms)}')
    names=[]
    for t in terms:
        name=canonical_solar_term_name(t)
        names.append(name)
        lon=t.get('sunLongitude', t.get('sun_longitude'))
        if name not in EXPECTED:
            problems.append(f'{label} {year}: unknown term name {name}')
            continue
        if lon is None:
            problems.append(f'{label} {year}: {name} sun longitude is null')
        elif int(round(float(lon))) % 360 != EXPECTED[name]:
            problems.append(f'{label} {year}: {name} longitude {lon} expected {EXPECTED[name]}')
        src=t.get('source')
        if src not in ALLOWED_SOURCES:
            problems.append(f'{label} {year}: {name} invalid source {src}')
        dt_raw=t.get('datetime_kst') or t.get('kst')
        if not dt_raw:
            problems.append(f'{label} {year}: {name} missing datetime/kst')
    if len(set(names)) != len(names):
        problems.append(f'{label} {year}: duplicate term names {sorted([n for n in set(names) if names.count(n)>1])}')
    missing=sorted(set(EXPECTED)-set(names), key=lambda x: EXPECTED[x])
    if missing:
        problems.append(f'{label} {year}: missing {missing}')
    return problems


def validate_references(root: Path, start: int, end: int) -> Dict[str, Any]:
    problems=[]; present=0
    for y in range(start,end+1):
        p=root/'references'/'jeolgi'/f'{y}.json'
        if not p.exists():
            problems.append(f'references {y}: missing file')
            continue
        present += 1
        d=load(p)
        if d.get('year') != y:
            problems.append(f'references {y}: year field mismatch {d.get("year")}')
        converted=load_reference_jeolgi_year(y) or []
        problems.extend(_validate_term_list(y, converted, 'references/jeolgi'))
    return {'years_present':present,'problem_count':len(problems),'problems':problems[:120]}


def validate_solar_cache(data_dir: Path, start: int, end: int) -> Dict[str, Any]:
    p=data_dir/'solar_terms_cache.json'
    if not p.exists():
        return {'years_present':0,'problem_count':1,'problems':['data/solar_terms_cache.json missing']}
    obj=load(p)
    years=obj.get('years', obj)
    problems=[]; present=0
    for y in range(start,end+1):
        arr=years.get(str(y))
        if not arr:
            problems.append(f'data cache {y}: missing year')
            continue
        present += 1
        problems.extend(_validate_term_list(y, arr, 'data/solar_terms_cache'))
    entries=sum(len(years.get(str(y),[])) for y in range(start,end+1))
    if entries != (end-start+1)*24:
        problems.append(f'data cache: expected {(end-start+1)*24} entries, got {entries}')
    return {'years_present':present,'entry_count':entries,'problem_count':len(problems),'problems':problems[:120]}


def _lunar_entry_solar_date(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get('solar_date') or entry.get('solarDate') or '')
    return ''


def _parse_lunar_key_date(value: str):
    parts=value.split('-')
    if len(parts) != 3:
        raise ValueError('invalid lunar date')
    y,m,d=(int(part) for part in parts)
    if y < 1 or not (1 <= m <= 12) or not (1 <= d <= 30):
        raise ValueError('invalid lunar date range')
    return y,m,d


def validate_lunar_conversion(data_dir: Path, start: int, end: int) -> Dict[str, Any]:
    root=data_dir/'lunar_to_solar_by_year'
    if not root.exists():
        return {'years_present':0,'entry_count':0,'problem_count':1,'problems':['data/lunar_to_solar_by_year missing']}
    problems=[]; years_present=0; entries=0; seen_solar={}
    for path in sorted(root.glob('*.json')):
        if path.name == '_meta.json':
            continue
        try:
            lunar_year=int(path.stem)
        except ValueError:
            problems.append(f'lunar conversion: invalid file name {path.name}')
            continue
        obj=load(path)
        mapping=obj.get('entries', obj) if isinstance(obj,dict) else {}
        if not isinstance(mapping,dict):
            problems.append(f'lunar conversion {path.name}: entries is not object')
            continue
        years_present += 1
        for key, value in mapping.items():
            entries += 1
            if not (isinstance(key,str) and (key.endswith(':regular') or key.endswith(':leap'))):
                problems.append(f'lunar conversion {path.name}: invalid key {key}')
                continue
            lunar_date=key.split(':',1)[0]
            try:
                lunar_y, _lunar_m, _lunar_d=_parse_lunar_key_date(lunar_date)
            except ValueError:
                problems.append(f'lunar conversion {path.name}: invalid lunar date key {key}')
                continue
            if lunar_y != lunar_year:
                problems.append(f'lunar conversion {path.name}: key year mismatch {key}')
            solar_raw=_lunar_entry_solar_date(value)
            try:
                sd=date.fromisoformat(solar_raw)
            except ValueError:
                problems.append(f'lunar conversion {path.name}: invalid solar date for {key}')
                continue
            if start <= sd.year <= end:
                previous=seen_solar.get(sd.isoformat())
                if previous:
                    problems.append(f'lunar conversion: solar date duplicate {sd.isoformat()} in {previous} and {key}')
                else:
                    seen_solar[sd.isoformat()]=key
    expected=[d.isoformat() for d in daterange(date(start,1,1), date(end,12,31))]
    missing=[d for d in expected if d not in seen_solar]
    if missing:
        problems.append(f'lunar conversion: missing solar dates {missing[:10]}')
    if len(seen_solar) != len(expected):
        problems.append(f'lunar conversion: expected {len(expected)} indexed solar dates, got {len(seen_solar)}')
    return {
        'years_present':years_present,
        'entry_count':entries,
        'solar_dates_indexed':len(seen_solar),
        'problem_count':len(problems),
        'problems':problems[:120],
    }


def main():
    p=argparse.ArgumentParser(description='Korean Manse Calculator 만세력 v0.8 캐시 검증')
    p.add_argument('--root-dir', default=str(package_root()))
    p.add_argument('--data-dir', default=None)
    p.add_argument('--start-year', type=int, default=1950)
    p.add_argument('--end-year', type=int, default=2030)
    a=p.parse_args()
    root=Path(a.root_dir).resolve()
    data_dir=Path(a.data_dir).resolve() if a.data_dir else root/'data'
    result={
        'day_ganzhi': validate_day(data_dir,a.start_year,a.end_year),
        'references_jeolgi': validate_references(root,a.start_year,a.end_year),
        'solar_terms_cache': validate_solar_cache(data_dir,a.start_year,a.end_year),
        'lunar_conversion': validate_lunar_conversion(data_dir,a.start_year,a.end_year),
    }
    print(json.dumps(result,ensure_ascii=False,indent=2))
    ok=(result['day_ganzhi']['missing_count']==0 and result['day_ganzhi']['mismatch_count']==0 and
        result['references_jeolgi']['problem_count']==0 and result['solar_terms_cache']['problem_count']==0 and
        result['lunar_conversion']['problem_count']==0)
    return 0 if ok else 1

if __name__=='__main__':
    raise SystemExit(main())
