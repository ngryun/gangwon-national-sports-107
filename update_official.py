#!/usr/bin/env python3
"""공식 홈페이지(meet.sports.or.kr/national) 자료로 강원 경기일정 HTML의 OFFICIAL 데이터를 갱신합니다.

사용법:  python3 update_official.py [html파일]
- 시·도 토너먼트일정(강원): 강원 경기의 상태·승패·경기장 주소·공식 경기구분
- 종료 경기 상세: 스코어
- 종목별 경기일정: 이후 라운드(진출 시) 공식 일정 검증용
- 시·도 기록경기일정(강원): 기록 종목 일정, 종료 경기는 상세에서 강원 순위·기록
- 메인: 강원 종합순위·메달
"""
import html as H
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://meet.sports.or.kr/national"
KST = timezone(timedelta(hours=9))  # GitHub Actions 서버는 UTC라서 반영 시각을 한국 시간으로 적는다
SIDO = "09"  # 강원
DEFAULT_HTML = Path(__file__).with_name("index.html")


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(0.2)
    return body


def text(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", H.unescape(s)).strip()


def gangwon_records():
    src = get(f"/schedule/scheduleT.do?searchSidoCd={SIDO}&searchGmDt=&searchClassCd=&searchGmConfirmYn=")
    raw = re.search(r'let resultList\s*=\s*"(\[.*?\])";', src, re.S).group(1)
    recs = []
    for body in re.findall(r"\{(.*?)\}", raw):
        d = {}
        for kv in re.split(r", (?=[A-Z_]+=)", body):
            k, _, v = kv.partition("=")
            d[k] = None if v == "null" else v
        recs.append(d)
    return recs


def score(rec):
    """종료 경기 상세에서 '강원 패(3) 전북 승(5)' 형태의 전적을 읽어 (강원점수, 상대점수)를 돌려준다."""
    q = (f"/schedule/scheduleDetailT.do?searchClassCd={rec['CLASS_CD']}"
         f"&searchDetailClassCd={rec['DETAIL_CLASS_CD']}&searchRhCd={rec['RH_CD']}&searchPcntGbn={rec['PCNT_GBN']}")
    try:
        t = text(get(q))
    except Exception:
        return None
    m = re.search(r"전적\s+(.*?)\s+세부전적|전적\s+(.*?)\s+참가선수", t)
    if not m:
        return None
    seg = m.group(1) or m.group(2)
    res = re.findall(r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)\s+([승패무])\(([^)]*)\)", seg)
    if len(res) != 2:
        return None
    me = [x for x in res if x[0] == "강원"]
    op = [x for x in res if x[0] != "강원"] or [res[1]]
    if not me:
        return None
    return [me[0][2], op[0][2]]


TR = re.compile(r"<tr>(.*?)</tr>", re.S)
CODES = re.compile(r"openSide\('([^']+)','([^']+)'")
TDS = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
# '2026/10/17 09:00 ~ 12:00', '2026/10/17 14:00 ~ 10/18 16:00', '2026/10/17 ~ 10/21'(요트처럼 기간만 있는 경우)
WHEN = re.compile(r"\d{4}/(\d\d)/(\d\d)\s*(\d\d:\d\d)?\s*(?:~\s*(?:(\d\d)/(\d\d))?\s*(\d\d:\d\d)?)?")


def when_of(cell):
    """일시 칸을 (날짜, 시작, 끝날짜, 끝시각)으로 나눈다. 끝날짜는 여러 날에 걸친 경기만 있다."""
    m = WHEN.search(cell)
    if not m:
        return None
    mo, dd, t1, mo2, dd2, t2 = m.groups()
    d, d2 = f"{mo}-{dd}", (f"{mo2}-{dd2}" if mo2 else "")
    return d, t1 or "", d2 if d2 != d else "", t2 or ""


def class_schedule(class_cd, wanted):
    """종목별 경기일정에서 강원 출전 세부종목의 라운드별 공식 일정 [날짜, 시작, 종료] 목록."""
    src = get(f"/schedule/scheduleClass.do?searchClassCd={class_cd}")
    out = {}
    for row in TR.findall(src):
        codes = CODES.search(row)
        tds = [text(t) for t in TDS.findall(row)]
        if not codes or len(tds) < 5 or codes.group(1) not in wanted:
            continue
        when = when_of(tds[4])
        if not when:
            continue
        d, s, _, e = when
        slot = [d, s, e]
        lst = out.setdefault(codes.group(1), {}).setdefault(round_key(tds[2]), [])
        if slot not in lst:
            lst.append(slot)
    return out


def round_key(rh_nm):
    b = re.sub(r"[０-９\d\s]", "", rh_nm)
    if b.startswith("준준결승"):
        return "QF"
    if b.startswith("준결승"):
        return "SF"
    if b.startswith("결승"):
        return "F"
    return "PRE"


def record_schedule():
    """시·도 기록경기일정(강원): 종목 제목(h5) 아래 표의 행마다 부별·세부종목·경기구분·상태·일시·경기장."""
    src = get(f"/schedule/scheduleR.do?searchSidoCd={SIDO}&searchGmDt=&searchClassCd=&searchGmConfirmYn=")
    parts = re.split(r'<h5 class="subTit"[^>]*>(.*?)</h5>', src)
    rows = []
    for i in range(1, len(parts), 2):
        sport = text(parts[i])
        for row in TR.findall(parts[i + 1]):
            m = re.search(r"openSide\('([^']+)','([^']+)','([^']+)'", row)
            tds = [text(t) for t in TDS.findall(row)]
            if not m or len(tds) < 6:
                continue
            when = when_of(tds[4])
            if not when:
                continue
            d, s, d2, e = when
            ad = re.search(r"mapSearch\('([^']*)'\)", row)
            rows.append({
                "s": sport, "k": tds[0], "e": tds[1], "r": tds[2], "st": tds[3],
                "d": d, "t1": s, "d2": d2, "t2": e,
                "v": tds[5], "ad": ad.group(1) if ad else "",
                "dc": m.group(1), "rh": m.group(2), "pg": m.group(3),
            })
    return rows


