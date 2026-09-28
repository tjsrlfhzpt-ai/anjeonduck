#!/usr/bin/env python3
"""안전duck 정적 사이트 생성기.

data/*.json + config/site.json 을 읽어 _site/ 에 완성된 HTML을 만든다.
서버 코드가 없으므로 GitHub Pages·Cloudflare Pages 어디에나 그대로 올릴 수 있다.

사용법:  python3 build.py [--out _site] [--today 2026-09-28]
"""
import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print("  경고:", msg, file=sys.stderr)


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def safe_url(u):
    """http(s) 주소만 허용. 그 외(javascript: 등)는 빈 문자열."""
    u = (u or "").strip()
    return u if re.match(r"^https?://", u, re.I) else ""


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def law_url(name, kind="법령"):
    return "https://www.law.go.kr/" + quote(kind) + "/" + quote(name)


def form_url(law, byl_no, byl_br="00"):
    # 법령명+서식번호로 연결하는 고정 주소. 서식이 개정돼도 항상 현행본을 연다.
    return ("https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?bylCls=BF"
            f"&lsNm={quote(law)}&bylNo={quote(byl_no)}&bylBrNo={quote(byl_br or '00')}")


def fmt_date(d):
    if not d or not DATE_RE.match(d):
        return e(d)
    y, m, dd = d.split("-")
    return f"{y}.{m}.{dd}"


# ---------------------------------------------------------------- 검증

def validate_jobs(jobs, today):
    out, seen = [], set()
    for j in jobs:
        jid = str(j.get("id", "")).strip()
        if not ID_RE.match(jid):
            warn(f"채용: id 형식 오류로 제외 ({jid!r}) — 영문 소문자·숫자·하이픈만")
            continue
        if jid in seen:
            warn(f"채용: id 중복으로 제외 ({jid})")
            continue
        if not j.get("title") or not j.get("company"):
            warn(f"채용 {jid}: 제목·회사명이 없어 제외")
            continue
        if not safe_url(j.get("source_url")):
            warn(f"채용 {jid}: 공고 원문 주소(https)가 없어 제외")
            continue
        dl = str(j.get("deadline", "")).strip()
        if dl and not DATE_RE.match(dl) and dl not in ("상시", "채용 시"):
            warn(f"채용 {jid}: 마감일 형식 오류({dl}) — YYYY-MM-DD, 상시, 채용 시 중 하나")
            continue
        j["jobs_list"] = [x.strip() for x in re.split(r"[|,·]", str(j.get("job", ""))) if x.strip()]
        j["closed"] = bool(DATE_RE.match(dl) and dl < today)
        seen.add(jid)
        out.append(j)
    # 마감 안 된 공고 먼저(등록일 최신순), 그 뒤에 마감 공고(마감일 최신순)
    open_ = sorted([j for j in out if not j["closed"]], key=lambda j: str(j.get("posted", "")), reverse=True)
    closed = sorted([j for j in out if j["closed"]], key=lambda j: str(j.get("deadline", "")), reverse=True)
    return open_ + closed


def resolve_resource(r):
    if r.get("byl_no") and r.get("law"):
        r["href"] = form_url(r["law"], r["byl_no"], r.get("byl_br", "00"))
        r["law_href"] = law_url(r["law"])
    else:
        r["href"] = safe_url(r.get("url"))
        r["law_href"] = ""
    return r



# ---------------------------------------------------------------- 레이아웃

NAV = [("tools/", "무료 도구"), ("jobs/", "채용정보"), ("resources/", "서식·자료"), ("laws/", "법령")]

LOGO_SVG = ('<svg class="logo-mark" viewBox="0 0 40 40" aria-hidden="true">'
            '<rect width="40" height="40" rx="11" fill="#1F6FD1"/>'
            '<circle cx="19" cy="24" r="10.5" fill="#FFD23F"/>'
            '<path d="M8.5 22.5a10.5 9.5 0 0 1 21 0z" fill="#F58A1F"/>'
            '<rect x="6.5" y="21" width="25" height="3" rx="1.5" fill="#D86F0C"/>'
            '<circle cx="23" cy="26.5" r="1.6" fill="#17365D"/>'
            '<path d="M28 28.5q5 .3 5.2 1.9-2 1.7-5.7 1.1z" fill="#F58A1F"/></svg>')

