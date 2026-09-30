#!/usr/bin/env python3
"""빌드된 _site 안의 외부 링크를 점검한다. 끊긴 링크 목록을 출력(빌드는 막지 않음).

GitHub Actions에서 주 1회 실행. 결과는 Actions 실행 요약(Summary)에 표로 남는다.
"""
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

SITE = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
links = set()
for f in SITE.rglob("*.html"):
    for u in re.findall(r'href="(https?://[^"]+)"', f.read_text(encoding="utf-8")):
        u = unescape(u)
        # 법령 전문 페이지의 조문별 원문 링크(1천여 개)는 같은 법령 주소 + 조번호라 법령 주소 하나만 점검
        if "law.go.kr/" in u and re.search(r"/%EC%A0%9C\d+%EC%A1%B0|/제\d+조", u):
            u = re.sub(r"/(%EC%A0%9C\d+%EC%A1%B0.*|제\d+조.*)$", "", u)
        links.add(u)


def check(u):
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 anjeonduck-linkcheck"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(200000).decode("utf-8", "ignore")
            # 법령정보센터는 없는 주소도 200으로 오류 안내를 돌려준다
            if "law.go.kr" in u and ("정확한 한글 주소명인지" in body or "요청하신 페이지를 찾을 수" in body):
                return u, "법령정보센터 오류 안내 페이지"
            return u, None
    except Exception as ex:  # noqa: BLE001
        return u, str(ex)[:120]


with ThreadPoolExecutor(8) as ex:
    results = list(ex.map(check, sorted(links)))
bad = [(u, err) for u, err in results if err]
print(f"외부 링크 {len(links)}개 중 문제 {len(bad)}개")
for u, err in bad:
    print(f"  ✗ {u}\n    {err}")
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as s:
        s.write(f"### 링크 점검: {len(links)}개 중 문제 {len(bad)}개\n\n")
        if bad:
            s.write("| 주소 | 오류 |\n|---|---|\n")
            for u, err in bad:
                s.write(f"| {u} | {err} |\n")
