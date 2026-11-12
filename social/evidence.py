"""주제 풀과 근거 묶음.

콘텐츠의 모든 사실은 이 저장소의 검증된 데이터(data/*.json — 국가법령정보센터 조문 원문, 고용노동부 질의회시,
중대재해 사고백서, 시행규칙 별표 등)에서만 가져온다. 글을 쓰는 AI 는 여기서 만든 '근거 묶음' 밖의 사실을 쓸 수 없고,
verify.py 가 조문 번호·수치를 근거 묶음과 대조한다.

주제 하나 = {id, cat, kind, risk, title, keyword, facts[], sources[], tools[], score, hold_reason}
"""
import re, random, datetime
from .common import ROOT, load, cfg, now

D = ROOT / "data"
LAW_KEYS = {"act": "산업안전보건법", "yeong": "산업안전보건법 시행령", "rule": "산업안전보건법 시행규칙",
            "krule": "산업안전보건기준에 관한 규칙", "sapa": "중대재해 처벌 등에 관한 법률", "sapa_dec": "중대재해 처벌 등에 관한 법률 시행령"}
CATS = ["법령", "중처법", "위험성평가", "서류", "재해예방", "보건", "실무", "도구", "소식", "커뮤니티", "질의회시"]
CAT_LABEL = {"법령": "산업안전보건법", "중처법": "중대재해처벌법", "위험성평가": "위험성평가·TBM", "서류": "안전보건 서류",
             "재해예방": "산업재해 예방", "보건": "보건관리", "실무": "실무 노하우", "도구": "무료 도구", "소식": "안전보건 소식",
             "커뮤니티": "실무자 커뮤니티", "질의회시": "고용노동부 질의회시"}
CAT_SLUG = {"법령": "osh_act", "중처법": "sapa", "위험성평가": "risk_assessment", "서류": "documents", "재해예방": "accident_prevention",
            "보건": "health", "실무": "practice", "도구": "free_tools", "소식": "news", "커뮤니티": "community", "질의회시": "moel_qa"}
FREQ = {"daily": "매일", "weekly": "매주", "monthly": "매월", "bimonthly": "2개월마다", "quarterly": "분기마다",
        "semiannual": "반기마다", "yearly": "매년", "every2": "2일마다"}

_cache = {}


def _d(name):
    if name not in _cache:
        _cache[name] = load(D / name, {})
    return _cache[name]


def lawtext(key):
    return _d(f"lawtext/{key}.json")


def article(key, jo):
    """조문 원문 한 개. jo 는 '제36조' 또는 '제619조의2'."""
    for a in lawtext(key).get("articles", []):
        if a.get("jo") == jo:
            return a
    return None


def jo_anchor(jo):
    m = re.match(r"제(\d+)조(?:의(\d+))?", jo)
    return ("#j" + m.group(1) + ("-" + m.group(2) if m.group(2) else "")) if m else ""


def anchor_jo(anchor):
    m = re.match(r"#?j(\d+)(?:-(\d+))?$", anchor)
    return f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "") if m else ""


def art_fact(key, jo, limit=1400):
    a = article(key, jo)
    if not a:
        return None, None
    lt = lawtext(key)
    text = re.sub(r"\s+", " ", a["text"])
    if len(text) > limit:
        text = text[:limit] + " …(이하 생략, 원문 확인)"
    fact = f"[조문 원문] {lt['law']} {jo}({a.get('title', '')}): {text}"
    src = {"label": f"{lt['law']} {jo} — {lt['version']}, 시행 {lt['effective']} (국가법령정보센터, 원문 확인 {lt['checked']})",
           "url": lt["url"], "site": f"laws/{key}/{jo_anchor(jo)}"}
    return fact, src


def site_tools():
    return {t["id"]: t for t in _d("../config/site.json").get("free_tools", [])}


def tool_ref(tid):
    t = site_tools().get(tid)
    return {"path": f"tools/{tid}/", "name": t["name"], "kind": "writer" if t.get("cat") == "작성기" else "lookup"} if t else None


def form_ref(fid):
    for f in _d("forms.json").get("forms", []):
        if f["id"] == fid:
            return {"path": f"tools/forms/{fid}/", "name": f.get("short") or f["title"], "kind": "writer"}
    return None