AVATAR_COLORS = ["#1F6FD1", "#17365D", "#0E8A6A", "#8A4FD6", "#C2571A", "#3B6E8F"]
QUICK_KEYWORDS = ["산업재해조사표", "선임 보고서", "위험성평가", "TBM", "작업허가"]


def avatar(name):
    name = str(name or "?").strip()
    color = AVATAR_COLORS[sum(ord(c) for c in name) % len(AVATAR_COLORS)]
    ch = name.replace("㈜", "").replace("(주)", "").strip()[:1] or "?"
    return f'<span class="avatar" style="--av:{color}" aria-hidden="true">{e(ch)}</span>'


def tool_link(site, rel_root):
    t = (site.get("tools") or [{}])[0]
    return safe_url(t.get("url")) or f"{rel_root}tools/"


def page(site, rel_root, path, title, body, desc=None, active=""):
    base = site["base_url"].rstrip("/")
    canonical = f"{base}/{path}"
    full_title = f"{title} | {site['name']}" if title != site["name"] else f"{site['name']} — {site['tagline']}"
    cur = ' aria-current="page"'
    nav = "".join(f'<a href="{rel_root}{href}"{cur if active == href else ""}>{e(label)}</a>' for href, label in NAV)
    tl = tool_link(site, rel_root)
    ext = ' target="_blank" rel="noopener"' if tl.startswith("http") else ""
    contact = site.get("contact_email", "")
    contact_html = f'<a href="mailto:{e(contact)}">{e(contact)}</a>' if contact else ""
    d = e(desc or site["description"])
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(site['name'])}">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:locale" content="ko_KR">
<meta name="theme-color" content="#1F6FD1">
<link rel="icon" href="{rel_root}assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="{rel_root}assets/style.css">
</head>
<body>
<a class="skip" href="#main">본문으로 바로가기</a>
<header class="hd">
  <div class="wrap hd-in">
    <a class="logo" href="{rel_root}" aria-label="{e(site['name'])} 홈">{LOGO_SVG}<span>{e(site['name'])}</span></a>
    <nav class="gnb" aria-label="주 메뉴">{nav}</nav>
    <a class="btn btn-sm hd-cta" href="{e(tl)}"{ext}>SAFE 덕희 열기</a>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="ft">
  <div class="wrap ft-in">
    <div>
      <a class="logo logo-ft" href="{rel_root}">{LOGO_SVG}<span>{e(site['name'])}</span></a>
      <p>{e(site['tagline'])}</p>
    </div>
    <ul class="ft-notes">
      <li>서식·법령은 국가법령정보센터 등 기관 원본으로 연결됩니다.</li>
      <li>채용 조건과 마감일은 공고 원문이 우선합니다.</li>
      <li>방문자 정보를 서버에 저장하지 않습니다. 즐겨찾기는 이 기기에만 남습니다.</li>
    </ul>
    <p class="ft-copy">© {dt.date.today().year} {e(site['name'])}{(' · ' + contact_html) if contact_html else ''}</p>
  </div>
