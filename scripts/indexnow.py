#!/usr/bin/env python3
"""배포 뒤 검색엔진에 '바뀐 주소'를 알린다(IndexNow). 빙·네이버 등이 받는다.
사이트맵의 주소를 한 번에 보낸다. 실패해도 배포에는 영향을 주지 않는다(경고만)."""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
site = json.loads((ROOT / "config/site.json").read_text(encoding="utf-8"))
base = (site.get("base_url") or "").rstrip("/")
key = str(site.get("indexnow_key") or "")
if not base or not re.match(r"^[a-f0-9]{16,64}$", key):
    print("IndexNow: base_url 또는 indexnow_key 가 없어 건너뜀")
    sys.exit(0)
host = re.sub(r"^https?://", "", base)
try:
    xml = urllib.request.urlopen(base + "/sitemap.xml", timeout=20).read().decode("utf-8")
except Exception as ex:  # noqa: BLE001
    print("IndexNow: 사이트맵을 읽지 못함 →", ex)
    sys.exit(0)
urls = re.findall(r"<loc>([^<]+)</loc>", xml)[:10000]
body = json.dumps({"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": urls}).encode("utf-8")
for ep in ("https://api.indexnow.org/indexnow", "https://searchadvisor.naver.com/indexnow"):
    try:
        req = urllib.request.Request(ep, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"IndexNow: {ep} → {r.status} (주소 {len(urls)}개)")
    except Exception as ex:  # noqa: BLE001
        print(f"IndexNow: {ep} 실패(경고) → {ex}")
