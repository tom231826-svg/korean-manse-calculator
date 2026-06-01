#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -S -m py_compile scripts/calculate_manse.py scripts/build_kasi_cache.py scripts/validate_caches.py
"$PYTHON_BIN" -S scripts/validate_caches.py --start-year 1950 --end-year 2030 >/tmp/korean_manse_v08_validate.json
"$PYTHON_BIN" - <<'PY'
import json, subprocess, tempfile
import os
from pathlib import Path
root=Path.cwd()
python_bin=os.environ.get('PYTHON_BIN', 'python3')

def run(date, time, calendar='solar', lunar_leap='auto', cache_dir=None):
    cmd=[python_bin,'-S','scripts/calculate_manse.py','--date',date,'--time',time,'--calendar',calendar,'--format','json']
    if calendar == 'lunar':
        cmd.extend(['--lunar-leap', lunar_leap])
    if cache_dir:
        cmd.extend(['--cache-dir', str(cache_dir)])
    cp=subprocess.run(cmd,cwd=root,text=True,capture_output=True,check=False)
    data=json.loads(cp.stdout)
    return cp.returncode, data

# 외부 기준 케이스 검증 A: 보정 후 22:58, 입력일 일진 병인 유지
code,r=run('1990-01-01','23:30')
assert code==0 and r['status']=='ok'
assert r['summary']=='己巳년 丙子월 丙寅일 己亥시'
assert r['calendar_data']['solar_date_for_day_pillar']=='1990-01-01'
assert r['normalized_time']['basis_time_kst']=='1990-01-01T22:58:00+09:00'

# 외부 기준 케이스 검증 B: 보정 후 전날 23:58 子시, 그래도 입력일 정묘 일주 유지
code,r=run('1990-01-02','00:30')
assert code==0 and r['status']=='ok'
assert r['summary']=='己巳년 丙子월 丁卯일 庚子시'
assert r['calendar_data']['solar_date_for_day_pillar']=='1990-01-02'
assert r['calendar_data']['time_corrected_date_for_year_month_and_hour']=='1990-01-01'
assert r['pillars']['hour']['branch']=='子'

# Skyfield 보완 영역
code,r=run('1965-07-07','16:00')
assert code==0 and r['summary']=='乙巳년 壬午월 壬戌일 戊申시'

# 기존 자시 정책 보존: 23시대 子시라도 다음날 일주로 넘기지 않음
code,r=run('2020-12-25','23:40')
assert code==0 and r['summary']=='庚子년 戊子월 壬寅일 庚子시'

# 시간 미상은 00:00으로 가정하지 않음
code,r=run('2015-08-15','unknown')
assert code==0 and r['pillars']['hour'] is None
assert r['normalized_time']['basis_time_kst'] is None
assert any(w['code']=='hour_unknown' for w in r['warnings'])

# 음력 평달 입력: 음력 2001-08-14 -> 양력 2001-09-30
code,r=run('2001-08-14','12:00','lunar','false')
assert code==0 and r['status']=='ok'
assert r['summary']=='辛巳년 丁酉월 丙申일 甲午시'
assert r['input']['lunar_leap'] is False
assert r['calendar_data']['converted_solar_date']=='2001-09-30'
assert r['calendar_data']['solar_date_for_day_pillar']=='2001-09-30'

# auto는 후보가 하나이면 자동 선택
code,r=run('2001-08-14','12:00','lunar','auto')
assert code==0 and r['calendar_data']['requested_lunar_leap']=='auto'
assert r['calendar_data']['input_lunar_leap'] is False

# 윤달/평달 선택: 2020년 음력 4월 1일은 평달과 윤달 후보가 모두 있음
code,r=run('2020-04-01','12:00','lunar','false')
assert code==0 and r['summary']=='庚子년 庚辰월 丙申일 甲午시'
assert r['calendar_data']['converted_solar_date']=='2020-04-23'
assert r['calendar_data']['input_lunar_leap'] is False
code,r=run('2020-04-01','12:00','lunar','true')
assert code==0 and r['summary']=='庚子년 辛巳월 丙寅일 甲午시'
assert r['calendar_data']['converted_solar_date']=='2020-05-23'
assert r['calendar_data']['input_lunar_leap'] is True
code,r=run('2020-04-01','12:00','lunar','auto')
assert code==2 and r['status']=='ambiguous_lunar_date'
assert r['error']['reason']=='ambiguous_lunar_date'

# 불가능한 음력 날짜와 cache 누락
code,r=run('2020-02-30','12:00','lunar','false')
assert code==2 and r['status']=='invalid_lunar_date'
with tempfile.TemporaryDirectory() as tmp:
    missing_dir=Path(tmp)
    code,r=run('2001-08-14','12:00','lunar','false',missing_dir)
    assert code==2 and r['status']=='lunar_conversion_missing'

# 범위 외
code,r=run('2031-01-01','10:00')
assert code==2 and r['status']=='error' and r['error']['reason']=='year_out_of_range'
print('smoke ok')
PY
