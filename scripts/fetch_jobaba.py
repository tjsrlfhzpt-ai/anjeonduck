#!/usr/bin/env python3
"""경기도일자리재단 잡아바 채용정보(경기데이터드림 Open API) → data/ggjobs.json

- 출처: https://openapi.gg.go.kr/GGJOBABARECRUSTM (경기데이터드림 '경기도일자리재단 잡아바 채용정보')
- 이용 허락 조건: 상업적이용허용 및 콘텐츠변경허용(2026-11-23 경기데이터드림 데이터 페이지에서 확인)
- 경기 지역 중소·중견기업 공고가 대부분이다. 고용24·잡아바 자체 공고·민간 채용 사이트 공고가 섞여 있고, 공고마다 원문 링크가 있다.
- 운영자 결정(2026-11-12)에 따라 원문이 잡코리아인 공고는 싣지 않는다(SKIP_HOSTS).
- 인증키: 저장소 비밀값 GG_DATA_KEY (경기데이터드림 회원가입 후 무료 발급). 없으면 아무것도 하지 않고 기존 파일을 유지한다.
- 요청 시에만 실행(.github/workflows/collect-jobs.yml).
"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("w24", Path(__file__).resolve().parent / "fetch_work24.py")
w24 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w24)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ggjobs.json"
KEY = os.environ.get("GG_DATA_KEY", "").strip()
API = "https://openapi.gg.go.kr/GGJOBABARECRUSTM"
PSIZE = 1000
TODAY = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()
SKIP_HOSTS = ("jobkorea.co.kr",)
UA = "Mozilla/5.0 (compatible; SafePlumBot/1.0; +https://safeplum.com)"
# 회사 채용 홈페이지 수집기와 같은 제외 기준 + 잡아바에 많은 경비·시설 공고
EXTRA_EXCLUDE_RE = re.compile(r"아파트|관리사무소|시설\s*관리|경비|미화|주차|보안|소방\s*안전\s*관리자?\s*\(?\s*[23]급|강사|교육생|훈련생|일자리\s*사업|노인|어르신", re.I)


def warn(msg):
    print("  경고:", msg, file=sys.stderr)


def page(i, tries=3):
    q = urllib.parse.urlencode({"KEY": KEY, "Type": "json", "pIndex": i, "pSize": PSIZE})
    for k in range(tries):
        try:
            req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            body = d.get("GGJOBABARECRUSTM")
            if not body:
                res = d.get("RESULT") or {}
                if res.get("CODE") == "INFO-200":  # 해당하는 데이터가 없음
                    return 0, []
                raise RuntimeError(f"응답 형식 오류: {str(res)[:120]}")
            head = body[0]["head"]
            total = head[0].get("list_total_count", 0)
            code = (head[1].get("RESULT") or {}).get("CODE")
            if code != "INFO-000":
                raise RuntimeError(f"결과 코드 {code}")
            return total, (body[1].get("row") if len(body) > 1 else []) or []
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(2 + k * 3)
    return 0, []


def ymd(s):
    s = re.sub(r"\D", "", str(s or ""))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else ""


def emp_of(form):
    f = form or ""
    if re.search(r"계약|기간의\s*정함이\s*있는|임시|일용|파트|시간제", f) and "정함이 없는" not in f:
        term = "파견" if "파견근로 희망" in f else ("대체인력" if "대체인력채용 희망" in f else "")
        return "계약직", term
    if re.search(r"정규|기간의\s*정함이\s*없는|상용", f):
        return "정규직", ""
    return "정규직", "고용형태는 원문 확인"


def src_of(url):
    h = urllib.parse.urlparse(url).netloc.lower()
    if "work.go.kr" in h or "work24.go.kr" in h:
        return "고용24", "w24"
    if "job.gg.go.kr" in h or "jobaba" in h:
        return "잡아바", "jbb"
    if "saramin" in h:
        return "사람인", "sr"
    if "incruit" in h:
        return "인크루트", "inc"
    return h.replace("www.", ""), "etc"


def main():
    if not KEY:
        print("  GG_DATA_KEY 없음 — 경기 잡아바 채용 수집을 건너뜁니다(기존 data/ggjobs.json 유지).")
        return 0
    try:
        total, first = page(1)
    except Exception as e:
        warn(f"잡아바 1쪽 읽기 실패: {str(e)[:200]}")
        return 0
    pages = (total + PSIZE - 1) // PSIZE
    print(f"  잡아바 전체 {total}건, {pages}쪽")
    rows = list(first)
    fails = 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(page, i): i for i in range(2, pages + 1)}
        for f in cf.as_completed(futs):
            try:
                rows.extend(f.result()[1])
            except Exception as e:
                fails += 1
                warn(f"{futs[f]}쪽 실패: {str(e)[:100]}")
    print(f"  읽은 행 {len(rows)}건 (실패 {fails}쪽)")
    if fails > max(3, pages // 10):
        warn("실패한 쪽이 많아 기존 파일을 유지합니다.")
        return 0
    out, seen = [], set()
    skipped = {"직무 아님": 0, "제외 직무": 0, "마감": 0, "잡코리아 원문": 0, "원문 주소 없음": 0, "중복": 0}
    for r in rows:
        title = (r.get("PBANC_CONT") or "").strip()
        field = r.get("RECRUT_FIELD_NM") or ""
        if not w24.JOB_RE.search(title):
            skipped["직무 아님"] += 1
            continue
        if w24.EXCLUDE_RE.search(title) or EXTRA_EXCLUDE_RE.search(title):
            skipped["제외 직무"] += 1
            continue
        dl = ymd(r.get("RCPT_END_DE"))
        if dl and dl < TODAY.isoformat():
            skipped["마감"] += 1
            continue
        url = (r.get("URL") or "").strip()
        if url.startswith("http://"):
            url = "https://" + url[7:]  # 고용24(work.go.kr)·잡아바 원문은 https로도 열림
        url = url if url.startswith("https://") else ""
        if not url:
            skipped["원문 주소 없음"] += 1
            continue
        if any(h in url for h in SKIP_HOSTS):
            skipped["잡코리아 원문"] += 1
            continue
        sname, sk = src_of(url)
        m = re.search(r"wantedAuthNo=([A-Za-z0-9]+)|seq=(\d+)|rec_idx=(\d+)", url)
        key = next((g for g in (m.groups() if m else ()) if g), "") or hashlib.sha1(url.encode()).hexdigest()[:12]
        jid = f"gg-{sk}-" + re.sub(r"[^a-z0-9]", "", key.lower())
        if jid in seen:
            skipped["중복"] += 1
            continue
        seen.add(jid)
        car, car_d = w24.career_of(r.get("CAREER_DIV"))
        emp, term = emp_of(r.get("PBANC_FORM_DIV"))
        city = (r.get("WORK_REGION_CONT") or "").strip()
        region = ("경기 " + city) if city and not city.startswith(("서울", "인천", "경기")) else (city or "경기")
        o = {
            "id": jid,
            "title": title,
            "company": (r.get("ENTRPRS_NM") or "").strip(),
            "region": region,
            "address": region,
            "job": w24.job_of(title),
            "career": car,
            "employment": emp,
            "company_type": "중소·기타",
            "industry": w24.industry_of(field + " " + title + " " + (r.get("ENTRPRS_NM") or "")),
            "deadline": dl or "채용 시",
            "posted": ymd(r.get("RCPT_BGNG_DE")) or TODAY.isoformat(),
            "source_url": url,
            "source_name": f"경기 잡아바({sname})",
            "origin": "jobaba",
            "career_detail": car_d,
            "education": w24.edu_of(r.get("ACDMCR_DIV")),
        }
        if r.get("SALARY_COND"):
            o["salary"] = str(r["SALARY_COND"])[:40]
        if term:
            o["term"] = term
        out.append(o)
    print("  잡아바 안전·보건 공고:", len(out), "건 / 뺀 공고:", ", ".join(f"{k} {v}" for k, v in skipped.items()))
    for o in sorted(out, key=lambda x: x["posted"], reverse=True)[:30]:
        print(f"    · {o['company']} | {o['title']} | {o['region']} | ~{o['deadline']} | {o['source_name']}")
    if not out and OUT.exists():
        warn("잡아바: 0건 — 기존 파일 유지")
        return 0
    OUT.write_text(json.dumps({"fetched": TODAY.isoformat(), "checked": TODAY.isoformat(),
                               "source": "경기도일자리재단 잡아바 채용정보(경기데이터드림 Open API, 상업적이용허용·콘텐츠변경허용)",
                               "items": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  ggjobs.json: {len(out)}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
