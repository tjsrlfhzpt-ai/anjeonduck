#!/usr/bin/env python3
"""채용 출처 후보 확인(로그만 남김, 아무것도 저장·게시하지 않음). .github/workflows/probe-sources.yml 에서 요청 시 실행.

1) 각 플랫폼 robots.txt — 공고 목록 경로를 막았는지 확인
2) 그리팅 후보 slug — 채용 홈페이지가 있는지, 안전·보건 공고가 몇 건인지
3) 나인하이어 채용 홈페이지 — 페이지 구조(공고 목록을 어디서 읽는지)
4) 워크데이(Workday) 회사 채용 사이트 — 한국 근무 안전·보건 공고가 있는지
5) 스마트리크루터스·그린하우스·레버 공개 게시판 API — 한국 근무 안전·보건 공고가 있는지
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_company as fc  # noqa: E402

UA = fc.UA
SAFE = re.compile(r"안전|보건|EHS|HSE|ESH|\bSHE\b|Safety|Industrial Hygien", re.I)
KR = re.compile(r"Korea|KOR\b|Seoul|서울|경기|Suwon|Hwaseong|Pyeongtaek|Icheon|Cheongju|Ansan|Incheon|Songdo|Busan|Ulsan|Gumi|Yeosu|Daejeon|Cheonan|Asan|Pohang|Changwon|Gimpo|Dongtan|Yongin|Giheung|Paju|Ochang|Pangyo|Seongnam", re.I)


def req(url, data=None, timeout=20, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "ko"}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.status, f.read().decode("utf-8", "replace")


def robots(host):
    try:
        st, t = req(f"https://{host}/robots.txt")
        lines = [l for l in t.splitlines() if l.strip() and not l.startswith("#")][:25]
        print(f"[robots] {host} ({st})\n    " + "\n    ".join(lines))
    except Exception as e:
        print(f"[robots] {host}: {str(e)[:80]}")


def main():
    cfg = json.loads((Path(__file__).resolve().parents[1] / "data" / "probe_candidates.json").read_text(encoding="utf-8"))
    for h in cfg.get("robots", []):
        robots(h)
    # 페이지 원문에서 API 주소·필드명 찾기
    for u in cfg.get("dump", []):
        try:
            st, t = req(u)
            print(f"[DUMP] {u} ({st}) len={len(t)}")
            for m in sorted(set(re.findall(r"https?://openapi\.gg\.go\.kr/[A-Za-z0-9_]+[^\"'<\s]*", t)))[:20]:
                print("    API:", m)
            body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body)
            print("    TEXT:", body[:3000])
        except Exception as e:
            print(f"[DUMP] {u}: {str(e)[:80]}")
    # 원문 HTML 구조 확인(API 주소·NEXT_DATA·스크립트) — 2026-11-27 recruiter.co.kr 확인용
    for u in cfg.get("rawdump", []):
        try:
            st, t = req(u)
        except Exception as e:
            print(f"[RAW] {u}: {str(e)[:80]}")
            continue
        print(f"[RAW] {u} ({st}) len={len(t)}")
        for m in sorted(set(re.findall(r"""["'](/[a-zA-Z0-9_/-]*(?:api|json|list|jobs|notice)[a-zA-Z0-9_/.?=&-]*)["']""", t)))[:40]:
            print("    PATH:", m)
        for m in sorted(set(re.findall(r"https?://[a-z0-9.-]+/[^\"'\s<>]*(?:api|json)[^\"'\s<>]*", t)))[:20]:
            print("    URL:", m)
        for m in re.findall(r'<script[^>]+src="([^"]+)"', t)[:15]:
            print("    SRC:", m)
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        if nd:
            print("    NEXT:", nd.group(1)[:2500])
        for m in re.findall(r'<meta[^>]+(?:name|property)="(?:description|og:title|og:description)"[^>]*>', t)[:6]:
            print("    META:", m[:400])
        for m in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', t, re.S)[:3]:
            print("    LD:", m[:1500])
        if t.lstrip().startswith("<?xml") or "<urlset" in t[:500] or "<sitemapindex" in t[:500]:
            locs = re.findall(r"<loc>([^<]+)</loc>", t)
            print(f"    LOCS {len(locs)}:", locs[:25])
        nf = "".join(re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', t, re.S))
        if nf:
            i = nf.find("마감")
            print("    NEXTF:", nf[max(0, i-1200):i+800] if i >= 0 else nf[:1500])
        body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
        body = re.sub(r"<[^>]+>", " ", body); body = re.sub(r"\s+", " ", body)
        print("    TEXT:", body[:1500])
    # 그리팅
    for slug in cfg.get("greeting", []):
        try:
            base, name, ops = fc.collect({"slug": slug})
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"[GR] {slug}: HTTP {e.code}")
            continue
        except Exception as e:
            print(f"[GR] {slug}: 실패 {str(e)[:60]}")
            continue
        finally:
            time.sleep(0.25)
        if ops is None:
            print(f"[GR] {slug}: 페이지 있음, 공고 목록 없음 ({name})")
            continue
        hits = [o for o in ops if fc.is_safety(o)]
        print(f"[GR] {slug}: 있음 '{name}' 공고 {len(ops)} 안전·보건 {len(hits)}" + "".join(f"\n      · {h.get('title')} | 마감 {fc.kst_date(h.get('dueDate')) or '상시'} | {fc.place_of(fc.positions(h))[:30]}" for h in hits[:6]))
    # 나인하이어 구조
    for slug in cfg.get("ninehire", []):
        for path in ("/job_posting", "/"):
            try:
                st, t = req(f"https://{slug}.ninehire.site{path}")
            except Exception as e:
                print(f"[NH] {slug}{path}: {str(e)[:60]}")
                continue
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
            apis = sorted(set(re.findall(r"https://[a-z0-9.-]*ninehire[a-z0-9.-]*/[A-Za-z0-9_/.-]{3,60}", t)))[:15]
            print(f"[NH] {slug}{path}: {st} len={len(t)} next={'Y' if nd else 'N'} apis={apis}")
            if nd:
                s = nd.group(1)
                print("      NEXT keys:", s[:1500].replace("\n", " "))
                i = s.find("job_posting") if "job_posting" in s else s.find("title")
                print("      ...", s[max(0, i - 300):i + 900].replace("\n", " "))
            else:
                print("      HTML:", re.sub(r"\s+", " ", t[:1200]))
            break
        time.sleep(0.3)
    # 워크데이
    for w in cfg.get("workday", []):
        t, wd, site = w
        url = f"https://{t}.{wd}.myworkdayjobs.com/wday/cxs/{t}/{site}/jobs"
        found = []
        for q in ("Korea EHS", "Korea Safety", "Korea 안전"):
            try:
                st, body = req(url, data=json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q}).encode(),
                               headers={"Content-Type": "application/json", "Accept": "application/json"})
                d = json.loads(body)
            except Exception as e:
                print(f"[WD] {t}/{site}: {str(e)[:70]}")
                break
            for p in d.get("jobPostings", []):
                if SAFE.search(p.get("title", "")) and KR.search(p.get("locationsText", "") + " " + p.get("externalPath", "")):
                    found.append(f"{p.get('title')} | {p.get('locationsText')} | {p.get('postedOn')} | {p.get('externalPath')}")
            time.sleep(0.3)
        else:
            print(f"[WD] {t}/{site}: 한국 안전·보건 {len(set(found))}" + "".join(f"\n      · {x}" for x in sorted(set(found))[:8]))
    # 스마트리크루터스
    for cid in cfg.get("smartrecruiters", []):
        try:
            st, body = req(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?country=kr&limit=100")
            d = json.loads(body)
            items = d.get("content", [])
            hits = [p for p in items if SAFE.search(p.get("name", ""))]
            print(f"[SR] {cid}: 한국 공고 {d.get('totalFound')} 안전·보건 {len(hits)}" + "".join(f"\n      · {p.get('name')} | {(p.get('location') or {}).get('city')} | {p.get('releasedDate')} | {p.get('id')}" for p in hits[:8]))
        except Exception as e:
            print(f"[SR] {cid}: {str(e)[:60]}")
        time.sleep(0.2)
    # 그린하우스
    for tok in cfg.get("greenhouse", []):
        try:
            total, items = fc.gh_jobs({"token": tok, "company": tok})
            print(f"[GH] {tok}: 공고 {total} 국내 안전·보건 {len(items)}" + "".join(f"\n      · {i['title']}" for i in items[:6]))
        except Exception as e:
            print(f"[GH] {tok}: {str(e)[:60]}")
        time.sleep(0.2)
    # 레버
    for tok in cfg.get("lever", []):
        try:
            st, body = req(f"https://api.lever.co/v0/postings/{tok}?mode=json")
            d = json.loads(body)
            hits = [p for p in d if SAFE.search(p.get("text", "")) and KR.search(json.dumps(p.get("categories", {})))]
            print(f"[LV] {tok}: 공고 {len(d)} 한국 안전·보건 {len(hits)}" + "".join(f"\n      · {p.get('text')} | {p.get('categories', {}).get('location')} | {p.get('hostedUrl')}" for p in hits[:6]))
        except Exception as e:
            print(f"[LV] {tok}: {str(e)[:60]}")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
