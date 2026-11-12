"""주제 → 플랫폼별 콘텐츠.

AI 는 '정보'만 쓴다. 링크·추적 주소(UTM)·홍보 문구·출처 표기·안내 카드는 전부 이 파일의 코드가 붙인다.
그래서 주소가 틀리거나 없는 기능을 홍보하는 일이 구조적으로 생기지 않는다.
"""
import html, re, hashlib, urllib.parse
from .common import cfg, today
from . import evidence as ev, llm


# ---------------------------------------------------------------- 링크·문구
def utm_link(platform, item, path=""):
    c = cfg()
    q = urllib.parse.urlencode({"utm_source": platform, "utm_medium": c["utm"]["medium"][platform],
                                "utm_campaign": ev.CAT_SLUG.get(item["cat"], "safety_content"), "utm_content": item["id"]})
    url = c["base_url"].rstrip("/") + "/" + path
    frag = ""
    if "#" in url:
        url, frag = url.split("#", 1)
        frag = "#" + frag
    return url + ("&" if "?" in url else "?") + q + frag


def josa(word, pair):
    """받침에 맞는 조사. pair 는 '이가' '은는' '을를'."""
    ch = re.sub(r"[^가-힣A-Za-z0-9]", "", word)[-1:] or "가"
    if "가" <= ch <= "힣":
        has = (ord(ch) - 0xAC00) % 28 != 0
    else:
        has = ch.lower() in "lmnr136780"          # 영문·숫자는 발음 기준 근사
    return pair[0] if has else pair[1]


def cta(item, n=0):
    """주제에 맞는 안내 문구 — 같은 문장이 반복되지 않게 글마다, 플랫폼마다 다른 변형을 고른다."""
    c = cfg()["cta_variants"]
    tool = item["tools"][0] if item.get("tools") else None
    kind = tool["kind"] if tool else ("law" if item["cat"] in ("법령", "중처법", "질의회시", "소식") else "general")
    if item["cat"] == "커뮤니티":
        kind = "community"
    vs = c.get(kind) or c["general"]
    h = int(hashlib.md5((item["id"] + str(n)).encode()).hexdigest(), 16)
    s = vs[h % len(vs)]
    if tool:
        name = tool["name"]
        s = s.replace("{tool}이(가)", name + josa(name, "이가")).replace("{tool}은(는)", name + josa(name, "은는")).replace("{tool}", name)
    return s


def primary_path(item):
    return item["tools"][0]["path"] if item.get("tools") else ""


# ---------------------------------------------------------------- 생성
def _user_text(topic, feedback=""):
    t = (f"[오늘 날짜] {today()}\n[분야] {ev.CAT_LABEL[topic['cat']]}\n[주제] {topic['title']}\n[핵심 검색어] {topic['keyword']}\n\n"
         f"[근거 묶음]\n{ev.evidence_text(topic)}\n")
    if feedback:
        t += f"\n[이전 초안에서 고칠 점 — 반드시 반영]\n{feedback}\n"
    return t


def _mock(topic, kind):
    """API 없이 파이프라인을 시험하기 위한 모의 응답. 근거 묶음의 문장만 그대로 써서 검증을 통과하게 만든다."""
    facts = [re.sub(r"^\[[^\]]+\]\s*", "", f) for f in topic["facts"]]
    short = [f[:60] for f in facts]
    title = topic["title"][:44]
    if kind == "blog":
        return {"title": title + ", 실무에서 확인할 것", "meta_description": (facts[0] + " " + facts[-1])[:110],
                "intro": facts[0] + "\n\n" + (facts[1] if len(facts) > 1 else facts[0]),
                "law_basis": [{"ref": s["label"][:60], "explain": facts[min(i, len(facts) - 1)][:160]} for i, s in enumerate(topic["sources"][:3])] or [{"ref": "세이프플럼 자료", "explain": facts[0][:160]}],
                "key_points": [{"heading": "핵심 사항", "body": f[:400]} for i, f in enumerate(facts[:4])],
                "how_to": [f[:90] for f in facts[:5]], "checklist": [f[:70] + " — 확인했는가" for f in facts[:5]],
                "faq": [{"q": topic["keyword"] + " 관련해 먼저 볼 것은?", "a": facts[0][:200]}], "labels": [topic["keyword"].replace(" ", ""), "안전관리자"]}
    if kind == "instagram":
        return {"cover_title": title[:22], "cover_sub": ev.CAT_LABEL[topic["cat"]] + " 실무 정리",
                "cards": [{"heading": "확인 사항", "lines": [s[:28], s[28:56] or "원문을 확인하세요"]} for i, s in enumerate(short[:4])],
                "caption": " ".join(facts[:2])[:400], "hashtags": [topic["keyword"].replace(" ", ""), "안전보건", "산업안전"]}
    return {"text": facts[0][:300] + "\n\n" + (facts[1][:200] if len(facts) > 1 else ""), "question": "여러분 현장에서는 어떻게 하고 계신가요?"}


def generate(topic, feedback=""):
    """플랫폼별 재료 3종. feedback 이 있으면 검증에서 걸린 점을 알려 주고 다시 쓰게 한다."""
    plat = cfg()["platforms"]
    out = {}
    for kind, key in (("blog", "blogger"), ("instagram", "instagram"), ("facebook", "facebook")):
        if plat.get(key):
            out[kind] = llm.call(kind, _user_text(topic, feedback), mock=lambda k=kind: _mock(topic, k))
    return out


# ---------------------------------------------------------------- 조립
def esc(s):
    return html.escape(str(s or ""), quote=True)