</footer>
<script src="{rel_root}assets/app.js" defer></script>
</body>
</html>
"""


# ---------------------------------------------------------------- 컴포넌트

def dl_badge(j):
    dl = str(j.get("deadline", "") or "")
    if DATE_RE.match(dl):
        cls, txt = ("badge-muted", "마감") if j["closed"] else ("badge-line", fmt_date(dl)[5:] + " 마감")
    elif dl:
        cls, txt = "badge-blue", dl
    else:
        cls, txt = "badge-line", "원문 확인"
    return f'<span class="badge {cls}" data-dl-badge>{e(txt)}</span>'


def job_row(j, rel_root, compact=False):
    tags = "".join(f'<span class="tag tag-job">{e(x)}</span>' for x in j["jobs_list"])
    tags += "".join(f'<span class="tag">{e(v)}</span>' for v in (j.get("career"), j.get("employment")) if v)
    loc = " · ".join(x for x in [j.get("company"), j.get("region")] if x)
    attrs = (f'data-item data-job="{e("|".join(j["jobs_list"]))}" '
             f'data-ctype="{e(j.get("company_type",""))}" data-industry="{e(j.get("industry",""))}" '
             f'data-deadline="{e(j.get("deadline",""))}" data-posted="{e(j.get("posted",""))}" '
             f'data-text="{e(" ".join(str(j.get(k,"")) for k in ("title","company","region","job","industry","company_type","career","employment")))}"')
    meta = " · ".join(x for x in [j.get("company_type"), j.get("industry")] if x)
    return f"""<li class="jrow{' closed' if j['closed'] else ''}{' compact' if compact else ''}" {attrs}>
  {avatar(j.get('company'))}
  <div class="jrow-main">
    <a class="jrow-title" href="{rel_root}jobs/{e(j['id'])}/">{e(j['title'])}</a>
    <p class="jrow-sub">{e(loc)}{(' <span class="dot">·</span> ' + e(meta)) if meta and not compact else ''}</p>
    {'' if compact else f'<p class="tags">{tags}</p>'}
  </div>
  <div class="jrow-side">{dl_badge(j)}</div>
</li>"""


def resource_row(r, site, rel_root="./"):
    tool = (site.get("tools") or [None])[0]
    acts = []
    if r.get("free_tool"):
        acts.append(f'<a class="btn btn-sm btn-green" href="{rel_root}tools/{e(r["free_tool"])}/">바로 작성 · 무료</a>')
    if r.get("href"):
        acts.append(f'<a class="btn btn-sm" href="{e(r["href"])}" target="_blank" rel="noopener">{"서식 원본" if r.get("byl_no") else "원문"} ↗</a>')
    if r.get("law_href"):
        acts.append(f'<a class="btn btn-sm btn-ghost" href="{e(r["law_href"])}" target="_blank" rel="noopener">근거 법령</a>')
    if r.get("app_kind") and tool:
        tpl, url = tool.get("deep_link_template", ""), safe_url(tool.get("url"))
        link = tpl.replace("{kind}", quote(r["app_kind"])) if tpl else url
        if safe_url(link):
            acts.append(f'<a class="btn btn-sm btn-accent" href="{e(link)}" target="_blank" rel="noopener">덕희에서 작성</a>')
        elif r.get("category") == "SAFE 덕희 서식":
            acts.append('<span class="btn btn-sm btn-disabled" aria-disabled="true">도구 주소 준비 중</span>')
    meta = [x for x in [r.get("law"), r.get("form_no")] if x]
    tags = r.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split("|") if t]
    text = " ".join([r.get("title", ""), r.get("summary", ""), r.get("law", ""), r.get("form_no", ""), " ".join(tags)])
    cat = r.get("category", "")
    cat_cls = {"법정 서식": "badge-blue", "고시·지침": "badge-navy", "SAFE 덕희 서식": "badge-orange", "무료 작성 도구": "badge-green"}.get(cat, "badge-line")
    return f"""<li class="rrow" data-item data-cat="{e(cat)}" data-id="{e(r['id'])}" data-text="{e(text)}">
  <div class="rrow-main">
    <p class="rrow-top"><span class="badge {cat_cls}">{e(cat)}</span>{f'<span class="rrow-meta">{e(" · ".join(meta))}</span>' if meta else ''}</p>
    <h3 class="rrow-title">{e(r['title'])}</h3>
    <p class="rrow-desc">{e(r.get('summary'))}</p>
    {f'<p class="rrow-note">원본 확인 {fmt_date(r["verified"])}</p>' if r.get("verified") else ''}
  </div>
  <div class="rrow-acts">{''.join(acts)}</div>
  <button class="fav" type="button" data-fav="{e(r['id'])}" aria-pressed="false" aria-label="즐겨찾기">☆</button>