STATIC_ROUTES = ["", "tools/", "tools/forms/", "laws/", "laws/qa/", "laws/bills/", "laws/act/", "laws/yeong/", "laws/rule/", "laws/krule/",
                 "laws/sapa/", "laws/sapa_dec/", "board/", "board/?b=free", "board/?b=qna", "board/?b=job", "jobs/", "resources/", "resources/files/",
                 "brief/", "videos/", "search/"]


def valid_routes():
    r = set(STATIC_ROUTES)
    r |= {f"tools/{i}/" for i in site_tools()}
    r |= {f"tools/forms/{f['id']}/" for f in _d("forms.json").get("forms", [])}
    return r


def _season(text):
    """계절 주제는 제철이 아닐 때 뒤로 미룬다."""
    m = now().month
    if re.search(r"폭염|온열|체감온도", text) and m not in (5, 6, 7, 8, 9):
        return -5.0
    if re.search(r"한랭|한파|동절기|동상", text) and m not in (11, 12, 1, 2):
        return -5.0
    return 0.0


def _mk(tid, cat, kind, risk, title, keyword, facts, sources, tools, score=0.0, hold=""):
    if kind != "monthly":
        score += _season(title + keyword)
    if re.search(r"위험성평가|TBM|작업 전 안전점검", title + keyword) and cat in ("법령", "실무", "서류", "질의회시"):
        cat = "위험성평가"
    tools = [t for t in tools if t]
    return {"id": tid, "cat": cat, "kind": kind, "risk": risk, "title": title, "keyword": keyword,
            "facts": [f for f in facts if f], "sources": [s for s in sources if s], "tools": tools[:3], "score": score, "hold_reason": hold}


# ---------------------------------------------------------------- 주제 만들기
def t_tools():
    out = []
    ai_note = "AI 기능은 이용자 본인의 Google Gemini API 키가 있어야 동작합니다. 키는 그 브라우저에만 저장되고 세이프플럼 서버로 보내지 않습니다."
    for tid, t in site_tools().items():
        facts = [f"도구 이름: {t['name']}", f"기능 설명(사이트 표기 그대로): {t['desc']}", f"관련 법령 표기: {t.get('law', '')}",
                 "이용 조건: 회원가입 없이 무료로 쓸 수 있고, 입력한 문서 내용은 서버로 보내지 않고 이용자 브라우저에서 처리합니다."]
        if tid in ("ai", "law-ai"):
            facts.append(ai_note)
        out.append(_mk(f"tool:{tid}", "도구", "tool", "general", t["name"], t.get("short") or t["name"], facts,
                       [{"label": f"세이프플럼 {t['name']}", "url": "", "site": f"tools/{tid}/"}], [tool_ref(tid)]))
    return out


def t_forms():
    out = []
    for f in _d("forms.json").get("forms", []):
        facts = [f"서식 이름: {f['title']}", f"설명(사이트 표기 그대로): {f.get('desc', '')}", f"관련 법령 표기: {f.get('law', '')}",
                 "세이프플럼 자체 제공 양식이며 사업장 상황에 맞게 고쳐 쓰는 용도입니다. 회원가입 없이 무료로 작성·인쇄할 수 있습니다."]
        out.append(_mk(f"form:{f['id']}", "서류", "form", "general", f["title"], f.get("short") or f["title"], facts,
                       [{"label": f"세이프플럼 서식 작성기 — {f['title']}", "url": "", "site": f"tools/forms/{f['id']}/"}], [form_ref(f["id"])]))
    return out


def t_schedule():
    out, sc = [], _d("schedule.json")
    for t in sc.get("tasks", []):
        if t.get("status") == "check":           # 원문 확인이 안 끝난 업무는 쓰지 않는다
            continue
        facts = [f"업무: {t['title']}", f"주기: {FREQ.get(t['freq'], t['freq'])} — 구분: {t.get('klass', '')}", f"근거: {t['basis']}", f"설명: {t.get('memo', '')}"]
        srcs = []
        for l in t.get("links", []):
            m = re.match(r"laws/(\w+)/(#j[\d-]+)", l["href"])
            if m:
                f, s = art_fact(m.group(1), anchor_jo(m.group(2)))
                facts.append(f); srcs.append(s)
        if t.get("status") == "practice":
            facts.append("주의: 이 업무의 주기는 법정 주기가 아니라 권장 운영입니다. 글에서 '법정 의무 주기'라고 쓰면 안 됩니다.")
        cat = "중처법" if "중대재해" in t["basis"] else ("법령" if t.get("klass") == "법정 주기" else "실무")
        out.append(_mk(f"sched:{t['key']}", cat, "schedule", "legal", t["title"], t["title"], facts, srcs,
                       [tool_ref(t.get("tool") or ""), tool_ref("schedule")]))
    return out


