"""게시 전 검증 관문.

1단계(규칙 대조, AI 없이): 조문 번호·수치·날짜가 근거 묶음에 있는지, 금지 표현, 주소 삽입, 분량·형식, 중복.
2단계(AI 검증자): 글의 사실 주장을 하나씩 근거 묶음과 대조. 글을 쓴 호출과 따로 부른다.
둘 중 하나라도 걸리면 한 번 고쳐 쓰게 하고, 그래도 걸리면 게시하지 않고 보류한다.
"""
import re, difflib, importlib.util
from .common import cfg, now, ROOT
from . import evidence as ev, llm, compose

UNITS = r"(?:시간|개월|만원|억원|천원|퍼센트|미터|ppm|mm|cm|kg|㎡|℃|분|일|주|월|년|명|인|원|%|m|톤|t|도|회|차|건|곳|배|종|장|세|호)"
NUM = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?) ?(만|억|천)? ?(" + UNITS + r")(?![A-Za-z])")
REF = re.compile(r"제\s?\d+\s?조(?:의\s?\d+)?|별표\s?\d+(?:의\s?\d+)?")
DATE = re.compile(r"(20\d\d|19\d\d)\s*[.년\-/]\s*(\d{1,2})\s*[.월\-/]\s*(\d{1,2})\s*[.일]?")
YM = re.compile(r"(20\d\d|19\d\d)\s*[.년\-/]\s*(\d{1,2})\s*월?")
URL = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|co\.kr|kr|net|org|go\.kr)\b", re.I)


