#!/usr/bin/env python3
"""회사 자체 채용 홈페이지 → data/auto/cojobs.json (빌드 직전에 실행).

대상: data/career_sites.json 의 sites(확인을 마친 회사) — 회사가 채용 솔루션 '그리팅'으로 직접 운영하는 채용 홈페이지
      (https://<slug>.career.greetinghr.com). 목록 페이지에 들어 있는 공고 목록(JSON)만 읽는다.
      candidates 는 채용 홈페이지가 있는지 알아보는 후보다. 응답한 회사 이름·공고 수를 로그에만 남기고 게시하지 않는다.

원칙
- 회사가 스스로 공개한 채용 홈페이지만 읽는다(채용 플랫폼의 공고 데이터베이스는 읽지 않는다).
- 회사당 하루 1회, 목록 페이지 1쪽만 요청한다. robots.txt 가 막은 지원서 제출 경로(/o/*/apply 등)는 요청하지 않는다.
- 공고 본문·급여·연락처는 옮기지 않는다. 제목·회사·근무지·경력·고용형태·마감일과 원문 링크만 저장한다.
- 한 회사가 실패해도 나머지는 계속한다. 전부 실패하면 기존 파일을 그대로 둔다.
"""
import datetime as dt
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "auto"
TODAY = dt.date.today()
UA = "Mozilla/5.0 (compatible; SafePlumJobs/1.0; +https://safeplum.com/jobs/)"

_sp = importlib.util.spec_from_file_location("w24", Path(__file__).with_name("fetch_work24.py"))
w24 = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(w24)

# 직군(occupation) 이름으로 안전 직무를 알아볼 때 쓰는 기준 — 제목에 '안전'이 없어도 직군이 환경안전·EHS면 넣는다
OCC_RE = re.compile(r"안전|EHS|HSE|\bSHE\b|Safety", re.I)
OCC_EXCLUDE_RE = re.compile(r"식품\s*안전|정보\s*보안|보안|품질", re.I)
# 제목만 보고 빼는 공고: 추천 채용·인재풀 안내, 업무 보조, 온라인 서비스의 Trust & Safety(이용자 보호 직무)
TITLE_EXCLUDE_RE = re.compile(r"추천\s*채용|인재\s*(풀|pool|DB)|업무\s*보조|\[Assistant\]|Trust\s*(&|and)\s*Safety|식품\s*안전", re.I)


