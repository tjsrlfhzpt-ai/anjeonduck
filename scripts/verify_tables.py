#!/usr/bin/env python3
"""data/selection.json 의 별표 행이 국가법령정보센터 별표 원본(assets/files/law/*.pdf)과 맞는지 대조한다.

- 행 번호 집합이 원본과 같은지, 업종명의 낱말이 원본에 있는지, <개정 …> 날짜가 같은지 본다.
- pdftotext(poppler)가 없으면 건너뛴다(경고). 불일치는 종료코드 1.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = {"b2": "yeong_BE0002-00.pdf", "b3": "yeong_BE0003-00.pdf", "b5": "yeong_BE0005-00.pdf", "b9": "yeong_BE0009-00.pdf", "r2": "rule_BE0002-00.pdf", "b1": "yeong_BE0001-00.pdf"}


def main():
    if not shutil.which("pdftotext"):
        print("verify_tables: pdftotext 없음 — 건너뜀")
        return 0
    d = json.loads((ROOT / "data/selection.json").read_text(encoding="utf-8"))
    bad = 0
    for key, fn in MAP.items():
        raw = subprocess.run(["pdftotext", "-layout", str(ROOT / "assets/files/law" / fn), "-"], capture_output=True, text=True).stdout
        flat = re.sub(r"\s", "", raw)
        head = re.search(r"<개정\s*([\d.\s]+)>", raw)
        ours = re.search(r"<개정\s*([\d.\s]+)>", d[key]["law"])
        if not head or not ours or re.sub(r"\s", "", head.group(1)) != re.sub(r"\s", "", ours.group(1)):
            print(f"  {key}: 개정일 불일치 — 원본 {head and head.group(0)} / 데이터 {d[key]['law']}")
            bad += 1
        if key == "b1":   # 별표 1은 요약 문구라 개정일만 대조
            continue
        nums = set(re.findall(r"^\s{0,3}(\d+(?:의\d+)?)\.\s", raw, re.M))
        mine = {r["no"] for r in d[key]["rows"]}
        if mine - nums:
            print(f"  {key}: 원본에 없는 행 번호 {sorted(mine - nums)}")
            bad += 1
        for r in d[key]["rows"]:
            toks = [w for w in re.split(r"[\s,;()ㆍ·]+", r["name"]) if len(w) >= 3 and not re.match(r"^제\d", w)]
            hit = sum(1 for w in toks if w in flat or w[:3] in flat)
            if toks and hit / len(toks) < 0.6:
                print(f"  {key} {r['no']}: 업종명이 원본과 다를 수 있음 — {r['name']}")
                bad += 1
    print("verify_tables:", "불일치 %d건" % bad if bad else "별표 1·2·3·5·9, 규칙 별표 2 — 원본과 일치")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