</li>"""


def update_row(u, full=True):
    src = safe_url(u.get("source_url"))
    link = f'<a class="link-ext" href="{e(src)}" target="_blank" rel="noopener">{e(u.get("source_name") or "원문")} ↗</a>' if src else ""
    d = u.get("date", "")
    return f"""<li class="urow" data-item data-text="{e(u.get('title','') + ' ' + u.get('summary','') + ' ' + u.get('law',''))}">
  <time class="urow-date" datetime="{e(d)}">{fmt_date(d)}</time>
  <div class="urow-body">
    <p class="urow-law">{e(u.get('law'))}{(' · 시행 ' + fmt_date(u.get('effective'))) if u.get('effective') else ''}</p>
    <h3 class="urow-title">{e(u['title'])}</h3>
    {f'<p class="urow-desc">{e(u.get("summary"))}</p><p class="urow-foot">{link}<span>원문 확인 {fmt_date(u.get("checked"))}</span></p>' if full else ''}
  </div>
</li>"""


def filter_group(group, values, label):
    items = "".join(f'<button type="button" class="chip" data-value="{e(v)}" aria-pressed="false">{e(v)}</button>' for v in values)
    return (f'<div class="fgroup"><p class="fgroup-label">{e(label)}</p>'
            f'<div class="chips" data-filter="{group}" role="group" aria-label="{e(label)}">'
            f'<button type="button" class="chip" data-value="" aria-pressed="true">전체</button>{items}</div></div>')


def sec_head(title, href=None, more="전체 보기", sub=None):
    link = f'<a class="more" href="{href}">{e(more)} <span aria-hidden="true">→</span></a>' if href else ""
    return f'<div class="sec-head"><div><h2>{e(title)}</h2>{f"<p>{e(sub)}</p>" if sub else ""}</div>{link}</div>'


def tool_panel(site, rel_root, big=False):
    t = (site.get("tools") or [None])[0]
    if not t:
        return ""
    url = safe_url(t.get("url"))
    btn = (f'<a class="btn btn-white" href="{e(url)}" target="_blank" rel="noopener">열기 ↗</a>' if url
           else f'<a class="btn btn-white" href="{rel_root}tools/">자세히 보기</a>' if not big
           else '<span class="btn btn-white btn-disabled" aria-disabled="true">주소 준비 중</span>')
    feats = "".join(f"<li>{e(x)}</li>" for x in ["위험성평가·TBM·작업허가·순회점검", "CAPA 개선조치와 사건번호 연결", "법정업무 이행관리·업무함", "엑셀 출력·가져오기, 백업·복원"])
    return f"""<div class="tool-panel{' big' if big else ''}">
  <p class="tool-eyebrow">무료 · 설치 없음 · 기록은 내 PC에만</p>
  <h3>{e(t['name'])}</h3>
  <p>{e(t.get('desc'))}</p>
  {f'<ul class="tool-feats">{feats}</ul>' if big else ''}
  <div class="btns">{btn}</div>
