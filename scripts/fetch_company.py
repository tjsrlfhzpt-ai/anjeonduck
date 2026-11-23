#!/usr/bin/env python3
"""회사 자체 채용 홈페이지 → data/cojobs.json (운영자가 요청할 때만 실행: .github/workflows/collect-jobs.yml).

대상: data/career_sites.json 의 sites(확인을 마친 회사) — 회사가 채용 솔루션 '그리팅'으로 직접 운영하는 채용 홈페이지
      (https://<slug>.career.greetinghr.com). 목록 페이지에 들어 있는 공고 목록(JSON)만 읽는다.
      candidates 는 채용 홈페이지가 있는지 알아보는 후보다. 응답한 회사 이름·공고 수를 로그에만 남기고 게시하지 않는다.

원칙
- 회사가 스스로 공개한 채용 홈페이지만 읽는다(채용 플랫폼의 공고 데이터베이스는 읽지 않는다).
- 수집은 요청이 있을 때만, 회사당 목록 페이지 1쪽만 요청한다. robots.txt 가 막은 지원서 제출 경로(/o/*/apply 등)는 요청하지 않는다.
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
OUT = ROOT / "data"   # 요청할 때만 수집하므로 결과를 저장소에 남긴다(data/cojobs.json)
TODAY = dt.date.today()
UA = "Mozilla/5.0 (compatible; SafePlumJobs/1.0; +https://safeplum.com/jobs/)"

_sp = importlib.util.spec_from_file_location("w24", Path(__file__).with_name("fetch_work24.py"))
w24 = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(w24)

# 직군(occupation) 이름으로 안전 직무를 알아볼 때 쓰는 기준 — 제목에 '안전'이 없어도 직군이 환경안전·EHS면 넣는다
OCC_RE = re.compile(r"안전|EHS|HSE|\bSHE\b|Safety", re.I)
OCC_EXCLUDE_RE = re.compile(r"식품\s*안전|정보\s*보안|보안|품질", re.I)
# 제목만 보고 빼는 공고: 추천 채용·인재풀 안내, 업무 보조, 온라인 서비스의 Trust & Safety(이용자 보호 직무),
# 자동차 기능안전(SOTIF·Functional/AI Safety), 의약품 안전관리책임자(RA)·약물감시 — 산업안전 직무가 아님
TITLE_EXCLUDE_RE = re.compile(r"추천\s*채용|인재\s*(풀|pool|DB)|업무\s*보조|\[Assistant\]|Trust\s*(&|and)\s*Safety|식품\s*안전|SOTIF|기능\s*안전|Functional\s*Safety|AI\s*Safety|안전관리책임자\s*\(RA\)|약물\s*감시|Pharmacovigilance", re.I)


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


def bracket_company(title, site):
    """그룹 채용 홈페이지의 '[동국씨엠] 안전환경 ...' 같은 제목에서 실제 회사 이름을 꺼낸다(그룹으로 등록한 곳만)."""
    if not site.get("group"):
        return ""
    m = re.match(r"\s*\[([^\]]{2,20})\]", title or "")
    if not m or re.search(r"경력|신입|채용|계약|인턴|정규|모집|수시|상시|공채", m.group(1)):
        return ""
    name = m.group(1).strip()
    if name.lower().replace(" ", "") == site.get("slug", "").lower() or name in site.get("company", ""):
        return ""   # [HYBE]처럼 회사 자신을 가리키는 표기는 그대로 둔다
    return name


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

# ---- 두산 채용(career.doosan.com): 로그인 없이 열리는 공고 목록 HTML(RecList.jsp)에서 회사·제목·접수기간만 읽는다.
# 2026-11-13 확인: 공개 이용약관 없음(개인정보처리방침만), robots.txt 없음. 상세 화면은 주소로 바로 열리지 않아 목록 화면으로 연결한다.
DOOSAN_LIST = "https://career.doosan.com/dsp/sa/RecList.jsp"
DOOSAN_ROW = re.compile(r"goDetail\('(\d+)'[^)]*\)[^>]*>(.*?)</a>", re.S)


def _text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def doosan_jobs(site):
    html = get(DOOSAN_LIST)
    rows = DOOSAN_ROW.findall(html)
    out, seen = [], set()
    for rid, inner in rows:
        if rid in seen:
            continue
        seen.add(rid)
        comp = _text((re.search(r'class="company"[^>]*>(.*?)<span', inner, re.S) or re.search(r'class="company"[^>]*>(.*?)</div>', inner, re.S) or [None, ""])[1])
        title = _text((re.search(r"<strong[^>]*>(.*?)</strong>", inner, re.S) or [None, ""])[1])
        kind = _text((re.search(r'class="badge-type"[^>]*>(.*?)</span>', inner, re.S) or [None, ""])[1])
        period = re.findall(r"(\d{4}-\d{2}-\d{2})", inner)
        if not title or w24.EXCLUDE_RE.search(title) or TITLE_EXCLUDE_RE.search(title) or not w24.JOB_RE.search(title):
            continue
        dl = period[1] if len(period) > 1 else "채용 시"
        if dl != "채용 시" and dl < TODAY.isoformat():
            continue
        car = "신입" if "신입" in kind else ("경력" if "경력" in kind else "경력무관")
        j = {
            "id": f"co-doosan-{rid}", "title": title, "company": comp or "두산",
            "region": "근무지 원문 확인", "address": "", "job": w24.job_of(title),
            "career": car, "employment": "계약직" if ("계약" in kind or "계약" in title) else "정규직",
            "company_type": "대기업", "group": "두산그룹", "industry": site.get("industry", "제조·화학"),
            "deadline": dl, "posted": period[0] if period else TODAY.isoformat(),
            "source_url": DOOSAN_LIST, "source_name": "두산 채용 홈페이지", "origin": "company",
            "career_detail": car if car != "경력무관" else "원문 확인", "education": "원문 확인",
            "note": "두산 채용 홈페이지 공고 목록에서 제목으로 찾아 지원",
        }
        if "계약" in kind and "계약" not in title:
            j["term"] = "기간은 원문 확인"
        out.append(j)
    return len(rows), out


# ---- 워크데이(Workday) 회사 채용 사이트: 회사가 직접 운영하는 공개 채용 페이지가 화면을 그릴 때 쓰는 공고 검색(JSON)만 읽는다.
# 2026-11-23 확인: robots.txt 가 공고 경로를 막지 않음(refreshFacet 만 막음). 한국 근무 + 안전·보건 직무만, 제목·근무지·게시 시기·원문 링크만 저장.
WD_QUERIES = ("Korea EHS", "Korea Safety", "Korea Health Safety", "Korea 안전", "Korea 보건")
WD_SAFE_RE = re.compile(r"\bEHS\b|\bHSE\b|\bESH\b|\bSHE\b|Safety|Industrial Hygien|안전|보건", re.I)
WD_EXCLUDE_RE = re.compile(r"Drug\s*Safety|Patient\s*Safety|Product\s*Safety|Food\s*Safety|Pharmacovigilance|Cyber|Information\s*Security|Sales|Field\s*Service\s*Engineer|Quality\s*Engineer", re.I)
WD_PLACES = [("Hwaseong", "경기 화성시"), ("Dongtan", "경기 화성시"), ("JangAn", "경기 화성시"), ("Bundang", "경기 성남시"), ("Seongnam", "경기 성남시"), ("Pangyo", "경기 성남시"),
             ("Suwon", "경기 수원시"), ("Pyeongtaek", "경기 평택시"), ("Icheon", "경기 이천시"), ("Yongin", "경기 용인시"), ("Giheung", "경기 용인시"), ("Ansan", "경기 안산시"),
             ("Anseong", "경기 안성시"), ("Paju", "경기 파주시"), ("Gimpo", "경기 김포시"), ("Siheung", "경기 시흥시"), ("Pyeongtaek", "경기 평택시"),
             ("Gangnam", "서울 강남구"), ("Seoul", "서울"), ("Songdo", "인천 연수구"), ("Incheon", "인천"), ("Cheongju", "충북 청주시"), ("Ochang", "충북 청주시"),
             ("Cheonan", "충남 천안시"), ("Asan", "충남 아산시"), ("Dangjin", "충남 당진시"), ("Seosan", "충남 서산시"), ("Daejeon", "대전"), ("Sejong", "세종"),
             ("Gumi", "경북 구미시"), ("Pohang", "경북 포항시"), ("Ulsan", "울산"), ("Busan", "부산"), ("Changwon", "경남 창원시"), ("Yeosu", "전남 여수시"),
             ("Gwangyang", "전남 광양시"), ("Gunsan", "전북 군산시"), ("Iksan", "전북 익산시"), ("Daegu", "대구"), ("Gwangju", "광주")]
WD_KR_RE = re.compile(r"Korea|KOR\b|대한민국|" + "|".join(k for k, _ in WD_PLACES), re.I)


def wd_days_ago(txt):
    t = str(txt or "")
    if re.search(r"Today|오늘", t):
        return 0
    if re.search(r"Yesterday|어제", t):
        return 1
    m = re.search(r"(\d+)\s*(\+)?\s*(Days|일)", t)
    return int(m.group(1)) if m else 30


def wd_jobs(site):
    t, wd, name = site["tenant"], site["wd"], site["site"]
    base = f"https://{t}.{wd}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{t}/{name}/jobs"
    seen, out, total = set(), [], 0
    for q in WD_QUERIES:
        body = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q}).encode()
        req = urllib.request.Request(api, data=body, headers={"User-Agent": UA, "Accept-Language": "ko", "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        total = max(total, d.get("total") or 0)
        for p in d.get("jobPostings") or []:
            path, title, loc = p.get("externalPath") or "", (p.get("title") or "").strip(), p.get("locationsText") or ""
            if not path or path in seen:
                continue
            seen.add(path)
            if not WD_SAFE_RE.search(title) or WD_EXCLUDE_RE.search(title) or TITLE_EXCLUDE_RE.search(title) or w24.EXCLUDE_RE.search(title):
                continue
            if not WD_KR_RE.search(loc + " " + path):
                continue
            place = next((v for k, v in WD_PLACES if re.search(k, loc + " " + path, re.I)), "")
            contract = bool(re.search(r"contract|Fixed[\s-]*Term|Temporary|계약|Backfill", title, re.I))
            jid = re.sub(r"[^A-Za-z0-9_-]", "", path.rsplit("_", 1)[-1])[:40] or str(len(out))
            j = {
                "id": f"co-wd-{t}-{jid}", "title": title, "company": site["company"],
                "region": place or "근무지 원문 확인", "address": "",
                "job": "보건관리자" if re.search(r"Nurse|Health\s*Manager|보건", title, re.I) else w24.job_of(title) or "EHS",
                "career": "경력무관", "employment": "계약직" if contract else "정규직",
                "company_type": site.get("company_type", "외국계"), "industry": site.get("industry", "제조·화학"),
                "deadline": "채용 시", "posted": (TODAY - dt.timedelta(days=wd_days_ago(p.get("postedOn")))).isoformat(),
                "source_url": f"{base}/ko-KR/{name}{path}", "source_name": f"{site['company']} 채용 홈페이지", "origin": "company",
                "career_detail": "원문 확인", "education": "원문 확인",
            }
            if contract:
                j["term"] = "기간은 원문 확인"
            else:
                j["term"] = "고용형태는 원문 확인"
            if site.get("group"):
                j["group"] = site["group"]
            out.append(j)
        time.sleep(0.5)
    return total, out


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
                "company": site.get("divisions", {}).get(division) or bracket_company(title, site) or site["company"],
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
    # 자체 채용 시스템(현재 두산)
    for site in cfg.get("custom", []):
        fn = {"doosan": doosan_jobs}.get(site.get("kind"))
        if not fn:
            continue
        try:
            total, items = fn(site)
        except Exception as e:
            fail += 1
            warn(f"{site.get('company')}({site['kind']}) 읽기 실패: {str(e)[:100]}")
            continue
        ok += 1
        out.extend(items)
        print(f"  {site['company']}: 공고 {total}건 중 안전·보건 {len(items)}건")
    # 워크데이 채용 사이트를 쓰는 회사(주로 외국계)
    for site in cfg.get("workday", []):
        try:
            total, items = wd_jobs(site)
        except Exception as e:
            fail += 1
            warn(f"{site.get('company')}(workday:{site['tenant']}) 읽기 실패: {str(e)[:100]}")
            continue
        ok += 1
        out.extend(items)
        print(f"  {site['company']}: 검색 공고 {total}건 중 한국 안전·보건 {len(items)}건")
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
    if (cfg.get("sites") or cfg.get("greenhouse") or cfg.get("custom") or cfg.get("workday")) and ok == 0:
        warn("회사 채용 홈페이지를 하나도 읽지 못해 기존 파일을 유지합니다.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cojobs.json").write_text(json.dumps({"fetched": TODAY.isoformat(), "source": "회사 자체 채용 홈페이지", "items": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  회사 채용 홈페이지 {ok}곳 읽음(실패 {fail}곳) → 안전·보건 공고 {len(out)}건")


if __name__ == "__main__":
    main()