def warn(msg):
    print("  경고:", msg, file=sys.stderr)


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def openings_of(html):
    """그리팅 채용 홈페이지 HTML → (회사 이름, 공고 목록). 구조가 다르면 (이름, None)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return "", None
    try:
        pp = json.loads(m.group(1))["props"]["pageProps"]
    except (ValueError, KeyError):
        return "", None
    name, ops = "", None
    for q in (pp.get("dehydratedState") or {}).get("queries", []):
        key, data = q.get("queryKey") or [], (q.get("state") or {}).get("data")
        if key[:2] == ["publicCareer", "getCareerBaseInfo"] and isinstance(data, dict):
            name = ((data.get("workspace") or {}).get("name") or "").strip()
        if key and key[0] == "openings" and isinstance(data, list):
            ops = data
    return name, ops


def positions(o):
    return ((o.get("openingJobPosition") or {}).get("openingJobPositions")) or []


def is_safety(o):
    title = o.get("title") or ""
    if w24.EXCLUDE_RE.search(title) or TITLE_EXCLUDE_RE.search(title):
        return False
    if w24.JOB_RE.search(title):
        return True
    occ = " ".join(str(((p.get("workspaceOccupation") or {}).get("occupation")) or "") + " " + str(((p.get("workspaceJob") or {}).get("job")) or "") for p in positions(o))
    return bool(OCC_RE.search(occ)) and not OCC_EXCLUDE_RE.search(occ) and not OCC_EXCLUDE_RE.search(title)


def kst_date(iso):
    """'2026-12-31T14:59:59Z' → 한국 날짜 '2026-12-31'."""
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    return (t + dt.timedelta(hours=9)).date().isoformat()


def career_of(ps):
    kinds, lo = set(), None
    for p in ps:
        c = p.get("jobPositionCareer") or {}
        t = c.get("careerType")
        if t:
            kinds.add(t)
        if isinstance(c.get("careerFrom"), int):
            lo = c["careerFrom"] if lo is None else min(lo, c["careerFrom"])
    new, exp = "NEW_COMER" in kinds, "EXPERIENCED" in kinds
    n = f" {lo}년↑" if lo else ""
    if new and exp:
        return "신입·경력", "신입·경력" + n
    if new:
        return "신입", "신입"
    if exp:
        return "경력", "경력" + n
    return "경력무관", "원문 확인"


def emp_of(ps):
    kinds = {((p.get("jobPositionEmployment") or {}).get("employmentType")) for p in ps} - {None}
    if not kinds:
        return "정규직", "고용형태는 원문 확인"
    if kinds <= {"FULL_TIME_WORKER"}:
        return "정규직", ""
    if any("INTERN" in k for k in kinds):
        return "계약직", "인턴"
    return "계약직", "" if not ("FULL_TIME_WORKER" in kinds) else "정규직·계약직"


def place_of(ps):
    for p in ps:
        pl = p.get("workspacePlace") or {}
        addr = (pl.get("place") or "").strip()
        if addr:
            return addr
    return ""


def norm_addr(addr):
    addr = re.sub(r"^대한민국\s*", "", addr)
    tk = addr.split()
    if tk:
        tk[0] = w24.SIDO.get(tk[0], tk[0])
    return " ".join(tk)


def collect(site):
    slug = site["slug"]
    base = f"https://{slug}.career.greetinghr.com"
    try:
        name, ops = openings_of(get(base + "/ko/home"))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        name, ops = "", None
    if ops is None:
        name2, ops = openings_of(get(base + "/"))
        name = name or name2
    return base, name, ops

# ---- 그린하우스(Greenhouse) 공개 채용 게시판 API: 회사가 자기 채용 홈페이지에 공고를 싣는 데 쓰는 공개 API(인증 없음)
GH_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
GH_EXCLUDE_RE = re.compile(r"변호사|Legal|Counsel|Analyst|Compliance Audit", re.I)
GH_PLACES = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주", "수원", "용인", "화성", "평택", "안산", "안성", "이천", "여주", "고양", "김포", "부천", "시흥", "동탄", "오산", "남양주", "양주", "파주", "천안", "아산", "청주", "음성", "진천", "전주", "군산", "창원", "김해", "양산", "칠곡", "구미", "경산", "포항", "원주", "춘천", "목포", "순천", "광양", "덕평", "곤지암", "마장", "장지", "송파"]


def gh_jobs(site):
    """그린하우스 게시판 → 국내 안전·보건 공고 목록. 제목·근무지 표기·게시일·원문 주소만 쓴다."""
    data = json.loads(get(GH_API.format(token=site["token"])))
    jobs = data.get("jobs") or []
    out = []
    for o in jobs:
        title = (o.get("title") or "").strip()
        loc = ((o.get("location") or {}).get("name") or "")
        if "Korea" not in loc and "한국" not in loc and "대한민국" not in loc:
            continue
        if w24.EXCLUDE_RE.search(title) or TITLE_EXCLUDE_RE.search(title) or GH_EXCLUDE_RE.search(title) or not w24.JOB_RE.search(title):
            continue
        dl = "채용 시"
        if o.get("application_deadline"):
            dl = kst_date(o["application_deadline"]) or "채용 시"
            if dl != "채용 시" and dl < TODAY.isoformat():
                continue
        m = re.search(r"\(([^)]*)\)\s*$", title)
        place = next((c for c in GH_PLACES if m and c in m.group(1)), "") or next((c for c in GH_PLACES if c in loc), "")
        if "Seoul" in loc and not place:
            place = "서울"
        company = site["company"]
        b = re.match(r"\[([^\]]+)\]", title)
        if b and b.group(1) in site.get("divisions", {}):
            company = site["divisions"][b.group(1)]
        url = o.get("absolute_url") or ""
        if site.get("url_from") and site.get("url_to"):
            url = url.replace(site["url_from"], site["url_to"])
        j = {
            "id": f"co-{site['token']}-{o.get('id')}",
            "title": title, "company": company,
            "region": place or "근무지 원문 확인", "address": "",
            "job": w24.job_of(title),
            "career": "경력무관", "employment": "계약직" if "계약직" in title else "정규직",
            "company_type": site.get("company_type", "중소·기타"), "industry": site.get("industry", "제조·화학"),
            "deadline": dl, "posted": kst_date(o.get("first_published") or o.get("updated_at")) or TODAY.isoformat(),
            "source_url": url, "source_name": f"{site['company']} 채용 홈페이지", "origin": "company",
            "career_detail": "원문 확인", "education": "원문 확인",
        }
        if "계약직" not in title:
            j["term"] = "고용형태는 원문 확인"
        if site.get("group"):
            j["group"] = site["group"]
        out.append(j)
    return len(jobs), out


def main():
    cfg = json.loads((ROOT / "data" / "career_sites.json").read_text(encoding="utf-8"))
    out, ok, fail = [], 0, 0
    for site in cfg.get("sites", []):
        try:
            base, name, ops = collect(site)
        except Exception as e:  # 한 회사 실패는 건너뜀
            fail += 1
            warn(f"{site.get('company')}({site['slug']}) 읽기 실패: {str(e)[:100]}")
            continue
        if ops is None:
            fail += 1
            warn(f"{site.get('company')}({site['slug']}) 공고 목록을 찾지 못함(페이지 구조가 다름)")
            continue
        ok += 1
        n = 0
        for o in ops:
            if not o.get("deploy", True) or not is_safety(o):
                continue
            ps = positions(o)
            dl = kst_date(o.get("dueDate")) if o.get("dueDate") else "채용 시"
            if dl != "채용 시" and dl < TODAY.isoformat():
                continue
            addr = norm_addr(place_of(ps))
            region = w24.region_of("", addr) if addr else ""
            if not region:  # 채용 홈페이지 목록에 근무지가 없는 공고 — 지역을 짐작하지 않고 원문 확인으로 표시
                region = "근무지 원문 확인"
            title = (o.get("title") or "").strip()
            car, car_d = career_of(ps)
            emp, term = emp_of(ps)
            division = ((o.get("workspaceDivision") or {}).get("division") or "").strip()
            j = {
                "id": f"co-{site['slug']}-{o.get('openingId')}",
                "title": title,
                "company": site.get("divisions", {}).get(division) or site["company"],
                "region": region,
                "address": addr,
                "job": w24.job_of(title),
                "career": car,
                "employment": emp,
                "company_type": site.get("company_type", "중소·기타"),
                "industry": site.get("industry", "제조·화학"),
                "deadline": dl,
                "posted": kst_date(o.get("openDate")) or TODAY.isoformat(),
                "source_url": f"{base}/ko/o/{o.get('openingId')}",
                "source_name": f"{site['company']} 채용 홈페이지",
                "origin": "company",
                "career_detail": car_d,
                "education": "원문 확인",
            }
            if site.get("group"):
                j["group"] = site["group"]
            if term:
                j["term"] = term
            out.append(j)
            n += 1
        print(f"  {site['company']}: 공고 {len(ops)}건 중 안전·보건 {n}건")
    # 그린하우스 게시판을 쓰는 회사
    for site in cfg.get("greenhouse", []):
        try:
            total, items = gh_jobs(site)
        except Exception as e:
            fail += 1
            warn(f"{site.get('company')}(greenhouse:{site['token']}) 읽기 실패: {str(e)[:100]}")
            continue
        ok += 1
        out.extend(items)
        print(f"  {site['company']}: 공고 {total}건 중 국내 안전·보건 {len(items)}건")
    for tok in cfg.get("greenhouse_candidates", []):
        try:
            total, items = gh_jobs({"token": tok, "company": tok})
            print(f"  [후보·GH] {tok}: 있음 — 공고 {total}건, 국내 안전·보건 {len(items)}건" + "".join(f"\n      · {i['title']}" for i in items[:5]))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"  [후보·GH] {tok}: HTTP {e.code}")
        except Exception as e:
            print(f"  [후보·GH] {tok}: 실패 {str(e)[:60]}")
        time.sleep(0.2)
    # 후보: 채용 홈페이지가 있는지만 확인하고 로그에 남긴다(게시하지 않음)
    for slug in cfg.get("candidates", []):
        try:
            base, name, ops = collect({"slug": slug})
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"  [후보] {slug}: HTTP {e.code}")
            continue
        except Exception as e:
            print(f"  [후보] {slug}: 실패 {str(e)[:60]}")
            continue
        finally:
            time.sleep(0.3)
        if ops is None:
            print(f"  [후보] {slug}: 페이지는 있으나 공고 목록 없음 (이름: {name})")
            continue
        hits = [o for o in ops if is_safety(o)]
        print(f"  [후보] {slug}: 있음 — 이름 '{name}', 공고 {len(ops)}건, 안전·보건 {len(hits)}건" + ("".join(f"\n      · {h.get('title')} | 근무지 {'있음' if place_of(positions(h)) else '없음'} | 마감 {kst_date(h.get('dueDate')) or '상시'}" for h in hits[:6])))
    if (cfg.get("sites") or cfg.get("greenhouse")) and ok == 0:
        warn("회사 채용 홈페이지를 하나도 읽지 못해 기존 파일을 유지합니다.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cojobs.json").write_text(json.dumps({"fetched": TODAY.isoformat(), "source": "회사 자체 채용 홈페이지", "items": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  회사 채용 홈페이지 {ok}곳 읽음(실패 {fail}곳) → 안전·보건 공고 {len(out)}건")


if __name__ == "__main__":
    main()