def site_banned():
    """사이트 감사(scripts/audit.py)가 쓰는 금지 표현 목록을 같이 쓴다."""
    try:
        spec = importlib.util.spec_from_file_location("sp_audit", ROOT / "scripts" / "audit.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return [w for w, ok in m.BANNED if ok is None]
    except Exception:
        return ["무조건", "법적으로 문제없", "이것만 하면 됩니다", "법적 의무를 충족합니다"]


def _norm(s):
    return re.sub(r"[\s,]", "", s)


def _dates(text):
    return {(int(y), int(m), int(d)) for y, m, d in DATE.findall(text)}


def _refs(text):
    return {re.sub(r"\s", "", r) for r in REF.findall(text)}


def rule_check(item, topic, ledger_titles=()):
    """규칙 대조. 걸린 점을 사람이 읽을 문장 목록으로 돌려준다(빈 목록이면 통과)."""
    c = cfg()
    evid = ev.evidence_text(topic, 10 ** 6) + "\n" + " ".join(s["label"] for s in topic["sources"]) + "\n" + topic["title"]
    evid_n, evid_refs, evid_dates = _norm(evid), _refs(evid), _dates(evid)
    evid_ym = {(int(y), int(m)) for y, m in YM.findall(evid)} | {(y, m) for y, m, _ in evid_dates}
    t = now()
    evid_dates.add((t.year, t.month, t.day)); evid_ym.add((t.year, t.month))
    years = set(re.findall(r"(?:19|20)\d\d", evid)) | {str(t.year)}
    evid_n += f"|{t.month}월|{t.day}일|{t.year}년"
    texts = compose.flat_text(item)
    bad = []
    banned = site_banned() + c["banned_extra"]
    for plat, text in texts.items():
        for r in sorted(_refs(text) - evid_refs):
            bad.append(f"[{plat}] 근거 묶음에 없는 조문·별표 번호: {r}")
        for d in sorted(_dates(text) - evid_dates):
            bad.append(f"[{plat}] 근거 묶음에 없는 날짜: {d[0]}-{d[1]:02d}-{d[2]:02d}")
        rest = DATE.sub(" ", text)
        for y, m in YM.findall(rest):
            if (int(y), int(m)) not in evid_ym:
                bad.append(f"[{plat}] 근거 묶음에 없는 연월: {y}년 {m}월")
        rest = YM.sub(" ", rest)
        for num, mul, unit in NUM.findall(rest):
            token = _norm(num + (mul or "") + unit)
            if unit == "년" and re.fullmatch(r"(?:19|20)\d\d", num) and num in years:
                continue
            if token in evid_n:
                continue
            bad.append(f"[{plat}] 근거 묶음에 없는 수치: {num}{mul or ''}{unit}")
        for w in banned:
            if w in text:
                bad.append(f"[{plat}] 금지 표현: {w}")
        if URL.search(text):
            bad.append(f"[{plat}] AI 가 쓴 글에 인터넷 주소가 들어 있음(주소는 시스템이 붙여야 함)")
        if re.search(r"\bAI\b|인공지능", text) and "API 키" not in text and topic["id"] in ("tool:ai", "tool:law-ai"):
            bad.append(f"[{plat}] AI 기능을 소개하면서 '본인 Google Gemini API 키 필요' 조건이 빠짐")
    r = item["raw"]
    if "blog" in r:
        b = r["blog"]
        n = len(texts["blog"])
        if n < 900:
            bad.append(f"[blog] 본문이 너무 짧음({n}자)")
        if not (10 <= len(b["title"]) <= 60):
            bad.append(f"[blog] 제목 길이 {len(b['title'])}자(10~60자여야 함)")
        if len(b["law_basis"]) < 1 or len(b["checklist"]) < 3 or len(b["how_to"]) < 3:
            bad.append("[blog] 법령 근거·체크리스트·적용 순서 중 빠진 것이 있음")
        for old in ledger_titles:
            if difflib.SequenceMatcher(None, b["title"], old).ratio() > 0.85:
                bad.append(f"[blog] 이전 글과 제목이 거의 같음: {old}")
                break
    if "instagram" in r:
        g = r["instagram"]
        if not (3 <= len(g["cards"]) <= 6):
            bad.append(f"[instagram] 본문 카드 {len(g['cards'])}장(3~6장이어야 전체 5~8장)")
        if len(g["cover_title"]) > 30:
            bad.append("[instagram] 표지 제목이 30자를 넘음")
        for i, x in enumerate(g["cards"]):
            if len(x["heading"]) > 24 or any(len(l) > 40 for l in x["lines"]) or not (1 <= len(x["lines"]) <= 4):
                bad.append(f"[instagram] {i + 2}번 카드 글이 카드에 들어가지 않는 길이")
    if "facebook" in r and not (120 <= len(texts["facebook"]) <= 900):
        bad.append(f"[facebook] 본문 길이 {len(texts['facebook'])}자(120~900자여야 함)")
    keys = list(texts)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b2 = texts[keys[i]], texts[keys[j]]
            if difflib.SequenceMatcher(None, a[:1500], b2[:1500]).ratio() > 0.7:
                bad.append(f"[{keys[i]}·{keys[j]}] 두 플랫폼 글이 거의 같음(그대로 복제 금지)")
    # 링크 대상이 실제 있는 페이지인지
    routes = ev.valid_routes()
    for tl in item.get("tools", []):
        if tl["path"] not in routes:
            bad.append(f"[링크] 사이트에 없는 페이지: {tl['path']}")
    hosts = c["allowed_link_hosts"]
    for s in item.get("sources", []):
        if s.get("url"):
            h = re.sub(r"^https?://", "", s["url"]).split("/")[0].lower()
            if h not in hosts:
                bad.append(f"[출처] 공식 출처 목록에 없는 주소: {h}")
    if topic["risk"] == "legal" and not topic["sources"]:
        bad.append("[출처] 법령·사고 관련 글인데 공식 출처가 없음")
    return bad


def ai_check(item, topic):
    """AI 검증자. (통과 여부, 걸린 점 목록)"""
    texts = compose.flat_text(item)
    body = "[근거 묶음]\n" + ev.evidence_text(topic) + "\n\n[검증할 글]\n" + "\n\n".join(f"<{k}>\n{v}" for k, v in texts.items())
    vm = cfg()["openai"].get("verify_model") or None
    r = llm.call("verify", body, mock=lambda: {"claims": [], "problems": [], "overall": "pass"}, model=vm)
    bad = [f"근거 없는 주장: {c['claim']} — {c['reason']}" for c in r.get("claims", []) if not c.get("supported")]
    bad += [f"검증자 지적: {p}" for p in r.get("problems", [])]
    if r.get("overall") == "fail" and not bad:
        bad.append("검증자가 불합격으로 판정(사유 미기재)")
    return (not bad), bad, len(r.get("claims", []))


def run(item, topic, ledger_titles=()):
    """검증 결과를 item['verification'] 에 적고 게시 가능 여부를 돌려준다."""
    rule = rule_check(item, topic, ledger_titles)
    ok_ai, ai_bad, n_claims = (True, [], 0)
    if not rule:                                    # 규칙에서 이미 걸렸으면 AI 검증 비용을 쓰지 않는다
        ok_ai, ai_bad, n_claims = ai_check(item, topic)
    item["verification"] = {"rule_issues": rule, "ai_issues": ai_bad, "claims_checked": n_claims, "passed": not rule and ok_ai,
                            "evidence_sources": [s["label"] for s in topic["sources"]]}
    return item["verification"]["passed"]
