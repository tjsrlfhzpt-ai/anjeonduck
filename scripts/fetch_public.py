#!/usr/bin/env python3
"""공공데이터포털 공식 API → data/auto/*.json (빌드 직전에 실행).

수집 대상 (모두 공공데이터포털 이용허락 확인, 2026-09-30):
  1) 재정경제부_공공기관 채용정보 조회서비스      apis.data.go.kr/1051000/recruitment/list
     이용허락범위: 제한 없음 → 안전·보건 직무 공고만 골라 data/auto/pubjobs.json
  2) 문화체육관광부_정책브리핑_정책뉴스_API       apis.data.go.kr/1371000/policyNewsService2/policyNewsList2
     이용허락범위: 공공누리 제1유형(출처표시) → 산업안전 관련 기사 제목·부처·날짜·원문링크만 data/auto/news.json
  3) 한국산업안전보건공단_사고사망 게시판 정보      apis.data.go.kr/B552468/news_api02/getNews_api02 (callApiId=1040)
     이용허락범위: 제한 없음 → data/auto/accidents.json

원칙
- 인증키는 환경변수 DATA_GO_KR_KEY 로만 받는다(GitHub Secret). 페이지·저장소에 절대 쓰지 않는다.
- 키가 없거나 API가 실패하면 해당 파일을 만들지 않고(또는 기존 파일 유지) 경고만 남긴다 → 사이트는 빈 상태 안내를 보여 준다.
- 기사 본문·공고 본문은 옮기지 않는다. 목록 정보와 원문 링크만 저장한다.
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
KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
TODAY = dt.date.today()

# 안전·보건 직무로 보는 기준 (제목 또는 NCS 직무명)
JOB_RE = re.compile(r"산업안전|안전관리|안전보건|보건관리|산업보건|건설안전|안전\s*\(|안전직|안전담당|안전감독|HSE|EHS|환경안전|중대재해|위험물|소방안전|전기안전|가스안전|기계안전|화공안전")
# 정책뉴스 중 산업안전 관련 기사
NEWS_RE = re.compile(r"산업안전|산업재해|산재|중대재해|안전보건|노동안전|위험성평가|추락|끼임|질식|폭염|온열질환|한파|안전관리|작업중지|재해예방|사망사고")
NEWS_MINISTRY_HINT = ("고용노동부",)


def warn(msg):
    print("  경고:", msg, file=sys.stderr)


GATEWAY_ERR = {"SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "인증키 미등록(해당 API 활용신청 전이거나 승인 대기)",
               "SERVICE_ACCESS_DENIED_ERROR": "이 API에 대한 활용 승인 없음",
               "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "일일 호출 한도 초과",
               "UNREGISTERED_IP_ERROR": "등록되지 않은 IP",
               "SERVICE_KEY_IS_NULL": "인증키가 비어 있음",
               "INVALID_REQUEST_PARAMETER_ERROR": "요청 항목 오류"}


def gateway_check(raw):
    """공공데이터포털 게이트웨이 오류(<OpenAPI_ServiceResponse>)를 사람이 읽을 수 있는 메시지로."""
    if "OpenAPI_ServiceResponse" in raw or "returnAuthMsg" in raw:
        m = re.search(r"<errMsg>([^<]+)", raw) or re.search(r'"errMsg"\s*:\s*"([^"]+)"', raw) or re.search(r"<returnAuthMsg>([^<]+)", raw)
        code = m.group(1).strip() if m else ""
        msg = GATEWAY_ERR.get(code, code) or "사유 코드 없음"
        raise RuntimeError(f"공공데이터포털 거부: {msg} / 응답: {snippet(raw, 120)}")


def snippet(text, n=160):
    """오류 응답 본문 요약(키가 섞이지 않도록 serviceKey 값은 가린다)."""
    text = re.sub(r"serviceKey=[^&\s\"'<]+", "serviceKey=***", text)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()[:n]


def get(url, params, timeout=30):
    # serviceKey 는 공공데이터포털이 '인코딩된 키'를 그대로 요구하는 경우가 있어 따로 붙인다
    q = urllib.parse.urlencode(params)
    full = f"{url}?serviceKey={KEY if '%' in KEY else urllib.parse.quote(KEY, safe='')}&{q}"
    req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0 (anjeonduck-fetch/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        gateway_check(body)
        raise RuntimeError(f"HTTP {e.code} — 응답: {snippet(body) or '(본문 없음)'}") from None
    gateway_check(raw)
    return raw


def probe():
    """키 없이 한 번 호출해 이 서버(빌드 러너)에서 공공데이터포털 게이트웨이에 닿는지 확인.
    국내에서는 SERVICE_KEY_IS_NULL(XML)이 돌아오고, 해외 IP 차단이면 HTTP 403 등이 돌아온다."""
    url = "https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList2?startDate=20260101&endDate=20260102"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            body, code = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        body, code = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:
        print(f"  진단: 게이트웨이 연결 실패 — {type(e).__name__}: {e}")
        return False
    ok = "SERVICE_KEY_IS_NULL" in body
    print(f"  진단(키 없이 호출): HTTP {code} / {'게이트웨이 정상 응답' if ok else '게이트웨이 응답 아님 → 이 서버 IP가 차단됐을 가능성'} / {snippet(body, 120)}")
    return ok


def ymd(s):
    s = re.sub(r"\D", "", str(s or ""))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else ""


def save(name, payload, min_keep=0):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    n = len(payload["items"])
    if p.exists() and n < min_keep:
        warn(f"{name}: {n}건만 받아 기존 파일 유지")
        return
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  {name}: {n}건 저장")


# ------------------------------------------------------------ 1) 공공기관 채용
def fetch_jobs():
    url = "https://apis.data.go.kr/1051000/recruitment/list"
    items, page = [], 1
    while page <= 30:  # 100건 × 30쪽 = 최대 3,000건(진행 중 공고 전체보다 넉넉)
        raw = get(url, {"resultType": "json", "ongoingYn": "Y", "numOfRows": 100, "pageNo": page})
        d = json.loads(raw)
        if str(d.get("resultCode", "200")) not in ("200", "0", "00"):
            raise RuntimeError(f"resultCode={d.get('resultCode')} {d.get('resultMsg')}")
        rows = d.get("result") or []
        if isinstance(rows, dict):
            rows = [rows]
        items += rows
        total = int(d.get("totalCount") or 0)
        if not rows or len(items) >= total:
            break
        page += 1
    out = []
    for r in items:
        r = r.get("item", r) if isinstance(r, dict) else {}
        title = (r.get("recrutPbancTtl") or "").strip()
        ncs = (r.get("ncsCdNmLst") or "").strip()
        if not title or not JOB_RE.search(title + " " + ncs):
            continue
        sn = str(r.get("recrutPblntSn") or "").strip()
        src = (r.get("srcUrl") or "").strip()
        link = src if src.startswith("https://") else (f"https://job.alio.go.kr/recruitview.do?idx={sn}" if sn else "")
        if not link:
            continue
        out.append({
            "id": f"alio-{sn}",
            "company": (r.get("instNm") or "").strip(),
            "title": title,
            "region": (r.get("workRgnNmLst") or "").replace(",", "·"),
            "ctype": (r.get("hireTypeNmLst") or "").replace(",", "·"),
            "career": (r.get("recrutSeNm") or "").strip(),
            "job": "안전관리" if re.search(r"안전", title + ncs) else "보건관리",
            "ncs": ncs,
            "headcount": r.get("recrutNope"),
            "posted": ymd(r.get("pbancBgngYmd")),
            "deadline": ymd(r.get("pbancEndYmd")) or "상시",
            "source_url": link,
            "source_name": "공공기관 채용정보시스템(ALIO)",
            "origin": "alio",
        })
    save("pubjobs.json", {"fetched": TODAY.isoformat(), "source": "재정경제부_공공기관 채용정보 조회서비스(공공데이터포털)",
                          "license": "이용허락범위 제한 없음", "items": out})


# ------------------------------------------------------------ 2) 정책뉴스
def fetch_news(days=30):
    url = "https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList2"
    seen, out = set(), []
    end = TODAY
    while (TODAY - end).days < days:
        start = end - dt.timedelta(days=2)  # API 제한: 조회 기간 3일 이내
        raw = get(url, {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d")})
        root = ET.fromstring(raw)
        code = (root.findtext(".//resultCode") or "").strip()
        if code and code not in ("0", "00", "200"):
            raise RuntimeError(f"resultCode={code} {root.findtext('.//resultMsg')}")
        for it in root.iter("NewsItem"):
            g = lambda k: (it.findtext(k) or "").strip()
            nid, title, minister, kogl = g("NewsItemId"), g("Title"), g("MinisterCode"), g("KoglType")
            if not nid or nid in seen:
                continue
            if not re.search(r"[1-4]", kogl):  # 공공누리 표시 없는 기사는 싣지 않음
                continue
            if not (NEWS_RE.search(title + " " + g("SubTitle1")) and (any(m in minister for m in NEWS_MINISTRY_HINT) or NEWS_RE.search(title))):
                continue
            link = g("OriginalUrl")
            if not link.startswith("https://"):
                link = link.replace("http://", "https://", 1) if link.startswith("http://www.korea.kr") else ""
            if not link:
                continue
            seen.add(nid)
            d = re.match(r"(\d{2})/(\d{2})/(\d{4})", g("ApproveDate"))
            out.append({"id": nid, "title": title, "sub": g("SubTitle1"), "ministry": minister,
                        "date": f"{d.group(3)}-{d.group(1)}-{d.group(2)}" if d else "",
                        "kogl": re.search(r"[1-4]", kogl).group(0), "url": link})
        end = start - dt.timedelta(days=1)
    out.sort(key=lambda x: x["date"], reverse=True)
    save("news.json", {"fetched": TODAY.isoformat(), "source": "문화체육관광부_정책브리핑_정책뉴스_API(공공데이터포털)",
                       "license": "공공누리 제1유형(출처표시) — 기사별 유형은 kogl 항목", "items": out})


# ------------------------------------------------------------ 3) 공단 사고사망 속보
def fetch_accidents(rows=60):
    url = "https://apis.data.go.kr/B552468/news_api02/getNews_api02"
    raw = get(url, {"callApiId": "1040", "pageNo": 1, "numOfRows": rows})
    root = ET.fromstring(raw)
    code = (root.findtext(".//resultCode") or "").strip()
    if code and code not in ("0", "00", "200"):
        raise RuntimeError(f"resultCode={code} {root.findtext('.//resultMsg')}")
    out = []
    for it in root.iter("item"):
        g = lambda k: (it.findtext(k) or "").strip()
        text = re.sub(r"\s+", " ", g("keyword"))
        if not text:
            continue
        out.append({"id": g("arno"), "text": text, "image": g("contents") if g("contents").startswith("https://") else ""})
    save("accidents.json", {"fetched": TODAY.isoformat(), "source": "한국산업안전보건공단_사고사망 게시판 정보 조회서비스(공공데이터포털)",
                            "license": "이용허락범위 제한 없음", "items": out})


def main():
    if not KEY:
        print("  DATA_GO_KR_KEY 없음 — 공공 API 수집을 건너뜁니다(기존 data/auto 파일이 있으면 그대로 사용).")
        return 0
    probe()
    for name, fn in (("공공기관 채용", fetch_jobs), ("정책뉴스", fetch_news), ("사고사망 속보", fetch_accidents)):
        try:
            fn()
        except Exception as e:  # 한 API 실패가 다른 수집·빌드를 막지 않게
            warn(f"{name} 수집 실패: {type(e).__name__}: {str(e)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