</div>"""


def free_tool_cards(site, rel_root):
    cards = []
    for t in site.get("free_tools", []):
        cards.append(f'''<a class="ftool" href="{rel_root}tools/{e(t["id"])}/">
  <span class="ftool-tag">{e(t.get("tag",""))}</span>
  <strong>{e(t["name"])}</strong>
  <span class="ftool-desc">{e(t.get("desc",""))}</span>
  <span class="ftool-go">바로 작성 →</span>
</a>''')
    return "".join(cards)


def render_free_tool(t, hazards):
    src = (ROOT / t["src"]).read_text(encoding="utf-8")
    if t.get("inject") == "hazards":
        payload = json.dumps(hazards, ensure_ascii=False).replace("</", "<\\/")
        assert "/*@HAZARDS@*/null" in src, t["src"]
        src = src.replace("/*@HAZARDS@*/null", payload)
    elif t.get("inject") == "tailwind":
        css = (ROOT / t["css"]).read_text(encoding="utf-8").replace("</style", "<\\/style")
        assert "/*@TAILWIND@*/" in src, t["src"]
        src = src.replace("/*@TAILWIND@*/", css)
    return src


def empty_box(msg, extra=""):
    return f'<div class="empty"><p>{e(msg)}</p>{extra}</div>'


# ---------------------------------------------------------------- 페이지

def build(out, today):
    site = load("config/site.json")
    resources = [resolve_resource(r) for r in load("data/resources.json")]
    laws = load("data/laws.json")
    sites = load("data/sites.json")
    jobs = validate_jobs(load("data/jobs.json"), today)
    hazards = load("data/hazards.json")
    hazards = {"groups": hazards["groups"], "items": hazards["items"]}

    if not safe_url(site.get("base_url")):
        sys.exit("config/site.json 의 base_url 이 https 주소가 아닙니다.")
    for t in site.get("tools", []):
        if not safe_url(t.get("url")):
            warn(f"도구 '{t.get('name')}' 주소가 비어 있음 → '준비 중'으로 표시")
    for r in resources:
        if r.get("category") != "SAFE 덕희 서식" and not r.get("free_tool") and not r.get("href"):
            warn(f"자료 {r['id']}: 원본 주소가 없음")

    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    for f in (ROOT / "assets").iterdir():
        shutil.copy(f, out / "assets" / f.name)

    urls = []

    def write(path, content):
        p = out / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if path.endswith("index.html"):
            urls.append(path[: -len("index.html")])

    open_jobs = [j for j in jobs if not j["closed"]]
    job_search_html = "".join(
        f'<a class="btn btn-sm btn-ghost" href="{e(safe_url(s["url"]))}" target="_blank" rel="noopener">{e(s["name"])} ↗</a>'
        for s in sites.get("job_search", []) if safe_url(s.get("url")))
    updates = sorted(laws.get("updates", []), key=lambda u: u.get("date", ""), reverse=True)
    official_list = "".join(
        f'<li><a href="{e(safe_url(s["url"]))}" target="_blank" rel="noopener"><strong>{e(s["name"])}</strong><span>{e(s["desc"])}</span></a></li>'
        for s in sites.get("official", []) if safe_url(s.get("url")))

    # ---- 홈
    quick = "".join(f'<a class="qk" href="resources/?q={quote(k)}">{e(k)}</a>' for k in QUICK_KEYWORDS)
    popular = [r for r in resources if r.get("popular")][:6]
    home_jobs = (f'<ul class="jlist">{"".join(job_row(j, "./") for j in open_jobs[:6])}</ul>' if open_jobs else
                 empty_box("지금 등록된 공고가 없습니다. 아래에서 바로 찾아볼 수 있습니다.", f'<div class="btns">{job_search_html}</div>'))
    home = f"""
<section class="hero">
  <div class="wrap">
    <p class="hero-eyebrow">안전관리자·보건관리자를 위한</p>
    <h1>안전관리 서류,<br class="br-m"> 여기서 바로</h1>
    <p class="hero-sub">TBM 일지·위험성평가서·산보위 회의록은 무료로 바로 작성해 인쇄하고, 법정 서식은 기관 원본으로, 채용 공고는 핵심 조건만 모았습니다.</p>
    <form class="hsearch" action="resources/" role="search" data-scope-form>
      <div class="scope" role="radiogroup" aria-label="검색 범위">
        <label><input type="radio" name="scope" value="resources/" checked> 서식·자료</label>
        <label><input type="radio" name="scope" value="jobs/"> 채용정보</label>
      </div>
      <div class="hsearch-box">
        <label for="q" class="sr">검색어</label>
        <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input id="q" name="q" type="search" placeholder="서식명, 회사명, 키워드" autocomplete="off">
        <button class="btn" type="submit">검색</button>
      </div>
    </form>
    <p class="quick"><span>자주 찾는</span>{quick}</p>
  </div>
</section>
<section class="wrap ftools-home">
  {sec_head("무료 작성 도구", "tools/", more="모두 보기", sub="회원가입 없이 바로 작성하고 A4로 인쇄하세요. 입력 내용은 서버로 가지 않습니다.")}
  <div class="ftools">{free_tool_cards(site, "./")}</div>
</section>
<div class="wrap layout-home">
  <section class="col-main">
    {sec_head("최신 채용정보", "jobs/", sub=f"진행 중 {len(open_jobs)}건")}
    {home_jobs}
    {sec_head("자주 찾는 서식·자료", "resources/")}
    <ul class="rlist">{"".join(resource_row(r, site, "./") for r in popular)}</ul>
  </section>
  <aside class="col-side">
    <section class="side-box">
      {sec_head("법령 개정", "laws/", more="더보기")}
      <ul class="ulist compact">{"".join(update_row(u, full=False) for u in updates[:4])}</ul>
    </section>
    {tool_panel(site, "./")}
    <section class="side-box">
      {sec_head("공식 사이트")}
      <ul class="olist">{official_list}</ul>
    </section>
  </aside>