def t_retention():
    r, out = _d("retention.json"), []
    by = {}
    for who, doc, period, basis in r.get("retention", []):
        by.setdefault(who, []).append(f"{doc} — 보존 {period} ({basis})")
    for who, rows in by.items():
        facts = [f"보존 의무자: {who}"] + rows + [f"참고: {n}" for n in r.get("notes", [])]
        f, s = art_fact("act", "제164조", 2400)
        out.append(_mk(f"retention:{who}", "서류", "retention", "legal", f"{who}가 보존해야 하는 안전보건 서류와 보존기간", "서류 보존기간",
                       facts + [f], [s], [tool_ref("retention"), tool_ref("docmap")]))
    return out


def t_edu():
    e, out = _d("edu_hours.json"), []
    for s in e.get("sections", []):
        rows = [(f"{x['target']} — 신규교육 {x['new']}, 보수교육 {x['re']}" if "new" in x else " / ".join(str(v) for v in x.values() if v)) for x in s.get("rows", [])][:24]
        out.append(_mk(f"edu:{s['id']}", "법령", "edu", "legal", re.sub(r"^\d+\.\s*", "", s["title"]) + " 교육시간", "법정 안전보건교육 시간",
                       [f"근거: {s.get('basis', '')}", f"출처: {e['source']}"] + rows,
                       [{"label": f"{e['source']} (원문 확인 {e['checked']})", "url": lawtext('rule').get("url", ""), "site": "tools/edu-hours/"}],
                       [tool_ref("edu-hours"), tool_ref("edu-log")]))
    return out


def t_articles():
    """조문 해설 주제 — 중처법·시행령 전체, 산안법은 실무에서 자주 찾는 조문."""
    out = []
    act_pick = ["제14조", "제15조", "제16조", "제17조", "제18조", "제19조", "제24조", "제25조", "제29조", "제31조", "제32조", "제36조", "제37조",
                "제38조", "제39조", "제41조", "제51조", "제52조", "제54조", "제57조", "제62조", "제63조", "제64조", "제65조", "제72조", "제80조",
                "제93조", "제114조", "제115조", "제125조", "제129조", "제130조", "제164조"]
    tools_by = {"제36조": ["risk", "tbm"], "제29조": ["edu-log", "edu-hours"], "제24조": ["committee"], "제64조": ["council", "patrol"],
                "제72조": ["safety-cost"], "제114조": ["msds"], "제164조": ["retention"], "제93조": ["inspect"], "제57조": ["retention"]}
    for key, picks, cat in (("act", act_pick, "법령"), ("sapa", None, "중처법"), ("sapa_dec", None, "중처법")):
        for a in lawtext(key).get("articles", []):
            if picks is not None and a["jo"] not in picks:
                continue
            if len(a.get("text", "")) < 150 or not a.get("title"):
                continue
            f, s = art_fact(key, a["jo"], 2600)
            tl = [tool_ref(x) for x in tools_by.get(a["jo"], [])] if key == "act" else [tool_ref("law-register"), tool_ref("selection")]
            out.append(_mk(f"art:{key}:{a['jo']}", cat, "article", "legal", f"{LAW_KEYS[key]} {a['jo']} {a['title']}", a["title"], [f], [s],
                           tl + [tool_ref("duties")]))
    return out


def t_qa():
    g, out = _d("gov_qa.json"), []
    meta = g.get("meta", {})
    for it in g.get("items", []):
        a = it.get("a", "")
        if not (250 <= len(a) <= 2600) or len(it.get("q", "")) > 2200:
            continue
        tools = [{"path": p, "name": n, "kind": "lookup"} for p, n in meta.get("tools", {}).get(it["c"], [])]
        tools = [t for t in tools if t["path"] in valid_routes()]
        yr = int(it["d"][:4]) if it.get("d", "")[:4].isdigit() else 2000
        facts = [f"질의 제목: {it['t']}", f"회신일: {it['d']}", f"분류: {it['c']}", f"관련 조문 표기: {it.get('l', '')}",
                 f"[질의 원문] {it['q']}", f"[고용노동부 회신 원문] {a}",
                 "주의: 질의회시는 개별 사안에 대한 행정해석입니다. 사업장 조건이 다르면 결론이 달라질 수 있고, 회신 뒤 법령이 바뀌었을 수 있습니다."]
        out.append(_mk(f"qa:{it['id']}", "질의회시", "qa", "legal", it["t"], it["c"], facts,
                       [{"label": f"고용노동부 질의회시({it['d']}) — 국가법령정보센터 중앙부처 1차 해석, 공공누리 제1유형",
                         "url": meta.get("item_url", "").replace("{id}", str(it["id"])), "site": "laws/qa/"}], tools, score=(yr - 2015) / 10))
    return out