def paras(text):
    return "".join(f"<p>{esc(p.strip())}</p>" for p in re.split(r"\n\s*\n|\n", str(text or "")) if p.strip())


def blog_html(item, cover_url=""):
    b, c = item["raw"]["blog"], cfg()
    H2 = 'style="font-size:1.35em;margin:1.8em 0 .6em;padding-bottom:.3em;border-bottom:2px solid #1D4ED8"'
    TD = 'style="border:1px solid #CBD5E1;padding:8px 10px;vertical-align:top"'
    p = []
    if cover_url:
        p.append(f'<p><img src="{esc(cover_url)}" alt="{esc(b["title"])}" style="max-width:100%;height:auto" /></p>')
    p.append(paras(b["intro"]))
    p.append(f"<h2 {H2}>관련 법령과 공식 근거</h2>")
    p.append('<table style="border-collapse:collapse;width:100%"><tbody>' + "".join(
        f'<tr><td {TD} width="34%"><b>{esc(x["ref"])}</b></td><td {TD}>{esc(x["explain"])}</td></tr>' for x in b["law_basis"]) + "</tbody></table>")
    p.append(f"<h2 {H2}>실무자가 알아야 할 핵심</h2>")
    for k in b["key_points"]:
        p.append(f'<h3 style="font-size:1.1em;margin:1.2em 0 .3em">{esc(k["heading"])}</h3>{paras(k["body"])}')
    p.append(f"<h2 {H2}>실제 업무에 적용하는 순서</h2><ol>" + "".join(f"<li>{esc(x)}</li>" for x in b["how_to"]) + "</ol>")
    p.append(f"<h2 {H2}>체크리스트</h2><ul style=\"list-style:none;padding-left:0\">" + "".join(f"<li>☐ {esc(x)}</li>" for x in b["checklist"]) + "</ul>")
    if b.get("faq"):
        p.append(f"<h2 {H2}>자주 묻는 질문</h2>" + "".join(f'<p><b>Q. {esc(f["q"])}</b><br />A. {esc(f["a"])}</p>' for f in b["faq"]))
    # 세이프플럼 무료 도구 안내 — 실제 있는 도구만, 추적 주소로
    p.append(f"<h2 {H2}>세이프플럼 무료 도구</h2><p>{esc(cta(item, 1))}</p><ul>")
    for t in item.get("tools", []):
        p.append(f'<li><a href="{esc(utm_link("blogger", item, t["path"]))}">{esc(t["name"])}</a></li>')
    p.append(f'<li><a href="{esc(utm_link("blogger", item, ""))}">세이프플럼 홈 — 쉽고 빠르게 안전·보건 무료 서류작성(무료양식)</a></li></ul>')
    # 출처·기준일 (작게)
    src = []
    for s in item.get("sources", []):
        lab = esc(s["label"])
        src.append(f'<a href="{esc(s["url"])}" rel="nofollow">{lab}</a>' if s.get("url") else lab)
    p.append('<p style="font-size:.8em;color:#64748B;margin-top:2em">근거 자료: ' + " · ".join(src) + f'<br />작성 기준일 {esc(item["date"])}. 법령은 개정될 수 있고, 사업장 규모·업종·작업 조건에 따라 적용이 달라집니다. 실제 적용 전에 원문을 확인하세요.</p>')
    return "\n".join(p)


def ig_caption(item):
    g, c = item["raw"]["instagram"], cfg()
    tags = []
    for t in list(g.get("hashtags", [])) + c["hashtags_base"]:
        t = re.sub(r"[#\s]", "", t)
        if t and t not in tags:
            tags.append(t)
    link = c["base_url"].replace("https://", "")
    return (g["caption"].strip() + "\n\n" + cta(item, 2) + f"\n프로필 링크 또는 {link}\n\n" + " ".join("#" + t for t in tags[:12]))[:2200]


def fb_text(item):
    f = item["raw"]["facebook"]
    return f["text"].strip() + "\n\n" + f["question"].strip() + "\n\n" + cta(item, 3) + "\n" + utm_link("facebook", item, primary_path(item))


def card_specs(item):
    """카드뉴스 장면 목록(표지 + 본문 + 마지막 안내). 5~8장이 되게 맞춘다."""
    g, c = item["raw"]["instagram"], cfg()
    cards = [{"type": "cover", "label": ev.CAT_LABEL[item["cat"]], "title": g["cover_title"], "sub": g["cover_sub"]}]
    for x in g["cards"][:6]:
        cards.append({"type": "body", "label": ev.CAT_LABEL[item["cat"]], "title": x["heading"], "lines": x["lines"][:4]})
    cards.append({"type": "final", "title": c["final_card_text"], "url": c["base_url"].replace("https://", "")})
    return cards


def flat_text(item):
    """검증용 — AI 가 쓴 글자만 모은다(코드가 붙인 링크·출처는 뺀다)."""
    out = {}
    r = item["raw"]
    if "blog" in r:
        b = r["blog"]
        out["blog"] = "\n".join([b["title"], b["meta_description"], b["intro"]] + [x["ref"] + " " + x["explain"] for x in b["law_basis"]]
                                + [x["heading"] + " " + x["body"] for x in b["key_points"]] + b["how_to"] + b["checklist"]
                                + [x["q"] + " " + x["a"] for x in b.get("faq", [])])
    if "instagram" in r:
        g = r["instagram"]
        out["instagram"] = "\n".join([g["cover_title"], g["cover_sub"]] + [x["heading"] + " " + " ".join(x["lines"]) for x in g["cards"]] + [g["caption"]])
    if "facebook" in r:
        out["facebook"] = r["facebook"]["text"] + "\n" + r["facebook"]["question"]
    return out