</div>"""
    write("index.html", page(site, "./", "", site["name"], home))

    # ---- 채용 목록
    def vals(key, split=False):
        s = []
        for j in jobs:
            for v in (j["jobs_list"] if split else [j.get(key, "")]):
                if v and v not in s:
                    s.append(v)
        return s

    if jobs:
        filters = (filter_group("job", vals("job", True), "직무") + filter_group("ctype", vals("company_type"), "기업분류")
                   + filter_group("industry", vals("industry"), "업종"))
        main = f"""
    <div class="listbar">
      <div class="search-inline">
        <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input type="search" class="filter-q" placeholder="회사명, 지역, 직무" aria-label="채용 검색">
      </div>
      <div class="listbar-right">
        <label class="switch"><input type="checkbox" class="hide-closed" checked><span>마감 숨기기</span></label>
        <label class="sr" for="sort">정렬</label>
        <select id="sort" class="sort">
          <option value="posted">최신 등록순</option>
          <option value="deadline">마감 임박순</option>
        </select>
      </div>
    </div>
    <p class="count" aria-live="polite">공고 <strong data-count>{len(jobs)}</strong>건</p>
    <ul class="jlist" data-list>{''.join(job_row(j, '../') for j in jobs)}</ul>
    {empty_box("조건에 맞는 공고가 없습니다. 필터를 줄여 보세요.").replace('class="empty"', 'class="empty" data-empty hidden')}"""
        side = f"""<details class="fpanel" open data-fpanel><summary>필터</summary><div class="fpanel-body">{filters}
      <button type="button" class="btn btn-sm btn-ghost fpanel-reset" data-reset>필터 초기화</button></div></details>"""
    else:
        main = empty_box("지금 등록된 공고가 없습니다. 공고는 매일 정리해 올립니다. 그 사이에는 아래에서 찾아보세요.",
                         f'<div class="btns">{job_search_html}</div>')
        side = ""
    jobs_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>채용정보</p>
  <h1>안전·보건 채용정보</h1>
  <p>안전관리자·보건관리자·EHS·소방 공고를 핵심 조건만 정리했습니다. 지원 전에는 공고 원문을 꼭 확인하세요.</p>
</div></section>
<div class="wrap layout-list{' no-side' if not side else ''}">
  {f'<aside class="col-filter">{side}</aside>' if side else ''}
  <section class="col-list">{main}
    <div class="more-box"><p>다른 채용 사이트에서 더 찾기</p><div class="btns">{job_search_html}</div></div>
  </section>
</div>"""
    write("jobs/index.html", page(site, "../", "jobs/", "채용정보", jobs_body,
                                  desc="안전관리자·보건관리자·EHS·소방 채용공고를 직무·기업분류·업종별로 찾아보세요.", active="jobs/"))

    # ---- 채용 상세
    for j in jobs:
        def lines(v):
            return "".join(f"<li>{e(x.strip())}</li>" for x in str(v or "").split("|") if x.strip())
        dl = str(j.get("deadline", "") or "")
        rows = [("기업분류", j.get("company_type")), ("업종", j.get("industry")), ("직무", " · ".join(j["jobs_list"])),
                ("근무지", j.get("region")), ("경력", j.get("career")), ("고용형태", j.get("employment")),
                ("등록일", fmt_date(j.get("posted")) if j.get("posted") else "")]
        table = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in rows if v)
        duties, reqs = lines(j.get("duties")), lines(j.get("requirements"))
        dl_txt = fmt_date(dl) if DATE_RE.match(dl) else (dl or "원문 확인")
        body = f"""
<section class="phead phead-detail"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">채용정보</a><span>/</span>{e(j['company'])}</p>
  <div class="dhead">
    {avatar(j.get('company'))}
    <div>
      <p class="dhead-co">{e(j['company'])}</p>
      <h1>{e(j['title'])}</h1>
      <p class="tags">{''.join(f'<span class="tag tag-job">{e(x)}</span>' for x in j["jobs_list"])}{f'<span class="tag">{e(j.get("region"))}</span>' if j.get("region") else ''}</p>
    </div>
  </div>
</div></section>
<div class="wrap layout-detail">
  <article class="col-main">
    {'<p class="alert">마감된 공고입니다. 기록용으로만 남겨 둡니다.</p>' if j['closed'] else ''}
    {f'<section class="block"><h2>요약</h2><p>{e(j.get("summary"))}</p></section>' if j.get('summary') else ''}
    <section class="block"><h2>모집 조건</h2><dl class="dl-grid">{table}</dl></section>
    {f'<section class="block"><h2>주요 업무</h2><ul class="bul">{duties}</ul></section>' if duties else ''}
    {f'<section class="block"><h2>자격 요건</h2><ul class="bul">{reqs}</ul></section>' if reqs else ''}
    <p class="src-note">출처: {e(j.get('source_name') or '공고 원문')} · 요약은 안전duck이 정리한 것이며 조건과 일정은 원문이 우선합니다.</p>
  </article>
  <aside class="col-side">
    <div class="apply-card" data-deadline="{e(dl)}">
      <p class="apply-label">마감</p>
      <p class="apply-dl"><span data-dl-text>{e(dl_txt)}</span> {dl_badge(j)}</p>
      <a class="btn btn-block" href="{e(safe_url(j['source_url']))}" target="_blank" rel="noopener nofollow">공고 원문에서 지원 ↗</a>
      <a class="btn btn-block btn-ghost" href="../">다른 공고 보기</a>
    </div>
  </aside>
</div>"""
        write(f"jobs/{j['id']}/index.html", page(site, "../../", f"jobs/{j['id']}/", f"{j['company']} {j['title']}", body,
                                                  desc=f"{j['company']} · {j.get('region','')} · {j.get('career','')} · 마감 {dl}", active="jobs/"))

    # ---- 서식·자료
    cats = []
    for r in resources:
        if r.get("category") and r["category"] not in cats:
            cats.append(r["category"])
    catnav = (f'<button type="button" class="chip" data-value="" aria-pressed="true">전체 <span class="n">{len(resources)}</span></button>'
              + "".join(f'<button type="button" class="chip" data-value="{e(c)}" aria-pressed="false">{e(c)} <span class="n">{sum(1 for r in resources if r.get("category")==c)}</span></button>' for c in cats))
    res_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>서식·자료</p>
  <h1>서식·자료</h1>
  <p>법정 서식은 국가법령정보센터의 현행 원본으로 열립니다. 서식이 개정돼도 같은 버튼이 최신본을 엽니다.</p>