def record_result(row):
    """종료된 기록 경기 상세에서 강원 행만 [순위, 선수·팀명, 기록, 비고, 소속]으로 돌려준다."""
    q = (f"/schedule/scheduleDetailR.do?searchClassCd={row['dc'][:2]}&searchDetailClassCd={row['dc']}"
         f"&searchRhCd={row['rh']}&searchPcntGbn={row['pg']}&searchConfirmYn=Y")
    try:
        src = re.sub(r"<script.*?</script>|<style.*?</style>", "", get(q), flags=re.S)
    except Exception:
        return None
    first = re.search(r"<table.*?</thead>", src, re.S)
    team = bool(first and "참가팀명" in first.group(0))
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", src, re.S):
        c = [text(x) for x in TDS.findall(tr)]
        if len(c) < 5 or c[1] != "강원":
            continue
        if team:
            out.append([c[0], c[2], c[3], c[4], ""])
        elif len(c) >= 7:
            out.append([c[0], c[2], c[5], c[6], c[3]])
    return out


def standing():
    src = get("/main.do")
    out = {}
    m = re.search(r"종합순위 내역.*?</table>", src, re.S)
    if m:
        for tr in re.findall(r"<tr.*?</tr>", m.group(0), re.S):
            cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if len(cells) >= 3 and cells[1] == "강원":
                out["rank"], out["score"] = cells[0], cells[2]
    m = re.search(r"메달집계 내역.*?</table>", src, re.S)
    if m:
        for tr in re.findall(r"<tr.*?</tr>", m.group(0), re.S):
            cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if cells and cells[0] == "강원" and len(cells) >= 5:
                out["medal"] = cells[1:5]
    return out


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HTML
    page = target.read_text(encoding="utf-8")

    recs = gangwon_records()
    print(f"강원 토너먼트 기록 {len(recs)}건")

    slim = []
    for r in recs:
        o = {
            "s": r["CLASS_NM"], "k": r["KIND_NM"], "e": r["DETAIL_CLASS_NM"], "dc": r["DETAIL_CLASS_CD"],
            "rh": r["RH_NM"], "rk": round_key(r["RH_NM"]),
            "d": r["GM_SDT"][5:].replace("/", "-"), "t1": r["GM_STM"] or "", "t2": r["GM_ETM"] or "",
            "v": (r["VENUE_NM"] or "").strip(), "ad": (r["VENUE_JUSO"] or "").strip(),
            "L": r["SIDO_NM_L"] or "", "R": r["SIDO_NM_R"] or "",
            "st": r["GM_CONFIRM_NM"] or "", "w": r["WINNER_GB"] or "",
        }
        if o["st"] == "종료":
            o["sc"] = score(r)
        slim.append(o)
    done = sum(o["st"] == "종료" for o in slim)
    print(f"종료 경기 {done}건 스코어 조회")

    by_class = {}
    for r in recs:
        by_class.setdefault(r["CLASS_CD"], set()).add(r["DETAIL_CLASS_CD"])
    sched = {}
    for cc, wanted in by_class.items():
        try:
            sched.update(class_schedule(cc, wanted))
        except Exception as ex:
            print(f"  종목 {cc} 일정 조회 실패: {ex}")
    print(f"세부종목 일정 {len(sched)}개")

    # 기록 종목: 이미 받아 둔 종료 경기 결과는 다시 받지 않는다
    prev = re.search(r"^const OFFICIAL=(.*);$", page, re.M)
    cached = {}
    if prev:
        for o in json.loads(prev.group(1)).get("rr", []):
            if o.get("st") == "종료" and o.get("res") is not None:
                cached[o["dc"] + "|" + o["rh"]] = o["res"]
    try:
        rr = record_schedule()
    except Exception as ex:
        print(f"기록경기일정 조회 실패: {ex}")
        rr = json.loads(prev.group(1)).get("rr", []) if prev else []
    todo = [o for o in rr if o["st"] == "종료" and (o["dc"] + "|" + o["rh"]) not in cached]
    for o in rr:
        if o["st"] == "종료" and (o["dc"] + "|" + o["rh"]) in cached:
            o["res"] = cached[o["dc"] + "|" + o["rh"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for o, res in zip(todo, pool.map(record_result, todo)):
            o["res"] = res
    print(f"기록 종목 {len(rr)}건 (종료 {sum(o['st'] == '종료' for o in rr)}건, 새로 결과 조회 {len(todo)}건)")

    try:
        gw = standing()
    except Exception as ex:
        print(f"순위·메달 조회 실패: {ex}")
        gw = {}

    data = {"at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "recs": slim, "sched": sched, "rr": rr, "gw": gw}
    line = "const OFFICIAL=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
    if re.search(r"^const OFFICIAL=.*;$", page, re.M):
        page = re.sub(r"^const OFFICIAL=.*;$", lambda _: line, page, count=1, flags=re.M)
    else:
        page = re.sub(r"^(const DATA=.*;)$", lambda m: m.group(1) + "\n" + line, page, count=1, flags=re.M)
    target.write_text(page, encoding="utf-8")
    print(f"갱신 완료: {target.name} ({data['at']}) · 강원 {gw.get('rank', '?')}위 {gw.get('score', '')}점 메달 {gw.get('medal')}")


if __name__ == "__main__":
    main()
