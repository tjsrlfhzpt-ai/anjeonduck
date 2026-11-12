#!/usr/bin/env python3
"""고용24(한국고용정보원) 채용정보 Open API → data/auto/w24jobs.json (빌드 직전에 실행).

API: https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
     (고용24 > 고객센터 > OPEN-API > 서비스 소개 및 신청 > 채용정보 API, 2026-11-04 확인)
     요청: authKey, callTp=L, returnType=XML, startPage(≤1000), display(≤100), keyword, coTp, regDate …
     응답: <wantedRoot><total/><wanted>wantedAuthNo, company, indTpNm, title, region, minEdubg, career,
           regDt, closeDt, wantedInfoUrl, basicAddr, empTpCd …</wanted></wantedRoot>

원칙
- 인증키는 환경변수 WORK24_KEY 로만 받는다(GitHub Secret). 페이지·저장소·로그에 쓰지 않는다.
- 키가 없거나 API가 실패하면 파일을 만들지 않고(또는 기존 파일 유지) 경고만 남긴다 → 빌드는 계속된다.
- 공고 본문·급여·연락처는 옮기지 않는다. 목록 정보(회사·제목·지역·경력·학력·고용형태·마감)와 원문 링크만 저장한다.
- 호출 수: 키워드 5개 × 최대 5쪽 + 기업형태(대기업·공공기관·외국계) 확인 호출 — 하루 60회 안팎(기본 한도 안).
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "auto"
KEY = os.environ.get("WORK24_KEY", "").strip()
URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
TODAY = dt.date.today()

KEYWORDS = ["안전관리자", "보건관리자", "안전보건", "산업안전", "EHS", "HSE", "환경안전", "안전환경", "총무 안전", "세이프티"]
CO_TYPES = {"01": "대기업", "04": "공공기관", "05": "외국계"}  # 응답에 기업형태가 없어 조건 검색으로 표시
MAX_PAGES = 5

# 안전·보건 직무로 보는 제목
JOB_RE = re.compile(r"안전\s*관리|안전\s*보건|보건\s*관리|산업\s*안전|산업\s*보건|건설\s*안전|안전\s*담당|안전\s*팀|환경\s*안전|안전\s*환경|EHS|HSE|(?-i:\bSHE\b)|\bSafety\b|세이프티|총무[^,]{0,8}안전|안전[^,]{0,8}총무|중대재해|전기\s*안전\s*관리|소방\s*안전\s*관리", re.I)
# 잡코리아 선별 기준과 같게 뺄 공고 (감시·경비·점검 대행·강사·영업·시설 단순 관리 등)
EXCLUDE_RE = re.compile(r"감시단|화재\s*감시|신호수|유도원|경비|보안요원|순찰|미화|청소|소방\s*점검|소방시설\s*(관리|점검)|"
                        r"대행|강사|교사|영업|판매|컨설팅|상담원|사무\s*보조|경리|운전원|운전기사|배달|요양|간호조무|"
                        r"안전\s*관리원|안전\s*요원|검사원|시험원|아르바이트|알바", re.I)


SIDO = {"서울특별시": "서울", "경기도": "경기", "경상남도": "경남", "경상북도": "경북", "충청남도": "충남", "충청북도": "충북", "전라남도": "전남",
        "전라북도": "전북", "전북특별자치도": "전북", "강원도": "강원", "강원특별자치도": "강원", "제주특별자치도": "제주", "인천광역시": "인천",
        "부산광역시": "부산", "대구광역시": "대구", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종"}


def warn(msg):
    print("  경고:", msg, file=sys.stderr)


def mask(text):
    return re.sub(r"authKey=[^&\s\"'<]+", "authKey=***", text).replace(KEY, "***") if KEY else text


def snippet(text, n=160):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", mask(text))).strip()[:n]


def call(params, timeout=30):
    q = urllib.parse.urlencode({"authKey": KEY, "callTp": "L", "returnType": "XML", **params})
    req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "Mozilla/5.0 (safeplum-fetch/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} — {snippet(e.read().decode('utf-8', 'replace')) or '(본문 없음)'}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"접속 실패 — {mask(str(e.reason))}") from None
    if "<wantedRoot" not in raw:
        raise RuntimeError(f"채용정보 응답이 아님 — {snippet(raw)}")
    root = ET.fromstring(raw)
    total = int((root.findtext("total") or "0").strip() or 0)
    rows = [{c.tag: (c.text or "").strip() for c in w} for w in root.iter("wanted")]
    return total, rows


def date_of(s):
    """'26-11-04', '2026-11-04', '20261104', '채용시까지 26-12-31' → 'YYYY-MM-DD' (없으면 '')."""
    s = str(s or "")
    m = re.search(r"(20\d{2})[-./]?(\d{2})[-./]?(\d{2})", s) or re.search(r"(?<!\d)(\d{2})-(\d{2})-(\d{2})(?!\d)", s)
    if not m:
        return ""
    y = m.group(1)
    y = y if len(y) == 4 else "20" + y
    try:
        return dt.date(int(y), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return ""


def job_of(title):
    t = title.upper()
    out = []
    if re.search(r"전기\s*안전", title):
        out.append("전기안전관리자")
    if re.search(r"소방\s*안전", title):
        out.append("소방안전관리자")
    if re.search(r"(?<!전기)(?<!소방)(?<!전기 )(?<!소방 )안전\s*(관리|보건|담당|팀|환경)|산업\s*안전|건설\s*안전|환경\s*안전|중대재해", title):
        out.append("안전관리자")
    if re.search(r"보건\s*관리|산업\s*보건|안전\s*보건", title):
        out.append("보건관리자")
    # 총무·환경 겸직, Safety/세이프티 표기도 안전 직무로 본다(전기안전·소방안전은 위에서 따로 분류)
    if re.search(r"총무[^,]{0,8}안전|안전[^,]{0,8}총무", title) and "안전관리자" not in out and not out:
        out.append("안전관리자")
    if re.search(r"EHS|HSE|SAFETY|세이프티", t) or re.search(r"\bSHE\b", title):
        out.append("EHS")
    return "|".join(dict.fromkeys(out)) or "안전관리자"


def career_of(s):
    s = s or ""
    if "관계없음" in s or "무관" in s or not s:
        return "경력무관", "경력무관"
    new, exp = "신입" in s, "경력" in s
    m = re.search(r"(\d+)\s*년", s)
    n = f" {m.group(1)}년↑" if m else ""
    if new and exp:
        return "신입·경력", "신입·경력" + n
    if new:
        return "신입", "신입"
    return "경력", "경력" + n


def edu_of(s):
    s = s or ""
    if not s or "무관" in s:
        return "학력무관"
    if "박사" in s or "석사" in s:
        return "석사↑"
    if "4년" in s or s.strip() in ("대졸", "대학교"):
        return "대졸↑"
    if "2~3" in s or "2,3" in s or "초대졸" in s or "전문" in s:
        return "초대졸↑"
    if "고졸" in s or "고등" in s:
        return "고졸↑"
    return "학력무관"


def emp_of(code):
    c = str(code or "").strip()
    if c in ("10", "11"):
        return "정규직", ""
    if c in ("20", "21"):
        return "계약직", ""
    if c == "4":
        return "계약직", "파견"
    if c.upper() == "Y":
        return "계약직", "대체인력"
    return "정규직", "고용형태는 원문 확인"


IND_MAP = [("반도체·전자", r"반도체|전자|디스플레이|전지|배터리"),
           ("건설·플랜트·조선", r"건설|건축|토목|공사|조선|플랜트|엔지니어링"),
           ("에너지·공공", r"전기|가스|증기|발전|에너지|수도|하수|폐기물|공공|행정|원자력"),
           ("물류·운수", r"운수|운송|물류|창고|택배|항공|해운|철도"),
           ("제조·화학", r"제조|화학|금속|기계|자동차|철강|고무|플라스틱|섬유|제지|의약|비금속|1차")]


def industry_of(s):
    for name, pat in IND_MAP:
        if re.search(pat, s or ""):
            return name
    return "식품·유통·서비스"


def region_of(r, addr):
    src = (r or addr or "").replace("특별시", "").replace("광역시", "").replace("특별자치시", "").replace("특별자치도", "")
    src = re.sub(r"^(경기|강원|충청북|충청남|전라북|전라남|경상북|경상남|제주)도?", lambda m: {"충청북": "충북", "충청남": "충남", "전라북": "전북", "전라남": "전남", "경상북": "경북", "경상남": "경남"}.get(m.group(1), m.group(1)), src.strip())
    tk = src.split()
    return " ".join(tk[:2]) if tk else ""


def https(u):
    u = (u or "").strip()
    if u.startswith("http://") and "work24.go.kr" in u:
        u = "https://" + u[7:]
    return u if u.startswith("https://") else ""


def collect(extra=None, pages=MAX_PAGES):
    got = {}
    for kw in KEYWORDS:
        for p in range(1, pages + 1):
            total, rows = call({"startPage": p, "display": 100, "keyword": kw, "sortOrderBy": "DESC", **(extra or {})})
            for r in rows:
                if r.get("wantedAuthNo"):
                    got.setdefault(r["wantedAuthNo"], r)
            if not rows or p * 100 >= total:
                break
    return got


def main():
    if not KEY:
        print("  WORK24_KEY 없음 — 고용24 채용 수집을 건너뜁니다(기존 data/auto/w24jobs.json 이 있으면 그대로 사용).")
        return 0
    try:
        rows = collect()
    except Exception as e:
        warn(f"고용24 채용 수집 실패: {type(e).__name__}: {mask(str(e))[:200]}")
        return 0
    print(f"  고용24 응답 {len(rows)}건(키워드 {len(KEYWORDS)}개 합산, 중복 제외)")
    if rows:
        first = next(iter(rows.values()))
        print("  응답 항목:", ", ".join(f"{k}({len(v)}자)" for k, v in first.items()))
        print("  첫 건 예시:", json.dumps({k: first.get(k, "") for k in ("company", "title", "region", "career", "minEdubg", "regDt", "closeDt", "empTpCd", "indTpNm")}, ensure_ascii=False))
    ctype = {}
    for code, name in CO_TYPES.items():
        try:
            for no in collect({"coTp": code}, pages=2):
                ctype.setdefault(no, name)
        except Exception as e:
            warn(f"기업형태({name}) 확인 실패: {mask(str(e))[:120]}")
    out, skipped = [], {"직무 아님": 0, "제외 직무": 0, "마감": 0, "원문 주소 없음": 0}
    for no, r in rows.items():
        title = r.get("title", "")
        if not JOB_RE.search(title):
            skipped["직무 아님"] += 1
            continue
        if EXCLUDE_RE.search(title):
            skipped["제외 직무"] += 1
            continue
        close = r.get("closeDt", "")
        dl = date_of(close) or "채용 시"  # '채용시까지 26-12-31'처럼 날짜가 있으면 그 날짜
        if dl != "채용 시" and dl < TODAY.isoformat():
            skipped["마감"] += 1
            continue
        link = https(r.get("wantedInfoUrl"))
        if not link:
            skipped["원문 주소 없음"] += 1
            continue
        car, car_d = career_of(r.get("career"))
        emp, term = emp_of(r.get("empTpCd"))
        addr = " ".join(x for x in (r.get("basicAddr"), r.get("detailAddr")) if x).strip()
        tk = addr.split()
        if tk:
            tk[0] = SIDO.get(tk[0], tk[0])
            addr = " ".join(tk)
        o = {
            "id": "w24-" + re.sub(r"[^a-z0-9]", "", no.lower()),
            "title": title,
            "company": r.get("company", ""),
            "region": region_of(r.get("region"), addr),
            "address": addr or r.get("region", ""),
            "job": job_of(title),
            "career": car,
            "employment": emp,
            "company_type": ctype.get(no, "중소·기타"),
            "industry": industry_of(r.get("indTpNm")),
            "deadline": dl,
            "posted": date_of(r.get("regDt")) or TODAY.isoformat(),
            "source_url": link,
            "source_name": "고용24",
            "origin": "work24",
            "career_detail": car_d,
            "education": edu_of(r.get("minEdubg")),
        }
        if term:
            o["term"] = term
        out.append(o)
    print("  고용24 안전·보건 공고:", len(out), "건 / 뺀 공고:", ", ".join(f"{k} {v}" for k, v in skipped.items()))
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "w24jobs.json"
    if not out and p.exists():
        warn("고용24: 0건 — 기존 파일 유지")
        return 0
    p.write_text(json.dumps({"fetched": TODAY.isoformat(), "source": "고용24(한국고용정보원) 채용정보 Open API",
                             "items": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  w24jobs.json: {len(out)}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