</div></section>
<div class="wrap layout-list">
  <aside class="col-filter">
    <div class="fpanel static"><div class="fpanel-body">
      <div class="fgroup"><p class="fgroup-label">분류</p><div class="chips catnav" data-filter="cat" role="group" aria-label="분류">{catnav}</div></div>
      <label class="switch"><input type="checkbox" class="only-fav"><span>★ 즐겨찾기만</span></label>
    </div></div>
  </aside>
  <section class="col-list">
    <div class="listbar"><div class="search-inline">
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input type="search" class="filter-q" placeholder="서식명, 법령, 키워드" aria-label="서식 검색"></div></div>
    <p class="count" aria-live="polite">자료 <strong data-count>{len(resources)}</strong>건</p>
    <ul class="rlist" data-list>{''.join(resource_row(r, site, '../') for r in resources)}</ul>
    {empty_box("검색 결과가 없습니다.").replace('class="empty"', 'class="empty" data-empty hidden')}
  </section>
</div>"""
    write("resources/index.html", page(site, "../", "resources/", "서식·자료", res_body,
                                       desc="산업재해조사표, 안전관리자 선임 보고서 등 산업안전보건 법정 서식을 원본으로 바로 여세요.", active="resources/"))

    # ---- 법령
    statutes = "".join(
        f'<li><a href="{e(law_url(s["name"], s.get("type","법령")))}" target="_blank" rel="noopener"><span class="badge {"badge-navy" if s.get("type")=="행정규칙" else "badge-line"}">{e(s.get("type"))}</span><strong>{e(s["name"])}</strong><span class="arr" aria-hidden="true">↗</span></a></li>'
        for s in laws.get("statutes", []))
    law_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>법령</p>
  <h1>법령</h1>
  <p>자주 보는 법령은 현행 본문으로 바로 열리고, 개정 소식은 원문 링크와 함께 정리합니다.</p>
</div></section>
<div class="wrap layout-detail">
  <section class="col-main">
    {sec_head("개정 소식", sub="요약은 원문을 읽고 정리한 것입니다. 적용 여부는 원문과 전문가 확인을 거치세요.")}
    <div class="listbar"><div class="search-inline">
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input type="search" class="filter-q" placeholder="법령명, 내용" aria-label="개정 소식 검색"></div></div>
    <ul class="ulist" data-list>{''.join(update_row(u) for u in updates)}</ul>
    {empty_box("검색 결과가 없습니다.").replace('class="empty"', 'class="empty" data-empty hidden')}
  </section>
  <aside class="col-side">
    <section class="side-box">{sec_head("법령 바로가기")}<ul class="llist">{statutes}</ul></section>
  </aside>
</div>"""
    write("laws/index.html", page(site, "../", "laws/", "법령", law_body,
                                  desc="산업안전보건법·중대재해처벌법 바로가기와 시행규칙 개정 소식.", active="laws/"))

    # ---- 도구
    tools_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>무료 도구</p>
  <h1>무료 안전관리 도구</h1>
  <p>회원가입도 서버도 없습니다. 입력한 내용은 내 브라우저 안에서만 처리됩니다.</p>
