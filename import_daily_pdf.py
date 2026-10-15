#!/usr/bin/env python3
"""'오늘의 경기(10. 13~22)' PDF에서 강원 출전 정보(기록 종목 일정·출전선수·예상메달)를 읽어 HTML의 DAILY 데이터를 갱신합니다.

사용법:  python3 import_daily_pdf.py <PDF 폴더> [html파일]
필요:    pip install pdfplumber
- 토너먼트 종목: 대진 DATA의 세부종목에 예상메달·출전선수(학교)를 붙입니다.
- 기록 종목(육상·수영·사격·볼링 등): 날짜별 일정 항목으로 추가합니다.
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

import pdfplumber

DEFAULT_HTML = Path(__file__).with_name("index.html")
COLS = ["s", "t", "k", "e", "v", "pl", "m"]


def join_lines(x):
    """표 셀 안의 줄바꿈을 정리한다. 이름 중간에서 끊긴 줄은 붙이고, 쉼표·슬래시 뒤와 메달 항목 사이는 띄운다."""
    if x is None:
        return None
    out = ""
    for line in (l.strip() for l in x.split("\n")):
        if not line:
            continue
        if not out:
            out = line
        elif re.match(r"[금은동]\d|\d+[위강]", line):
            out = out.rstrip(", ") + ", " + line
        elif out.endswith((",", "/")) or line.startswith("/"):
            out += " " + line
        else:
            out += line
    return re.sub(r"\s+", " ", out).strip()


def read_pdfs(folder):
    rows = []
    for f in glob.glob(os.path.join(folder, "*.pdf")):
        m = re.search(r"\((\d+)\.\s*(\d+)\)", os.path.basename(f))
        if not m:
            continue
        day = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        prev = None
        with pdfplumber.open(f) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for raw in table:
                        if len(raw) != 7 or raw[0] == "종목" or all(c in (None, "") for c in raw):
                            continue
                        cells = [join_lines(c) for c in raw]
                        rec = {"d": day}
                        for key, val in zip(COLS, cells):
                            # 병합 셀(None)은 윗행 값을 이어받는다. 예상메달은 같은 묶음에 한 번만 적혀 있으므로 이어받지 않는다.
                            if val is None and prev is not None and key != "m":
                                val = prev[key]
                            rec[key] = val or ""
                        rec["s"] = rec["s"].replace(" ", "")
                        rows.append(rec)
                        prev = rec
    rows.sort(key=lambda r: r["d"])
    return rows


def norm(s):
    return re.sub(r"[\s\-·]", "", s or "").lower()


def gender_age(kind, event=""):
    k = kind or event
    g = "남자" if "남" in k else "여자" if "여" in k else "혼성/공통"
    a = "일반부" if re.search(r"일반|[남여]일", k) else "대학부" if "대학" in k else "18세이하부"
    return g, a


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    folder = sys.argv[1]
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_HTML
    page = target.read_text(encoding="utf-8")
    data = json.loads(re.search(r"^const DATA=(.*);$", page, re.M).group(1))
    keys = {(r["s"], r["g"], r["a"], norm(r["e"])) for r in data}
    tour_sports = {r["s"] for r in data}

    rows = read_pdfs(folder)
    em, pl, rec, miss = {}, {}, [], 0
    for r in rows:
        g, a = gender_age(r["k"], r["e"])
        if r["s"] in tour_sports:
            key = (r["s"], g, a, norm(re.sub(r"\(.*?\)", "", r["e"])))
            if key not in keys:
                miss += 1
                continue
            k = "|".join(key)
            if r["m"]:
                em[k] = r["m"]
            if r["pl"] and "," in r["pl"]:
                pl[k] = r["pl"]
        else:
            rec.append({"d": r["d"], "t": r["t"], "s": r["s"], "k": r["k"], "e": r["e"], "v": r["v"],
                        "pl": r["pl"], "m": r["m"], "g": g, "a": a})

    daily = {"src": os.path.basename(os.path.normpath(folder)), "rec": rec, "em": em, "pl": pl}
    line = "const DAILY=" + json.dumps(daily, ensure_ascii=False, separators=(",", ":")) + ";"
    if re.search(r"^const DAILY=.*;$", page, re.M):
        page = re.sub(r"^const DAILY=.*;$", lambda _: line, page, count=1, flags=re.M)
    else:
        page = re.sub(r"^(const DATA=.*;)$", lambda m: m.group(1) + "\n" + line, page, count=1, flags=re.M)
    target.write_text(page, encoding="utf-8")
    print(f"PDF {len(rows)}행 → 기록 종목 {len(rec)}건, 토너먼트 예상메달 {len(em)}개 세부종목"
          + (f", 대진과 맞지 않는 행 {miss}건" if miss else ""))


if __name__ == "__main__":
    main()