def t_fatal():
    f, out = _d("fatal_cases.json"), []
    meta = f.get("meta", {})
    by = {}
    for it in f.get("items", []):
        if it.get("m") and len(it.get("t", "")) > 20:
            by.setdefault((it["k"], it["g"]), []).append(it)
    tool_by = {"끼임": ["loto", "tbm"], "떨어짐": ["risk", "permit"], "감전": ["permit", "loto"], "화재·폭발": ["permit", "msds"], "질식": ["confined", "permit"]}
    for (k, g), items in by.items():
        items.sort(key=lambda x: x["d"], reverse=True)
        for p in range(min(len(items) // 3, 30)):
            chunk = items[p * 3:p * 3 + 3]
            facts = [f"재해 유형: {k} / 업종: {g}"]
            for c in chunk:
                facts.append(f"[사례] {c['d'][:7]} {c['r']} {c.get('s', '')} — {c['t']} (사망 {c.get('dead', 1)}명) / 백서의 예방대책: " + "; ".join(c["m"]))
            facts += [f"출처: {meta.get('source', '')}", f"주의: {meta.get('note', '')}",
                      "사례에 나온 회사를 추정하거나 사고 원인을 단정하지 않습니다. 사례에 없는 통계 수치를 만들지 않습니다."]
            out.append(_mk(f"fatal:{k}:{g}:{p}", "재해예방", "fatal", "legal", f"{g}업 {k} 사망사고 사례와 예방대책", f"{k} 재해 예방", facts,
                           [{"label": "고용노동부 「중대재해 사고백서」 부록 사망사고 일람(2023~2025년 발간)", "url": "", "site": "tools/fatal-cases/"}],
                           [tool_ref(x) for x in tool_by.get(k, ["risk", "tbm"])] + [tool_ref("fatal-cases")], score=0.3 if p < 3 else 0))
    return out


def t_search_topics():
    out = []
    health = ("근골격", "온열", "폭염", "한랭", "MSDS", "화학", "건강", "소음", "분진", "밀폐")
    for t in _d("search_topics.json").get("topics", []):
        facts, srcs = [f"주제: {t['key']} — {t.get('desc', '')}"], []
        for key, jo in t.get("law", [])[:5]:
            f, s = art_fact(key, jo, 1100)
            facts.append(f); srcs.append(s)
        tools = [tool_ref(i) if k == "tool" else form_ref(i) for k, i in t.get("go", [])]
        cat = "보건" if any(h in t["key"] + " ".join(t.get("syn", [])) for h in health) else "재해예방"
        out.append(_mk(f"topic:{t['key']}", cat, "lawtopic", "legal", f"{t['key']} — 법에서 정한 조치와 실무", t["key"], facts, srcs, tools, score=0.4))
    return out


def t_monthly():
    e, out = _d("edu_monthly.json"), []
    m_now = now().month
    for m in e.get("months", []):
        facts = [f"{m['m']}월 교육 주제: {m['title']}", f"이 달에 다루는 이유: {m.get('why', '')}"]
        for s in m.get("sec", []):
            facts.append(f"[{s.get('h', '')}] " + " / ".join(s.get("b", [])))
        if m.get("law"):
            facts.append("관련 법령 표기: " + (m["law"] if isinstance(m["law"], str) else " · ".join(map(str, m["law"]))))
        facts.append(f"출처: {e.get('source', '')}")
        cat = "보건" if re.search(r"한랭|한파|폭염|온열|건강|질환|스트레스|근골격", m["title"]) else "재해예방"
        out.append(_mk(f"monthly:{m['m']}", cat, "monthly", "legal", m["title"], m.get("short", m["title"]), facts,
                       [{"label": f"세이프플럼 월별 정기 안전보건교육 자료 — {e.get('source', '')}", "url": "", "site": "tools/edu-monthly/"}],
                       [tool_ref("edu-monthly"), tool_ref("edu-log")], score=2.0 if m["m"] == m_now else -5.0))
    return out


def t_rules():
    w, out = _d("work_rules.json"), []
    src = w.get("source", {})
    for it in w.get("items", []):
        if len(it.get("rules", [])) < 5:
            continue
        out.append(_mk(f"rules:{it['id']}", "재해예방", "rules", "general", f"{it['title']} — 현장 안전수칙", it["title"],
                       [f"분야: {it.get('cat', '')}", "안전수칙 예시(사업장에 맞게 고쳐 쓰는 예시 문구):"] + [f"- {r}" for r in it["rules"][:14]]
                       + [f"출처: {src.get('org', '')} 「{src.get('title', '')}」"],
                       [{"label": f"{src.get('org', '')} 「{src.get('title', '')}」", "url": "", "site": "tools/rule-sign/"}],
                       [tool_ref("rule-sign"), tool_ref("top-rules")]))
    return out


def _age(datestr):
    try:
        return (now().date() - datetime.date.fromisoformat(str(datestr)[:10])).days
    except ValueError:
        return 9999


def t_news():
    out = []
    for u in _d("laws.json").get("updates", []):
        age = _age(u.get("date"))
        facts = [f"법령: {u['law']} — {u['kind']}", f"공포·발표일: {u['date']}", f"시행일: {u.get('effective', '')}", f"제목: {u['title']}",
                 f"요약: {u.get('summary', '')}", f"실무 영향: {u.get('practical_impact', '')}",
                 "발표일(공포일)과 시행일을 반드시 구분해서 씁니다."]
        hold = "개정 소식에 '확인 필요' 표시가 남아 있음" if "확인 필요" in str(u.get("verify", "")) else ""
        out.append(_mk(f"law:{u['id']}", "소식", "lawupdate", "legal", u["title"], f"{u['law']} 개정", facts,
                       [{"label": f"{u.get('source_name', '국가법령정보센터')} (확인 {u.get('checked', '')})", "url": u.get("source_url", ""), "site": "laws/#updates"}],
                       [tool_ref("law-register"), tool_ref("schedule")], score=3.0 if age <= 14 else (0.5 if age <= 60 else -1), hold=hold))
    for p in _d("bills.json").get("posts", []):
        age = _age(p.get("date"))
        facts = [f"단계: {p['stage']} ({p['date']})", f"제목: {p['title']}", f"요지: {p.get('lead', '')}", f"시행: {p.get('effective', '')}", f"대상 법령: {p.get('law', '')}",
                 "바뀌기 전: " + " / ".join(p.get("before", [])), "바뀐 뒤: " + " / ".join(p.get("after", [])), f"개정 이유: {p.get('why', '')}",
                 "핵심: " + " / ".join(p.get("points", [])), "사업장이 준비할 일: " + " / ".join(p.get("todo", []))]
        facts += [f"[자주 묻는 질문] {q} → {a}" for q, a in p.get("faq", [])[:4]]
        facts.append("국회 통과·입법예고 단계의 내용은 확정된 현행 법령이 아닙니다. 단계와 시행 시점을 그대로 밝혀야 합니다.")
        out.append(_mk(f"bill:{p['slug']}", "소식", "bill", "legal", p["title"], "산업안전보건법 개정", facts,
                       [{"label": n, "url": u, "site": f"laws/bills/"} for n, u in p.get("sources", [])[:3]],
                       [{"path": pth, "name": nm, "kind": "writer"} for nm, pth in p.get("tools", []) if pth in valid_routes()],
                       score=3.0 if age <= 14 else (0.8 if age <= 90 else -1)))
    for fp in sorted((D / "briefs").glob("*.json"), reverse=True)[:4]:
        b = load(fp, {})
        for i, it in enumerate(b.get("items", [])):
            age = _age(it.get("date"))
            facts = [f"발표 기관: {it.get('agency', '')}", f"발표일: {it.get('date', '')}", f"공식 제목: {it.get('official_title', '')}", f"요약: {it.get('summary', '')}",
                     f"시행·적용: {it.get('effective', '')}", f"실무 포인트: {it.get('point', '')}", "발표일과 시행일을 구분해서 씁니다. 요약에 없는 수치를 쓰지 않습니다."]
            out.append(_mk(f"brief:{b.get('date')}:{i}", "소식", "brief", "legal", it.get("title", ""), it.get("cat", "소식"), facts,
                           [{"label": s.get("name", ""), "url": s.get("url", ""), "site": "brief/"} for s in it.get("sources", [])[:2]], [tool_ref("schedule")],
                           score=3.5 if age <= 7 else (1.0 if age <= 21 else -2),
                           hold="브리핑이 아직 운영자 검토 전(review: pending)" if b.get("review") == "pending" else ""))
    return out


COMMUNITY = [
    ("첫 출근한 안전관리자, 첫 주에 무엇부터 했나요?", "신입 안전관리자", ["first-job", "schedule"]),
    ("위험성평가, 근로자 참여는 어떻게 받고 계신가요?", "위험성평가 근로자 참여", ["risk", "tbm"]),
    ("TBM, 형식적으로 끝나지 않게 하는 우리 현장 방법", "TBM 운영", ["tbm"]),
    ("산업안전보건위원회 안건, 어떻게 모으시나요?", "산업안전보건위원회 안건", ["committee"]),
    ("협력업체 순회점검·합동점검, 지적사항 관리는 어떻게 하시나요?", "도급 순회점검", ["patrol", "joint", "improve"]),
    ("안전보건교육 시간 채우기, 현장에서 쓰는 방법", "안전보건교육 운영", ["edu-log", "edu-hours"]),
    ("안전·보건관리자 이직 준비, 무엇을 보고 고르시나요?", "안전관리자 채용", []),
    ("감독 나오기 전 서류 점검, 무엇부터 보시나요?", "감독 대비 서류", ["docmap", "retention"]),
]


def t_community():
    out = []
    feat = ["세이프플럼 게시판에는 커뮤니티(자유), 자료 공유, Q&A, 회원이 직접 올리는 채용공고 게시판이 있습니다.",
            "가입은 이메일로 하며, 글을 처음 쓸 때 한 번 이메일 인증을 합니다. 읽기는 가입 없이 됩니다.",
            "이 글은 정보를 단정하는 글이 아니라 실무자에게 경험을 묻는 글입니다. 법적 의무·수치·기한을 쓰지 않습니다."]
    for i, (q, kw, tools) in enumerate(COMMUNITY):
        out.append(_mk(f"comm:{i}", "커뮤니티", "community", "general", q, kw, [f"오늘의 질문: {q}"] + feat,
                       [{"label": "세이프플럼 게시판", "url": "", "site": "board/?b=qna"}],
                       [{"path": "board/?b=qna", "name": "세이프플럼 Q&A 게시판", "kind": "community"}] + [tool_ref(t) for t in tools]))
    return out


def pool():
    if "pool" not in _cache:
        topics = []
        for fn in (t_tools, t_forms, t_schedule, t_retention, t_edu, t_articles, t_qa, t_fatal, t_search_topics, t_monthly, t_rules, t_news, t_community):
            topics += fn()
        _cache["pool"] = {t["id"]: t for t in topics if t["facts"] and t["title"]}
    return _cache["pool"]


def pick(n, used_ids, date=None):
    """오늘 다룰 주제 n개. 요일별 우선 분야 → 최근에 쓰지 않은 것 → 점수(시의성) → 날짜로 고정한 무작위 순."""
    date = date or now().date()
    c = cfg()
    cats = list(c["category_week"][str(date.weekday())])
    topics = list(pool().values())
    topics = [t for t in topics if not t["hold_reason"]]          # 검토 전 소식은 정규 주제로 쓰지 않는다(held_news 가 따로 다룬다)
    fresh = [t for t in topics if t["cat"] == "소식" and t["score"] >= 3 and t["id"] not in used_ids]
    if fresh:
        cats.insert(0, "소식")
    rnd = random.Random(date.isoformat())
    out = []
    for cat in cats + CATS:
        if len(out) >= n:
            break
        cand = [t for t in topics if t["cat"] == cat and t["id"] not in used_ids and t["id"] not in {o["id"] for o in out} and t["score"] > -1]
        if not cand:
            continue
        rnd.shuffle(cand)
        cand.sort(key=lambda t: -t["score"])
        top = [t for t in cand if t["score"] >= cand[0]["score"] - 0.35]
        out.append(rnd.choice(top))
    return out


def held_news(used_ids):
    """운영자 검토가 안 끝난 최신 공식 발표 1건 — 초안만 만들어 보류함에 넣고 승인을 기다린다."""
    cand = [t for t in pool().values() if t["hold_reason"] and t["score"] >= 3 and t["id"] not in used_ids]
    cand.sort(key=lambda t: -t["score"])
    return cand[:1]


def evidence_text(topic, limit=9000):
    txt = "\n".join(topic["facts"])
    return txt[:limit]