</div></section>
<section class="wrap ftools-page">
  {sec_head("무료 작성 도구", sub="바로 작성하고 인쇄하거나 PDF로 저장하는 일회성 문서 도구")}
  <div class="ftools">{free_tool_cards(site, "../")}</div>
</section>
<div class="wrap layout-detail">
  <section class="col-main">{sec_head("기록까지 관리하려면")}{tool_panel(site, "../", big=True)}</section>
  <aside class="col-side"><section class="side-box">
    <h2 class="h-sm">왜 서버가 없나요?</h2>
    <p>안전관리 기록에는 사고·건강 정보처럼 민감한 내용이 많습니다. 서버에 모으지 않으면 유출 위험과 운영비가 함께 사라집니다.</p>
    <p>대신 여러 PC 사이 자동 동기화는 되지 않습니다. 옮길 때는 백업 파일이나 구글 스프레드시트 연동을 씁니다.</p>
  </section></aside>
</div>"""
    write("tools/index.html", page(site, "../", "tools/", "도구", tools_body, active="tools/"))

    # ---- 무료 작성 도구 (각각 한 파일로 완결)
    for t in site.get("free_tools", []):
        write(f"tools/{t['id']}/index.html", render_free_tool(t, hazards))

    # ---- 404 (어느 경로에서 열려도 되도록 절대 주소 사용)
    base = site["base_url"].rstrip("/")
    (out / "404.html").write_text(page(site, base + "/", "404.html", "페이지를 찾을 수 없습니다",
        f'<section class="phead"><div class="wrap"><h1>페이지를 찾을 수 없습니다</h1><p>마감되어 내려간 공고이거나 주소가 바뀌었을 수 있습니다.</p><p class="btns"><a class="btn" href="{e(base)}/">홈으로</a></p></div></section>'),
        encoding="utf-8")

    sm = "".join(f"<url><loc>{e(base + '/' + u)}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>', encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"완료: 페이지 {len(urls)}개(무료 도구 {len(site.get('free_tools', []))}개 포함), 채용 {len(jobs)}건(진행 {len(open_jobs)}), 자료 {len(resources)}건, "
          f"개정소식 {len(updates)}건, 전체 {total/1024:.0f}KB → {out}")
    if WARNINGS:
        print(f"경고 {len(WARNINGS)}건 (위 참고)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--today", default=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat())
    a = ap.parse_args()
    build(ROOT / a.out, a.today)
