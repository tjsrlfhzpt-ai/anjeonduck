#!/usr/bin/env python3
"""SafePlum 정적 사이트 생성기.

data/*.json + config/site.json 을 읽어 _site/ 에 완성된 HTML을 만든다.
서버 코드가 없으므로 GitHub Pages·Cloudflare Pages 어디에나 그대로 올릴 수 있다.

사용법:  python3 build.py [--out _site] [--today 2026-09-28]
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import urllib.parse
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


def form_url(law, byl_no, byl_br="00", cls="BF"):
    # 법령명+서식번호로 연결하는 고정 주소. 서식이 개정돼도 항상 현행본을 연다. BF=서식(별지), BE=별표
    return (f"https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?bylCls={cls}"
            f"&lsNm={quote(law)}&bylNo={quote(byl_no)}&bylBrNo={quote(byl_br or '00')}")


BOARD_BUILT = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch_board_posts(url, key):
    """게시판(커뮤니티·Q&A)의 공개 글과 댓글을 빌드 때 읽어 온다 — 검색엔진이 읽을 수 있는 글별 정적 페이지를 만들기 위해서다.
    - 브라우저 게시판과 같은 공개(anon) 키·같은 읽기 정책(삭제되지 않은 글)만 쓴다. 채용공고(job)는 연락처 등이 있어 만들지 않는다.
    - 접속에 실패하면 None(이번 빌드는 정적 글 페이지 없이 진행). 시험용으로 BOARD_FIXTURE=파일 경로를 주면 그 파일을 쓴다."""
    import os, urllib.request
    fx = os.environ.get("BOARD_FIXTURE")
    if fx:
        return json.loads(Path(fx).read_text(encoding="utf-8"))
    if os.environ.get("SKIP_BOARD_FETCH") or not url or not key:
        return None
    def get(path):
        req = urllib.request.Request(url.rstrip("/") + "/rest/v1/" + path, headers={"apikey": key, "Authorization": "Bearer " + key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    try:
        posts = get("posts?select=id,board,category,title,body,created_at,updated_at,comment_count,accepted_comment_id,notice,author_nick,author:profiles(nickname)"
                    "&deleted_at=is.null&board=in.(free,qna)&order=id.desc&limit=1000")
        ids = [p["id"] for p in posts]
        cms = []
        for i in range(0, len(ids), 150):
            chunk = ",".join(str(x) for x in ids[i:i + 150])
            cms += get(f"comments?select=id,post_id,body,created_at,author_nick,author:profiles(nickname)&deleted_at=is.null&post_id=in.({chunk})&order=id.asc&limit=5000")
        return {"posts": posts, "comments": cms}
    except Exception as ex:   # 네트워크 차단·정책 변경 등 — 사이트 빌드는 멈추지 않는다
        warn(f"게시판 글을 읽지 못해 글별 정적 페이지를 만들지 않음({type(ex).__name__}: {str(ex)[:120]})")
        return None


def fmt_date(d):
    if not d or not DATE_RE.match(d):
        return e(d)
    y, m, dd = d.split("-")
    return f"{y}.{m}.{dd}"


# ---------------------------------------------------------------- 안전 브리핑 (data/briefs/YYYY-MM-DD.json)

# 브리핑·법령 근거로 쓸 수 있는 공식 1차 출처(도메인 끝). 그 밖의 주소는 '참고 보도'로만 표시하고 근거로 세지 않는다.
OFFICIAL_HOSTS = ("law.go.kr", "moel.go.kr", "kosha.or.kr", "korea.kr", "assembly.go.kr", "moleg.go.kr", "lawmaking.go.kr", "gwanbo.go.kr",
                  "comwel.or.kr", "me.go.kr", "nfa.go.kr", "mois.go.kr", "molit.go.kr", "kgs.or.kr", "data.go.kr", "work24.go.kr", "opinion.lawmaking.go.kr",
                  "kdi.re.kr", "safetymonth.or.kr", "bizinfo.go.kr")  # kdi.re.kr: KDI 경제정책정보센터가 부처 보도자료 원문을 그대로 게재(국책연구기관)


def is_official(url):
    m = re.match(r"^https://([^/:?#]+)", str(url or ""))
    host = m.group(1).lower() if m else ""
    return any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


BRIEF_STAGE = {"법안": "lst-bill", "입법예고": "lst-bill", "국회 통과": "lst-bill", "공포": "lst-next", "시행 예정": "lst-next", "시행 중": "lst-cur", "발표": "lst-rec", "권장": "lst-rec"}
BRIEF_CATS = {"법령": "badge-navy", "정책": "badge-blue", "감독": "badge-orange", "사고": "badge-red", "화학물질": "badge-green", "보건": "badge-green", "자료": "badge-line"}


def load_briefs(today):
    """하루 한 건. 형식이 틀린 파일·항목은 빼고 경고만 남긴다(브리핑 때문에 배포가 멈추지 않게)."""
    out = []
    d = ROOT / "data/briefs"
    for f in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except Exception as ex:  # noqa: BLE001
            warn(f"브리핑 {f.name}: JSON 오류로 제외 — {ex}")
            continue
        if b.get("date") != f.stem or not DATE_RE.match(f.stem) or f.stem > today:
            warn(f"브리핑 {f.name}: date 값이 파일 이름과 다르거나 미래 날짜라 제외")
            continue
        items = []
        for it in b.get("items", []):
            allsrc = [x for x in it.get("sources", []) + it.get("press", []) if safe_url(x.get("url")) and x.get("name")]
            srcs = [x for x in allsrc if is_official(x["url"])]
            it["press"] = [x for x in allsrc if not is_official(x["url"])]
            if not it.get("title") or not it.get("summary") or not srcs:
                warn(f"브리핑 {f.stem}: 제목·요약·공식 1차 출처가 없는 항목 제외 — {it.get('title')!r}")
                continue
            it["sources"] = srcs
            items.append(it)
        if not b.get("title") or not items:
            warn(f"브리핑 {f.name}: 제목 또는 유효한 항목이 없어 제외")
            continue
        b["items"] = items
        out.append(b)
    return out


BRIEF_PENDING = '<span class="lst lst-chk" tabindex="0">확인 필요</span> 자동으로 작성해 게시한 브리핑입니다. 사실 확인이 끝나지 않았으니 공식 출처 원문을 함께 확인하세요. '


def brief_article(b, rel):
    def item(it):
        cat = it.get("cat") or "정책"
        link = lambda x: f'<a class="link-ext" href="{e(safe_url(x["url"]))}" target="_blank" rel="noopener nofollow">{e(x["name"])} ↗</a>'
        srcs = " · ".join(link(x) for x in it["sources"])
        press = " · ".join(link(x) for x in it.get("press", []))
        d = it.get("date") or ""
        ev = it.get("event_date") or ""
        stage = it.get("stage") or ""
        st = f'<span class="lst {BRIEF_STAGE.get(stage, "lst-rec")}">{e(stage)}</span>' if stage else ""
        facts = [("발표·공포일", fmt_date(d) if DATE_RE.match(d) else ""), ("사건·기준일", fmt_date(ev) if DATE_RE.match(ev) else ""), ("기관", e(it.get("agency") or "")),
                 ("공식 제목", e(it.get("official_title") or "")), ("시행일", fmt_date(it["effective"]) if DATE_RE.match(str(it.get("effective") or "")) else e(it.get("effective") or ""))]
        dl = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts if v)
        point = f'<p class="br-point"><b>실무 포인트</b>{e(it["point"])}</p>' if it.get("point") else ""
        return (f'<article class="br-item"><p class="br-meta"><span class="badge {BRIEF_CATS.get(cat, "badge-line")}">{e(cat)}</span>{st}</p>'
                f'<h3>{e(it["title"])}</h3><dl class="br-facts">{dl}</dl><p class="br-sum">{e(it["summary"])}</p>{point}<p class="br-src">공식 출처 {srcs}</p>'
                + (f'<p class="br-src br-press">참고 보도(법령·정책의 근거로 쓰지 않음) {press}</p>' if press else "") + "</article>")

    def todo_li(t):
        href = str(t.get("href") or "")
        ok = bool(re.match(r"^(tools|resources|laws|jobs|brief)/[A-Za-z0-9_/#?=&%.-]*$", href))
        return f'<li><a href="{e(rel + href)}">{e(t["text"])}</a></li>' if ok else f'<li>{e(t["text"])}</li>'

    todo = "".join(todo_li(t) for t in b.get("todo", []) if t.get("text"))
    lead = f'<p class="br-lead">{e(b["lead"])}</p>' if b.get("lead") else ""
    todo_sec = f'<section class="br-todo"><h3>이번 주 챙길 일</h3><ul class="bul">{todo}</ul></section>' if todo else ""
    return (f'{lead}{"".join(item(it) for it in b["items"])}{todo_sec}'
            f'<p class="src-note">{BRIEF_PENDING if b.get("review") != "verified" else ""}SafePlum이 공식 원문을 요약한 참고 콘텐츠입니다. 원문을 옮겨 싣지 않으며, 숫자·조문·시행일은 공식 출처 원문이 우선합니다. '
            f'국회 통과안·입법예고 내용은 공포·시행 때 확정됩니다. 확인일 {fmt_date(b.get("checked") or b["date"])}</p>')


BILL_STAGE_NOTE = {
    "입법예고": "입법예고 단계입니다. 의견 수렴·심사 과정에서 내용이 바뀔 수 있고, 공포·시행 때 확정됩니다.",
    "국회 통과": "국회를 통과했지만 아직 공포 전입니다. 조문 번호와 시행일은 공포문으로 확정되고, 대통령령에 맡긴 내용(금액·대상 등)은 하위법령이 나와야 알 수 있습니다.",
    "시행 예정": "공포를 마치고 시행을 기다리는 내용입니다. 시행일 전까지 준비하세요.",
    "시행 중": "이미 시행 중인 내용입니다.",
}


def write_bills(site, write, B):
    """입법예고·개정 포인트: 개정 사항 하나를 한 글로 — 현행·개정 비교, 왜 바뀌나, 준비할 것, 묻고 답하기, 출처."""
    posts = [x for x in B.get("posts", []) if x.get("slug") and x.get("title") and x.get("lead")]
    if not posts:
        return
    order = {"입법예고": 0, "국회 통과": 1, "시행 예정": 2, "시행 중": 3}
    chk = fmt_date(B.get("checked", ""))
    css = """<style>
.bl-list{list-style:none;margin:0;padding:0;border-top:2px solid var(--text)}.bl-list li{border-bottom:1px solid var(--line)}
.bl-list a{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:14px 4px;color:var(--text);text-decoration:none}.bl-list a:hover .bl-t{text-decoration:underline}
.bl-list .lst{grid-row:span 2;align-self:start;margin-top:2px}.bl-t{font-weight:800;font-size:16px;line-height:1.45}.bl-d{font-size:13.5px;color:var(--text-2);line-height:1.55}
.bl-cmp{width:100%;border-collapse:collapse;margin:8px 0 4px;font-size:14.5px;line-height:1.6}.bl-cmp th,.bl-cmp td{border:1px solid var(--line);padding:10px 12px;vertical-align:top;text-align:left}
.bl-cmp thead th{background:var(--surface-2,#F4F6F9);font-size:13.5px}.bl-cmp td:last-child{background:#F5F9FF}.bl-cmp ul{margin:0;padding-left:18px}
.bl-sec{margin-top:26px}.bl-sec h2{font-size:18px;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.bl-facts{display:grid;grid-template-columns:110px 1fr;gap:6px 12px;margin:10px 0 0;font-size:14.5px}.bl-facts dt{font-weight:800;color:var(--text-2)}.bl-facts dd{margin:0}
.bl-note{background:#FFF7E6;border:1px solid #F5D9A8;border-radius:10px;padding:10px 12px;font-size:13.5px;color:#7a4a00;margin-top:12px}
.bl-todo li{margin:4px 0}.bl-faq dt{font-weight:800;margin-top:10px}.bl-faq dd{margin:4px 0 0}
@media (max-width:1023px){.layout-detail.bl-layout .col-side{order:2}}
@media (max-width:600px){.bl-cmp,.bl-cmp tbody,.bl-cmp tr,.bl-cmp td{display:block;width:100%}.bl-cmp thead{display:none}.bl-cmp td{border-top:0}.bl-cmp td:first-child{border-top:1px solid var(--line)}
.bl-cmp td:before{content:attr(data-h);display:block;font-weight:800;font-size:12.5px;color:var(--text-2);margin-bottom:2px}.bl-facts{grid-template-columns:1fr}.bl-facts dt{margin-top:6px}}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .bl-cmp td:last-child{background:#16213A}:root:not([data-theme="light"]) .bl-note{background:#2A2110;border-color:#5C4720;color:#F5D9A8}}
:root[data-theme="dark"] .bl-cmp td:last-child{background:#16213A}:root[data-theme="dark"] .bl-note{background:#2A2110;border-color:#5C4720;color:#F5D9A8}
</style>"""
    posts = sorted(posts, key=lambda x: (order.get(x["stage"], 9), x["date"]), reverse=False)

    def stage(x):
        return f'<span class="lst {BRIEF_STAGE.get(x["stage"], "lst-rec")}">{e(x["stage"])}</span>'

    rows = "".join(f'<li><a href="{e(x["slug"])}/">{stage(x)}<span class="bl-t">{e(x["title"])}</span><span class="bl-d">{e(x.get("effective", ""))}</span></a></li>' for x in posts)
    blog = (f'<p class="hint">같은 내용을 <a href="{e(BLOG["url"])}" target="_blank" rel="noopener">SafePlum 네이버 블로그 ↗</a>에도 올립니다.</p>' if BLOG else "")
    side = (f'<aside class="col-side stack"><div class="side-box"><h2 class="h-sm">단계 표시</h2><ul class="bul hint">'
            + "".join(f"<li><b>{k}</b> — {v}</li>" for k, v in BILL_STAGE_NOTE.items()) +
            '</ul></div><div class="side-box"><h2 class="h-sm">함께 보기</h2><ul class="bul"><li><a href="{up}laws/#upcoming">시행 예정 법령</a></li><li><a href="{up}brief/?c=%EC%9E%85%EB%B2%95%EC%98%88%EA%B3%A0">입법예고 소식(브리핑)</a></li><li><a href="{up}laws/qa/">고용노동부 질의회시</a></li></ul></div></aside>')
    head = ('<section class="phead"><div class="wrap"><p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">법령</a><span>/</span>입법예고·개정 포인트</p>'
            '<h1>입법예고·개정 포인트</h1><p>입법예고되거나 국회를 통과한 산업안전보건 법령 개정 사항을 한 가지씩 풀어 씁니다. 무엇이 바뀌는지(현행·개정 비교), 언제부터인지, 현장에서 무엇을 준비할지를 정리하고 공식 출처를 붙였습니다.</p></div></section>')
    write("laws/bills/index.html", page(site, "../../", "laws/bills/", "입법예고·개정 포인트",
          css + head + f'<div class="wrap layout-detail bl-layout"><section class="col-main"><ul class="bl-list">{rows}</ul>{blog}<p class="src-note">SafePlum이 공식 발표·법령 원문과 법무법인 분석 자료를 바탕으로 쓴 해설입니다. 원문을 옮겨 싣지 않으며, 법적 판단이 필요하면 원문과 고용노동부 상담(국번 없이 1350)으로 확인하세요. 확인일 {chk}</p></section>{side.format(up="../../")}</div>',
          desc="산업안전보건법 입법예고·국회 통과 개정안을 포인트별로 정리 — 신고포상금, 작업중지권 확대, 사망사고 과징금, 위험성평가 과태료 등 시행일과 준비사항.", active="laws/"))
    for i, x in enumerate(posts):
        cmp_rows = max(len(x.get("before", [])), 1)
        ul = lambda L: "<ul>" + "".join(f"<li>{e(t)}</li>" for t in L) + "</ul>" if L else "—"
        tools = "".join(f'<li><a href="../../../{e(h)}">{e(n)}</a></li>' for n, h in x.get("tools", []))
        srcs = "".join(f'<li><a class="link-ext" href="{e(safe_url(u))}" target="_blank" rel="noopener{"" if is_official(u) else " nofollow"}">{e(n)} ↗</a>{"" if is_official(u) else " <span class=muted>(참고 자료)</span>"}</li>' for n, u in x.get("sources", []) if safe_url(u))
        faq = "".join(f"<dt>Q. {e(q)}</dt><dd>{e(a)}</dd>" for q, a in x.get("faq", []))
        prev = posts[i - 1] if i > 0 else None
        nxt = posts[i + 1] if i + 1 < len(posts) else None
        nav = "".join(f'<a class="bdn-{k}" href="../{y["slug"]}/"><span>{lab}</span>{e(y["title"])}</a>' for k, lab, y in (("prev", "← 이전 글", prev), ("next", "다음 글 →", nxt)) if y)
        body = (css + '<section class="phead"><div class="wrap"><p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">법령</a><span>/</span><a href="../">입법예고·개정 포인트</a></p>'
                f'<p class="bdm">{stage(x)}<time datetime="{e(x["date"])}">{fmt_date(x["date"])}</time></p><h1>{e(x["title"])}</h1><p>{e(x["lead"])}</p></div></section>'
                '<div class="wrap layout-detail bl-layout"><section class="col-main"><article class="bdv">'
                f'<dl class="bl-facts"><dt>단계</dt><dd>{e(x["stage"])}</dd><dt>시행 시기</dt><dd>{e(x.get("effective", ""))}</dd><dt>관련 조문</dt><dd>{e(x.get("law", ""))}</dd></dl>'
                f'<p class="bl-note">{e(BILL_STAGE_NOTE.get(x["stage"], ""))}</p>'
                f'<section class="bl-sec"><h2>무엇이 바뀌나</h2><table class="bl-cmp"><thead><tr><th style="width:45%">지금(현행)</th><th>바뀌는 내용</th></tr></thead><tbody><tr><td data-h="지금(현행)">{ul(x.get("before", []))}</td><td data-h="바뀌는 내용">{ul(x.get("after", []))}</td></tr></tbody></table></section>'
                f'<section class="bl-sec"><h2>왜 바뀌나</h2><p>{e(x.get("why", ""))}</p></section>'
                f'<section class="bl-sec"><h2>핵심 포인트</h2>{ul(x.get("points", []))}</section>'
                f'<section class="bl-sec"><h2>현장에서 준비할 것</h2><ol class="bl-todo">' + "".join(f"<li>{e(t)}</li>" for t in x.get("todo", [])) + '</ol></section>'
                + (f'<section class="bl-sec"><h2>자주 묻는 질문</h2><dl class="bl-faq">{faq}</dl></section>' if faq else "")
                + (f'<section class="bl-sec"><h2>SafePlum 무료 작성기로 준비하기</h2><ul class="bul">{tools}</ul></section>' if tools else "")
                + f'<section class="bl-sec"><h2>출처</h2><ul class="bul">{srcs}</ul></section>'
                f'<p class="src-note">SafePlum이 공식 발표·법령 원문과 법무법인 분석 자료를 바탕으로 쓴 해설입니다. 원문을 옮겨 싣지 않았고, 법적 판단이 필요하면 원문을 확인하세요. 확인일 {chk}</p>'
                + (f'<nav class="bdn" aria-label="이전·다음 글">{nav}</nav>' if nav else "")
                + f'</article></section>{side.format(up="../../../")}</div>')
        write(f"laws/bills/{x['slug']}/index.html", page(site, "../../../", f"laws/bills/{x['slug']}/", x["title"], body,
              desc=f'{x["stage"]} · {x.get("effective", "")} — {x["lead"]}'[:150], active="laws/"))


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
        if not safe_url(j.get("source_url")) and not str(j.get("apply", "")).strip():
            warn(f"채용 {jid}: 공고 원문 주소(https)도 지원 방법도 없어 제외")
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
        r["href"] = form_url(r["law"], r["byl_no"], r.get("byl_br", "00"), r.get("byl_cls", "BF"))
        r["law_href"] = law_url(r["law"])
    else:
        r["href"] = safe_url(r.get("url"))
        r["law_href"] = ""
    return r



# ---------------------------------------------------------------- 법령 별표·서식 목록
LF_RE = re.compile(r"^\[(별지|별표)\s*(?:제)?(\d+)(?:호)?(?:의(\d+))?(?:서식)?\]\s*(.+)$")
# 사업장(사업주·안전관리자)이 직접 작성·제출하는 별지. 나머지는 기관·지도사·행정청용으로 분류
LF_WORKPLACE = {"산업안전보건법 시행규칙": {"1", "2", "3", "3-2", "5", "15", "16", "17", "18", "29", "30", "31", "32", "33", "35", "36", "39",
                                           "42", "43", "48", "50", "52", "57", "60", "61", "63", "65", "70", "72", "74", "77", "78",
                                           "80", "82", "83", "84", "85", "86", "88", "100", "101", "102", "103", "104"},
                "산업안전보건기준에 관한 규칙": {"3", "4"}}
LF_TOPICS = [("위험성평가·TBM", ["위험성평가", "TBM", "아차사고"]),
             ("재해·중대재해", ["산업재해", "중대재해", "작업중지", "사고"]),
             ("표지", ["표지"]),
             ("교육", ["교육"]),
             ("선임·관리체제", ["선임", "해임", "관리자", "관리 업무", "관리규정", "업무계약", "책임자", "위원회", "관리감독자"]),
             ("점검·작업허가", ["점검", "작업허가"]),
             ("작업계획서", ["작업계획"]),
             ("유해위험방지계획서", ["유해위험방지계획서", "공사 개요서", "자체심사"]),
             ("도급·건설", ["도급", "공사", "건설", "설계변경", "기술지도", "관리비", "타워크레인", "대여", "비계", "굴착"]),
             ("기계·설비 인증·검사", ["안전인증", "자율안전", "안전검사", "자율검사", "제조업체", "제조사업", "합격표시", "방호조치", "기계ㆍ기구"]),
             ("화학물질·석면", ["화학물질", "물질안전보건자료", "금지물질", "허가대상", "허가신청", "석면", "유해성", "위험물질", "화학설비", "유해물질", "안전거리"]),
             ("작업환경·건강", ["작업환경", "건강진단", "건강관리", "휴게", "유해인자", "노출", "사후관리", "분진", "밀폐공간", "체감온도"]),
             ("평가·진단·행정", ["평가", "진단", "명령", "과징금", "과태료", "행정처분", "보증보험", "적용하지", "확인 결과", "확인결과", "심사결과"]),
             ("기관·지도사", ["지정", "지도사", "교육기관", "등록"])]
WF_TOPIC = {"교육·회의": "교육", "점검·허가": "점검·작업허가", "작업계획서": "작업계획서", "조직·발령": "선임·관리체제",
            "관리대장": "기타", "중대재해처벌법 이행": "재해·중대재해", "작업시작 전 점검(별표 3)": "점검·작업허가"}
LF_INSTITUTION = ["인력ㆍ시설", "지도사", "지정신청", "지정서", "등록증", "기관(등록", "기관 등록"]
LF_TOOLS = {("산업안전보건법 시행규칙", "별표", "4", "00"): "edu-hours", ("산업안전보건법 시행규칙", "별표", "2", "00"): "selection",
            ("산업안전보건법 시행규칙", "별표", "6", "00"): "@signs", ("산업안전보건법 시행규칙", "별지", "102", "00"): "safety-cost",
            ("산업안전보건법 시행령", "별표", "2", "00"): "selection", ("산업안전보건법 시행령", "별표", "3", "00"): "selection",
            ("산업안전보건법 시행령", "별표", "5", "00"): "selection", ("산업안전보건법 시행령", "별표", "9", "00"): "selection",
            ("산업안전보건법 시행령", "별표", "35", "00"): "penalty"}


def lawform_resources(existing):
    have = {(r.get("law"), r.get("byl_no"), r.get("byl_br", "00"), r.get("byl_cls", "BF")) for r in existing if r.get("byl_no")}
    data, out = load("data/lawforms.json"), []
    for lw in data["laws"]:
        law = lw["law"]
        for t in lw["items"]:
            m = LF_RE.match(t)
            if not m:
                warn(f"법령 서식 목록: 형식을 읽지 못함 ({t[:40]})")
                continue
            kind, no, br, title = m.group(1), m.group(2), m.group(3) or "", m.group(4).strip()
            cls = "BE" if kind == "별표" else "BF"
            byl_no, byl_br = no.zfill(4), (br or "0").zfill(2)
            if (law, byl_no, byl_br, cls) in have:
                continue
            rel = ""
            mr = re.search(r"\((제\d+조[^()]*?)\s*관련\)$", title)
            if mr:
                rel, title = mr.group(1), title[:mr.start()].strip()
            mp = re.match(r"^[(\[]([^()\[\]]{1,80})[)\]]\s*(.+)$", title)
            if mp:
                title = f"{mp.group(2).strip()}({re.sub(r', *', '·', mp.group(1).strip())})"
            title = re.sub(r"\s*ㆍ\s*", "·", title)
            label = f"{kind} 제{no}호" + (f"의{br}" if br else "") + ("서식" if kind == "별지" else "")
            key = no + (f"-{br}" if br else "")
            inst = any(k in title for k in LF_INSTITUTION)
            topic = "기관·지도사" if inst else next((tp for tp, kws in LF_TOPICS if any(k in title for k in kws)), "기타")
            if inst:
                cat, aud = "기관·행정용", "기관"
            elif kind == "별표":
                cat, aud = "법정 기준표(별표)", "기준표"
            elif key in LF_WORKPLACE.get(law, set()):
                cat, aud = "법정 서식", "사업장"
            else:
                cat, aud = "기관·행정용", "기관"
            tool = LF_TOOLS.get((law, kind, no, byl_br))
            out.append({"id": "lf-" + ("t" if kind == "별표" else "f") + key + "-" + str(lw.get("lsiSeq", "")),
                        "category": cat, "title": title, "law": law, "form_no": label, "byl_no": byl_no, "byl_br": byl_br,
                        "byl_cls": cls, "summary": "", "rel": rel, "topic": topic, "aud": aud,
                        "tags": [topic], "free_tool": tool if tool and not tool.startswith("@") else "",
                        "page_link": "resources/signs/" if tool == "@signs" else ""})
    return out


SITUATIONS = [
    ("재해가 났을 때", "재해·중대재해", "조사표 제출, 작업중지 해제, 중대재해 대응"),
    ("선임·조직을 갖출 때", "선임·관리체제", "관리자 선임·해임 보고, 책임자·위원회 대상"),
    ("교육을 할 때", "교육", "교육시간·내용 기준, 교육일지"),
    ("작업 전 점검·허가", "점검·작업허가", "작업시작 전 점검표, 작업허가"),
    ("위험성평가·TBM", "위험성평가·TBM", "위험성평가서, TBM 일지, 지침"),
    ("도급·건설공사", "도급·건설", "도급승인, 공사기간·설계변경, 안전보건관리비"),
    ("기계·설비 검사", "기계·설비 인증·검사", "안전인증·안전검사·자율검사"),
    ("화학물질·석면", "화학물질·석면", "MSDS 비공개, 허가물질, 석면해체"),
    ("작업환경측정·건강진단", "작업환경·건강", "측정 결과, 건강진단 결과, 휴게시설"),
]
CAT_RANK = {"무료 작성 도구": 0, "웹 작성 서식": 1, "법정 서식": 2, "고시·지침": 3, "법정 기준표(별표)": 4}


SIT_TOOLS = {"재해·중대재해": [], "선임·관리체제": ["selection", "duties", "committee"], "교육": ["edu-hours"], "점검·작업허가": ["improve", "docmap", "inspect", "loto", "rule-sign", "top-rules"],
             "위험성평가·TBM": ["risk", "tbm"], "도급·건설": ["council", "safety-cost", "cost-use", "hpp"], "기계·설비 인증·검사": ["machines", "gear-cert", "inspect"],
             "화학물질·석면": ["msds"], "작업환경·건강": ["heat", "confined", "cvd"]}


def situation_cards(resources, rel, tools=None):
    out = []
    by = {t["id"]: t for t in (tools or [])}
    for title, topic, sub in SITUATIONS:
        items = [r for r in resources if r.get("topic") == topic and r.get("category") in CAT_RANK]
        tl = [by[i] for i in SIT_TOOLS.get(topic, []) if i in by]
        if not items and not tl:
            continue
        items.sort(key=lambda r: (0 if r.get("popular") else 1, CAT_RANK[r["category"]]))
        lis = "".join(
            f'<li><a href="{rel}{e(r["detail"]) if r.get("detail") else "tools/" + e(r.get("free_tool","")) + "/"}">{e(r["title"])}</a></li>'
            for r in items[:max(1, 4 - len(tl))] if r.get("detail") or r.get("free_tool"))
        lis = "".join(f'<li><a href="{rel}tools/{e(t["id"])}/">{e(t.get("menu") or t["name"])} <span class="sit-tool">도구</span></a></li>' for t in tl) + lis
        n = sum(1 for r in resources if r.get("topic") == topic)
        out.append(f'<section class="sit"><h3>{e(title)}</h3><p class="sit-sub">{e(sub)}</p><ul>{lis}</ul>'
                   f'<a class="sit-all" href="?topic={quote(topic)}" data-topic-go="{e(topic)}">{n}건 모두 보기 →</a></section>')
    return "".join(out)


# ---------------------------------------------------------------- 서식·별표 상세 페이지
def write_lawai(out):
    """법령 AI 질문(tools/law-ai)이 브라우저에서 내려받아 검색하는 조문 묶음. 개정 표시(<개정 …>)는 빼고 본문만 담는다."""
    tag = re.compile(r"\s*<(?:개정|신설|전문개정|본조신설|제목개정|종전[^>]*|삭제)[^>]*>")
    laws, arts = [], []
    for i, (k, _n) in enumerate(LAW_MENU):
        d = load(f"data/lawtext/{k}.json")
        laws.append({"key": k, "law": d["law"], "short": d["short"], "version": d.get("version", ""), "url": d.get("url", "")})
        for a in d["articles"]:
            t = tag.sub("", a.get("text") or "").strip()
            if not t or (t.startswith("삭제") and len(t) < 40):
                continue
            arts.append([i, a["jo"], a.get("title") or "", t])
    pen = load("data/penalties.json")
    laws.append({"key": "pen", "law": "산안법 시행령 별표 35 과태료 부과기준", "short": "과태료 기준", "version": pen.get("version", ""), "url": pen.get("source_url", "")})
    pi = len(laws) - 1
    for it in pen["items"]:
        a = it.get("a") or ["", "", ""]
        arts.append([pi, "별표35 " + it["c"], "과태료", f'{it["v"]} — 근거 {it["b"]} · 과태료(만원) 1차 {a[0]} / 2차 {a[1]} / 3차 이상 {a[2]}'])
    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "assets/lawai.json").write_text(json.dumps({"laws": laws, "arts": arts}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def law_index():
    """법령명 → {조번호: (제목, 본문)}. data/lawtext/*.json(전문) + data/lawref.json(개별 조문)을 합친다."""
    idx = {}
    for fp in sorted((ROOT / "data/lawtext").glob("*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        idx.setdefault(d["law"], {})
        for a in d["articles"]:
            idx[d["law"]][a["jo"]] = (a["title"], a["text"], d.get("checked", ""))
    for v in load("data/lawref.json")["laws"].values():
        for k, txt in v["articles"].items():
            m = re.match(r"(제\d+조(?:의\d+)?)\(([^)]*)\)\s*", k)
            if m and m.group(1) not in idx.setdefault(v["law"], {}):
                body = re.sub(r"^제\d+조(?:의\d+)?\([^)]*\)\s*", "", txt)
                idx[v["law"]][m.group(1)] = (m.group(2), body, load("data/lawref.json").get("checked", ""))
    return idx


def byl_pattern(r):
    no, br = int(r["byl_no"]), int(r.get("byl_br") or 0)
    if r.get("byl_cls") == "BE":
        return re.compile(rf"별표\s*{no}" + (rf"의{br}" if br else r"(?![\d의])"))
    return re.compile(rf"별지\s*제\s*{no}호" + (rf"의{br}\s*서식" if br else r"(?:의\s+|\s*)서식"))


def byl_refs(r, idx):
    arts = idx.get(r.get("law"), {})
    pat, hits = byl_pattern(r), []
    rel = re.findall(r"제\d+조(?:의\d+)?", r.get("rel", ""))
    for jo, (title, text, ck) in arts.items():
        if pat.search(text) or jo in rel:
            hits.append({"jo": jo, "title": title, "text": text, "checked": ck, "direct": bool(pat.search(text))})
    hits.sort(key=lambda h: (not h["direct"], [int(x) for x in re.findall(r"\d+", h["jo"])]))
    missing = [j for j in rel if j not in arts]
    return hits, missing, pat


def article_html(h, pat, law):
    paras = [p for p in h["text"].split("\n") if p.strip()]
    def fmt(p):
        return pat.sub(lambda m: f"<mark>{e(m.group(0))}</mark>", e(p)) if pat.search(p) else e(p)
    key = [i for i, p in enumerate(paras) if pat.search(p)] or list(range(min(2, len(paras))))
    shown = "".join(f"<p>{fmt(paras[i])}</p>" for i in key[:4])
    full = "".join(f"<p>{fmt(p)}</p>" for p in paras)
    more = f'<details class="art-more"><summary>조문 전체 보기</summary><div class="art-full">{full}</div></details>' if len(paras) > len(key[:4]) else ""
    link = law_url(law) + "/" + quote(h["jo"])
    return (f'<article class="art"><h3>{e(law)} {e(h["jo"])}({e(h["title"])})'
            f' <a class="art-src" href="{e(link)}" target="_blank" rel="noopener">원문 ↗</a></h3>{shown}{more}</article>')


def dl_name(r, ext):
    short = re.sub(r"\s*\(.*$", "", r.get("law", "")).replace("산업안전보건법 ", "")
    return re.sub(r'[\\/:*?"<>|]', "", f'[{r.get("form_no","")}] {r["title"]}({short}).{ext}')[:150]


def resource_detail(r, all_res, idx, files, site):
    rel_root = "../../../"
    hits, missing, pat = byl_refs(r, idx)
    kind = "별표" if r.get("byl_cls") == "BE" else "서식"
    fkey = f'{r["law"]}|{r.get("byl_cls","BF")}|{r["byl_no"]}|{r.get("byl_br","00")}'
    fl = files.get(fkey) or {}
    dl = "".join(f'<a class="btn btn-block{" btn-ghost" if i else ""}" href="{rel_root}{e(v["path"])}" download="{e(dl_name(r, k))}">{e(k.upper())} 내려받기 <span class="dl-size">{round(v["bytes"]/1024)}KB</span></a>'
                 for i, (k, v) in enumerate(sorted(fl.get("files", {}).items(), key=lambda kv: kv[0] != "hwp")))
    tool = ""
    if r.get("free_tool"):
        tool = f'<a class="btn btn-block btn-green" href="{rel_root}tools/{e(r["free_tool"])}/">SafePlum 도구로 바로 계산·작성</a>'
    if r.get("page_link"):
        tool = f'<a class="btn btn-block btn-green" href="{rel_root}{e(r["page_link"])}">SafePlum에서 바로 보기</a>'
    same = [x for x in all_res if x is not r and x.get("topic") == r.get("topic") and x.get("category") not in ("기관·행정용",)][:8]
    def rel_href(x):
        return rel_root + (x["detail"] if x.get("detail") else "tools/" + x.get("free_tool", "") + "/")
    same_html = "".join(
        f'<li><a href="{e(rel_href(x))}"><span class="badge badge-line">{e(x["category"])}</span>'
        f'<strong>{e(x["title"])}</strong><span class="muted">{e(x.get("form_no", ""))}</span></a></li>'
        for x in same if x.get("detail") or x.get("free_tool"))
    if hits:
        arts = "".join(article_html(h, pat, r["law"]) for h in hits[:6])
        arts_note = f'<p class="src-line">조문 원문: 국가법령정보센터, 확인일 {e(hits[0]["checked"])}. 이 {kind}를 직접 언급한 문장은 <mark>표시</mark>했습니다.</p>'
    else:
        arts, arts_note = "", ""
    if missing:
        arts += (f'<p class="hint">{e(", ".join(missing))} 원문은 아직 SafePlum에 수록하지 않았습니다. '
                 f'<a href="{e(law_url(r["law"]))}" target="_blank" rel="noopener">국가법령정보센터에서 {e(r["law"])} 보기 ↗</a></p>')
    elif not hits:
        full = r.get("law") in idx and len(idx[r["law"]]) > 50
        msg = (f'{r["law"]} 본문에는 이 {kind}를 직접 언급한 조문이 없습니다. 고용노동부 고시 등 다른 규정에서 쓰도록 정한 {kind}일 수 있습니다.'
               if full else "관련 조문 원문은 아직 SafePlum에 수록하지 않았습니다.")
        arts += (f'<p class="hint">{e(msg)} '
                 f'<a href="{e(law_url(r["law"]))}" target="_blank" rel="noopener">국가법령정보센터에서 {e(r["law"])} 보기 ↗</a></p>')
    meta = [("법령", r["law"]), ("번호", r.get("form_no", "")), ("분류", r.get("category", "")), ("주제", r.get("topic", ""))]
    if r.get("rel"):
        meta.append(("관련 조문", r["rel"]))
    if r.get("verified"):
        meta.append(("원본 확인", fmt_date(r["verified"])))
    dlg = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in meta if v)
    summary = f'<section class="block"><h2>이런 때 씁니다</h2><p>{e(r["summary"])}</p></section>' if r.get("summary") else ""
    file_note = (f'<p class="hint">국가법령정보센터 첨부파일을 그대로 옮긴 것입니다(확인일 {e(load("data/lawfiles.json")["checked"])}). 법령이 개정되면 원본 화면의 최신본을 쓰세요.</p>' if dl
                 else '<p class="hint">HWP·PDF 파일은 원본 화면에서 받을 수 있습니다.</p>')
    body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="{rel_root}">홈</a><span>/</span><a href="{rel_root}resources/">서식·자료</a><span>/</span>{e(r.get("form_no",""))}</p>
  <p class="rrow-top"><span class="badge badge-blue">{e(r.get("category",""))}</span><span class="rrow-meta">{e(r["law"])} · {e(r.get("form_no",""))}</span></p>
  <h1>{e(r["title"])}</h1>
</div></section>
<div class="wrap layout-detail">
  <article class="col-main">
    {summary}
    <section class="block"><h2>기본 정보</h2><dl class="dl-grid">{dlg}</dl></section>
    <section class="block"><h2>근거 조문</h2>{arts}{arts_note}</section>
    {f'<section class="block"><h2>같은 주제의 서식·자료</h2><ul class="rel-list">{same_html}</ul></section>' if same_html else ''}
  </article>
  <aside class="col-side">
    <div class="apply-card">
      <p class="apply-label">원본</p>
      {dl}
      <a class="btn btn-block{" btn-ghost" if dl else ""}" href="{e(r["href"])}" target="_blank" rel="noopener">국가법령정보센터 원본 {"보기" if dl else "열기"} ↗</a>
      {tool}
      {file_note}
      <button class="btn btn-block btn-ghost fav-big" type="button" data-fav="{e(r["id"])}" aria-pressed="false">☆ 즐겨찾기</button>
      <p class="hint">법령 서식은 누구나 무료로 내려받아 쓸 수 있습니다. 개정되면 원본 버튼이 최신본을 엽니다.</p>
    </div>
  </aside>
</div>"""
    return body


# ---------------------------------------------------------------- 공단 자료실(공공누리) 목록
KM_TOPICS = [
    ("추락", ["추락", "떨어짐", "비계", "사다리", "안전난간", "고소", "지붕", "개구부", "작업발판"]),
    ("끼임", ["끼임", "협착", "말림", "컨베이어", "프레스", "롤러", "정비", "혼합기", "파쇄"]),
    ("부딪힘·맞음", ["부딪힘", "충돌", "맞음", "낙하", "비래"]),
    ("화재·폭발", ["화재", "폭발", "화기", "용접", "용단", "인화"]),
    ("질식·밀폐공간", ["질식", "밀폐", "황화수소", "산소결핍", "중독"]),
    ("감전", ["감전", "전기", "활선"]),
    ("붕괴·무너짐", ["붕괴", "무너짐", "굴착", "흙막이", "거푸집", "동바리", "해체"]),
    ("지게차·중장비", ["지게차", "크레인", "고소작업대", "굴착기", "차량", "건설기계", "양중"]),
    ("화학물질·MSDS", ["화학", "MSDS", "물질안전", "유해물질", "경고표지", "GHS", "유기용제"]),
    ("폭염·온열", ["폭염", "온열", "열사병", "더위"]),
    ("한파·겨울철", ["한파", "한랭", "동절기", "겨울", "해빙"]),
    ("건강·직업병", ["근골격", "요통", "뇌심", "건강", "직무스트레스", "소음", "분진", "직업병", "감정노동"]),
    ("위험성평가·TBM", ["위험성평가", "TBM", "아차"]),
    ("중대재해", ["중대재해", "SIF", "사망사고"]),
    ("재해사례", ["사고사례", "재해사례", "사례 전파", "사고 사례", "사례집"]),
    ("우수사례", ["우수사례", "선진사례", "모범사례", "우수 사례"]),
    ("가이드·매뉴얼", ["가이드", "매뉴얼", "지침", "길잡이", "안내서"]),
    ("점검표", ["체크리스트", "점검표", "자가진단", "자율점검"]),
    ("보호구", ["보호구", "안전모", "안전대", "방진마스크", "호흡보호"]),
    ("외국인", ["외국인", "다국어", "이주"]),
    ("건설업", ["건설"]),
    ("농림·서비스", ["벌목", "예초", "농작업", "조리", "급식", "환경미화", "택배", "배달", "청소"]),
]


def build_kosha_client(out_dir):
    """data/kosha_media.json → assets/data/kosha.json (열 단위 압축, 주제 태그 포함)."""
    d = load("data/kosha_media.json")
    shapes, langs, cols = [], [], {k: [] for k in ("s", "n", "k", "g", "f", "dt", "h", "no", "la", "th", "t")}
    for x in d["items"]:
        if x["f"] not in shapes:
            shapes.append(x["f"])
        la = x.get("lang", "")
        if la and la not in langs:
            langs.append(la)
        probe = x["n"] + " " + x["k"] + " " + la
        tags = [i for i, (_, kws) in enumerate(KM_TOPICS) if any(k in probe for k in kws)]
        for k, v in (("s", x["s"]), ("n", x["n"]), ("k", x["k"]), ("g", x["g"]), ("f", shapes.index(x["f"])),
                     ("dt", x["dt"]), ("h", x["h"]), ("no", x["no"]), ("la", langs.index(la) if la else -1), ("th", x["th"]), ("t", tags)):
            cols[k].append(v)
    client = {"checked": d["checked"], "total_all": d["total_all"], "shapes": shapes, "langs": langs,
              "topics": [t for t, _ in KM_TOPICS], "cols": cols}
    (out_dir / "assets/data").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets/data/kosha.js").write_text("window.ANJEONDUCK_KOSHA=" + json.dumps(client, ensure_ascii=False, separators=(",", ":")) + ";", encoding="utf-8")
    return len(d["items"])


# ---------------------------------------------------------------- 서식 자동화(자동 채우기·계산) 데이터
def edu_auto():
    """교육일지: 교육과정 → 법정 교육시간(규칙 별표 4)·교육내용(별표 5)."""
    ec, eh = load("data/edu_contents.json"), load("data/edu_hours.json")
    sec = {s["id"]: s for s in eh["sections"]}

    # 별표 4 행을 요약한 문구(원문: data/edu_hours.json). 기준이 바뀌면 이 표와 함께 고칠 것
    half = " ※ 영 별표 1 제1호 사업, 상시 50명 미만 도매업·숙박 및 음식점업은 교육시간의 2분의 1 이상"
    H = {
        ("worker", "가."): "사무직·판매업무 직접 종사 근로자: 매반기 6시간 이상 / 그 밖의 근로자: 매반기 12시간 이상" + half,
        ("worker", "나."): "일용·근로계약 1주일 이하 기간제: 1시간 이상 / 1주일 초과 1개월 이하 기간제: 4시간 이상 / 그 밖의 근로자: 8시간 이상" + half,
        ("worker", "다."): "일용·근로계약 1주일 이하 기간제: 1시간 이상 / 그 밖의 근로자: 2시간 이상" + half,
        ("worker", "라."): "일용·근로계약 1주일 이하 기간제: 2시간 이상(제39호 타워크레인 신호작업은 8시간 이상) / 그 밖의 근로자: 16시간 이상(최초 작업 전 4시간 이상, 12시간은 3개월 이내 분할 가능), 단기간·간헐적 작업은 2시간 이상" + half,
        ("worker", "마."): "건설 일용근로자: 4시간 이상",
        ("supervisor", "가."): "연간 16시간 이상" + half,
        ("supervisor", "나."): "8시간 이상" + half,
        ("supervisor", "다."): "2시간 이상" + half,
        ("supervisor", "라."): "16시간 이상(최초 작업 전 4시간 이상, 12시간은 3개월 이내 분할 가능), 단기간·간헐적 작업은 2시간 이상" + half,
    }
    for (sid, pre) in H:  # 요약이 원문 행과 어긋나지 않았는지 최소 점검
        assert any(r["course"].startswith(pre) for r in sec[sid]["rows"]), (sid, pre)

    def hours(sid, course_prefix):
        return H[(sid, course_prefix)]

    def body(title, items):
        return f"【{title} — 시행규칙 별표 5】\n" + "\n".join("○ " + x for x in items)
    src = "시행규칙 별표 5"
    courses = [
        ("근로자 정기교육", hours("worker", "가."), body("근로자 정기교육 교육내용", ec["worker_regular"])),
        ("근로자 채용 시 교육", hours("worker", "나."), body("채용 시 교육 교육내용", ec["worker_hire"])),
        ("근로자 작업내용 변경 시 교육", hours("worker", "다."), body("작업내용 변경 시 교육 교육내용", ec["worker_hire"])),
        ("근로자 특별교육", hours("worker", "라."), body("특별교육 공통내용(채용 시 교육과 같은 내용)", ec["worker_hire"]) + "\n※ 아래에서 특별교육 대상 작업을 고르면 개별내용이 추가됩니다."),
        ("관리감독자 정기교육", hours("supervisor", "가."), body("관리감독자 정기교육 교육내용", ec["sup_regular"])),
        ("관리감독자 채용 시 교육", hours("supervisor", "나."), body("관리감독자 채용 시 교육 교육내용", ec["sup_hire"])),
        ("관리감독자 작업내용 변경 시 교육", hours("supervisor", "다."), body("관리감독자 작업내용 변경 시 교육 교육내용", ec["sup_hire"])),
        ("관리감독자 특별교육", hours("supervisor", "라."), body("관리감독자 특별교육 공통내용", ec["sup_hire"]) + "\n※ 아래에서 특별교육 대상 작업을 고르면 개별내용이 추가됩니다."),
        ("건설업 기초안전보건교육", hours("worker", "마."), "【건설업 기초안전보건교육 — 시행규칙 별표 5 제2호】\n" + "\n".join(f"○ {t} ({h})" for t, h in ec["construction_basic"])),
    ]
    course_picker = {"id": "course", "label": "교육과정", "target": "f.course",
                     "hint": "고르면 법정 교육시간(별표 4)과 교육내용(별표 5)이 들어갑니다. 사업장에 맞게 고쳐 쓰세요.",
                     "options": [{"label": c, "set": {"f.req": h, "x.content": b}} for c, h, b in courses]}
    special = []
    for sp in ec["special"]:
        short = re.sub(r"\(.*", "", sp["name"]).strip()
        short = (short[:34] + "…") if len(short) > 35 else short
        add = f'\n\n【특별교육 개별내용 — 별표 5 제1호라목 제{sp["no"]}호: {sp["name"]}】\n' + "\n".join("○ " + x for x in sp["items"])
        special.append({"label": f'{sp["no"]}. {short}', "variants": {
            "관리감독자 특별교육": {"x.content": body("관리감독자 특별교육 공통내용", ec["sup_hire"]) + add, "f.req": hours("supervisor", "라."), "f.course": "관리감독자 특별교육"},
            "*": {"x.content": body("특별교육 공통내용(채용 시 교육과 같은 내용)", ec["worker_hire"]) + add, "f.req": hours("worker", "라."), "f.course": "근로자 특별교육"}}})
    special_picker = {"id": "special", "label": "특별교육 대상 작업(별표 5 제1호라목)", "depends": "f.course",
                      "hint": "근로자·관리감독자 특별교육일 때 고르세요. 공통내용과 해당 작업의 개별내용이 함께 들어갑니다.", "options": special}
    return [course_picker, special_picker], f"{ec['source']} · {eh['source']}"


AI_EX_GROUP = {
    "교육·회의": ["신규 입사자 3명 채용 시 교육, 물류센터 지게차·컨베이어 작업에 배치 예정",
              "정기 안전보건교육 2시간, 생산직 20명, 이번 달 주제는 끼임 사고 예방과 전원 차단(LOTO)",
              "산업안전보건위원회 정기회의 — 안건: 하반기 위험성평가 결과, 보호구 교체, 아차사고 3건",
              "협력업체 5개사 협의체 회의, 다음 달 고소작업·화기작업 일정 조정"],
    "점검·허가": ["2층 배관 수리 용접 작업, 주변에 단열재 있음, 화재감시자 1명 배치",
              "정화조 청소 밀폐공간 작업 3명, 산소·황화수소 측정 후 진입",
              "월간 순회점검 — 가공동·창고·전기실, 지게차 통로 적치물과 분전반 덮개 확인",
              "고소작업대로 천장 배관 보수, 높이 6m, 아래로 사람이 지나다님"],
    "재해·사고 조사": ["오전 10시 2라인 컨베이어 이물을 손으로 빼다 손가락 끼임, 설비 가동 중이었고 덮개가 열려 있었음",
                  "창고에서 사다리(1.5m)에 올라 박스를 내리다 떨어짐, 사다리를 잡아 주는 사람 없었음",
                  "지게차 후진 중 보행자와 부딪힐 뻔한 아차사고, 교차 지점에 반사경 없음"],
    "보건·작업환경": ["포장 라인 반복 작업 8명, 하루 6시간 10kg 상자 들기, 허리·어깨 통증 호소",
                 "콜센터 상담원 30명, 고객 폭언이 잦아 상담 중단 기준과 휴식 시간이 필요함",
                 "도장 작업장 유기용제 사용, 국소배기장치 있음, 작업자 4명"],
    "업무일지": ["오늘 프레스 2호기 금형 교체, 지게차 하역 작업 지휘, 신규자 1명 배치, 통로에 팔레트 적치 발견",
             "순회점검 2회, 용접 작업장 불티 비산 지적, 협력업체 배관 작업 화기작업 허가",
             "건설 현장 골조 공사 — 3층 슬래브 거푸집 설치, 타워크레인 양중 작업"],
    "작업계획서": ["창고 A동 입고장에서 2.5톤 지게차로 팔레트 하역, 보행자 통로와 겹치는 구간 있음",
              "배수관 매설을 위해 깊이 2.5m 굴착, 0.6㎥ 굴착기 1대, 옆 도로에 차량 통행",
              "1.2톤 모터를 체인블록으로 들어 올려 교체, 좁은 기계실",
              "수변전실 저압반 정기점검, 정전 작업, 전기기능사 2명"],
    "조직·발령": ["생산팀장을 관리감독자로 지정, 담당 공정은 프레스·용접, 근로자 25명",
              "상시근로자 120명 제조업, 안전관리자 1명 선임"],
    "관리대장": ["신규 입사자와 교체 대상에게 안전화 10켤레·안전모 5개 지급",
             "세척제·절삭유·도료 등 12종 MSDS 대장 정리"],
    "중대재해처벌법 이행": ["상시근로자 60명 제조업, 경영책임자의 안전보건 목표와 경영방침 수립",
                    "반기 이행점검 — 위험성평가·종사자 의견 청취·협력업체 평가를 했는지 확인",
                    "협력업체 3곳 안전보건 수준 평가, 기준은 안전관리 체계·재해 이력·교육"],
    "작업시작 전 점검(별표 3)": ["2.5톤 지게차 1호기 작업시작 전 점검, 후진 경보음이 작게 들림",
                           "25톤 이동식 크레인 작업 전 점검, 연약지반 위에 설치"],
}


# 서식별 AI 입력 예시: 묶음 예시는 서식마다 맞지 않는 것이 섞여(보호구 대장에 '금형 교체' 등) 서식별로 둔다
#   ex: 눌러 넣는 예시(앞의 것이 입력칸 예시가 됨) · note: '추가로 알려 줄 내용' 칸 예시 · ph: 입력 칸별 예시 바꾸기
AI_FORM = {
    "edu-log": {"ex": ["정기 안전보건교육 2시간, 생산직 20명, 주제는 끼임 사고 예방과 전원 차단(LOTO)", "신규 채용자 3명 채용 시 교육 8시간, 물류센터 지게차·컨베이어 작업 배치 예정", "용접 작업자 5명 특별교육 — 화재·폭발 예방, 불티 비산 방지포 사용법"],
                "note": "지난달 컨베이어 끼임 아차사고 1건이 있어 사례로 다루고 싶음"},
    "drill-emergency": {"ex": ["상반기 화재 대피 훈련, 본관·생산동 85명, 비상벨 발령 후 집결지(정문 주차장)까지 대피 시간 측정", "암모니아 누출 가정 비상대응 훈련, 냉동기실, 방독면 착용·누출 차단·인원 확인"],
                        "note": "지난 훈련 때 2층 계단이 혼잡했고 인원 확인이 늦었음"},
    "drill-fire": {"ex": ["소방훈련 — 창고동 화재 가정, 옥내소화전 방수와 소화기 사용 실습, 참여 40명", "야간 근무조 대상 소방훈련, 비상방송·대피 유도·초기 소화 역할 분담 확인"],
                   "note": "소화기 압력 게이지가 낮은 것 2개 발견"},
    "drill-confined": {"ex": ["정화조 밀폐공간 긴급구조훈련 — 작업자 쓰러짐 가정, 송기마스크 착용·구조용 삼각대로 인양", "맨홀 내부 질식 사고 가정 구조훈련, 감시인 신고·외부 구조 원칙 확인, 참여 6명"],
                       "note": "공기호흡기 착용에 3분 넘게 걸린 인원이 있었음"},
    "patrol": {"ph": {"proc": "예: 협력업체 배관·전기 작업 구역 순회점검", "equip": "예: 용접기, 가설 분전반, 이동식 비계"}, "ex": ["월간 순회점검 — 협력업체 2곳(배관 A사, 전기 B사) 작업장, 화기작업 구역과 가설 분전반 확인", "주 1회 순회점검, 외벽 비계 작업 구간 — 작업발판 고정·안전난간·추락방지망 확인"]},
    "joint": {"ph": {"proc": "예: 도급인·수급인 합동점검(협력사 3곳)", "equip": "예: 고소작업대, 용접 장비, 소화기"}, "ex": ["도급인·수급인 합동점검 — 2개월 1회, 협력사 3곳, 고소작업대·용접 장비·소화기 비치 확인", "하반기 합동점검, 물류센터 하역장 — 지게차 통로 구획, 보행자 동선, 협력사 보호구 착용"]},
    "permit": {"ph": {"proc": "예: 2층 배관 용접 보수", "equip": "예: 용접기, 이동식 사다리, 산소농도 측정기"}, "ex": ["2층 배관 수리 용접 작업, 주변에 단열재 있음, 화재감시자 1명 배치", "정화조 청소 밀폐공간 작업 3명, 산소·황화수소 측정 후 진입", "수변전실 저압반 정비 정전 작업, 차단기 잠금·표지 부착"]},
    "appoint": {"ex": ["생산팀장을 관리감독자로 지정, 담당 공정은 프레스·용접, 근로자 25명", "안전관리자 신규 선임(산업안전기사), 상시근로자 120명 제조업"], "note": "기존 안전관리자 퇴사로 30일 이내 새로 선임해야 함"},
    "concurrent": {"ex": ["총무팀장이 안전보건관리담당자 겸직, 상시근로자 35명 제조업", "공장장이 안전보건관리책임자 겸직, 생산 총괄 업무와 병행"]},
    "reorg": {"ex": ["안전팀을 생산본부에서 대표이사 직속으로 변경, 안전관리자 2명·보건관리자 1명", "물류센터 신설로 현장 안전담당 1명 추가 배치"]},
    "delegation": {"ex": ["안전보건 예산 집행 — 500만원 이하는 안전팀장, 초과는 공장장 전결", "작업중지·재개 결정은 관리감독자, 중대재해 보고는 경영책임자까지"]},
    "board": {"ex": ["상시근로자 600명 제조업, 2027년 안전보건 계획 — 위험성평가 고도화, 노후 프레스 방호장치 교체 예산 1억", "건설업 시공능력 순위 800위 이내, 현장 12곳, 추락 재해 감소 목표와 안전보건 예산"]},
    "safety-rules": {"ex": ["상시근로자 150명 금속 가공 제조업, 안전보건관리규정 처음 작성", "물류센터 신설에 따라 규정 중 작업장 안전관리 조항 개정"]},
    "cert-ledger": {"ex": ["안전관리자·보건관리자·관리감독자 8명 자격과 선임일 정리, 신규 선임 1명 포함", "지게차·크레인 운전원 6명 면허·자격증 유효기간 정리"],
                    "note": "올해 갱신해야 하는 자격 2건이 있음", "ph": {"proc": "예: 안전관리자·관리감독자 자격, 지게차 운전원 면허"}},
    "edu-ledger": {"ex": ["안전관리자 2명 직무교육(신규 34시간·보수 24시간) 이수 현황 정리", "보건관리자·안전보건관리책임자 보수교육 기한 확인"],
                   "note": "안전보건관리책임자 보수교육 기한이 다음 달임", "ph": {"proc": "예: 안전관리자·보건관리자 직무교육 이수"}},
    "ppe-ledger": {"ex": ["신규 입사자 3명과 교체 대상에게 안전화 10켤레·안전모 5개 지급", "용접 작업자 6명에게 용접 보안면·가죽 장갑 지급, 분기 점검", "도장 작업장 방독마스크 정화통 교체 8개"],
                   "note": "안전화 바닥이 닳은 교체 대상이 4명 있음", "ph": {"proc": "예: 안전화·안전모 지급, 방독마스크 정화통 교체"}},
    "sapa-policy": {"ex": ["상시근로자 60명 제조업, 경영책임자의 안전보건 목표와 경영방침 수립", "건설업 현장 5곳, 추락 재해 0건 목표와 실행과제·예산"]},
    "sapa-budget": {"ex": ["2027년 안전보건 예산 — 노후 프레스 방호장치 교체, 국소배기장치 보수, 교육비", "상반기 집행 실적 점검, 보호구·작업환경측정·외부 컨설팅 비용"]},
    "sapa-eval": {"ex": ["안전보건관리책임자·관리감독자 5명 상반기 업무수행 평가", "관리감독자 평가 기준 정리 — 위험성평가 참여, TBM, 작업 전 점검"]},
    "sapa-voice": {"ex": ["3분기 종사자 의견 청취 — 건의함 5건, TBM 의견 3건, 조치 결과 회신", "냉동창고 작업자 결빙 미끄럼 건의 → 미끄럼 방지 매트 설치 후속 확인"]},
    "sapa-emergency": {"ex": ["제조업 공장 중대산업재해 대응 매뉴얼 — 끼임·화재·암모니아 누출 시나리오", "물류센터 비상 대응 — 지게차 충돌, 랙 붕괴, 폭염 온열질환"]},
    "sapa-contractor": {"ex": ["협력업체 3곳 안전보건 수준 평가, 기준은 안전관리 체계·재해 이력·교육", "신규 도장 업체 선정 전 평가, 최근 3년 재해 이력과 작업 절차서 확인"]},
    "sapa-half": {"ex": ["하반기 이행점검 — 위험성평가·종사자 의견 청취·협력업체 평가를 했는지 확인", "상반기 반기 점검 결과 경영책임자 보고, 미흡 2건 개선 계획"]},
    "accident": {"ex": ["창고에서 사다리(1.5m)에 올라 박스를 내리다 떨어짐, 사다리를 잡아 주는 사람 없었음", "지게차 후진 중 보행자와 부딪힐 뻔한 아차사고, 교차 지점에 반사경 없음"]},
    "log-sup": {"ex": ["오늘 프레스 2호기 금형 교체 작업 지휘, 작업 전 점검과 TBM 실시, 신규자 1명 배치", "용접 작업 화기 허가 확인, 불티 비산 방지포 설치 지시, 통로 적치물 정리"]},
    "log-safety": {"ex": ["순회점검 2회, 용접 작업장 불티 비산 지적, 협력업체 배관 작업 화기작업 허가", "지게차 하역 작업 입회, 신규 입사자 2명 채용 시 교육, 아차사고 1건 조사"]},
    "log-safety-w": {"ph": {"proc": "예: 수시 위험성평가 1건, 합동점검 1회, 지적 5건 중 3건 개선"}, "ex": ["이번 주 — 위험성평가 수시평가 1건, 합동점검 1회, 지적 5건 중 3건 개선", "주간 — 협력업체 신규 작업 2건 작업계획서 검토, 안전교육 2회"]},
    "log-safety-m": {"ph": {"proc": "예: 정기교육 4회, 순회점검 20회, 아차사고 3건"}, "ex": ["이번 달 — 정기교육 4회, 순회점검 20회, 아차사고 3건, 산업안전보건위원회 준비", "월간 — 작업환경측정 결과 검토, 협의체 회의 1회, 개선 요청 12건 중 9건 완료"]},
    "log-health": {"ph": {"proc": "예: 혈압 측정 12명, 근골격계 통증 상담 2명, 휴게실 위생 점검"}, "ex": ["오늘 혈압 측정 12명, 근골격계 통증 호소자 2명 상담, 휴게실 위생 점검", "폭염 대비 — 오후 작업장 온도 33℃, 물·그늘·휴식 시간 확인"]},
    "log-health-w": {"ph": {"proc": "예: 건강상담 20명, 특수건강진단 대상자 안내"}, "ex": ["이번 주 — 건강상담 20명, 특수건강진단 대상자 안내, 소음 작업장 귀마개 착용 확인", "주간 — 직무스트레스 상담 3건, 근골격계 유해요인조사 준비"]},
    "log-health-m": {"ph": {"proc": "예: 건강진단 사후관리 15명, 작업환경측정 결과 설명회"}, "ex": ["이번 달 — 건강진단 사후관리 15명, 작업환경측정 결과 설명회, MSDS 교육", "월간 — 온열질환 예방 점검, 휴게시설 점검, 보건교육 2회"]},
    "log-shm": {"ex": ["오늘 작업장 순회, 지게차 작업 전 점검 확인, 소화기 압력 점검", "협력업체 작업 시작 전 교육, 위험성평가 회의 참석"]},
    "msd-survey": {"ex": ["포장 라인 반복 작업 8명, 하루 6시간 10kg 상자 들기, 허리·어깨 통증 호소", "조립 라인 부품 체결 작업, 팔을 어깨 위로 드는 자세 하루 2시간 이상"]},
    "confined-program": {"ex": ["정화조·집수정·맨홀 등 밀폐공간 6곳, 연 2회 청소 작업, 협력업체 수행", "발효 탱크 내부 세척, 질소 퍼지 후 진입, 작업자 3명"]},
    "customer-care": {"ex": ["콜센터 상담원 30명, 고객 폭언이 잦아 상담 중단 기준과 휴식 시간이 필요함", "매장 판매직 12명, 고객 응대 중 폭언·위협 시 보호 조치와 상담 지원"]},
    "council": {},
    "wp-tower": {"ph": {"proc": "예: 타워크레인 설치 후 철골 자재 양중", "equip": "예: 타워크레인 T-50, 줄걸이 와이어"}},
    "wp-forklift": {"ph": {"proc": "예: 입고장 팔레트 하역·적재", "equip": "예: 2.5톤 지게차 2대"}},
    "wp-aerial": {"ph": {"proc": "예: 천장 배관 보수(높이 6m)", "equip": "예: 시저형 고소작업대 1대"}},
    "wp-truck": {"ph": {"proc": "예: 화물차 적재함 자재 하역", "equip": "예: 5톤 카고 크레인 트럭"}},
    "wp-excavator": {"ph": {"proc": "예: 배수관 매설 터파기", "equip": "예: 0.6㎥ 굴착기 1대, 덤프트럭"}},
    "wp-chem": {"ph": {"proc": "예: 반응기 내부 세척 후 시운전", "equip": "예: 반응기 R-101, 질소 퍼지 설비"}},
    "wp-elec": {"ph": {"proc": "예: 수변전실 저압반 정기점검(정전)", "equip": "예: 저압반, 검전기, 접지 기구"}},
    "wp-dig": {"ph": {"proc": "예: 깊이 2.5m 굴착, 흙막이 설치", "equip": "예: 굴착기 1대, H-파일 흙막이"}},
    "wp-tunnel": {"ph": {"proc": "예: 터널 굴진·발파 후 숏크리트", "equip": "예: 점보드릴, 숏크리트 장비"}},
    "wp-bridge": {"ph": {"proc": "예: 교량 상부 거더 설치", "equip": "예: 200톤 이동식 크레인 2대"}},
    "wp-quarry": {"ph": {"proc": "예: 채석장 발파·적재", "equip": "예: 천공기, 덤프트럭"}},
    "wp-demolish": {"ph": {"proc": "예: 3층 건물 철거", "equip": "예: 압쇄기 장착 굴착기"}},
    "wp-heavy": {"ph": {"proc": "예: 1.2톤 모터 교체(인양)", "equip": "예: 체인블록 2톤, 슬링벨트"}},
    "wp-rail": {"ph": {"proc": "예: 궤도 침목 교체 보수", "equip": "예: 레일 절단기, 모터카"}},
}


# AI 작성 도우미 입력 칸(구조화 입력): 묶음별 기본값, 서식별로 form_auto의 ai.fields 로 바꿀 수 있다(빈 목록이면 칸 없이 글만)
_COND = {"k": "cond", "label": "당일 작업 조건", "type": "chips", "options": ["주간", "야간", "우천", "강풍", "폭염", "한파", "협소 공간", "고소(2m 이상)", "소음·분진", "동시 작업", "협력업체 참여", "신규·미숙련자"]}
_WORK = [
    {"k": "type", "label": "작업 유형", "type": "select", "required": True, "options": ["일반 작업", "고소작업", "중량물 취급·양중", "화기작업(용접·용단)", "밀폐공간 작업", "전기작업", "굴착·토목", "차량·건설기계", "하역·운반", "기계 정비·청소·수리", "화학물질 취급", "해체·철거", "기타"]},
    {"k": "proc", "label": "공정·작업 내용", "required": True, "min": 6, "ph": "예: 2라인 프레스 금형 교체"},
    {"k": "equip", "label": "설비·장비·공구", "ph": "예: 천장크레인 5톤, 체인블록"},
    {"k": "place", "label": "작업 위치", "required": True, "ph": "예: 가공동 2층 기계실"},
    {"k": "crew", "label": "작업 인원", "ph": "예: 4명(협력업체 2명 포함)"},
    _COND]
AI_FIELDS_GROUP = {
    "작업계획서": _WORK, "점검·허가": _WORK, "작업시작 전 점검(별표 3)": [
        {"k": "equip", "label": "점검 대상 기계·장비", "required": True, "ph": "예: 지게차 2.5톤 3호기"},
        {"k": "proc", "label": "오늘 할 작업", "required": True, "ph": "예: 창고 입고 팔레트 하역"},
        {"k": "place", "label": "작업 위치", "ph": "예: 물류동 1번 도크"}, {"k": "issue", "label": "이상 징후·특이사항", "ph": "예: 후진 경보음이 작게 들림"}, _COND],
    "업무일지": [
        {"k": "proc", "label": "오늘 한 주요 업무·작업", "type": "area", "required": True, "ph": "예: 프레스 금형 교체 작업 지휘, 지게차 하역 입회, 신규자 1명 배치"},
        {"k": "place", "label": "점검·작업 장소", "ph": "예: 가공동, 자재창고"}, {"k": "crew", "label": "출력 인원", "ph": "예: 28명"},
        {"k": "issue", "label": "지적·특이사항", "ph": "예: 통로에 팔레트 적치, 아차사고 1건"}, _COND],
    "재해·사고 조사": [
        {"k": "kind", "label": "발생 형태", "type": "select", "required": True, "options": ["떨어짐", "넘어짐", "끼임", "부딪힘", "물체에 맞음", "깔림·뒤집힘", "절단·베임·찔림", "감전", "화재·폭발", "화상", "질식·중독", "근골격계", "아차사고(부상 없음)", "기타"]},
        {"k": "proc", "label": "당시 하던 작업", "required": True, "ph": "예: 컨베이어 벨트 이물 제거"},
        {"k": "place", "label": "발생 장소", "required": True, "ph": "예: 2라인 컨베이어 끝단"},
        {"k": "equip", "label": "관련 설비·기계·도구", "ph": "예: 벨트컨베이어(가동 중), 덮개 열림"},
        {"k": "course", "label": "어떻게 일어났나(경위)", "type": "area", "required": True, "min": 10, "ph": "예: 설비를 멈추지 않고 손으로 이물을 빼다 롤러에 손가락이 끼임"},
        {"k": "harm", "label": "피해 정도", "ph": "예: 손가락 골절, 병원 이송 (진단명·실명은 적지 마세요)"}],
    "교육·회의": [
        {"k": "proc", "label": "교육·회의 주제", "required": True, "ph": "예: 끼임 사고 예방과 전원 차단(LOTO)"},
        {"k": "target", "label": "대상·인원", "ph": "예: 생산직 20명, 협력업체 5개사"},
        {"k": "place", "label": "업종·사업장", "required": True, "ph": "예: 금속 가공 제조업 상시 120명"},
        {"k": "issue", "label": "최근 이슈", "ph": "예: 이번 달 아차사고 3건, 감독 지적 사항"}],
    "보건·작업환경": [
        {"k": "proc", "label": "작업·업무 내용", "required": True, "ph": "예: 포장 라인 상자 들기(10kg) 하루 6시간"},
        {"k": "place", "label": "작업 장소·부서", "required": True, "ph": "예: 물류동 포장 라인"},
        {"k": "crew", "label": "대상 인원", "ph": "예: 8명"}, {"k": "issue", "label": "유해요인·호소 증상·민원", "ph": "예: 허리·어깨 통증 호소, 소음"}],
    "조직·발령": [
        {"k": "place", "label": "업종·사업장 규모", "required": True, "ph": "예: 제조업 상시근로자 120명"},
        {"k": "target", "label": "지정·선임 대상(직위)", "ph": "예: 생산팀장"}, {"k": "proc", "label": "담당 공정·업무", "ph": "예: 프레스·용접 공정"}],
    "관리대장": [
        {"k": "proc", "label": "관리 대상", "required": True, "ph": "예: 안전화·안전모 지급, MSDS 12종"},
        {"k": "place", "label": "업종·사업장", "ph": "예: 금속 가공 제조업"}, {"k": "issue", "label": "특이사항", "ph": "예: 신규 입사자 5명"}],
    "중대재해처벌법 이행": [
        {"k": "place", "label": "업종·규모", "required": True, "ph": "예: 제조업 상시근로자 60명, 협력업체 3곳"},
        {"k": "proc", "label": "이번에 작성·점검할 범위", "required": True, "ph": "예: 하반기 이행점검, 경영방침 수립"},
        {"k": "issue", "label": "현재 상황·미흡 사항", "ph": "예: 위험성평가는 했으나 종사자 의견 청취 기록 없음"}],
}


def form_auto_map():
    fa = load("data/form_auto.json")
    m = fa["forms"]
    pickers, src = edu_auto()
    m.setdefault("edu-log", {})["pickers"] = pickers
    m["edu-log"]["source"] = src
    for k in m:
        m[k].setdefault("source", fa["source"])
        m[k]["checked"] = fa["checked"]
    return m


# ---------------------------------------------------------------- 레이아웃

NAV = [("tools/", "무료 도구"), ("resources/", "서식·자료"), ("laws/", "법령"), ("brief/", "안전 브리핑"), ("jobs/", "채용정보"), ("news/", "안전뉴스")]

LOGO_SVG = "@LOGO@"  # page()에서 경로에 맞는 <img>로 바뀐다

AVATAR_COLORS = ["#1F6FD1", "#17365D", "#0E8A6A", "#8A4FD6", "#C2571A", "#3B6E8F"]
HOME_FORMS = ["lf-f29-288431", "lf-f35-288431", "lf-f102-288431", "lf-f50-288431", "lf-f5-288431"]
QUICK_KEYWORDS = ["산업재해조사표", "선임 보고서", "위험성평가", "TBM", "MSDS", "작업허가"]


def avatar(name):
    name = str(name or "?").strip()
    color = AVATAR_COLORS[sum(ord(c) for c in name) % len(AVATAR_COLORS)]
    ch = re.sub(r"[㈜㈔]|\((주|유|사|재)\)|^주식회사\s*", "", name).strip()[:1] or "?"
    return f'<span class="avatar" style="--av:{color}" aria-hidden="true">{e(ch)}</span>'


def tool_link(site, rel_root):
    t = (site.get("tools") or [{}])[0]
    return safe_url(t.get("url")) or f"{rel_root}tools/"


DIAG_TOOLS = ["selection", "hpp", "machines", "docmap"]
LAW_MENU = [("act", "산업안전보건법"), ("yeong", "산안법 시행령"), ("rule", "산안법 시행규칙"), ("krule", "안전보건기준에 관한 규칙"),
            ("sapa", "중대재해처벌법"), ("sapa_dec", "중대재해처벌법 시행령")]


TOOL_ICONS = {"tbm": "📋", "risk": "⚠️", "committee": "🤝", "council": "🧑‍🤝‍🧑", "joint": "🔍", "patrol": "🚶", "edu-log": "🎓", "permit": "🔥", "msds": "🧪", "loto": "🔒", "rule-sign": "🪧", "top-rules": "📌", "heat": "🌡️", "improve": "📷", "confined": "🫁", "selection": "⚖️", "hpp": "🏭",
              "machines": "⚙️", "penalty": "💸", "safety-cost": "🏗️", "cost-use": "🧾", "headcount": "👥", "edu-hours": "🎓", "cvd": "❤️", "schedule": "🗓️",
              "duties": "🧑‍💼", "ai": "✨", "law-ai": "⚖️", "gear-cert": "⛑️", "retention": "🗄️", "inspect": "🔎", "docmap": "🗂️", "forms": "📝"}
# 도구 카드 아이콘(assets/img/ico/*.webp). 캐릭터 컷(assets/img/plum/)은 홈 상단·안내 화면에 쓴다.
TOOL_DUCKS = {"tbm": "tbm", "risk": "warning", "committee": "chat", "council": "flag", "joint": "ok", "patrol": "vest", "edu-log": "idea", "permit": "fire", "msds": "msds", "loto": "loto", "rule-sign": "flag", "top-rules": "salute", "heat": "heat", "improve": "fix", "confined": "confined",
              "selection": "shield", "penalty": "calc", "hpp": "bell", "machines": "process", "safety-cost": "helmet", "cost-use": "helmet", "edu-hours": "book", "headcount": "mascot", "cvd": "plum",
              "schedule": "calendar", "duties": "briefcase", "ai": "book", "law-ai": "book", "gear-cert": "helmet", "retention": "folder", "inspect": "search", "docmap": "audit"}
# 기능·완성도가 높은 작성기부터(홈 '자주 쓰는 작성기'·메뉴 순서)
WRITE_TOOLS = ["tbm", "risk", "msds", "edu-log", "committee", "council", "patrol", "joint", "permit", "confined", "heat", "loto", "rule-sign", "top-rules", "improve"]
# 홈 '자주 쓰는 작성기' 탭에 함께 올리는 서식 작성기(data/forms.json 의 id → 아이콘)
HOME_WRITE_FORMS = [("log-safety", "salute", "안전·보건관리자 업무일지", "안전·보건을 고르고 일일·주간·월간 일지를 업종별 예시로 채워 작성합니다"),
                    ("workplan", "folder", "작업계획서", "지게차·중량물·고소작업대 등 작업 종류를 골라 별표 4 사항대로 작성합니다", "안전보건규칙 제38조"),
                    ("accident", "alarm"), ("ppe-ledger", "goggles")]
CALC_TOOLS = ["selection", "hpp", "machines", "penalty", "safety-cost", "edu-hours", "headcount", "cvd"]
LOOKUP_TOOLS = ["ai", "law-ai", "gear-cert", "schedule", "duties", "retention", "cost-use", "inspect", "docmap"]
# 주 메뉴 4개. 예전 경로(brief/, jobs/ …)로 넘어온 active 값은 속한 묶음으로 바꿔 표시한다
JOB_HOME = "https://www.work24.go.kr/cm/f/c/0100/selectUnifySearch.do?topQuerySearchArea=tb_workinfo&topQueryData=" + quote("안전관리자")
NAV4 = [("lib", "자료실", "resources/"), ("law", "법령", "laws/"), ("brief", "브리핑·소식", "brief/"), ("jobs", "채용", "jobs/"), ("board", "게시판", "board/")]
ACTIVE_GROUP = {"videos/": "brief", "tools/": "lib", "resources/": "lib", "laws/": "law", "brief/": "brief", "news/": "brief", "jobs/": "jobs", "board/": "board"}


def nav_cols(site, rel):
    by = {t["id"]: t for t in site.get("free_tools", [])}
    def tl(ids):
        return [(f'{rel}tools/{i}/', by[i].get("menu") or by[i].get("short") or by[i]["name"]) for i in ids if i in by]
    return {
        "lib": [("작성기", tl(["tbm", "risk", "edu-log", "patrol", "permit"]) + [(f"{rel}tools/forms/#{WRITER_GID[g]}" if g else g_href, n) for g, n, g_href in (("업무일지", "안전·보건 업무일지", ""), ("", "작업계획서 (종류 선택)", f"{rel}tools/forms/workplan/"), ("작업시작 전 점검(별표 3)", "작업시작 전 점검표", ""), ("중대재해처벌법 이행", "중대재해법 이행 서식", ""))]
                 + [(f"{rel}tools/forms/", "작성기 전체 보기 →")]), ("진단·계산", tl(CALC_TOOLS)), ("조회·일정", tl(LOOKUP_TOOLS) + [(f"{rel}tools/", "도구 전체 보기 →")]),
                ("서식·자료", [(f"{rel}resources/", "법령 서식·자료 찾기"), (f"{rel}resources/signs/", "안전보건표지 40종"), (f"{rel}resources/library/", "안전보건 자료실"), (f"{rel}resources/templates/", "무료 양식 내려받기 (엑셀·PPT)")])],
        "law": [("현행 전문", [(f"{rel}laws/{k}/", n) for k, n in LAW_MENU]),
                ("해석·소식", [(f"{rel}laws/qa/", "고용노동부 질의회시"), (f"{rel}laws/#upcoming", "시행 예정"), (f"{rel}laws/#updates", "개정 소식"), (f"{rel}laws/bills/", "입법예고·개정 포인트")] + ([(BLOG["url"], "입법예고 해설 (네이버 블로그)")] if BLOG else []))],
        "brief": [("소식", [(f"{rel}brief/", "안전 브리핑"), (f"{rel}laws/#updates", "법령 개정 소식")] + ([(BLOG["url"], "네이버 블로그")] if BLOG else [])), ("영상", [(f"{rel}videos/", "안전보건 영상")])],
        "jobs": [("SafePlum 채용", [(f"{rel}jobs/", "채용공고 전체"), (f"{rel}jobs/today/", "오늘의 채용 모음"), (f"{rel}board/?b=job", "회원 직접 등록 공고"), (f"{rel}board/write/?b=job", "공고 등록")][:4 if (site.get("features") or {}).get("job_posting", True) else 3] + ([(OPENCHAT["url"], "채용 오픈채팅방 (카카오톡)")] if OPENCHAT else [])),
                 ("다른 채용 사이트", [(JOB_HOME, "고용24 · 안전관리자"), ("https://www.work24.go.kr/cm/f/c/0100/selectUnifySearch.do?topQuerySearchArea=tb_workinfo&topQueryData=" + quote("보건관리자"), "고용24 · 보건관리자"),
                                    ("https://www.saramin.co.kr/zf_user/search?searchword=" + quote("안전관리자"), "사람인"), ("https://www.jobkorea.co.kr/Search/?stext=" + quote("안전관리자"), "잡코리아"),
                                    ("https://job.alio.go.kr/recruit.do", "공공기관 채용정보")])],
        "board": [("게시판", [(f"{rel}board/?b=free", "커뮤니티"), (f"{rel}board/?b=qna", "Q&A")]),
                  ("회원·안내", [(f"{rel}board/account/", "로그인 · 마이페이지"), (f"{rel}board/rules/", "이용수칙"), (f"{rel}privacy/", "개인정보 처리방침")])],
    }


CHK_SVG = '<svg class="chk-svg" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3 2.5 20h19z" fill="#D92D20" stroke="#D92D20" stroke-width="2" stroke-linejoin="round"/><path d="M12 10v4.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="17.3" r="1.25" fill="#fff"/></svg>'


def chk_icon(tip):
    """'확인 필요' 표시: 작은 빨간 글자. 마우스를 올리거나 누르면(포커스) 설명이 뜬다."""
    return f'<span class="chk-i chk-txt" tabindex="0" aria-label="확인 필요: {e(tip)}" data-tip="{e(tip)}">확인 필요</span>'


def gnb_html(site, rel, active):
    grp = ACTIVE_GROUP.get(active, "")
    cols = nav_cols(site, rel)
    out = ""
    for key, label, href in NAV4:
        cur = ' aria-current="page"' if key == grp else ""
        def ext(u):
            return ' target="_blank" rel="noopener"' if u.startswith("http") else ""
        body = "".join(f'<div class="mega-col"><p class="mega-h">{e(h)}</p><ul>{"".join(f"<li><a href={chr(34)}{e(u)}{chr(34)}{ext(u)}>{e(n)}</a></li>" for u, n in ls)}</ul></div>' for h, ls in cols[key])
        mega = f'<div class="mega" role="region" aria-label="{e(label)} 메뉴"><div class="mega-in">{body}</div></div>' if body else ""
        top = href if href.startswith("http") else rel + href
        out += f'<div class="gnb-item"><a href="{e(top)}"{ext(top)}{cur}>{e(label)}</a>{mega}</div>'
    return out


def job_info_html(site, cls="ft-jobno"):
    """직업정보제공사업 신고번호 — 직업안정법 시행령 제28조제5호(정보이용자가 알아보기 쉽게 표시)."""
    op = site.get("operator") or {}
    no = str(op.get("job_info_no") or "").strip()
    if not re.fullmatch(r"[A-Z]\d{6,20}", no):
        return ""
    org = str(op.get("job_info_org") or "").strip()
    return f'<p class="{cls}">직업정보제공사업 신고번호 <b>{e(no)}</b>{(" (" + e(org) + ")") if org else ""}</p>'


def mnav_html(site, rel, active):
    """휴대폰·태블릿 전체 메뉴: 헤더 '메뉴' 버튼으로 여는 서랍. PC 메가메뉴(nav_cols)와 같은 항목을 묶음별로 펼쳐 보인다."""
    grp = ACTIVE_GROUP.get(active, "")
    cols = nav_cols(site, rel)
    def ext(u):
        return ' target="_blank" rel="noopener"' if u.startswith("http") else ""
    groups = ""
    for key, label, href in NAV4:
        top = href if href.startswith("http") else rel + href
        inner = "".join(f'<p class="mnav-h">{e(h)}</p><ul>{"".join(f"<li><a href={chr(34)}{e(u)}{chr(34)}{ext(u)}>{e(n)}</a></li>" for u, n in ls)}</ul>' for h, ls in cols.get(key, []))
        groups += (f'<details class="mnav-g"{" open" if key == grp else ""}><summary>{e(label)}</summary>'
                   f'<div class="mnav-b"><a class="mnav-top" href="{e(top)}"{ext(top)}>{e(label)} 첫 화면 →</a>{inner}</div></details>')
    return ('<div class="mnav" id="mnav" hidden><div class="mnav-bg" data-mnav-x></div>'
            '<nav class="mnav-p" aria-label="전체 메뉴"><div class="mnav-hd"><a class="mnav-home" href="' + e(rel or "./") + '">홈</a>'
            '<button type="button" class="mnav-x" data-mnav-x aria-label="메뉴 닫기">닫기 ✕</button></div>' + groups + '</nav></div>'
            '<script>(function(){var b=document.getElementById("hdMenu"),m=document.getElementById("mnav");if(!b||!m)return;'
            'function set(o){m.hidden=!o;b.setAttribute("aria-expanded",o?"true":"false");document.documentElement.classList.toggle("mnav-on",o);if(o){var f=m.querySelector("summary");if(f)f.focus();}else b.focus();}'
            'b.addEventListener("click",function(){set(m.hidden);});'
            'm.addEventListener("click",function(ev){if(ev.target.closest("[data-mnav-x]"))set(false);});'
            'document.addEventListener("keydown",function(ev){if(ev.key==="Escape"&&!m.hidden)set(false);});})();</script>')


def dock_html(rel, active):
    grp = ACTIVE_GROUP.get(active, "")
    items = [("", "🏠", "홈", "home")] + [(href, ic, label.replace("안전 ", "").replace("브리핑·소식", "소식"), key) for (key, label, href), ic in zip(NAV4, ["🗂️", "⚖️", "📰", "💼", "💬"])]
    return '<nav class="dock" aria-label="빠른 이동">' + "".join(
        f'<a href="{e(href if href.startswith("http") else rel + href)}"{" target=_blank rel=noopener" if href.startswith("http") else ""}{" aria-current=" + chr(34) + "page" + chr(34) if key == grp else ""}><span aria-hidden="true">{ic}</span>{e(label)}</a>' for href, ic, label, key in items) + "</nav>"


def _asset_ver():
    import hashlib
    h = hashlib.sha1()
    for f in ("assets/style.css", "assets/docs.js", "assets/app.js", "assets/community.js", "assets/home-cal.js", "assets/ping.js", "assets/favicon.png", "assets/img/plum/logo.webp", "assets/img/plum/hero.webp", "assets/img/ico/tbm.webp"):
        h.update((ROOT / f).read_bytes())
    return h.hexdigest()[:8]


def _openchat():
    c = (json.loads((ROOT / "config/site.json").read_text(encoding="utf-8")).get("community") or {}).get("openchat") or {}
    u = str(c.get("url") or "")
    if not u.startswith("https://open.kakao.com/"):
        return None
    return {"url": u, "title": str(c.get("title") or "오픈채팅방"), "desc": str(c.get("desc") or "")}


OPENCHAT = _openchat()  # 홍보용 카카오톡 오픈채팅방. 주소가 없으면 배너·메뉴에서 모두 빠진다


def chat_banner(cls=""):
    if not OPENCHAT:
        return ""
    return (f'<a class="cm-chat {cls}" href="{html.escape(OPENCHAT["url"])}" target="_blank" rel="noopener">'
            f'<span class="cm-chat-t">{html.escape(OPENCHAT["title"])}</span><span class="cm-chat-d">{html.escape(OPENCHAT["desc"])}</span>'
            f'<span class="cm-chat-go">카카오톡으로 참여 ↗</span></a>')


def _blog():
    c = (json.loads((ROOT / "config/site.json").read_text(encoding="utf-8")).get("community") or {}).get("blog") or {}
    u = str(c.get("url") or "")
    if not re.match(r"^https://(m\.)?blog\.naver\.com/[A-Za-z0-9_-]+/?$", u):
        return None
    return {"url": u, "title": str(c.get("title") or "네이버 블로그"), "desc": str(c.get("desc") or "")}


BLOG = _blog()  # 공식 네이버 블로그. 주소가 없으면 배너·메뉴·푸터에서 모두 빠진다


def blog_banner(cls=""):
    if not BLOG:
        return ""
    return (f'<a class="cm-chat cm-blog {cls}" href="{html.escape(BLOG["url"])}" target="_blank" rel="noopener">'
            f'<span class="cm-chat-t">{html.escape(BLOG["title"])}</span><span class="cm-chat-d">{html.escape(BLOG["desc"])}</span>'
            f'<span class="cm-chat-go">네이버 블로그 보기 ↗</span></a>')


def yt_banner(cls=""):
    u = VIDEO_CHANNELS.get("youtube")
    if not u:
        return ""
    return (f'<a class="cm-chat cm-yt {cls}" href="{html.escape(u)}" target="_blank" rel="noopener">'
            f'<span class="cm-chat-t">SafePlum 유튜브</span><span class="cm-chat-d">현장 안전수칙을 짧은 영상으로 정리해 올립니다.</span>'
            f'<span class="cm-chat-go"><span class="cm-yt-play" aria-hidden="true"></span>유튜브 채널 보기 ↗</span></a>')


def _videos():
    p = ROOT / "data/videos.json"
    if not p.exists():
        return []
    out = []
    data = json.loads(p.read_text(encoding="utf-8"))
    global VIDEO_CHANNELS
    VIDEO_CHANNELS = {k: u for k, u in (data.get("channels") or {}).items() if safe_url(u)}
    for v in data.get("items", []):
        tk = str(v.get("id", "")) if re.match(r"^\d{15,25}$", str(v.get("id", ""))) else ""
        yt = str(v.get("youtube", "")) if re.match(r"^[A-Za-z0-9_-]{11}$", str(v.get("youtube", ""))) else ""
        if not (tk or yt) or not v.get("title"):
            continue
        v["key"] = yt or tk
        v["poster"] = next((f"assets/img/videos/{x}.webp" for x in (yt, tk) if x and (ROOT / f"assets/img/videos/{x}.webp").exists()), "")
        v["tt_url"] = (f"https://www.tiktok.com/@{v.get('account', '')}/video/{tk}" if re.match(r"^[\w.]{2,30}$", str(v.get("account", ""))) else f"https://www.tiktok.com/video/{tk}") if tk else ""
        v["wide"] = v.get("format") == "wide"
        v["yt_url"] = (f"https://www.youtube.com/watch?v={yt}" if v["wide"] else f"https://www.youtube.com/shorts/{yt}") if yt else ""
        out.append(v)
    feat = [v for v in out if v.get("featured")][:1]   # 대표 영상을 맨 앞으로, 나머지는 파일 순서(최신순) 그대로
    return feat + [v for v in out if v not in feat]


VIDEO_CHANNELS = {}


VIDEOS = _videos()   # 안전보건 영상(유튜브·틱톡). 맨 위가 대표 영상. 재생을 누르기 전에는 외부에 접속하지 않는다(자체 썸네일 → 클릭 시 iframe)


def video_card(v, rel, big=False, lead=False):
    pw, ph = (960, 540) if v.get("wide") else (540, 960)
    poster = f'<img src="{rel}{e(v["poster"])}" alt="" loading="{"eager" if lead else "lazy"}" width="{pw}" height="{ph}">' if v.get("poster") else ""
    rl = "".join(f'<a href="{rel}{e(u)}">{e(n)}</a>' for u, n in v.get("related", []) if not str(u).startswith(("http", "/", "javascript")))
    src = f'data-youtube="{e(v["youtube"])}"' if v.get("yt_url") else f'data-tiktok="{e(v["id"])}"'
    cls = "vcard" + (" wide" if v.get("wide") else "") + (" vlead" if lead else "")
    return (f'<article class="{cls}" id="v-{e(v["key"])}" data-cat="{e(v.get("cat") or v.get("topic", ""))}"><div class="vplayer" {src}>{poster}'
            f'<button type="button" class="vplay" aria-label="{e(v["title"])} 재생"><span aria-hidden="true">▶</span></button>'
            f'<span class="vbadge">{("YouTube · 음성 해설" if v.get("voice") else "YouTube") if v.get("yt_url") else "TikTok"}</span></div><div class="vmeta">' + ('<p class="vfeat">대표 영상</p>' if lead else "") + f'<p class="vtopic">{e(v.get("topic", ""))} · {e(fmt_date(v.get("date", "")))}</p>'
            f'<h2 class="vtitle">{e(v["title"])}</h2>' + (f'<p class="vsum">{e(v.get("summary", ""))}</p>' if big else "")
            + (f'<p class="vlaw">근거: {e(v["law"])}</p>' if v.get("law") and big else "")
            + (f'<p class="vrel">{rl}</p>' if rl and big else "")
            + '<p class="vexts">' + (f'<a class="vext" href="{e(v["yt_url"])}" target="_blank" rel="noopener">유튜브에서 보기 ↗</a>' if v.get("yt_url") else "")
            + (f'<a class="vext" href="{e(v["tt_url"])}" target="_blank" rel="noopener">틱톡에서 보기 ↗</a>' if v.get("tt_url") else "") + "</p></div></article>")


VIDEO_CAT_ORDER = ["위험성평가", "추락·보호구", "지게차·운반", "화재·밀폐공간", "점검·비상대응", "근골격계"]


def video_filter(videos):
    """/videos/ 분류 칩. 영상이 있는 분류만, 정해 둔 순서대로. 누르면 그 분류만 보이고 주소에 #cat=… 이 붙는다."""
    import collections
    cnt = collections.Counter(v.get("cat") or v.get("topic", "") for v in videos)
    cats = [c for c in VIDEO_CAT_ORDER if cnt.get(c)] + sorted(c for c in cnt if c and c not in VIDEO_CAT_ORDER)
    if len(cats) < 2:
        return ""
    chips = f'<button type="button" class="chip" data-vcat="" aria-pressed="true">전체 <span class="n">{len(videos)}</span></button>' + "".join(
        f'<button type="button" class="chip" data-vcat="{e(c)}" aria-pressed="false">{e(c)} <span class="n">{cnt[c]}</span></button>' for c in cats)
    js = """<script>(function(){var bar=document.querySelector(".vcats");if(!bar)return;
function show(c){var cards=[].slice.call(document.querySelectorAll(".vgrid .vcard"));[].forEach.call(bar.querySelectorAll(".chip"),function(b){b.setAttribute("aria-pressed",String(b.getAttribute("data-vcat")===c));});
cards.forEach(function(x){x.hidden=!!c&&x.getAttribute("data-cat")!==c;});}
bar.addEventListener("click",function(ev){var b=ev.target.closest(".chip");if(!b)return;var c=b.getAttribute("data-vcat");show(c);try{history.replaceState(null,"",c?"#cat="+encodeURIComponent(c):location.pathname);}catch(e){}});
function init(){var m=/^#cat=(.+)$/.exec(location.hash);if(m){try{show(decodeURIComponent(m[1]));}catch(e){}}}
window.addEventListener("hashchange",init);if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();})();</script>"""
    return f'<div class="wrap"><div class="chips vcats" role="group" aria-label="영상 분류">{chips}</div></div>' + js


VIDEO_JS = """<script>(function(){if(window.__vjs)return;window.__vjs=1;document.addEventListener("click",function(ev){var b=ev.target.closest(".vplay");if(!b)return;var box=b.closest(".vplayer"),yt=box.getAttribute("data-youtube"),tk=box.getAttribute("data-tiktok"),src="";
if(yt&&/^[A-Za-z0-9_-]{11}$/.test(yt))src="https://www.youtube-nocookie.com/embed/"+yt+"?autoplay=1&playsinline=1&rel=0";else if(tk&&/^\\d{15,25}$/.test(tk))src="https://www.tiktok.com/player/v1/"+tk+"?autoplay=1&rel=0&music_info=0&description=0";if(!src)return;
var f=document.createElement("iframe");f.src=src;f.title=yt?"YouTube 영상":"TikTok 영상";f.allow="autoplay; fullscreen; encrypted-media; picture-in-picture";f.allowFullscreen=true;f.loading="eager";f.referrerPolicy="strict-origin-when-cross-origin";
box.innerHTML="";box.appendChild(f);box.classList.add("on");});})();</script>"""


ASSET_VER = _asset_ver()  # 스타일·스크립트가 바뀌면 주소가 바뀌어 브라우저가 예전 파일을 쓰지 않는다
_MAN = None


def manifest():
    global _MAN
    if _MAN is None:
        import lawpages
        _MAN = lawpages.load_manifest()
    return _MAN


def stale(checked, today=None):
    """확인일이 기준 기간(매니페스트 stale_after_days)을 넘겼는지."""
    try:
        d = dt.date.fromisoformat(checked)
    except Exception:
        return True
    return ((today or dt.date.today()) - d).days > int(manifest().get("stale_after_days", 45))


def lawver_html(tool_id, rel_root, fallback=""):
    """도구·서식 하단: 법적 근거 확인일 / 적용 법령 버전 / 원문 링크."""
    m = manifest()
    rows, dates = [], []
    for l in m.get("laws", []):
        if tool_id in l.get("used_by", []):
            c = l["current"]
            nxt = [u for u in l.get("upcoming", []) if u.get("effective", "") > dt.date.today().isoformat()]
            nx = f' · <span class="lst lst-next">시행 예정 {len(nxt)}건</span>' if nxt else ""
            rows.append(f'<a href="{e(c.get("source_url") or l.get("history_url") or "")}" target="_blank" rel="noopener">{e(l["name"])}</a> {e(c["no"])} · 시행 {e(c["effective"])}{nx}')
            dates.append(l.get("checked_at") or m.get("checked_at"))
    for n in m.get("notices", []):
        if tool_id in n.get("used_by", []):
            chk = ' · <span class="lst lst-chk" tabindex="0">확인 필요</span>' if n.get("status") != "verified" else ""
            rows.append(f'<a href="{e(n["source_url"])}" target="_blank" rel="noopener">{e(n["name"])}</a> {e(n["no"])}{(" · 시행 " + e(n["effective"])) if n.get("effective") else ""}{chk}')
            dates.append(n.get("checked_at"))
    if not rows:
        if not fallback:
            return ""
        return (f'<aside class="wrap"><p class="lawver"><b>관련 근거</b> {e(fallback)}<br><b>적용 법령 버전</b> 법령 버전 목록(law_manifest)에 등록되지 않은 근거입니다 — <span class="stale">공식 원문 재확인 필요</span><br>'
                f'<b>원문</b> <a href="https://www.law.go.kr/" target="_blank" rel="noopener">국가법령정보센터</a> · <a href="{rel_root}laws/#status">법령 버전 보기</a></p></aside>')
    oldest = min(d for d in dates if d)
    warn_s = ' <span class="stale">· 확인일이 오래되었습니다 — 공식 원문 재확인 필요</span>' if stale(oldest) else ""
    return (f'<aside class="wrap"><p class="lawver"><b>법적 근거 확인일</b> {e(oldest)}{warn_s}<br><b>적용 법령 버전</b> ' + " / ".join(rows)
            + f'<br><b>원문</b> <a href="https://www.law.go.kr/" target="_blank" rel="noopener">국가법령정보센터</a> · <a href="{rel_root}laws/#status">법령 버전·시행 예정 보기</a>'
            + '<br>이 화면의 판정·계산·예시 문구는 SafePlum이 법령 원문을 바탕으로 정리한 참고 자료입니다.</p></aside>')


def operator_html(site, rel_root):
    """운영 주체와 문의 링크. 개인 연락처는 싣지 않는다 — config/site.json 의 operator.contact_url(오픈채팅·폼·공용 메일)만 쓴다."""
    op = site.get("operator") or {}
    url = op.get("contact_url") or ""
    ok = url.startswith("mailto:") or safe_url(url)
    link = f'<a href="{e(url)}"{"" if url.startswith("mailto:") else " target=_blank rel=noopener"}>{e(op.get("contact_label") or "문의하기")}</a>' if ok else "문의 채널 준비 중"
    blog = f' · <a href="{e(BLOG["url"])}" target=_blank rel=noopener>네이버 블로그</a>' if BLOG else ""
    return f'운영: {e(op.get("name") or site["name"])} · 문의·오류 신고·삭제 요청: {link}{blog} · <a href="{rel_root}about/">서비스 소개·문의 창구</a>'


def og_image_tags(site):
    """공유 미리보기 이미지(카카오톡·메신저·SNS). 절대 주소여야 하므로 base_url 이 있을 때만 넣는다."""
    base = (site.get("base_url") or "").rstrip("/")
    if not base or not (ROOT / "assets/og.png").exists():
        return ""
    u = f"{base}/assets/og.png?v={ASSET_VER}"
    return (f'<meta property="og:image" content="{u}">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:image" content="{u}">')


def ping_tag(site, rel_root):
    """하루 방문자 수 집계 스크립트(assets/ping.js). 게시판(Supabase)이 연결됐을 때만 넣는다."""
    cm = site.get("community") or {}
    m = re.match(r"^https://([a-z0-9]+)\.supabase\.co/?$", str(cm.get("supabase_url") or ""))
    if not (m and cm.get("supabase_anon_key")):
        return ""
    return f'<script async src="{rel_root}assets/ping.js?v={ASSET_VER}" data-url="https://{m.group(1)}.supabase.co" data-key="{html.escape(str(cm["supabase_anon_key"]))}"></script>'


def hd_auth(site, rel_root):
    """헤더의 회원 영역. 게시판(Supabase)이 연결됐을 때만 나온다. 로그인 여부는 브라우저에 저장된 세션으로 판단한다."""
    cm = site.get("community") or {}
    m = re.match(r"^https://([a-z0-9]+)\.supabase\.co/?$", str(cm.get("supabase_url") or ""))
    if not (m and cm.get("supabase_anon_key")):
        return ""
    return (ping_tag(site, rel_root) + f'<div class="hd-auth" id="hdAuth" data-key="sb-{m.group(1)}-auth-token" data-acct="{rel_root}board/account/">'
            f'<a class="hd-auth-in" href="{rel_root}board/account/">로그인</a></div>')


def page(site, rel_root, path, title, body, desc=None, active=""):
    body = body.replace('assets/ai.js"', f'assets/ai.js?v={ASSET_VER}"')  # AI 모듈도 바뀌면 새 주소로(예전 파일 캐시 방지)
    base = (site.get("base_url") or "").rstrip("/")
    canonical = f"{base}/{path}" if base else ""
    canon_tags = f'<link rel="canonical" href="{e(canonical)}">\n<meta property="og:url" content="{e(canonical)}">' if canonical else ""
    # 검색엔진 소유 확인 태그(네이버 서치어드바이저·구글 서치콘솔). 홈에만 넣는다. 값은 영문·숫자·-_ 만 허용
    _sv = site.get("search_verification") or {}
    if path == "":
        for _k, _n in (("naver", "naver-site-verification"), ("google", "google-site-verification"), ("bing", "msvalidate.01")):
            _v = str(_sv.get(_k) or "").strip()
            if re.match(r"^[A-Za-z0-9_-]{8,120}$", _v):
                canon_tags += f'\n<meta name="{_n}" content="{_v}">'
    _brand = f"{site.get('name_ko')} {site['name']}" if site.get("name_ko") else site["name"]   # 한글 이름으로 검색해도 잡히도록 제목에 함께 쓴다
    full_title = f"{title} | {_brand}" if title != site["name"] else (site.get("home_title") or f"{site['name']} | {site['tagline']}")
    if path == "" and base:
        _ld = {"@context": "https://schema.org", "@type": "WebSite", "name": site["name"], "alternateName": [x for x in (site.get("name_ko"), "세이프 플럼", "safeplum") if x],
               "url": base + "/", "inLanguage": "ko", "description": site.get("description", "")}
        if BLOG:
            _ld["sameAs"] = [BLOG["url"]]
        canon_tags += '\n<script type="application/ld+json">' + json.dumps(_ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    cur = ' aria-current="page"'
    on_news = (site.get("features") or {}).get("public_api", False)
    nav = gnb_html(site, rel_root, active)
    tl = tool_link(site, rel_root)
    ext = ' target="_blank" rel="noopener"' if tl.startswith("http") else ""
    contact_html = ""
    d = e(desc or site["description"])
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{d}">
{canon_tags}
<meta property="og:type" content="website">
{og_image_tags(site)}
{f'<link rel="alternate" type="application/rss+xml" title="{e(site["name"])} 브리핑·소식" href="{e(base)}/rss.xml">' if base else ''}
<meta property="og:site_name" content="{e(site['name'])}">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{d}">
<meta property="og:locale" content="ko_KR">
<meta name="theme-color" content="#0F172A">
<link rel="icon" href="{rel_root}assets/favicon.png?v={ASSET_VER}" type="image/png">
<link rel="apple-touch-icon" href="{rel_root}assets/apple-touch-icon.png?v={ASSET_VER}">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="{rel_root}assets/style.css?v={ASSET_VER}">
<script src="{rel_root}assets/docs.js?v={ASSET_VER}"></script>
</head>
<body>
<a class="skip" href="#main">본문으로 바로가기</a>
<header class="hd">
  <div class="wrap hd-in">
    <a class="logo" href="{rel_root}" aria-label="{e(site['name'])} 홈">{LOGO_SVG}<span>{e(site['name'])}</span></a>
    <nav class="gnb" aria-label="주 메뉴">{nav}</nav>
    {hd_auth(site, rel_root)}
    <button type="button" class="hd-menu" id="hdMenu" aria-expanded="false" aria-controls="mnav"><span class="hd-menu-i" aria-hidden="true"></span>메뉴</button>
    {f'<a class="btn btn-sm hd-cta" href="{e(tl)}"{ext}>Mallo 열기</a>' if safe_url(((site.get("tools") or [{}])[0]).get("url")) else ""}
  </div>
</header>
{mnav_html(site, rel_root, active)}
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
      <li>게시판의 글과 답변은 회원 개인의 의견입니다. 법령 해석은 원문과 관할 기관 안내를 기준으로 하세요. <a href="{rel_root}board/rules/">이용수칙</a> · <a href="{rel_root}privacy/">개인정보 처리방침</a></li>
      <li>작성 도구는 입력한 문서 내용을 SafePlum 서버로 보내지 않고 브라우저 안에 저장합니다(AI 기능을 쓸 때만 입력 내용이 Google로 전송). 호스팅(GitHub Pages)·글꼴 CDN 등 인프라의 접속 기록에는 각 제공자의 정책이 적용됩니다.</li>
      <li>판정·계산 결과는 자가진단용 참고 자료이며, 최종 판단은 관할 행정기관의 해석을 따릅니다.</li>
    </ul>
    <p class="ft-op">{operator_html(site, rel_root)}</p>
    {job_info_html(site)}
    <p class="ft-disc">Disclaimer: SafePlum에서 제공하는 안전보건 정보 및 문서 양식은 현장 참고용이며, 실제 적용 시 발생하는 법적 책임은 지지 않습니다.</p>
    <p class="ft-copy">© {dt.date.today().year} {e(site['name'])}{(' · ' + contact_html) if contact_html else ''}{' · <button type="button" class="linkbtn ft-backup" data-mydata>작성 내용 백업</button>' if path.startswith("tools/") and path != "tools/" else ""} · 법령 데이터 기준일 {e(manifest().get("checked_at", ""))} · <a href="{rel_root}legal/">면책 안내</a></p>
  </div>
</footer>
{dock_html(rel_root, active)}
<script src="{rel_root}assets/app.js?v={ASSET_VER}" defer></script>
</body>
</html>
""".replace("@LOGO@", f'<img class="logo-mark" alt="" width="36" height="36" src="{rel_root}assets/img/plum/logo.webp?v={ASSET_VER}">')


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


GRADE_ORDER = ["대기업", "공공기관", "외국계", "중견기업", "공공·협회", "중소·기타"]


def grade_tag(j):
    g = j.get("company_type") or ""
    if g not in ("대기업", "공공기관", "외국계", "중견기업", "공공·협회"):
        return ""
    txt = g + (" · " + j["group"] if j.get("group") else "")
    return f'<span class="tag tag-grade g-{GRADE_ORDER.index(g)}">{e(txt)}</span>'


def company_box(j):
    """세이프플럼에서 덧붙이는 정보: 기업 구분·계열, 기업 리뷰·연봉 찾기(외부 검색), 안전·보건관리자 직무 도구."""
    co = re.sub(r"[㈜㈔]|\((주|유|사|재)\)|주식회사|유한책임회사|\s+", " ", str(j.get("company") or "")).strip()
    q = urllib.parse.quote(co)
    health = any("보건" in x for x in j.get("jobs_list", []))
    return (f'<div class="side-box job-co"><h2 class="h-sm">지원 전에 확인하기</h2><ul class="bul">'
            f'<li><a href="https://www.jobplanet.co.kr/search?query={q}" target="_blank" rel="noopener nofollow">{e(co)} 기업 리뷰·연봉 (잡플래닛) ↗</a></li>'
            f'<li><a href="https://search.naver.com/search.naver?query={q}" target="_blank" rel="noopener nofollow">{e(co)} 기업 정보·뉴스 (네이버) ↗</a></li>'
            f'<li><a href="../../tools/duties/">{"보건관리자" if health else "안전관리자"} 법정 직무 미리 보기</a></li>'
            f'<li><a href="../../tools/selection/">이 회사 규모면 몇 명 선임해야 할까?</a></li></ul>'
            '<p class="hint">기업 구분·계열은 공고와 공개 정보를 바탕으로 SafePlum이 붙인 참고 표시입니다.</p></div>')


def career_txt(j):
    """경력 표시: 공고 요약의 년수(career_detail)가 있으면 우선, 없으면 신입/경력 구분."""
    return j.get("career_detail") or j.get("career") or ""


def term_txt(j):
    t = j.get("term") or ""
    return re.sub(r"\((.+)\)$", r", \1", t) if t.count("(") == 1 and t.endswith(")") and not t.startswith("(") else t


def job_row(j, rel_root, compact=False):
    tags = "".join(f'<span class="tag tag-job">{e(x)}</span>' for x in j["jobs_list"])
    tags += "".join(f'<span class="tag">{e(v)}</span>' for v in (career_txt(j), j.get("education"), (j.get("employment") or "") + (f" · {j['term']}" if j.get("term") else "")) if v)
    loc = " · ".join(x for x in [j.get("company"), j.get("region")] if x)
    attrs = (f'data-item data-job="{e("|".join(j["jobs_list"]))}" '
             f'data-ctype="{e(j.get("company_type",""))}" data-industry="{e(j.get("industry",""))}" '
             f'data-deadline="{e(j.get("deadline",""))}" data-posted="{e(j.get("posted",""))}" '
             f'data-text="{e(" ".join(str(j.get(k,"")) for k in ("title","company","region","job","industry","company_type","career","career_detail","education","employment")))}"')
    meta = " · ".join(x for x in [j.get("company_type"), j.get("group"), j.get("industry")] if x)
    return f"""<li class="jrow{' closed' if j['closed'] else ''}{' compact' if compact else ''}" {attrs}>
  {avatar(j.get('company'))}
  <div class="jrow-main">
    <a class="jrow-title" href="{rel_root}jobs/{e(j['id'])}/">{e(j['title'])}</a>
    <p class="jrow-sub">{e(loc)}{(' <span class="dot">·</span> ' + e(meta)) if meta and not compact else ''}</p>
    {'' if compact else f'<p class="tags">{tags}</p>'}
  </div>
  <div class="jrow-side">{dl_badge(j)}</div>
</li>"""


TODAY_SECTORS = ["제조·화학", "반도체·전자", "건설·플랜트·조선", "식품·유통·서비스", "물류·운수", "에너지·공공"]


def jobs_today_pick(jobs, today):
    pick = [j for j in jobs if not j["closed"] and (j.get("company_type") in GRADE_ORDER[:5])]
    return sorted(pick, key=lambda j: (GRADE_ORDER.index(j["company_type"]), str(j.get("deadline") or "9")))


def jobs_today_text(site, jobs, today):
    """카카오톡 오픈채팅에 붙여 넣는 글. 링크는 모두 세이프플럼 공고 화면(거기서 원문으로 이동)."""
    base = (site.get("base_url") or "https://safeplum.com").rstrip("/")
    d = dt.date.fromisoformat(today)
    pick = jobs_today_pick(jobs, today)
    out = [f"🔥 오늘의 안전·보건 채용 ({d.month}월 {d.day}일 · 마감 전 {len(pick)}건)",
           "대기업·공공기관·외국계·중견기업 공고만 골라 매일 아침 올립니다.",
           f"👉 전체 보기: {base}/jobs/today/", ""]
    for sec in TODAY_SECTORS + ["기타"]:
        items = [j for j in pick if (j.get("industry") if j.get("industry") in TODAY_SECTORS else "기타") == sec]
        if not items:
            continue
        # 같은 회사·같은 마감의 지역별 공고는 한 줄로
        groups, seen = [], {}
        for j in items:
            k = (j["company"], j.get("deadline"), "|".join(j["jobs_list"]))
            if k in seen:
                seen[k]["more"].append(j)
            else:
                seen[k] = {"j": j, "more": []}
                groups.append(seen[k])
        out.append(f"■ {sec}")
        for g in groups:
            j = g["j"]
            def city(x):
                tk = (x.get("region") or "").split()
                if not tk:
                    return ""
                last = tk[-1]
                if len(tk) > 1 and last.endswith("구"):
                    return tk[0] + " " + last          # 울산 남구, 서울 중구
                return last[:-1] if len(last) > 2 and last[-1] in "시군" else last
            cities = "·".join(dict.fromkeys(city(x) for x in [j] + g["more"] if city(x)))
            tag = j["company_type"] + (f"·{j['group']}" if j.get("group") else "")
            co = re.sub(r"[㈜㈔]|\((주|유|사)\)", "", j["company"]).strip()
            dl = str(j.get("deadline") or "")
            dl_s = f"~{int(dl[5:7])}/{int(dl[8:10])}" if DATE_RE.match(dl) else (dl or "")
            emp = j.get("employment") or ""
            if emp == "계약직":
                emp += f"({term_txt(j)})" if j.get("term") else "(기간은 원문 확인)"
            cond = " · ".join(x for x in ['·'.join(j['jobs_list']), career_txt(j), j.get("education"), emp] if x)
            out.append(f"- {co}({cities}) [{tag}] / {cond} {dl_s}".rstrip())
            out.append(f"  {base}/jobs/{j['id']}/")
        out.append("")
    no = ((site.get("operator") or {}).get("job_info_no") or "")
    out.append("※ 조건·마감은 공고 원문이 우선합니다. 세이프플럼은 채용을 알선하지 않습니다." + (f" (직업정보제공사업 신고번호 {no})" if no else ""))
    out.append("안전보건 서류는 네이버에서 '세이프플럼' 검색 → 무료 작성")
    return "\n".join(out)


def jobs_today_body(site, jobs, today):
    pick = jobs_today_pick(jobs, today)
    d = dt.date.fromisoformat(today)
    secs = ""
    for sec in TODAY_SECTORS + ["기타"]:
        items = [j for j in pick if (j.get("industry") if j.get("industry") in TODAY_SECTORS else "기타") == sec]
        if items:
            secs += f'<section class="block jt-sec"><h2>{e(sec)} <span class="muted">{len(items)}</span></h2><ul class="jlist">' + "".join(job_row(j, "../../") for j in items) + "</ul></section>"
    text = jobs_today_text(site, jobs, today)
    return f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">채용정보</a><span>/</span>오늘의 채용 모음</p>
  <h1>오늘의 안전·보건 채용 <span class="muted">{d.month}월 {d.day}일</span></h1>
  <p>대기업·공공기관·외국계·중견기업의 안전관리자·보건관리자·EHS 공고 중 <b>마감 전 {len(pick)}건</b>을 업종별로 모았습니다. 매일 아침 갱신되고, 마감된 공고는 자동으로 빠집니다.</p>
</div></section>
<div class="wrap layout-detail">
  <article class="col-main">{job_info_html(site, "job-no")}{secs or empty_box("오늘 모을 공고가 없습니다.")}</article>
  <aside class="col-side">
    <div class="side-box jt-share" id="jtShare" hidden><h2 class="h-sm">오픈채팅방 공유 글 <span class="muted">운영자용</span></h2>
      <p class="hint">눌러서 복사한 뒤 카카오톡에 붙여 넣으세요. 링크는 세이프플럼 공고 화면으로 연결됩니다.</p>
      <textarea id="jtText" readonly rows="14" aria-label="공유할 글">{e(text)}</textarea>
      <button type="button" class="btn btn-block" id="jtCopy">공유 글 복사</button>
    </div>
    <div class="side-box"><h2 class="h-sm">표시 기준</h2><ul class="bul hint">
      <li>기업 구분·계열은 공고와 공개 정보를 바탕으로 SafePlum이 붙인 참고 표시입니다.</li>
      <li>경력·학력은 공고 원문의 요약 조건(필수 자격)을 옮긴 것입니다. 직무별 세부 요건은 원문을 확인하세요.</li>
      <li>공고 원문에서 조건·마감이 바뀔 수 있습니다. 지원 전에 원문을 확인하세요.</li>
    </ul></div>
  </aside>
</div>
<script>(function(){{var box=document.getElementById("jtShare"),a=document.getElementById("hdAuth");
/* 운영자(관리자)로 로그인한 브라우저에서만 공유 글 상자를 보인다 — app.js 의 '운영 관리' 표시와 같은 기준 */
try{{var ses=JSON.parse(localStorage.getItem(a&&a.getAttribute("data-key"))||"null");if(box&&ses&&ses.user&&localStorage.getItem("safetake.adm")===ses.user.id)box.hidden=false;}}catch(e){{}}
var b=document.getElementById("jtCopy"),t=document.getElementById("jtText");if(!b||!t)return;
b.addEventListener("click",function(){{var done=function(){{b.textContent="복사했습니다";setTimeout(function(){{b.textContent="공유 글 복사";}},1600);}};
if(navigator.clipboard&&navigator.clipboard.writeText){{navigator.clipboard.writeText(t.value).then(done,function(){{t.select();document.execCommand("copy");done();}});}}else{{t.select();document.execCommand("copy");done();}}}});}})();</script>"""


def resource_row(r, site, rel_root="./"):
    tool = (site.get("tools") or [None])[0]
    acts = []
    if r.get("free_tool"):
        acts.append(f'<a class="btn btn-sm btn-green" href="{rel_root}tools/{e(r["free_tool"])}/">바로 작성 · 무료</a>')
    if r.get("page_link"):
        acts.append(f'<a class="btn btn-sm btn-green" href="{rel_root}{e(r["page_link"])}">바로 보기</a>')
    for ext in ("hwp", "pdf"):
        fv = (r.get("files") or {}).get(ext)
        if fv:
            acts.append(f'<a class="btn btn-sm btn-ghost dl-chip" href="{rel_root}{e(fv["path"])}" download="{e(dl_name(r, ext))}" aria-label="{e(r["title"])} {ext.upper()} 내려받기">{ext.upper()}</a>')
    if r.get("detail"):
        acts.append(f'<a class="btn btn-sm btn-ghost" href="{rel_root}{e(r["detail"])}">자세히</a>')
    if r.get("href"):
        lbl = ("별표 원문" if r.get("byl_cls") == "BE" else "서식 원본") if r.get("byl_no") else "원문"
        acts.append(f'<a class="btn btn-sm" href="{e(r["href"])}" target="_blank" rel="noopener">{lbl} ↗</a>')
    if r.get("law_href") and not r.get("detail"):
        acts.append(f'<a class="btn btn-sm btn-ghost" href="{e(r["law_href"])}" target="_blank" rel="noopener">근거 법령</a>')
    if r.get("app_kind") and tool:
        tpl, url = tool.get("deep_link_template", ""), safe_url(tool.get("url"))
        link = tpl.replace("{kind}", quote(r["app_kind"])) if tpl else url
        if safe_url(link):
            acts.append(f'<a class="btn btn-sm btn-accent" href="{e(link)}" target="_blank" rel="noopener">Mallo에서 작성</a>')
        elif r.get("category") == "Mallo 서식":
            acts.append('<span class="btn btn-sm btn-disabled" aria-disabled="true">도구 주소 준비 중</span>')
    meta = [x for x in [r.get("law"), r.get("form_no"), (r.get("rel") + " 관련") if r.get("rel") else ""] if x]
    tags = r.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split("|") if t]
    text = " ".join([r.get("title", ""), r.get("summary", ""), r.get("law", ""), r.get("form_no", ""), r.get("basis", ""), " ".join(tags)])
    cat = r.get("category", "")
    cat_cls = {"법정 서식": "badge-blue", "고시·지침": "badge-navy", "Mallo 서식": "badge-orange", "무료 작성 도구": "badge-green",
               "웹 작성 서식": "badge-green", "공단 자료": "badge-navy"}.get(cat, "badge-line")
    return f"""<li class="rrow" data-item data-cat="{e(cat)}" data-topic="{e(r.get('topic', ''))}" data-id="{e(r['id'])}" data-text="{e(text)}">
  <div class="rrow-main">
    <p class="rrow-top"><span class="badge {cat_cls}">{e(cat)}</span>{f'<span class="rrow-meta">{e(" · ".join(meta))}</span>' if meta else ''}</p>
    <h3 class="rrow-title">{f'<a href="{rel_root}{e(r["detail"])}">{e(r["title"])}</a>' if r.get("detail") else e(r["title"])}</h3>
    {f'<p class="rrow-desc">{e(r.get("summary"))}</p>' if r.get('summary') else ''}
    {f'<p class="rrow-note">근거: {e(r["basis"])}</p>' if r.get('basis') else ''}
    {f'<p class="rrow-note">원본 확인 {fmt_date(r["verified"])}</p>' if r.get("verified") else ''}
  </div>
  <div class="rrow-acts">{''.join(acts)}</div>
  <button class="fav" type="button" data-fav="{e(r['id'])}" aria-pressed="false" aria-label="즐겨찾기">☆</button>
</li>"""


def update_row(u, full=True, today=""):
    src = safe_url(u.get("source_url"))
    link = f'<a class="link-ext" href="{e(src)}" target="_blank" rel="noopener">{e(u.get("source_name") or "원문")} ↗</a>' if src else ""
    d = u.get("date", "")
    eff = str(u.get("effective") or "")
    st = ""
    if DATE_RE.match(eff) and today:
        st = '<span class="lst lst-next">시행 예정</span>' if eff > today else '<span class="lst lst-cur">시행 중</span>'
    arts = " · ".join(e(x) for x in u.get("affected_articles", []) or [])
    extra = ""
    basis = f'<span>근거 {e(u["basis"])}</span>' if u.get("basis") else ""
    if full:
        extra = (f'<p class="urow-desc">{e(u.get("summary"))}</p>'
                 + (f'<p class="lup-a">대상 조문: {arts}</p>' if arts else "")
                 + (f'<p class="lup-i"><b>실무 영향</b> {e(u["practical_impact"])}</p>' if u.get("practical_impact") else "")
                 + f'<p class="urow-foot">{link}{basis}'
                 + ('<span class="lst-chk" tabindex="0">확인 필요</span>' if u.get("verify") else "") + f'<span>원문 확인 {fmt_date(u.get("checked"))}</span></p>')
    return f"""<li class="urow" data-item data-text="{e(u.get('title','') + ' ' + u.get('summary','') + ' ' + u.get('law',''))}">
  <time class="urow-date" datetime="{e(d)}">{fmt_date(d)}<span class="urow-k">공포</span></time>
  <div class="urow-body">
    <p class="urow-law">{st} {e(u.get('law'))}{(' · 시행 ' + fmt_date(eff)) if eff else ''}{(' · ' + e(u.get('kind'))) if u.get('kind') else ''}</p>
    <h3 class="urow-title">{e(u['title'])}</h3>
    {extra}
  </div>
</li>"""


def filter_group(group, values, label):
    items = "".join(f'<button type="button" class="chip" data-value="{e(v)}" aria-pressed="false">{e(v)}</button>' for v in values)
    return (f'<div class="fgroup"><p class="fgroup-label">{e(label)}</p>'
            f'<div class="chips" data-filter="{group}" role="group" aria-label="{e(label)}">'
            f'<button type="button" class="chip" data-value="" aria-pressed="true">전체</button>{items}</div></div>')


ACC_PAGE = "accidents/"  # 사고사망 속보 목록(상세) 페이지 주소


JOB_POST = True  # main() 에서 config/site.json features.job_posting 으로 정한다
JOBS_OPEN = 0     # main() 에서: 채용정보(/jobs/)의 마감 전 공고 수 — 회원 채용공고 게시판에서 안내


def bdate(x, long=False):
    """브리핑·소식 날짜 표기. 게시일을 일 단위로 확인하지 못한 항목(date_prec: month)은 월까지만 적는다."""
    d = str(x.get("date") or "")
    if x.get("date_prec") == "month":
        return f"{d[:4]}년 {int(d[5:7])}월" if long else d[2:7].replace("-", ".")
    return fmt_date(d) if long else d[2:].replace("-", ".")


def acc_key(a, i):
    """속보 한 건의 페이지 안 위치 이름(#a-...). 공단 게시물 번호가 없으면 순번을 쓴다."""
    k = re.sub(r"[^0-9A-Za-z_-]", "", str(a.get("id") or ""))
    return "a-" + (k or f"n{i}")


def acc_trend_html(auto_acc, today, days=7, rel="../"):
    """사고사망 속보(공단 게시 기준) 옆 상자: 최근 며칠의 속보를 한 건씩 보여 주고, 누르면 속보 목록 페이지의 해당 건으로 간다.
    발생일을 읽은 자료가 없으면 '' (상자를 만들지 않음)."""
    import collections, datetime as _dt
    from urllib.parse import quote
    allitems = auto_acc.get("items", [])
    items = [(i, a) for i, a in enumerate(allitems) if a.get("date")]
    if not items:
        if allitems:
            warn("사고사망 속보: 발생일을 읽은 항목이 없어 동향 상자를 만들지 않음(scripts/fetch_public.py 의 acc_date 확인)")
        return ""
    today = str(today)[:10]
    # 최근 N일 = 오늘 포함 N+1일 범위(예: 10.13 기준 10.6~10.13). 공단 게시가 며칠 늦어 이 범위가 비면
    # 가장 최근 발생일 기준 1주를 보여 주고 기간을 밝힌다(0건으로 보이지 않게).
    since = (_dt.date.fromisoformat(today) - _dt.timedelta(days=days)).isoformat()
    recent = sorted(((i, a) for i, a in items if since <= a["date"] <= today), key=lambda x: x[1]["date"], reverse=True)
    period = f"최근 {days}일"
    if not recent:
        last = max(a["date"] for _, a in items if a["date"] <= today) if any(a["date"] <= today for _, a in items) else ""
        if last:
            s2 = (_dt.date.fromisoformat(last) - _dt.timedelta(days=days - 1)).isoformat()
            recent = sorted(((i, a) for i, a in items if s2 <= a["date"] <= last), key=lambda x: x[1]["date"], reverse=True)
            period = f"{int(s2[5:7])}.{int(s2[8:10])}~{int(last[5:7])}.{int(last[8:10])}"
    total = collections.Counter((a.get("type") or "기타") for _, a in recent)
    WD = "월화수목금토일"
    href = rel + ACC_PAGE
    if recent:
        # 유형별 합계는 같은 유형이 2건 이상일 때만(전부 1건이면 아래 목록과 같은 내용이라 생략)
        summ = ""
        if max(total.values()) > 1:
            summ = f'<ul class="acc-sum" aria-label="{period} 재해유형별 건수">' + "".join(
                f'<li><a href="{href}?cat={quote(k)}"><span class="acc-k">{e(k)}</span><span class="acc-bar" aria-hidden="true"><i style="width:{round(v / len(recent) * 100)}%"></i></span><span class="acc-n">{v}건</span></a></li>'
                for k, v in total.most_common()) + "</ul>"
        MAX = 6
        rows = "".join(
            f'<li><a href="{href}#{acc_key(a, i)}"><time datetime="{e(a["date"])}">{int(a["date"][5:7])}.{int(a["date"][8:10])} <span>{WD[_dt.date.fromisoformat(a["date"]).weekday()]}</span></time>'
            f'<span class="acc-b"><span class="tag tag-acc">{e(a.get("type") or "기타")}</span><span class="acc-t">{e(a.get("text", ""))}</span></span>'
            f'<span class="acc-go" aria-hidden="true">›</span></a></li>'
            for i, a in recent[:MAX])
        rest = f'<p class="acc-rest">외 {len(recent) - MAX}건</p>' if len(recent) > MAX else ""
        body = f'{summ}<ul class="acc-days">{rows}</ul>{rest}'
        badge = f'<span class="badge badge-red">{period} {len(recent)}건</span>'
    else:
        body = f'<p class="hint">최근 {days}일 동안 게시된 사고사망 속보가 없습니다.</p>'
        badge = f'<span class="badge badge-muted">최근 {days}일 0건</span>'
    return (f'<div class="side-box acc-box"><div class="acc-head"><h2 class="h-sm">사고사망 속보 동향</h2>{badge}</div>{body}'
            f'<a class="acc-all" href="{href}">속보 전체 보기 <span aria-hidden="true">→</span></a>'
            f'<p class="acc-src">안전보건공단 속보 기준 · 자동 분류 · 수집일 {e(auto_acc.get("fetched", ""))}</p></div>')


def acc_page_body(auto_acc, today):
    """사고사망 속보 목록 페이지 본문. 공단 속보 문장을 그대로 싣고 발생일·재해유형으로 거를 수 있게 한다."""
    import collections, datetime as _dt
    WD = "월화수목금토일"
    items = list(enumerate(auto_acc.get("items", [])))
    items.sort(key=lambda x: x[1].get("date") or "", reverse=True)  # 발생일 최신순, 발생일을 못 읽은 건은 뒤로
    cnt = collections.Counter((a.get("type") or "기타") for _, a in items)

    def row(i, a):
        d, t = a.get("date") or "", a.get("type") or "기타"
        when = (f'<time datetime="{e(d)}">{fmt_date(d)} <span>{WD[_dt.date.fromisoformat(d).weekday()]}</span></time>' if d else '<time>발생일 확인 필요</time>')
        img = safe_url(a.get("image"))
        src = f'<a class="link-ext" href="{e(img)}" target="_blank" rel="noopener">공단 속보 원본 이미지 ↗</a>' if img else ""
        return (f'<li class="arow" id="{acc_key(a, i)}" data-item data-cat="{e(t)}" data-text="{e(a.get("text", "") + " " + t)}">'
                f'<div class="arow-h">{when}<span class="tag tag-acc">{e(t)}</span></div>'
                f'<p class="arow-t">{e(a.get("text", ""))}</p>{f"<p class=arow-f>{src}</p>" if src else ""}</li>')
    chips = "".join(f'<button type="button" class="chip" data-value="{e(k)}" aria-pressed="false">{e(k)} <span class="n">{v}</span></button>' for k, v in cnt.most_common())
    if items:
        main = (f'<div class="listbar"><div class="search-inline"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
                f'<input type="search" class="filter-q" placeholder="예: 지게차, 사다리, 굴착기" aria-label="속보 검색"></div></div>'
                f'<div class="chips acc-chips" data-filter="cat" role="group" aria-label="재해유형"><button type="button" class="chip" data-value="" aria-pressed="true">전체</button>{chips}</div>'
                f'<p class="count" aria-live="polite">속보 <strong data-count>{len(items)}</strong>건</p>'
                f'<ul class="arows" data-list>{"".join(row(i, a) for i, a in items)}</ul>'
                + empty_box("조건에 맞는 속보가 없습니다.").replace('class="empty"', 'class="empty" data-empty hidden'))
    else:
        main = empty_box("사고사망 속보를 아직 받아 오지 못했습니다. 공단 산업안전포털에서 확인해 주세요.",
                         '<div class="btns"><a class="btn btn-sm btn-ghost" href="https://portal.kosha.or.kr/" target="_blank" rel="noopener">산업안전포털 ↗</a></div>')
    return f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span><a href="../brief/">안전 브리핑</a><span>/</span>사고사망 속보</p>
  <h1>사고사망 속보</h1>
  <p>안전보건공단이 게시한 사고사망 속보를 발생일·재해유형별로 모았습니다. 같은 작업이 있는 현장은 TBM·위험성평가에 바로 반영해 보세요.</p>
</div></section>
<div class="wrap layout-detail">
  <section class="col-main">{main}</section>
  <aside class="col-side stack">
    <div class="side-box"><h2 class="h-sm">현장에 바로 반영하기</h2>
      <div class="btns acc-btns"><a class="btn btn-sm" href="../tools/tbm/">TBM 일지 작성</a><a class="btn btn-sm btn-ghost" href="../tools/risk/">위험성평가서 작성</a></div></div>
    <div class="side-box"><h2 class="h-sm">자료 안내</h2>
      <p class="hint">출처: 한국산업안전보건공단 사고사망 게시판(공공데이터포털 API, 이용허락범위 제한 없음) · 수집일 {e(auto_acc.get("fetched", ""))}</p>
      <p class="hint">속보 문장은 공단 게시 내용 그대로이며, 발생일·재해유형은 SafePlum이 문장에서 자동으로 읽어 분류한 참고 정보입니다. 누락·분류 오류가 있을 수 있고, 공식 산업재해 통계는 고용노동부 발표를 확인하세요.</p>
      <p><a class="link-ext" href="https://portal.kosha.or.kr/" target="_blank" rel="noopener">안전보건공단 산업안전포털 ↗</a></p></div>
  </aside>
</div>"""


def sec_head(title, href=None, more="전체 보기", sub=None):
    link = f'<a class="more" href="{href}">{e(more)} <span aria-hidden="true">→</span></a>' if href else ""
    return f'<div class="sec-head"><div><h2>{e(title)}</h2>{f"<p>{e(sub)}</p>" if sub else ""}</div>{link}</div>'


def tool_panel(site, rel_root, big=False):
    t = (site.get("tools") or [None])[0]
    if not t:
        return ""
    url = safe_url(t.get("url"))
    if not url:
        return ""  # PC 버전 주소가 생기기 전에는 패널을 내지 않는다
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


TOOL_KINDS = [("작성기", "k-write", "바로 작성해 A4로 인쇄·PDF 저장"), ("계산기", "k-calc", "법령 기준으로 대상·시간·금액 계산"),
              ("조회·일정", "k-find", "의무·주기·과태료를 찾아보고 일정 관리")]
ARROW = '<svg class="tcard-arr" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'


# 작성기 하나로 통합(2026-10-12): 전용 작성기(config free_tools, cat=작성기)를 서식 작성기 묶음 속에 넣어 /tools/forms/ 한 곳에서 찾는다.
WRITER_LEAD = ("위험성평가·TBM", ["tbm", "risk"])          # 맨 앞 묶음(서식에는 없는 묶음)
WRITER_TOOLS_IN = {"교육·회의": ["edu-log", "committee", "council"],
                   "점검·허가": ["patrol", "joint", "permit", "confined", "heat", "loto", "rule-sign", "top-rules", "improve"],
                   "관리대장": ["msds"]}
WRITER_GID = {"위험성평가·TBM": "w-risk", "교육·회의": "w-edu", "점검·허가": "w-check", "재해·사고 조사": "w-acc", "업무일지": "w-log",
              "작업계획서": "w-plan", "작업시작 전 점검(별표 3)": "pre", "조직·발령": "w-org", "관리대장": "w-ledger", "중대재해처벌법 이행": "w-sapa"}
WRITER_N = 0  # main() 에서 계산: 전용 작성기 + 서식 - 겹치는 것


def writer_groups(site, groups, forms):
    """[(묶음 이름, [('tool', t) | ('form', f)])]. 같은 id 의 전용 작성기가 있으면 서식 카드는 빼고 전용 작성기만 보인다."""
    tools = {t["id"]: t for t in site.get("free_tools", []) if t.get("cat") == "작성기"}
    dup = set(tools) & {f["id"] for f in forms}
    out = [(WRITER_LEAD[0], [("tool", tools[i]) for i in WRITER_LEAD[1] if i in tools] + [("form", f) for f in forms if f["group"] == WRITER_LEAD[0]])]
    used = set(WRITER_LEAD[1])
    for g in groups:
        items = [("tool", tools[i]) for i in WRITER_TOOLS_IN.get(g, []) if i in tools]
        used |= set(WRITER_TOOLS_IN.get(g, []))
        items += [("form", f) for f in forms if f["group"] == g and f["id"] not in dup]
        if items:
            out.append((g, items))
    rest = [("tool", t) for i, t in tools.items() if i not in used]
    if rest:
        out.append(("기타", rest))
    return out


def tool_card(href, kind, name, desc, law="", sub="", ico=""):
    cls = next((c for k, c, _ in TOOL_KINDS if k == kind), "k-write")
    pic = f'<img class="tcard-i" src="{ico}" width="52" height="52" alt="" loading="lazy">' if ico else ""
    return (f'<a class="tcard {cls}" href="{href}"><span class="tcard-top"><span class="tbadge">{e(kind)}</span>'
            f'{f"<span class=tcard-sub>{e(sub)}</span>" if sub else ""}</span>'
            f'{pic}<strong class="tcard-t">{e(name)}</strong><span class="tcard-d">{e(desc)}</span>'
            f'<span class="tcard-f"><span class="tcard-law">{e(law) or "&nbsp;"}</span>{ARROW}</span></a>')


def free_tool_cards(site, rel_root, group=None, limit=None, ids=None, kind=None):
    tools = [t for t in site.get("free_tools", []) if (group is None or t.get("group") == group) and (kind is None or t.get("cat") == kind)]
    if ids:
        by = {t["id"]: t for t in tools}
        tools = [by[i] for i in ids if i in by]
    return "".join(tool_card(f'{rel_root}tools/{e(t["id"])}/', t.get("cat", "작성기"), t["name"], t.get("desc", ""), t.get("law", ""), t.get("tag", ""), ico=(f'{rel_root}assets/img/ico/{TOOL_DUCKS[t["id"]]}.webp' if t["id"] in TOOL_DUCKS else ""))
                   for t in tools[:limit])


def inject_data(src, names, where):
    """빌드 때 data/*.json 을 페이지 안에 넣는다. 첫 번째는 /*@DATA@*/, 나머지는 /*@이름@*/ 자리."""
    for i, name in enumerate(names):
        payload = json.dumps(load(f"data/{name}.json"), ensure_ascii=False).replace("</", "<\\/")
        mark = "/*@DATA@*/null" if i == 0 and "/*@DATA@*/null" in src else f"/*@{name.upper()}@*/null"
        assert mark in src, f"{where}: {mark} 자리가 없음"
        src = src.replace(mark, payload)
    return src


def tool_ld(t, site):
    """도구 화면의 구조화 데이터(무료 웹 도구). 검색엔진이 '무엇을 하는 페이지인지' 읽는 정보."""
    base = (site.get("base_url") or "").rstrip("/")
    if not base:
        return ""
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": t["name"], "url": f"{base}/tools/{t['id']}/",
          "description": t.get("desc", ""), "applicationCategory": "BusinessApplication", "operatingSystem": "All", "inLanguage": "ko",
          "isAccessibleForFree": True, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "KRW"},
          "publisher": {"@type": "Organization", "name": site["name"], "url": base + "/"}}
    return '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def render_free_tool(t, hazards, site=None, penalties=None):
    src = (ROOT / t["src"]).read_text(encoding="utf-8")
    if t.get("kind") == "page":
        if t.get("inject") == "penalties":
            payload = json.dumps(penalties, ensure_ascii=False).replace("</", "<\\/")
            assert "/*@PENALTIES@*/null" in src, t["src"]
            src = src.replace("/*@PENALTIES@*/null", payload)
        elif t.get("inject"):
            names = t["inject"] if isinstance(t["inject"], list) else [t["inject"]]
            src = inject_data(src, names, t["src"])
        src += dl_section("../../", tool=t["id"]) + lawver_html(t["id"], "../../", t.get("law", "")) + tool_ld(t, site)
        return page(site, "../../", f"tools/{t['id']}/", t["name"] + (" · 무료 양식" if t.get("cat") == "작성기" else ""), src, desc=t.get("desc"), active="tools/")
    if t.get("inject") == "hazards":
        payload = json.dumps(hazards, ensure_ascii=False).replace("</", "<\\/")
        assert "/*@HAZARDS@*/null" in src, t["src"]
        src = src.replace("/*@HAZARDS@*/null", payload)
    elif t.get("inject") == "tailwind":
        css = (ROOT / t["css"]).read_text(encoding="utf-8").replace("</style", "<\\/style")
        assert "/*@TAILWIND@*/" in src, t["src"]
        src = src.replace("/*@TAILWIND@*/", css)
    if site.get("name_ko") and f" | {site['name']}</title>" in src:   # 단독 화면 제목에도 한글 이름
        src = src.replace(f" | {site['name']}</title>", f"{' · 무료 양식' if t.get('cat') == '작성기' else ''} | {site['name_ko']} {site['name']}</title>", 1)
    if "og:image" not in src and "</head>" in src:
        src = src.replace("</head>", og_image_tags(site) + "\n" + tool_ld(t, site) + "\n</head>", 1)
    if "</body>" in src and "assets/ping.js" not in src:   # 단독 화면(헤더 없는 작성기)도 방문자 수에 포함
        src = src.replace("</body>", ping_tag(site, "../../") + "</body>", 1)
    if t["id"] in ("tbm", "committee", "council", "joint", "patrol", "edu-log", "permit"):
        note = ('<style>@media print{.adk-note{display:none!important}}</style><p class="adk-note" style="max-width:210mm;margin:8px auto;padding:0 12px;font-size:11px;color:#8A94A3;line-height:1.6">SafePlum 실무용 보조양식 — '
                '관련 조문을 참고해 만든 보조양식이며, 이 양식을 채운 것만으로 법령상 의무를 이행했다고 볼 수는 없습니다. '
                f'법령 데이터 기준일 {e(manifest().get("checked_at", ""))}</p>')
        assert "</body>" in src
        src = src.replace("</body>", note + "</body>", 1)
    _dl = dl_section("../../", tool=t["id"])
    if _dl:   # 화면 높이에 맞춘 작성기(본문 스크롤 없음)는 입력 칸 영역 맨 아래로 옮겨 작성 화면을 줄이지 않는다
        _dl += ('<script>(function(){var s=document.querySelector(".spdl");if(!s||getComputedStyle(document.body).overflow!=="hidden")return;'
                'var p=[].slice.call(document.querySelectorAll(".no-print")).filter(function(x){return /(auto|scroll)/.test(getComputedStyle(x).overflowY);})[0];'
                'if(p){s.style.margin="20px 0 8px";s.style.padding="0 4px";p.appendChild(s);}})();</script>')
        assert "</body>" in src
        src = src.replace("</body>", _dl + "</body>", 1)
    return src.replace('assets/ai.js"', f'assets/ai.js?v={ASSET_VER}"')


def precheck_forms(lawref):
    """기준규칙 별표 3(작업시작 전 점검사항) 19개 작업 → 점검표 서식."""
    b3 = lawref["byl3"]
    out = []
    for i, it in enumerate(b3["items"], 1):
        m = re.match(r"^(\d+(?:의\d+)?)\.\s*(.+?)\s*(\(제\d+편[^)]*\))?$", it["work"])
        no, name, part = (m.group(1), m.group(2), m.group(3) or "") if m else (str(i), it["work"], "")
        checks = [re.sub(r"^[가-하]\.\s*", "", c) for c in it["checks"]]
        short = re.sub(r"(을|를)?\s*(사용하여|사용하는|가동할|취급하는|사용할).*$", "", name).strip() or name
        out.append({
            "id": f"pre-{i:02d}", "group": "작업시작 전 점검(별표 3)", "title": f"작업시작 전 점검표 — {short}",
            "short": short, "doc_title": "작업시작 전 점검표",
            "desc": f"{name}. 관리감독자가 작업을 시작하기 전에 점검하고, 이상이 발견되면 즉시 수리하거나 필요한 조치를 합니다.",
            "law": f"산업안전보건기준에 관한 규칙 제35조제2항 · 별표 3 제{no}호 {part}".strip(), "src_law": "산업안전보건기준에 관한 규칙",
            "approval": ["점검자(관리감독자)", "확인"],
            "sections": [
                {"type": "fields", "cols": 2, "fields": [
                    {"k": "date", "label": "점검일", "type": "date"}, {"k": "place", "label": "작업 장소"},
                    {"k": "equip", "label": "기계·설비명(번호)"}, {"k": "who", "label": "점검자"}]},
                {"type": "note", "text": f"작업: {name}"},
                {"type": "check", "k": "chk", "title": "점검 내용 (별표 3)", "opts": ["양호", "불량"], "items": checks},
                {"type": "table", "k": "fix", "title": "이상 발견 시 조치 (제35조제3항)", "rows": 3, "cols": [
                    {"label": "이상 내용", "multi": True}, {"label": "조치 내용", "multi": True}, {"label": "조치일", "w": 14}, {"label": "확인", "w": 12}]}
            ]})
    return out


FAMILY = {"worklog": {"title": "안전 · 보건관리자 업무일지", "roles": [("safety", "안전관리자"), ("health", "보건관리자")], "periods": [("day", "일일"), ("week", "주간"), ("month", "월간")]}}
# 작업계획서(안전보건규칙 제38조제1항) — 화면 안에서 작업 종류를 바꿔 가며 쓰는 묶음. 선택 화면: tools/forms/workplan/
WORKPLAN_GROUPS = [("장비 사용", ["wp-forklift", "wp-heavy", "wp-aerial", "wp-truck", "wp-excavator", "wp-tower"]),
                   ("작업", ["wp-elec", "wp-chem", "wp-dig", "wp-demolish", "wp-bridge", "wp-tunnel", "wp-quarry", "wp-rail"])]
WORKPLAN_IDS = [i for _, ids in WORKPLAN_GROUPS for i in ids]

# ---- 무료 내려받기 양식(data/downloads.json): 관련 화면 아래 카드 + resources/templates/ 모음
_DL = None


def _jpeg_size(p):
    b = p.read_bytes()
    i = 2
    while i < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    return 720, 413


def downloads():
    global _DL
    if _DL is None:
        _DL = load("data/downloads.json")["items"]
        for x in _DL:
            fp, pv = ROOT / x["file"], ROOT / x["preview"]
            assert fp.exists() and pv.exists(), x["id"]
            x["size"], x["ext"] = fp.stat().st_size, fp.suffix[1:]
            x["w"], x["h"] = _jpeg_size(pv)
    return _DL


DL_CSS = ('<style>.spdl{max-width:1000px;margin:28px auto 12px;padding:0 16px;color:var(--text,#0F172A)}'
          '.spdl h2{font-size:18px;margin:0 0 4px;color:var(--text,#0F172A);font-weight:800}.spdl>p{margin:0 0 14px;font-size:13.5px;line-height:1.6;color:var(--muted,#64748B)}'
          '.spdl-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px}'
          '.spdl-c{display:flex;flex-direction:column;border:1px solid var(--line,#E2E8F0);border-radius:12px;background:var(--surface,#fff);overflow:hidden}'
          '.spdl-t{display:block;background:#E8EBF2;border-bottom:1px solid var(--line,#E2E8F0)}.spdl-t img{display:block;width:100%;height:auto}'
          '.spdl-b{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;flex:1}'
          '.spdl-k{font-size:12px;font-weight:700;color:#0E7A44;margin:0}.spdl-k.pp{color:#C2410C}'
          '.spdl-b strong{font-size:15.5px;line-height:1.4;color:var(--text,#0F172A)}'
          '.spdl-d{font-size:13px;line-height:1.6;color:var(--text-2,#334155);margin:0}.spdl-p{font-size:12px;line-height:1.5;color:var(--muted,#64748B);margin:0}'
          '.spdl-a{margin-top:6px;display:flex;justify-content:center;align-items:center;min-height:44px;border-radius:10px;background:var(--blue,#1D4ED8);color:#fff!important;font-weight:700;font-size:14.5px;text-decoration:none!important}'
          '.spdl-a:hover{filter:brightness(1.08)}.spdl-more{display:inline-block;margin-top:12px;font-size:14px;font-weight:700;color:var(--blue,#1D4ED8)}'
          '@media print{.spdl{display:none!important}}</style>')


def one_sentence(d):
    d = re.split(r"(?<=[.다요])\s", str(d or "").strip())[0]
    return d.rstrip(".")


def dl_size(n):
    return f"{n / 1024:.0f}KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f}MB"


def dl_card(x, rel):
    pp = x["kind"] == "PowerPoint"
    return (f'<article class="spdl-c"><a class="spdl-t" href="{rel}{e(x["file"])}" download="{e(x["dl"])}" tabindex="-1" aria-hidden="true">'
            f'<img src="{rel}{e(x["preview"])}" width="{x["w"]}" height="{x["h"]}" loading="lazy" alt=""></a>'
            f'<div class="spdl-b"><p class="spdl-k{" pp" if pp else ""}">{e(x["kind"])} 양식 · 무료</p><strong>{e(x["title"])}</strong>'
            f'<p class="spdl-d">{e(x["desc"])}</p><p class="spdl-p">들어 있는 것: {e(" · ".join(x.get("parts") or []))}</p>'
            f'<a class="spdl-a" href="{rel}{e(x["file"])}" download="{e(x["dl"])}">내려받기 (.{e(x["ext"])} · {dl_size(x["size"])})</a></div></article>')


def dl_section(rel, tool=None, form=None):
    """이 화면과 관련된 내려받기 양식 카드. 없으면 빈 문자열."""
    items = [x for x in downloads() if (tool and tool in x.get("tools", [])) or (form and form in x.get("forms", []))]
    if not items:
        return ""
    return (DL_CSS + f'<section class="spdl" aria-label="내려받기 양식"><h2>엑셀·PPT 양식으로도 받을 수 있습니다</h2>'
            f'<p>화면 작성이 어려운 곳(사내 결재 양식, 출력해서 수기 작성)에서 쓰도록 만든 파일입니다. 회색 기울임 글씨는 예시이니 지우고 쓰세요.</p>'
            f'<div class="spdl-g">{"".join(dl_card(x, rel) for x in items)}</div>'
            f'<a class="spdl-more" href="{rel}resources/templates/">무료 양식 전체 {len(downloads())}종 보기 →</a></section>')


def all_forms(lawref):
    fj = load("data/forms.json")
    forms = fj["forms"] + precheck_forms(lawref)
    groups = fj["groups"] + ["작업시작 전 점검(별표 3)"]
    ids = [f["id"] for f in forms]
    assert len(ids) == len(set(ids)), "서식 id 중복"
    auto = form_auto_map()
    for f in forms:
        f.setdefault("checked", fj.get("checked"))
        if f.get("src_law"):
            f["source_url"] = law_url(f["src_law"])
        f["auto"] = auto.get(f["id"], {"source": "", "checked": ""})
        # AI 작성 도우미 입력 예시: 서식별 예시 + 묶음별 예시를 합쳐 5개까지(눌러서 넣는 칩으로 보인다)
        _ai = f["auto"].setdefault("ai", {})
        _own = AI_FORM.get(f["id"], {})
        _ex = ([_ai["example"]] if _ai.get("example") else []) + list(_ai.get("examples") or []) + list(_own.get("ex") or [])
        if not _ex:   # 서식별 예시가 없을 때만 묶음 예시를 쓴다(다른 서식 예시가 섞이지 않게)
            _ex = AI_EX_GROUP.get(f.get("group", ""), [])
        _ai["examples"] = list(dict.fromkeys(x for x in _ex if x))[:5]
        if _own.get("note"):
            _ai.setdefault("note", _own["note"])
        if "fields" not in _ai:
            _ai["fields"] = [dict(x, ph=_own["ph"][x["k"]]) if x.get("k") in (_own.get("ph") or {}) else x for x in AI_FIELDS_GROUP.get(f.get("group", ""), [])]
        fam = f.get("family")
        if fam:   # 같은 묶음(직무 × 주기)을 화면 안에서 오가는 선택 버튼
            sib = [x for x in forms if (x.get("family") or {}).get("name") == fam["name"]]
            pick = lambda role, period: next((x["id"] for x in sib if x["family"]["role"] == role and x["family"]["period"] == period), None)
            f["switch"] = {"title": FAMILY[fam["name"]]["title"], "groups": [
                {"label": "직무", "options": [{"label": lb, "on": k == fam["role"], "href": f"../{pick(k, fam['period'])}/"} for k, lb in FAMILY[fam["name"]]["roles"] if pick(k, fam["period"])]},
                {"label": "작성 주기", "options": [{"label": lb, "on": k == fam["period"], "href": f"../{pick(fam['role'], k)}/"} for k, lb in FAMILY[fam["name"]]["periods"] if pick(fam["role"], k)]}]}
        if f["id"] in WORKPLAN_IDS:   # 작업계획서: 화면 안에서 작업 종류(지게차·중량물 등)를 바꾼다. 서식마다 입력값은 따로 저장
            _fb = {x["id"]: x for x in forms}
            f["switch"] = {"title": f["title"], "keep": True, "hub": "../workplan/", "groups": [
                {"label": g, "options": [{"label": _fb[i].get("short") or _fb[i]["title"], "on": i == f["id"], "href": f"../{i}/"} for i in ids if i in _fb]}
                for g, ids in WORKPLAN_GROUPS]}
        f.pop("approval", None)  # 결재란은 공통(담당·검토·승인, 사용자가 고침) — assets/docs.js
        if f["id"] == "patrol":
            f["flow"] = {"chk": {"bad": ["불량"], "to": "fix", "col": 1, "label": "지적 사항 표"}}
        elif f["id"].startswith("pre-"):
            f["flow"] = {"chk": {"bad": ["불량"], "to": "fix", "col": 0, "label": "이상 발견 시 조치 표"}}
        a = f["auto"]
        # 공통 자동화: 날짜(…일) 칸은 오늘, 작업시작 전 점검표의 점검자는 관리감독자(기준규칙 제35조제2항)
        for sec in f["sections"]:
            for fl in sec.get("fields", []):
                key = "f." + fl["k"]
                if fl.get("type") == "date" and fl["k"] == "date" and key not in a.get("today", []):
                    a.setdefault("today", []).append(key)
                if f["id"].startswith("pre-") and fl["k"] == "who":
                    a.setdefault("profile", {}).setdefault(key, "sup")
                if fl["k"] == "site":
                    a.setdefault("profile", {}).setdefault(key, "company")
        for key, opts in (f.get("auto", {}).get("cycle_options") or {}).items():
            for sec in f["sections"]:
                for fl in sec.get("fields", []):
                    if "f." + fl["k"] == key:
                        fl["options"] = opts
    return groups, forms


STATUS_LABEL = {"ok": ("badge-green", "바로 사용"), "external": ("badge-blue", "공식 자료 연결"),
                "planned": ("badge-muted", "준비 중"), "skip": ("badge-line", "제공 안 함")}


def catalog_html(cat, rel):
    """법령 순서 카탈로그: 법령별 표 하나, 장(章)은 구분 행, 항목은 이름 · 근거 · 상태 한 줄."""
    ST = {"ok": "바로 사용", "external": "공식 자료", "planned": "준비 중", "skip": "제공 안 함"}
    parts, acts = [], []
    for c in cat["categories"]:
        if c["act"] not in acts:
            acts.append(c["act"])
    for act in acts:
        cats = [c for c in cat["categories"] if c["act"] == act]
        n_ok = sum(1 for c in cats for x in c["items"] if x["status"] in ("ok", "external"))
        n_all = sum(len(c["items"]) for c in cats)
        rows = []
        for c in cats:
            ok = sum(1 for x in c["items"] if x["status"] in ("ok", "external"))
            rows.append(f'<tr class="ct-g"><th colspan="3" scope="colgroup">{e(c["cat"])} <span>{ok} / {len(c["items"])}</span></th></tr>')
            for x in c["items"]:
                st = x["status"]
                if st == "ok":
                    name = f'<a href="{rel}{e(x["link"])}">{e(x["name"])}</a>'
                elif st == "external":
                    name = f'<a href="{e(x["link"])}" target="_blank" rel="noopener">{e(x["name"])} ↗</a>'
                else:
                    name = f'<span>{e(x["name"])}</span>'
                note = f'<span class="ct-note">{e(x["note"])}</span>' if x.get("note") else ""
                rows.append(f'<tr class="ct-r st-{st}"><td class="ct-n">{name}{note}</td><td class="ct-b">{e(x["basis"])}</td><td class="ct-s">{ST[st]}</td></tr>')
        parts.append(f'<section class="cat-act"><h3 class="ct-h">{e(act)} <span>사용 가능 {n_ok} / 전체 {n_all}</span></h3>'
                     f'<table class="ct"><thead><tr><th scope="col">항목</th><th scope="col">근거</th><th scope="col">상태</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')
    return "".join(parts)


def empty_box(msg, extra=""):
    return f'<div class="empty"><p>{e(msg)}</p>{extra}</div>'


def duck_signs_html(site, write):
    """SafePlum 자체 제작 현장 안내 게시물 — 목록(표지 페이지 상단) + 한 장씩 A4 인쇄 페이지."""
    d = load("data/duck_signs.json")
    cards = []
    for it in d["items"]:
        pid = f"resources/signs/duck-{it['id']}/"
        cards.append(f'<li class="dk-card"><a href="duck-{e(it["id"])}/"><img src="../../{e(it["thumb"])}" width="240" height="240" alt="{e(it["title"])} 안내 게시물 미리보기" loading="lazy">'
                     f'<strong>{e(it["title"])}</strong><span>{e(" · ".join(it.get("langs", [])))}</span></a></li>')
        body = f"""
<section class="phead no-print"><div class="wrap">
  <p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">서식·자료</a><span>/</span><a href="../#duck">안전보건표지</a><span>/</span>{e(it["title"])}</p>
  <h1>{e(it["title"])} <span class="muted" style="font-size:.6em">SafePlum 안내 게시물</span></h1>
  <p>{e(it.get("desc", ""))}</p>
  <p class="btns" style="margin-top:14px"><button type="button" class="btn" onclick="window.print()">A4 인쇄 · PDF 저장</button>
  <a class="btn btn-ghost" href="../../../{e(it["print"])}" download="SafePlum_{e(it["title"])}.png">원본 이미지 내려받기</a>
  {f'<a class="btn btn-ghost" href="../../../{e(it["law_href"])}">근거 조문 보기</a>' if it.get("law_href") else ""}</p>
  <p class="hint" style="margin-top:10px">근거: {e(it.get("basis", ""))} · 법정 안전보건표지(시행규칙 별표 6)와 함께 게시하는 현장 안내물입니다.</p>
</div></section>
<div class="dk-sheet"><img src="../../../{e(it["print"])}" alt="{e(it["title"])} 안내 게시물"></div>"""
        write(f"{pid}index.html", page(site, "../../../", pid, f'{it["title"]} 안내 게시물', body, desc=it.get("desc"), active="resources/"))
    return (f'<section class="dk-sec" id="duck"><div class="dk-head"><div><h2>SafePlum 현장 안내 게시물</h2>'
            f'<p>SafePlum이 자체 제작·SafePlum이 번역한 다국어 안내 게시물입니다. 누르면 A4 한 장으로 인쇄할 수 있습니다. 법정 안전보건표지(아래 40종)를 대신하지는 않습니다.</p></div></div>'
            f'<ul class="dk-grid">{"".join(cards)}</ul></section>')


# ---------------------------------------------------------------- 페이지

def build(out, today):
    site = load("config/site.json")
    global JOB_POST
    JOB_POST = bool((site.get("features") or {}).get("job_posting", True))  # 회원 채용공고 등록을 열어 둘지
    base_res = load("data/resources.json")
    _groups, _forms = all_forms(load("data/lawref.json"))
    global WRITER_N
    WRITER_N = sum(len(items) for _, items in writer_groups(site, _groups, _forms))
    web_forms = [{"id": "wf-" + f["id"], "category": "웹 작성 서식", "title": f["title"], "law": "", "form_no": f.get("group", ""),
                  "summary": f.get("desc", ""), "tags": [f.get("group", ""), f.get("short", "")], "topic": WF_TOPIC.get(f.get("group", ""), "기타"),
                  "free_tool": "forms/" + f["id"], "basis": f.get("law", "")} for f in _forms]
    HAS_PC = bool(safe_url(((site.get("tools") or [{}])[0]).get("url")))
    resources = [resolve_resource(r) for r in base_res + web_forms + lawform_resources(base_res) if r.get("category") != "무료 작성 도구" and (HAS_PC or r.get("category") != "Mallo 서식")]
    for r in resources:
        if not r.get("topic") or r["topic"] == "기타":
            probe = r.get("title", "") + " " + " ".join(r.get("tags") or [])
            r["topic"] = next((tp for tp, kws in LF_TOPICS if any(k in probe for k in kws)), r.get("topic") or "기타")
    for r in resources:
        if r.get("byl_no") and r.get("law"):
            r["detail"] = f"resources/f/{r['id']}/"
    LIDX = law_index()
    LFILES = load("data/lawfiles.json")["items"] if (ROOT / "data/lawfiles.json").exists() else {}
    for r in resources:
        if r.get("byl_no"):
            fk = f'{r["law"]}|{r.get("byl_cls","BF")}|{r["byl_no"]}|{r.get("byl_br","00")}'
            r["files"] = (LFILES.get(fk) or {}).get("files", {})
    laws = load("data/laws.json")
    sites = load("data/sites.json")
    AUTO = ROOT / "data/auto"
    def load_auto(name):
        f = AUTO / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"items": [], "fetched": ""}
    pubjobs = load_auto("pubjobs.json")
    for j in pubjobs["items"]:
        j.setdefault("company_type", "공공기관")
        j.setdefault("employment", j.get("ctype", ""))
    user_jobs = load("data/job_posts.json") if (ROOT / "data/job_posts.json").exists() else []
    for j in user_jobs:
        j["origin"] = "user"
        j.setdefault("source_name", "기업 직접 등록")
    jobs = validate_jobs(load("data/jobs.json") + user_jobs + pubjobs["items"], today)
    global JOBS_OPEN
    JOBS_OPEN = sum(1 for x in jobs if not x["closed"])
    briefs = load_briefs(today)
    auto_news, auto_acc = load_auto("news.json"), load_auto("accidents.json")
    hazards = load("data/hazards.json")
    hazards = {"groups": hazards["groups"], "items": hazards["items"]}
    penalties = load("data/penalties.json")

    if site.get("base_url") and not safe_url(site.get("base_url")):
        sys.exit("config/site.json 의 base_url 이 https 주소가 아닙니다.")
    if not site.get("base_url"):
        warn("base_url 이 비어 있음 → canonical·og:url·sitemap 을 만들지 않음(도메인이 정해지면 config/site.json 에 입력)")
    for t in site.get("tools", []):
        if not safe_url(t.get("url")):
            warn(f"도구 '{t.get('name')}' 주소가 비어 있음 → '준비 중'으로 표시")
    for r in resources:
        if r.get("category") != "Mallo 서식" and not r.get("free_tool") and not r.get("href"):
            warn(f"자료 {r['id']}: 원본 주소가 없음")

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "assets", out / "assets")
    write_lawai(out)
    n_kosha = build_kosha_client(out)

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
    EXT = '<svg class="chip-ext" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>'
    job_chips = "".join(
        f'<a class="jchip" href="{e(safe_url(s["url"]))}" target="_blank" rel="noopener">{e(s["name"])}{EXT}<span class="sr">(새 창)</span></a>'
        for s in sites.get("job_search", []) if safe_url(s.get("url")))
    jobs_empty = (f'<div class="jempty"><div class="jempty-ico" aria-hidden="true"><img src="../assets/img/ico/helmet.webp" width="96" height="96" alt=""></div>'
                  f'<p class="jempty-t">채용 플랫폼의 안전·보건 공고로 바로 연결합니다.</p>'
                  f'<p class="jempty-d">아래 채용 플랫폼에서 안전·보건 직무의 실시간 공고를 바로 확인하세요.</p>'
                  f'<div class="jchips">{job_chips}</div></div>')
    updates = sorted(laws.get("updates", []), key=lambda u: u.get("date", ""), reverse=True)
    official_list = "".join(
        f'<li><a href="{e(safe_url(s["url"]))}" target="_blank" rel="noopener"><strong>{e(s["name"])}</strong><span>{e(s["desc"])}</span></a></li>'
        for s in sites.get("official", []) if safe_url(s.get("url")))

    n_forms = len(_forms)
    counsel_list = "".join(
        f'<li><a href="{e(safe_url(s["url"]))}" target="_blank" rel="noopener"><strong>{e(s["name"])} ↗</strong><span>{e(s["desc"])}</span></a></li>'
        for s in sites.get("counsel", []) if safe_url(s.get("url")))
    diag_band = f"""<section class="dx" aria-label="빠른 판정">
  <div class="wrap dx-in">
    <form class="dx-main" action="tools/selection/" method="get">
      <p class="dx-eye">⚖️ 인원·업종별 적용범위</p>
      <h2>우리 사업장, 산안법·중처법 어디까지?<br><span class="dx-yn y">YES</span><span class="dx-or">or</span><span class="dx-yn n">NO</span></h2>
      <div class="dx-row">
        <label class="sr" for="dxInd">업종</label><input id="dxInd" name="ind" type="text" placeholder="업종 (예: 식료품, 금속가공, 건설)" autocomplete="off">
        <label class="sr" for="dxN">상시근로자 수</label><input id="dxN" name="n" type="number" min="0" inputmode="numeric" placeholder="상시근로자 수">
        <button class="btn" type="submit">판정하기</button>
      </div>
      <p class="dx-sub">공통 의무·선임·위원회·공시·도급·중대재해처벌법까지 근거 조문과 함께 적용·조건부·확인 필요·적용 제외로 보여 주는 자가진단입니다.</p>
    </form>
    <div class="dx-cards">
      <a class="dx-card" href="tools/hpp/"><span class="i" aria-hidden="true"><img src="assets/img/ico/bell.webp" width="40" height="40" alt="" loading="lazy"></span><span><b>유해위험방지계획서, 내야 하나?</b><span>공장 설치·증설 300kW·100kW, 위험 설비, 건설공사</span></span><span class="arr" aria-hidden="true">→</span></a>
      <a class="dx-card" href="tools/machines/"><span class="i" aria-hidden="true"><img src="assets/img/ico/process.webp" width="40" height="40" alt="" loading="lazy"></span><span><b>이 기계, 무슨 의무가 있지?</b><span>안전인증·자율안전확인·안전검사·방호조치 31종</span></span><span class="arr" aria-hidden="true">→</span></a>
      <a class="dx-card" href="tools/docmap/"><span class="i" aria-hidden="true"><img src="assets/img/ico/audit.webp" width="40" height="40" alt="" loading="lazy"></span><span><b>감독 오면 서류 다 있나?</b><span>업무 12가지 서류 자가점검 · 준비율 계산</span></span><span class="arr" aria-hidden="true">→</span></a>
    </div>
  </div>
</section>"""
    sched = load("data/schedule.json")
    MO_KEYS = ("key", "title", "freq", "month", "day", "weekday", "qmonth", "hmonth", "m0", "anchor", "work", "time", "tool", "form", "off", "ind")
    mo_tasks = [{k: t[k] for k in MO_KEYS if k in t} for t in sched["tasks"]]
    mo_json = json.dumps(mo_tasks, ensure_ascii=False).replace("</", "<\\/")
    month_box = f"""<section class="side-box" id="moBox">
      {sec_head("이번 달 안전보건 달력", "tools/schedule/", more="전체 달력")}
      <div class="mc" id="moCal"></div>
      <h3 class="mo-day" id="moDay" aria-live="polite"></h3>
      <ul class="mo-list" id="moList"><li>달력을 불러오는 중…</li></ul>
      <p class="hint" id="moMine" hidden style="margin-top:8px">이 브라우저에서 바꾼 주기업무 설정을 반영했습니다.</p>
      <p class="hint" style="margin-top:8px">날짜를 누르면 그날 업무가 바뀝니다. 날짜는 권장 기준일이며 <a href="tools/schedule/">법정 주기업무 달력</a>에서 사업장에 맞게 바꿀 수 있습니다.</p>
      <noscript><p class="hint">달력을 보려면 자바스크립트를 켜야 합니다.</p></noscript>
      <script>window.ST_MO={mo_json};window.ST_IND={json.dumps(sched.get("industries", []), ensure_ascii=False)};</script>
      <script src="assets/home-cal.js?v={ASSET_VER}"></script>
    </section>"""
    # ---- 홈
    quick = "".join(f'<a class="qk" href="resources/?q={quote(k)}">{e(k)}</a>' for k in QUICK_KEYWORDS)
    # 자주 찾는 서식·자료: 법정 서식(원본 파일 있음)과 고시·지침만. 작성 도구는 '무료 도구'에서만 보여 중복을 없앤다
    by_id = {r["id"]: r for r in resources}
    popular = [r for r in resources if r.get("popular") and r.get("category") in ("법정 서식", "고시·지침")]
    popular += [by_id[i] for i in HOME_FORMS if i in by_id and by_id[i] not in popular]
    popular = popular[:8]
    tools_cta = ('<aside class="cta-banner"><div><strong>실무 문서는 무료 도구에서 바로 작성하세요</strong>'
                 '<p>법정 서식이 아닌 실무용 문서(TBM 일지, 위험성평가서, 산보위 회의록, 점검표 등)는 무료 도구에서 직접 작성하고 결재·서명·사진까지 넣어 인쇄할 수 있습니다 👉</p></div>'
                 '<a class="btn" href="{rel}tools/">무료 도구로 가기 <span aria-hidden="true">→</span></a></aside>')
    def board(title, href, rows, more="더보기", badge=""):
        return (f'<section class="bd"><div class="bd-h"><h2>{e(title)}{badge}</h2><a class="more" href="{href}">{e(more)} <span aria-hidden="true">→</span></a></div>'
                f'<ul class="bd-list">{rows}</ul></section>')

    def bd_row(href, text, meta="", tag="", ext=False):
        t = f'<span class="bd-tag">{e(tag)}</span>' if tag else ""
        x = ' target="_blank" rel="noopener"' if ext else ""
        return f'<li><a href="{e(href)}"{x}>{t}<span class="bd-t">{e(text)}</span></a>{f"<span class=bd-m>{e(meta)}</span>" if meta else ""}</li>'

    def md(d):
        return f"{d[5:7]}.{d[8:10]}" if DATE_RE.match(str(d or "")) else ""

    if briefs:
        b0 = briefs[0]
        rows = "".join(bd_row(f"brief/{b0['date']}/", it["title"], md(it.get("date") or b0["date"]), it.get("cat") or "정책") for it in b0["items"][:4])
        rows += "".join(bd_row(f"brief/{b['date']}/", b["title"], md(b["date"]), "지난 호") for b in briefs[1:3])
        bd_brief = board("오늘의 안전 브리핑", "brief/", rows, badge=f'<span class="bd-new">{md(b0["date"])}</span>')
    else:
        bd_brief = board("오늘의 안전 브리핑", "brief/", '<li class="bd-empty">아직 발행된 브리핑이 없습니다.</li>')
    if open_jobs:
        rows = "".join(bd_row(f"jobs/{j['id']}/", f"{j['company']} · {j['title']}", (md(j.get("deadline")) + " 마감") if DATE_RE.match(str(j.get("deadline") or "")) else str(j.get("deadline") or ""), (j["jobs_list"] or ["채용"])[0]) for j in open_jobs[:5])
    else:
        rows = "".join(
            bd_row(safe_url(x["url"]), x["name"] + "에서 찾기", "", "외부", ext=True) for x in sites.get("job_search", [])[:3] if safe_url(x.get("url")))
    bd_jobs = board("채용정보", "jobs/", rows)
    import lawpages
    man = manifest()
    LAWS_KEYS = {l["key"] for l in man["laws"]}
    _tbl, n_up, n_chk = lawpages.status_panel(LAWS_KEYS, man, today, "laws/")
    n_chk += sum(1 for n in man.get("notices", []) if n.get("status") != "verified") + len(man.get("open_items", []))
    ups_all = sorted(((u["effective"], l["name"], u) for l in man["laws"] for u in l.get("upcoming", []) if u["effective"] > today), key=lambda x: x[0])
    today_chg = [(l["name"], u) for l in man["laws"] for u in l.get("upcoming", []) + l.get("recent", []) + [l["current"]] if u.get("effective") == today or u.get("promulgated") == today]
    chg_txt = ("오늘 시행·공포 " + ", ".join(f"{nm} {u['no']}" for nm, u in today_chg)) if today_chg else "오늘 시행·공포된 변경 없음(확인일 기준)"
    nxt_txt = f"다음 시행 {lawpages.kdate(ups_all[0][0])} {ups_all[0][1]}" if ups_all else "확인된 시행 예정 없음"
    stale_txt = ' · <b>확인일이 오래되었습니다 — 공식 원문 재확인 필요</b>' if stale(man.get("checked_at", ""), dt.date.fromisoformat(today)) else ""
    stale_txt2 = ' · <b>공식 원문 재확인 필요</b>' if stale_txt else ""
    asof_strip = (f'<p class="asof"><span class="wrap">법령 데이터 기준일 <b>{e(man.get("checked_at", ""))}</b>{stale_txt2}'
                  f' · <a href="laws/#upcoming">시행 예정 {n_up}건</a></span></p>')
    def short_law(nm):
        return nm.replace("산업안전보건기준에 관한 규칙", "안전보건규칙").replace("산업안전보건법", "산안법").replace("중대재해 처벌 등에 관한 법률", "중대재해처벌법")
    law_rows = "".join(bd_row("laws/#upcoming", f"{short_law(nm)} {lawpages.kdate(eff)} 시행 ({u['no'].split(' ')[-1]})", "", "시행 예정") for eff, nm, u in ups_all[:4])
    law_rows += "".join(bd_row("laws/#bills", b.get("title", ""), md(b.get("stage_date")), "입법 동향") for b in man.get("bills", [])[:1])
    seen_t = set()
    for u in [x for x in updates if (x.get("effective") or x.get("date") or "") <= today]:
        key = (u.get("law"), u["title"].split(" — ")[0])
        if key in seen_t or len(seen_t) >= 2:
            continue
        seen_t.add(key)
        law_rows += bd_row("laws/#updates", short_law(u.get("law", "")) + " " + u["title"].split(" — ")[0], md(u.get("effective") or u.get("date")), "시행 중")
    bd_laws = board(f"법령 현황 · 기준일 {md(man.get('checked_at'))}", "laws/", law_rows)
    _unused = board("법령 개정", "laws/#updates", "".join(bd_row(f"laws/#updates", u["title"], md(u.get("date")), u.get("law", "").replace("산업안전보건법 ", "").replace("산업안전보건", "산안")[:6]) for u in updates[:5]))
    FORM_PICKS = ["log-safety", "log-safety-w", "log-health", "accident", "ppe-ledger", "log-sup"]
    fby = {f["id"]: f for f in _forms}
    bd_forms = board(f"작성기 {WRITER_N}종", "tools/forms/", "".join(bd_row(f"tools/forms/{i}/", fby[i]["title"], "", fby[i]["group"][:5]) for i in FORM_PICKS if i in fby))
    bd_res = board("자주 찾는 법정 서식", "resources/", "".join(bd_row(f"resources/{r['detail']}" if r.get("detail") else "resources/", r["title"], "", "서식" if r.get("category") == "법정 서식" else "고시") for r in popular[:6]))
    lib = load("data/library.json")
    bd_lib = board("안전보건 자료실", "resources/library/", "".join(bd_row(safe_url(x["url"]), x["name"], "", "공식", ext=True) for x in lib.get("official", [])[:3] if safe_url(x.get("url")))
                   + bd_row("resources/signs/", "안전보건표지 40종 · SafePlum 현장 안내 게시물", "", "표지") + bd_row("tools/docmap/", "감독 대비 서류 자가점검", "", "점검"))
    quick_strip = ('<section class="qs" aria-label="기관 바로가기"><div class="wrap qs-in"><span class="qs-l">바로 신청·신고</span>' + "".join(
        f'<a class="qs-go" href="{e(safe_url(x["url"]))}" target="_blank" rel="noopener" title="{e(x.get("desc", ""))}">{e(x["name"])} ↗</a>' for x in sites.get("civil", []) if safe_url(x.get("url"))) + '<span class="qs-l qs-l2">기관</span>' + "".join(
        f'<a href="{e(safe_url(x["url"]))}" target="_blank" rel="noopener">{e(x.get("short") or x["name"])}</a>' for x in sites.get("official", []) + sites.get("quick", []) if safe_url(x.get("url"))) + "</div></section>")
    tby = {t["id"]: t for t in site.get("free_tools", [])}
    def one_line(d):
        d = re.split(r"(?<=[.다요])\s", str(d or "").strip())[0]
        return d.rstrip(".")
    def mcard(href, icon, title, desc, badge):
        return (f'<a class="hc" href="{e(href)}"><span class="hc-i" aria-hidden="true">{icon}</span><span class="hc-b"><strong>{e(title)}</strong>'
                f'<span class="hc-d">{e(desc)}</span></span><span class="hc-g">{e(badge)}</span></a>')
    def tcards(ids):
        return "".join(mcard(f"tools/{i}/", (f'<img src="assets/img/ico/{TOOL_DUCKS[i]}.webp" width="44" height="44" alt="" loading="lazy">' if i in TOOL_DUCKS else TOOL_ICONS.get(i, "📄")), tby[i].get("menu") or tby[i].get("short") or tby[i]["name"], one_line(tby[i]["desc"]), (tby[i].get("law") or "무료").split(" · ")[0][:22]) for i in ids if i in tby)
    tab1 = tcards(WRITE_TOOLS) + "".join(mcard(f"tools/forms/{i}/", f'<img src="assets/img/ico/{ic}.webp" width="44" height="44" alt="" loading="lazy">', (x[2] if len(x) > 2 else fby[i].get("short") or fby[i]["title"]), (x[3] if len(x) > 3 else one_line(fby[i].get("desc", ""))), ((x[4] if len(x) > 4 else "시행령 제18조·제22조") if len(x) > 2 else (fby[i].get("law") or "무료").replace("산업안전보건기준에 관한 규칙", "기준규칙").replace("산업안전보건법", "산안법").split(" · ")[0][:22])) for x in HOME_WRITE_FORMS for i, ic in [x[:2]] if i in fby or len(x) > 4)
    tab2 = tcards(CALC_TOOLS)
    look = "".join(f'<a href="tools/{i}/"><img src="assets/img/ico/{TOOL_DUCKS[i]}.webp" width="20" height="20" alt="" loading="lazy"> {e(tby[i].get("menu") or tby[i]["name"])}</a>' for i in LOOKUP_TOOLS if i in tby)
    form_rows = "".join(f'<li data-s="{e((f["title"] + " " + f.get("group", "")).lower())}"><a href="tools/forms/{e(f["id"])}/"><span class="fl-g">{e(f.get("group", "")[:10])}</span>{e(f["title"])}</a><span class="fkind fkind-b">웹 작성</span></li>' for f in _forms)
    form_rows += "".join(f'<li data-s="{e((r["title"] + " " + (r.get("form_no") or "")).lower())}"><a href="{e(r["detail"] if r.get("detail") else "resources/?q=" + quote(r["title"]))}"><span class="fl-g">{e((r.get("form_no") or "원본")[:10])}</span>{e(r["title"])}</a><span class="fkind fkind-a">법령 원본</span></li>' for r in popular)
    _bd = load("data/board.json")
    BOARD_CHECKED = _bd.get("checked", "")
    BOARD = [dict(x) for x in _bd.get("items", []) if x.get("title") and x.get("summary") and is_official(x.get("url", ""))]
    for b in briefs:
        for it in b["items"]:
            BOARD.append({"date": it.get("date") or b["date"], "cat": it.get("cat") or "정책", "agency": it.get("agency", ""), "title": it["title"], "official_title": it.get("official_title", ""),
                          "summary": it["summary"], "point": it.get("point", ""), "period": "", "url": it["sources"][0]["url"], "href": f"{b['date']}/",
                          "verify": "" if b.get("review") == "verified" else ""})
    # 입법예고·개정 포인트(data/bills.json): 게시판에는 요약만, 전문은 laws/bills/<slug>/
    BILLS = load("data/bills.json") if (ROOT / "data/bills.json").exists() else {"posts": []}
    for x in BILLS.get("posts", []):
        offi = [u for _n, u in x.get("sources", []) if is_official(u)]
        if not (x.get("title") and x.get("lead") and offi):
            warn(f"입법예고 포인트 {x.get('slug')}: 제목·요약·공식 출처가 없어 게시판에서 제외")
            continue
        BOARD.append({"date": x["date"], "cat": "입법예고" if x["stage"] in ("입법예고", "국회 통과") else "법령", "agency": "고용노동부", "title": x["title"],
                      "official_title": "", "summary": x["lead"], "point": (x.get("todo") or [""])[0], "period": x.get("effective", ""),
                      "url": offi[0], "href": f"../laws/bills/{x['slug']}/", "href_label": "해설 전문"})
    # 언론 보도 스크랩: 제목·요약·실무 포인트는 SafePlum이 쓴 문장, 원문은 링크만 (사진·기사 문장 미사용)
    for x in load("data/scrap.json").get("items", []):
        if x.get("title") and x.get("summary") and re.match(r"^https://", x.get("url", "")) and x.get("press"):
            BOARD.append({"date": x["date"], "cat": "언론보도", "agency": x["press"], "title": x["title"], "summary": x["summary"], "point": x.get("point", ""),
                          "period": "", "url": x["url"], "src_label": f'{x["press"]} 기사 원문', "press": True})
    BOARD.sort(key=lambda x: x["date"], reverse=True)
    import hashlib as _hl
    _seen = set()
    for x in BOARD:  # 상세 페이지 주소: 출처 주소+제목으로 만든 짧은 고유값(같은 글이면 빌드마다 같다)
        k = _hl.sha1((x.get("url", "") + "|" + x["title"]).encode("utf-8")).hexdigest()[:8]
        while k in _seen:
            k = _hl.sha1(k.encode()).hexdigest()[:8]
        _seen.add(k)
        x["id"] = k
    if BOARD:
        brief_rows = "".join(bd_row(f"brief/n/{x['id']}/", x["title"], md(x["date"]) if x.get("date_prec") != "month" else x["date"][5:7] + "월", x["cat"]) for x in BOARD[:7])
    elif briefs:
        b0 = briefs[0]
        brief_rows = "".join(bd_row(f"brief/{b0['date']}/", it["title"], md(it.get("date") or b0["date"]), it.get("cat") or "정책") for it in b0["items"][:4])
        brief_rows += "".join(bd_row(f"brief/{b['date']}/", b["title"], md(b["date"]), "지난 호") for b in briefs[1:3])
    else:
        brief_rows = '<li class="bd-empty">아직 발행된 브리핑이 없습니다.</li>'
    dm = load("data/docmap.json")
    def dm_href(h):
        return h.split("?q=")[0] + "?q=" + quote(h.split("?q=")[1]) if "?q=" in h else h
    dm_html = "".join(
        f'<section class="dmx"><h3><span>{i + 1}</span>{e(g["title"])}</h3><ul>' + "".join(
            f'<li><a href="{e(dm_href(d["href"]))}">{e(d["name"])}</a>{f"<em>{e(d[chr(99)+chr(111)+chr(110)+chr(100)])}</em>" if d.get("cond") else ""}</li>' for d in g["docs"]) + "</ul></section>"
        for i, g in enumerate(dm["groups"]))
    idx = [{"t": t["name"], "k": "도구", "h": f"tools/{t['id']}/", "d": (t.get("short") or "") + " " + (t.get("law") or "")} for t in site.get("free_tools", [])]
    idx += [{"t": f["title"], "k": "웹 서식", "h": f"tools/forms/{f['id']}/", "d": f.get("group", "")} for f in _forms]
    idx += [{"t": n, "k": "법령", "h": f"laws/{k}/", "d": "현행 전문"} for k, n in LAW_MENU]
    idx += [{"t": r["title"], "k": "서식·자료", "h": r["detail"] if r.get("detail") else "resources/?q=" + quote(r["title"]), "d": (r.get("form_no") or "") + " " + " ".join(r.get("tags") or [])}
            for r in resources if r.get("category") != "웹 작성 서식"]
    idx += [{"t": "안전보건표지 40종", "k": "자료", "h": "resources/signs/", "d": "표지 금지 경고 지시 안내"}, {"t": "오늘의 안전 브리핑", "k": "소식", "h": "brief/", "d": "뉴스 리포트"},
            {"t": "채용정보", "k": "소식", "h": "jobs/", "d": "안전관리자 보건관리자 채용"},
            {"t": "커뮤니티 게시판", "k": "게시판", "h": "board/?b=free", "d": "자유 현장 이야기 정보 공유"}, {"t": "Q&A 질문·답변", "k": "게시판", "h": "board/?b=qna", "d": "질문 답변 법령 실무"}, {"t": "법령 개정 소식·시행 예정", "k": "법령", "h": "laws/#upcoming", "d": "개정"}]
    idx_json = json.dumps(idx, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    def go_badge(x):
        return f'<em class="go-bdg">{e(x["badge"])}</em>' if x.get("badge") else ""
    civil = "".join(f'<li><a href="{e(safe_url(x["url"]))}" target="_blank" rel="noopener" title="{e(x.get("desc", ""))}"><span>{e(x["name"])}{go_badge(x)}</span> <span aria-hidden="true">↗</span></a></li>' for x in sites.get("civil", []) if safe_url(x.get("url")))
    orgs = "".join(f'<a href="{e(safe_url(x["url"]))}" target="_blank" rel="noopener">{e(x.get("short") or x["name"])}</a>' for x in sites.get("official", []) + sites.get("quick", []) if safe_url(x.get("url")))
    chips = "".join(f'<a class="qk" href="{h}">{e(k)}</a>' for k, h in [("TBM 일지", "tools/tbm/"), ("위험성평가", "tools/risk/"), ("적용범위 판정", "tools/selection/"), ("과태료", "tools/penalty/"), ("산업재해조사표", "resources/?q=" + quote("산업재해조사표")), ("MSDS 경고표지", "tools/msds/")])
    home_js = """<script>
(function () {
  var IDX = /*IDX*/[];
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var q = document.getElementById("uq"), box = document.getElementById("uqOut"), sel = -1;
  function find(v) {
    var ws = v.toLowerCase().split(/\\s+/).filter(Boolean); if (!ws.length) return [];
    var out = [];
    for (var i = 0; i < IDX.length && out.length < 60; i++) {
      var x = IDX[i], tt = x.t.toLowerCase(), all = tt + " " + (x.d || "").toLowerCase() + " " + x.k;
      if (ws.every(function (w) { return all.indexOf(w) >= 0; })) out.push({ x: x, s: (tt.indexOf(ws[0]) === 0 ? 0 : tt.indexOf(ws[0]) > 0 ? 1 : 2) + (x.k === "도구" ? 0 : 0.5) });
    }
    return out.sort(function (a, b) { return a.s - b.s; }).slice(0, 8).map(function (o) { return o.x; });
  }
  function draw() {
    var v = q.value.trim(), r = find(v); sel = -1;
    if (!v) { box.hidden = true; q.setAttribute("aria-expanded", "false"); return; }
    box.innerHTML = r.map(function (x, i) { return '<a role="option" id="uqo' + i + '" href="' + esc(x.h) + '"><span class="uq-k">' + esc(x.k) + "</span>" + esc(x.t) + "</a>"; }).join("") +
      '<a class="uq-all" href="resources/?q=' + encodeURIComponent(v) + '">서식·자료 전체에서 “' + esc(v) + '” 찾기 →</a>';
    box.hidden = false; q.setAttribute("aria-expanded", "true");
  }
  q.addEventListener("input", draw); q.addEventListener("focus", draw);
  q.addEventListener("keydown", function (ev) {
    var as = box.querySelectorAll("a"); if (box.hidden || !as.length) return;
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") { ev.preventDefault(); sel = (sel + (ev.key === "ArrowDown" ? 1 : -1) + as.length) % as.length; [].forEach.call(as, function (a, i) { a.classList.toggle("on", i === sel); }); }
    else if (ev.key === "Enter" && sel >= 0) { ev.preventDefault(); location.href = as[sel].href; }
    else if (ev.key === "Escape") { box.hidden = true; }
  });
  document.addEventListener("click", function (ev) { if (!ev.target.closest(".uq")) box.hidden = true; });
  // 탭
  var tabs = [].slice.call(document.querySelectorAll(".hub-tab")), panes = [].slice.call(document.querySelectorAll(".hub-pane"));
  function show(id, focus) {
    tabs.forEach(function (t) { var on = t.dataset.tab === id; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); });
    panes.forEach(function (p) { p.hidden = p.dataset.pane !== id; });
    try { sessionStorage.setItem("safetake.hometab", id); } catch (e) {}
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { show(t.dataset.tab); });
    t.addEventListener("keydown", function (ev) { if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") { ev.preventDefault(); show(tabs[(i + (ev.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length].dataset.tab, true); } });
  });
  var want = (location.hash || "").replace("#tab-", ""), saved = ""; try { saved = sessionStorage.getItem("safetake.hometab") || ""; } catch (e) {}
  var ids = tabs.map(function (t) { return t.dataset.tab; });
  show(ids.indexOf(want) >= 0 ? want : ids.indexOf(saved) >= 0 ? saved : ids[0]);
  // 서식 필터
  var fq = document.getElementById("fq"), fl = document.getElementById("fList"), fn = document.getElementById("fNone");
  function filt() { var v = fq.value.trim().toLowerCase(), n = 0; [].forEach.call(fl.children, function (li) { var ok = !v || li.dataset.s.indexOf(v) >= 0; li.hidden = !ok; if (ok) n++; }); fn.hidden = n > 0; }
  fq.addEventListener("input", filt);
})();
</script>""".replace("/*IDX*/[]", idx_json)
    home = f"""
<section class="hero2">
  <div class="wrap hero2-in">
    <img class="hero2-duck" src="assets/img/plum/hero.webp" width="150" height="150" alt="손을 흔드는 SafePlum 캐릭터" fetchpriority="high">
    <p class="hero2-eye">세이프플럼 SafePlum · 현장 안전지식 공유 커뮤니티</p>
    <h1>안전관리 서류, 여기서 바로</h1>
    <div class="uq" role="search">
      <label for="uq" class="sr">통합 검색</label>
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input id="uq" type="search" placeholder="필요한 서식, 법령, 계산기를 검색하세요" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="uqOut">
      <div class="uq-out" id="uqOut" role="listbox" hidden></div>
    </div>
    <p class="quick">{chips}</p>
  </div>
</section>
<div class="wrap home2">
  <section class="hub" aria-label="주요 기능">
    <div class="hub-tabs" role="tablist" aria-label="기능 묶음">
      <button type="button" role="tab" class="hub-tab" data-tab="write" aria-controls="pane-write" aria-selected="true">🔥 자주 쓰는 작성기</button>
      <button type="button" role="tab" class="hub-tab" data-tab="calc" aria-controls="pane-calc" aria-selected="false">🧮 진단·계산기</button>
      <button type="button" role="tab" class="hub-tab" data-tab="forms" aria-controls="pane-forms" aria-selected="false">📄 업무별 서류·서식</button>
      <button type="button" role="tab" class="hub-tab" data-tab="news" aria-controls="pane-news" aria-selected="false">📰 브리핑·법령 동향</button>
    </div>
    <div class="hub-pane" role="tabpanel" id="pane-write" data-pane="write">
      <div class="hc-grid">{tab1}</div>
      <p class="hub-more"><a href="tools/forms/">교육일지·점검표·작업계획서 등 작성기 전체 {WRITER_N}종 →</a></p>
    </div>
    <div class="hub-pane" role="tabpanel" id="pane-calc" data-pane="calc" hidden>
      <div class="hc-grid">{tab2}</div>
      <p class="hub-links"><span>조회·일정</span>{look}</p>
    </div>
    <div class="hub-pane" role="tabpanel" id="pane-forms" data-pane="forms" hidden>
      <p class="hint" style="margin:0 0 12px">사업장이 갖춰야 할 안전보건 서류를 업무 12가지로 묶었습니다. 서류 이름을 누르면 바로 작성하거나 원본 서식을 찾을 수 있습니다. 보유 여부를 체크하려면 <a href="tools/docmap/">서류 자가점검</a>을 쓰세요.</p>
      <div class="dmx-grid">{dm_html}</div>
      <h3 class="h-sm" style="margin:22px 0 10px">서식 이름으로 찾기</h3>
      <div class="search-inline fl-q"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input type="search" id="fq" placeholder="서식 이름으로 찾기 (예: 교육, 점검, 작업계획서, 선임)" aria-label="서식 찾기"></div>
      <ul class="fl" id="fList">{form_rows}</ul>
      <p class="hint" id="fNone" hidden>맞는 서식이 없습니다. <a href="resources/">서식·자료 {len(resources)}건 전체에서 찾기 →</a></p>
      <p class="hub-more"><a href="resources/">법령 별지 서식·별표·고시 등 자료 {len(resources)}건 전체 보기 →</a></p>
    </div>
    <div class="hub-pane" role="tabpanel" id="pane-news" data-pane="news" hidden>
      <div class="news2">
        <section><div class="bd-h"><h2>브리핑·소식</h2><a class="more" href="brief/">전체 {len(BOARD)}건 →</a></div><ul class="bd-list">{brief_rows}</ul></section>
        <section><div class="bd-h"><h2>법령 동향</h2><a class="more" href="laws/">더보기 →</a></div><ul class="bd-list">{law_rows}</ul></section>
      </div>
      <p class="hub-links"><span>더 보기</span><a href="board/?b=free">커뮤니티</a><a href="board/?b=qna">Q&amp;A</a><a href="jobs/">채용정보</a><a href="board/?b=job">회원 채용공고</a><a href="laws/act/">산업안전보건법</a><a href="laws/sapa/">중대재해처벌법</a></p>
    </div>
  </section>
  <aside class="home2-side">
    {month_box}
    {chat_banner("cm-chat-side")}
    {blog_banner("cm-chat-side")}
    {yt_banner("cm-chat-side")}
    {(f'<section class="side-box vside"><div class="bd-h"><h2 class="h-sm">안전보건 영상</h2><a class="more" href="videos/">전체 {len(VIDEOS)}편 →</a></div>' + video_card(VIDEOS[0], "") + '</section>' + VIDEO_JS) if VIDEOS else ""}
    <section class="side-box go-box"><h2 class="h-sm go-h"><img src="assets/img/ico/write.webp" width="40" height="40" alt="" loading="lazy">바로 신청·신고</h2><ul class="go-list">{civil}</ul><p class="go-orgs">{orgs}</p></section>
  </aside>
</div>
{home_js}"""
    write("index.html", page(site, "./", "", site["name"], home))

    # ---- 브리핑·소식 게시판
    def board_row(x):
        chk = f' {chk_icon("확인 필요 · " + x["verify"])}' if x.get("verify") else ""
        per = f'<p><b>기간</b> {e(x["period"])}</p>' if x.get("period") else ""
        ot = f'<p class="muted">공식 제목: {e(x["official_title"])}</p>' if x.get("official_title") else ""
        vf = f'<p class="lst-note">{CHK_SVG} <b>확인 필요</b> {e(x["verify"])}</p>' if x.get("verify") else ""
        more = f' · <a href="{e(x["href"])}">{e(x.get("href_label") or "브리핑 전문")}</a>' if x.get("href") else ""
        more += f' · <a href="n/{x["id"]}/">자세히 보기</a>'
        q = " ".join([x["title"], x.get("official_title", ""), x.get("summary", ""), x.get("agency", ""), x["cat"]])
        return (f'<details class="nb-row" id="b-{x["id"]}" data-cat="{e(x["cat"])}" data-q="{e(q.lower())}"><summary><time datetime="{e(x["date"][:7] if x.get("date_prec") == "month" else x["date"])}">{e(bdate(x))}</time><span class="nb-cat nb-{e(x["cat"])}">{e(x["cat"])}</span>'
                f'<span class="nb-t">{e(x["title"])}{chk}</span><span class="nb-a">{e(x.get("agency", ""))}</span></summary>'
                f'<div class="nb-body">{ot}<p>{e(x["summary"])}</p>{per}<p><b>실무 포인트</b> {e(x.get("point", ""))}</p>{vf}'
                f'<p><a class="link-ext" href="{e(x["url"])}" target="_blank" rel="noopener">{e(x.get("src_label") or "공식 출처")} ↗</a>{more}</p></div></details>')
    def board_detail(x, i, side):
        same = [y for y in BOARD if y is not x and y["cat"] == x["cat"]][:5]
        newer, older = (BOARD[i - 1] if i > 0 else None), (BOARD[i + 1] if i + 1 < len(BOARD) else None)
        rel = "".join(f'<li><a href="../{y["id"]}/"><time>{e(bdate(y))}</time><span>{e(y["title"])}</span></a></li>' for y in same)
        nav = "".join(f'<a class="bdn-{k}" href="../{y["id"]}/"><span>{lab}</span>{e(y["title"])}</a>' for k, lab, y in (("prev", "← 이전 소식", newer), ("next", "다음 소식 →", older)) if y)
        rows = [("요약", f'<p>{e(x["summary"])}</p>')]
        if x.get("period"):
            rows.append(("기간", f'<p>{e(x["period"])}</p>'))
        if x.get("point"):
            rows.append(("실무 포인트", f'<p>{e(x["point"])}</p>'))
        tbl = "".join(f'<tr><th scope="row">{k}</th><td>{v}</td></tr>' for k, v in rows)
        vf = f'<p class="lst-note">{CHK_SVG} <b>확인 필요</b> {e(x["verify"])}</p>' if x.get("verify") else ""
        full = f'<a class="btn btn-ghost" href="../../{e(x["href"])}">{e(x.get("href_label") or "브리핑 전문")}</a>' if x.get("href") else ""
        return f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">안전 브리핑</a><span>/</span><a href="../../?c={quote(x["cat"])}">{e(x["cat"])}</a></p>
  <p class="bdm"><span class="nb-cat nb-{e(x["cat"])}">{e(x["cat"])}</span><time datetime="{e(x["date"][:7] if x.get("date_prec") == "month" else x["date"])}">{e(bdate(x, True))}</time>{f'<span>{e(x.get("agency"))}</span>' if x.get("agency") else ''}</p>
  <h1>{e(x["title"])}</h1>
  {f'<p class="bd-ot">공식 제목 · {e(x["official_title"])}</p>' if x.get("official_title") else ''}
</div></section>
<div class="wrap layout-detail"><section class="col-main"><article class="bdv">
  <table class="bdv-t"><tbody>{tbl}</tbody></table>
  {vf}
  <p class="btns bdv-btns"><a class="btn" href="{e(x["url"])}" target="_blank" rel="noopener">{e(x.get("src_label") or "공식 출처 원문")} ↗</a>{full}<a class="btn btn-ghost" href="../../#b-{x["id"]}">목록으로</a></p>
  <p class="src-note">{"언론 보도를 SafePlum이 자체 문장으로 요약한 참고 콘텐츠입니다. 기사 저작권은 해당 언론사에 있으며, 자세한 내용과 사실관계는 기사 원문과 공식 발표를 확인하세요." if x.get("press") else "공식 발표를 SafePlum이 요약한 참고 콘텐츠입니다. 숫자·기간·대상은 공식 출처 원문이 우선합니다."}</p>
  {f'<nav class="bdn" aria-label="이전·다음 소식">{nav}</nav>' if nav else ''}
  {f'<section class="bdr"><h2 class="h-sm">같은 분류 소식 · {e(x["cat"])}</h2><ul>{rel}</ul></section>' if rel else ''}
</article></section>{side}</div>"""

    cats = ["입법예고", "점검", "감독", "지원사업", "공모전·대회", "법령", "정책", "통계", "사고", "자료", "언론보도"]
    cat_btns = '<button type="button" data-c="" aria-pressed="true">전체</button>' + "".join(f'<button type="button" data-c="{c}" aria-pressed="false">{c} {sum(1 for x in BOARD if x["cat"] == c)}</button>' for c in cats if any(x["cat"] == c for x in BOARD))
    board_html = f"""<div class="nb"><div class="nb-tools"><div class="search-inline"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="search" id="nbQ" placeholder="예: 위험성평가, 지게차, 보조금" aria-label="브리핑·소식 검색"></div><p class="nb-count" aria-live="polite"><strong id="nbN">{len(BOARD)}</strong>건</p></div>
<div class="seg nb-filter" id="nbF" role="group" aria-label="분류">{cat_btns}</div>
<div class="nb-list" id="nbL">{"".join(board_row(x) for x in BOARD)}</div>
<p class="empty" id="nbE" hidden>조건에 맞는 소식이 없습니다.</p>
<p class="src-note">고용노동부·정책브리핑·국가법령정보센터 등 공식 발표를 SafePlum이 요약한 참고 콘텐츠입니다. '언론보도'는 기사 문장·사진을 옮기지 않고 SafePlum이 직접 쓴 요약과 원문 링크만 싣습니다. 자동으로 작성·게시되는 글이 있어 사실 확인이 끝나지 않은 내용이 있을 수 있습니다. 숫자·기간·대상은 공식 출처 원문이 우선합니다. 확인 {e(BOARD_CHECKED)}</p></div>
<script>(function(){{var f=document.getElementById("nbF"),l=document.getElementById("nbL"),q=document.getElementById("nbQ"),n=document.getElementById("nbN"),em=document.getElementById("nbE"),c="";
function run(){{var t=(q.value||"").toLowerCase().split(/\\s+/).filter(Boolean),k=0;[].forEach.call(l.children,function(r){{var ok=(!c||r.dataset.cat===c)&&t.every(function(w){{return r.dataset.q.indexOf(w)>=0;}});r.hidden=!ok;if(ok)k++;}});n.textContent=k;em.hidden=k>0;l.hidden=k===0;}}
f.addEventListener("click",function(ev){{var b=ev.target.closest("button");if(!b)return;c=b.dataset.c;[].forEach.call(f.children,function(x){{x.setAttribute("aria-pressed",String(x===b));}});run();}});q.addEventListener("input",run);
try{{var p=new URLSearchParams(location.search);if(p.get("q")){{q.value=p.get("q");}}var pc=p.get("c");if(pc){{var bb=[].filter.call(f.children,function(x){{return x.dataset.c===pc;}})[0];if(bb){{bb.click();}}}}run();}}catch(e){{}}
var h=location.hash.slice(1),r=h&&document.getElementById(h);if(r&&r.tagName==="DETAILS"){{r.open=true;}}}})();</script>"""
    if briefs:
        b0 = briefs[0]
        arch = "".join(f'<li><a href="{e(b["date"])}/"><time datetime="{e(b["date"])}">{fmt_date(b["date"])}</time><span>{e(b["title"])}</span></a></li>' for b in briefs)
        brief_main = board_html
    else:
        arch, brief_main = "", board_html
    brief_side = f"""<aside class="col-side stack">
    {acc_trend_html(auto_acc, today)}
    {blog_banner("cm-chat-side")}
    {yt_banner("cm-chat-side")}
    <div class="side-box"><h2 class="h-sm">지난 브리핑</h2><ul class="br-arch">{arch or '<li>없음</li>'}</ul></div>
    <div class="side-box"><h2 class="h-sm">브리핑은 이렇게 만듭니다</h2><ul class="bul hint">
      <li>국가법령정보센터, 고용노동부, 안전보건공단, 정부 부처·국회·공공기관의 공식 발표만 근거로 씁니다.</li>
      <li>언론 기사는 근거로 쓰지 않습니다. 싣더라도 '참고 보도'로 따로 표시합니다.</li>
      <li>원문은 싣지 않고 요약한 뒤 공식 출처로 연결합니다. 숫자·조문·시행일은 원문과 대조한 것만 적습니다.</li>
      <li>법안·국회 통과·공포·시행 예정·시행 중을 구분해 표시합니다.</li>
    </ul></div>
    <div class="side-box"><h2 class="h-sm">원문 보러 가기</h2><ul class="bul">
      <li><a href="https://www.moel.go.kr/news/enews/report/enewsList.do" target="_blank" rel="noopener">고용노동부 보도자료 ↗</a></li>
      <li><a href="https://www.moel.go.kr/info/lawinfo/instruction/list.do" target="_blank" rel="noopener">고용노동부 훈령·예규·고시 ↗</a></li>
      <li><a href="../laws/#updates">SafePlum 법령 개정 소식</a></li>
    </ul></div></aside>"""
    brief_head = """
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="{up}">홈</a><span>/</span>{crumb}</p>
  <h1>안전 브리핑·소식</h1>
  <p>고용노동부·안전보건공단의 점검·감독 예정, 지원사업, 공모전·대회, 법령·정책, 통계 발표를 한 게시판에 모았습니다. 제목을 누르면 요약과 실무 포인트, 공식 출처가 열립니다.</p>
</div></section>"""
    if VIDEOS:
        vbody = ('<section class="phead"><div class="wrap"><p class="crumbs"><a href="../">홈</a><span>/</span>안전보건 영상</p><h1>안전보건 영상</h1>'
                 '<p>1분 안팎의 짧은 영상으로 현장 안전보건 수칙과 법령을 정리합니다. 영상마다 근거 조문을 적었습니다. 재생 버튼을 누르면 이 화면에서 바로 재생됩니다.</p>'
                 + ('<p class="vch">' + "".join(f'<a class="btn btn-sm btn-ghost" href="{e(u)}" target="_blank" rel="noopener">{n} 채널 ↗</a>' for k, n in (("youtube", "유튜브"), ("tiktok", "틱톡")) for u in [VIDEO_CHANNELS.get(k)] if u) + "</p>" if VIDEO_CHANNELS else "") + '</div></section>'
                 + video_filter(VIDEOS) +
                 f'<div class="wrap vgrid">{"".join(video_card(v, "../", True, lead=(i == 0)) for i, v in enumerate(VIDEOS))}</div>'
                 '<aside class="wrap"><p class="hint vnote">영상은 유튜브·틱톡에 올린 것을 각 서비스가 제공하는 플레이어로 보여 줍니다. 재생 버튼을 누르기 전에는 유튜브·틱톡에 접속하지 않으며, 재생하면 해당 서비스의 개인정보 처리방침이 적용됩니다.</p></aside>' + VIDEO_JS)
        write("videos/index.html", page(site, "../", "videos/", "안전보건 영상", vbody, desc="밀폐공간·끼임 등 현장 안전보건 수칙을 1분 영상으로 정리하고 근거 조문을 함께 적었습니다.", active="videos/"))
    write("brief/index.html", page(site, "../", "brief/", "안전 브리핑",
          brief_head.format(up="../", crumb="안전 브리핑") + f'<div class="wrap layout-detail"><section class="col-main">{brief_main}</section>{brief_side}</div>',
          desc="산업안전 법령·정책·감독·사고 소식을 매일 요약하고 실무 포인트를 정리한 SafePlum 브리핑.", active="brief/"))
    side2 = brief_side.replace('href="../laws/', 'href="../../../laws/').replace('href="../accidents/', 'href="../../../accidents/').replace('<a href="20', '<a href="../../20')
    for i, x in enumerate(BOARD):
        write(f"brief/n/{x['id']}/index.html", page(site, "../../../", f"brief/n/{x['id']}/", f'{x["title"]} — {x["cat"]}', board_detail(x, i, side2),
              desc=f'{x["cat"]} · {x.get("agency", "")} · {bdate(x, True)} — {x["summary"]}'[:150], active="brief/"))
    for b in briefs:
        body = (brief_head.format(up="../../", crumb='<a href="../">안전 브리핑</a><span>/</span>' + fmt_date(b["date"]))
                + f'<div class="wrap layout-detail"><section class="col-main"><article class="br"><p class="br-date">{fmt_date(b["date"])} 브리핑</p><h2 class="br-title">{e(b["title"])}</h2>{brief_article(b, "../../")}</article></section>'
                + brief_side.replace('href="../laws/', 'href="../../laws/').replace('href="../accidents/', 'href="../../accidents/').replace('<a href="20', '<a href="../20') + "</div>")
        write(f"brief/{b['date']}/index.html", page(site, "../../", f"brief/{b['date']}/", f'{fmt_date(b["date"])} 안전 브리핑 — {b["title"]}', body,
              desc=(b.get("lead") or b["title"])[:150], active="brief/"))

    write_bills(site, write, BILLS)

    # ---- 고용노동부 질의회시(중앙부처 1차 해석) 모음: data/gov_qa.json (scripts/import_gov_qa.py 로 만든다)
    GQ = load("data/gov_qa.json") if (ROOT / "data/gov_qa.json").exists() else None
    if GQ:
        gm, gitems = GQ["meta"], GQ["items"]
        OLD = "2020-01-16"  # 산업안전보건법 전부개정 시행일. 그 전 해석은 조문 번호가 현행과 다를 수 있다

        def gq_paras(t):
            # '□ 질의', '<질의 1>' 처럼 짧은 소제목 줄은 굵게 보여 준다(본문 낱말은 고치지 않는다)
            def one(ln):
                k = "gq-h" if (len(ln) <= 30 and re.match(r"^\s*(?:[□■▶]|<[^>]{1,20}>$|\[[^\]]{1,20}\]$|[가-하]\.\s*\(?질의)", ln)) else ""
                return f'<p class="{k}">{e(ln)}</p>' if k else f"<p>{e(ln)}</p>"
            return "".join(one(ln) for ln in t.split("\n") if ln.strip())

        def gq_badges(x, long=False):
            dd = (fmt_date(x["d"]) if long else x["d"].replace("-", ".")) if x["d"] else "회신일 미상"
            old = '<span class="gq-old">구법 기준</span>' if (x["d"] and x["d"] < OLD) else ""
            return f'<span class="nb-cat gq-cat">{e(x["c"])}</span><time datetime="{e(x["d"])}">{e(dd)}</time>{old}'

        gq_note = ('이 자료는 법제처가 공공데이터로 개방한 「중앙부처 1차 해석」 중 고용노동부의 질의회시입니다(출처: 국가법령정보센터, 공공누리 제1유형). '
                   '부처가 해석 당시의 법령을 기준으로 답한 것이며 법제처의 해석이 아닙니다. 지금은 폐지·변경된 해석도 있고, 2020년 1월 16일 산업안전보건법 전부개정 전 해석은 조문 번호가 현행과 다릅니다. '
                   '실제 적용 여부는 현행 법령과 고용노동부(관할 지방고용노동관서)에서 확인하세요. 주제 분류는 SafePlum이 안건명 낱말로 자동으로 나눈 것입니다.')
        topics = [t for t in gm["topics"] if any(x["c"] == t for x in gitems)]
        tcount = {t: sum(1 for x in gitems if x["c"] == t) for t in topics}
        years = sorted({x["d"][:4] for x in gitems if x["d"]}, reverse=True)

        def gq_side(rel, topics_box=True):
            tl = "".join(f'<li><a href="{rel}laws/qa/?c={quote(t)}">{e(t)} <span class="muted">{tcount[t]}</span></a></li>' for t in topics)
            tbox = f'<div class="side-box"><h2 class="h-sm">주제별 보기</h2><ul class="bul gq-tl">{tl}</ul></div>' if topics_box else ""
            return f"""<aside class="col-side stack">
    {tbox}
    <div class="side-box"><h2 class="h-sm">현행 법령으로 확인하기</h2><ul class="bul">
      <li><a href="{rel}tools/law-ai/">법령 AI 질문 — 현행 조문 근거로 답변</a></li>
      <li><a href="{rel}laws/act/">산업안전보건법 전문</a></li><li><a href="{rel}laws/yeong/">시행령 전문</a></li><li><a href="{rel}laws/rule/">시행규칙 전문</a></li>
      <li><a href="{rel}board/?b=qna">Q&amp;A 게시판에 질문하기</a></li></ul></div>
    <div class="side-box"><h2 class="h-sm">원문 보러 가기</h2><ul class="bul"><li><a href="{e(gm["src_url"])}" target="_blank" rel="noopener">국가법령정보센터 중앙부처 1차 해석 ↗</a></li></ul></div>
    {blog_banner("cm-chat-side")}
    {yt_banner("cm-chat-side")}</aside>"""

        def gq_snip(x):
            # 목록에서 제목 아래 한 줄로 보여 줄 질의 요지. 제목과 같으면 비운다
            q = re.sub(r"^\s*(?:[□■○◦\-]?\s*(?:사건\s*경위|질의\s*요지|질의\s*내용|질의|사실관계)\s*[:：]?\s*)+", "", x["q"].replace("\n", " "))
            q = re.sub(r"\s+", " ", q).strip()
            if not q or re.sub(r"\W", "", q)[:30] == re.sub(r"\W", "", x["t"])[:30]:
                return ""
            return q[:120]

        GQ_FIRST = 30  # 처음 그리는 줄 수. 나머지는 list.json 으로 받는다(목록 페이지가 1MB를 넘지 않게)
        def gq_row(x):
            old = x["d"] and x["d"] < OLD
            sn = gq_snip(x)
            dd = x["d"].replace("-", ".") if x["d"] else "회신일 미상"
            return (f'<li class="gq-row"><a href="{e(x["id"])}/"><strong class="gq-t">{e(x["t"])}</strong>'
                    + (f'<span class="gq-s">{e(sn)}</span>' if sn else "")
                    + f'<span class="gq-m"><span class="gq-cat">{e(x["c"])}</span><time datetime="{e(x["d"])}">{e(dd)}</time>'
                    + ('<span class="gq-old">구법 기준</span>' if old else "") + '</span></a></li>')

        write("laws/qa/list.json", json.dumps([[x["id"], x["t"], x["d"], x["c"], gq_snip(x)] for x in gitems], ensure_ascii=False, separators=(",", ":")))
        seg = '<button type="button" data-c="" aria-pressed="true">전체 <em>' + f"{len(gitems):,}" + '</em></button>' + "".join(f'<button type="button" data-c="{e(t)}" aria-pressed="false">{e(t)} <em>{tcount[t]}</em></button>' for t in topics)
        yopt = '<option value="">전체 연도</option>' + "".join(f'<option value="{y}">{y}년</option>' for y in years)
        n_old = sum(1 for x in gitems if x["d"] and x["d"] < OLD)
        qa_body = f"""
<section class="phead gq-head"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">법령</a><span>/</span>질의회시</p>
  <h1>고용노동부 질의회시 모음</h1>
  <p>산업안전보건법에 대해 현장에서 실제로 물어본 질문과 고용노동부의 회신 <b>{len(gitems):,}건</b>을 주제별로 모았습니다.</p>
  <form class="gq-search" role="search" onsubmit="return false"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input type="search" id="gqQ" placeholder="예: 관리감독자 교육, 안전관리자 겸직" aria-label="질의회시 검색" autocomplete="off" enterkeyhint="search">
    <button type="button" class="gq-x" id="gqX" aria-label="검색어 지우기" hidden>×</button></form>
</div></section>
<div class="wrap layout-detail gq-layout"><section class="col-main">
  <div class="gq-chips" id="gqF" role="group" aria-label="주제">{seg}</div>
  <div class="gq-bar"><p class="gq-n" aria-live="polite">총 <strong id="gqN">{len(gitems):,}</strong>건</p>
    <div class="gq-sel"><select id="gqY" aria-label="회신 연도">{yopt}</select>
    <select id="gqS" aria-label="정렬"><option value="new">최신 회신순</option><option value="old">오래된 회신순</option></select>
    <label class="gq-chk"><input type="checkbox" id="gqC"> 현행법 기준만</label></div></div>
  <ul class="gq-list" id="gqL">{"".join(gq_row(x) for x in gitems[:GQ_FIRST])}</ul>
  <p class="empty" id="gqE" hidden>조건에 맞는 질의회시가 없습니다. 낱말을 줄이거나 <a href="../../tools/law-ai/">법령 AI 질문</a>을 써 보세요.</p>
  <p class="gq-more"><button type="button" class="btn btn-ghost" id="gqM">더 보기 <span id="gqMn"></span></button></p>
  <details class="gq-note"><summary>{CHK_SVG} 이 자료를 볼 때 꼭 알아 둘 점 <span class="muted">— 부처 해석이며, {n_old:,}건은 2020년 전부개정 전 법령 기준</span></summary><p>{e(gq_note)}</p>
  <p class="src-note">출처: 법제처 국가법령정보센터 「중앙부처 1차 해석」(고용노동부) · 공공누리 제1유형 · 수집 {e(gm.get("collected", ""))} · 질의·회답 본문은 원문 그대로 옮기고 줄바꿈만 넣었습니다.</p></details>
</section>{gq_side("../../", False)}</div>
<script>(function(){{var L=document.getElementById("gqL"),q=document.getElementById("gqQ"),x=document.getElementById("gqX"),y=document.getElementById("gqY"),so=document.getElementById("gqS"),cb=document.getElementById("gqC"),f=document.getElementById("gqF"),n=document.getElementById("gqN"),em=document.getElementById("gqE"),mb=document.getElementById("gqM"),mn=document.getElementById("gqMn"),c="",lim=30,D=null,OLD="{OLD}";
function h(s){{return String(s).replace(/[&<>"]/g,function(m){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[m];}});}}
function mark(s,t){{s=h(s);if(!t.length)return s;var re=new RegExp("("+t.map(function(w){{return h(w).replace(/[.*+?^${{}}()|[\\]\\\\]/g,"\\\\$&");}}).join("|")+")","gi");return s.replace(re,"<mark>$1</mark>");}}
function row(r,t){{var old=r[2]&&r[2]<OLD;return '<li class="gq-row"><a href="'+r[0]+'/"><strong class="gq-t">'+mark(r[1],t)+'</strong>'+(r[4]?'<span class="gq-s">'+mark(r[4],t)+'</span>':'')+'<span class="gq-m"><span class="gq-cat">'+h(r[3])+'</span><time datetime="'+r[2]+'">'+(r[2]?r[2].replace(/-/g,"."):"회신일 미상")+'</time>'+(old?'<span class="gq-old">구법 기준</span>':'')+'</span></a></li>';}}
function sync(){{try{{var p=new URLSearchParams();if(q.value.trim())p.set("q",q.value.trim());if(c)p.set("c",c);if(y.value)p.set("y",y.value);if(so.value==="old")p.set("s","old");if(cb.checked)p.set("cur","1");var s=p.toString();history.replaceState(null,"",s?"?"+s:location.pathname);}}catch(e){{}}}}
function run(){{x.hidden=!q.value;if(!D)return;var t=(q.value||"").toLowerCase().split(/\\s+/).filter(Boolean),yy=y.value,out=[];
for(var i=0;i<D.length;i++){{var r=D[i];if(c&&r[3]!==c)continue;if(yy&&r[2].slice(0,4)!==yy)continue;if(cb.checked&&(!r[2]||r[2]<OLD))continue;var hay=(r[1]+" "+r[4]+" "+r[3]).toLowerCase();if(!t.every(function(w){{return hay.indexOf(w)>=0;}}))continue;out.push(r);}}
if(so.value==="old")out.reverse();n.textContent=out.length.toLocaleString();em.hidden=out.length>0;L.innerHTML=out.slice(0,lim).map(function(r){{return row(r,t);}}).join("");
mb.hidden=out.length<=lim;mn.textContent="("+Math.min(lim,out.length).toLocaleString()+" / "+out.length.toLocaleString()+")";sync();}}
function reset(){{lim=30;run();}}
function setC(v){{c=v;[].forEach.call(f.children,function(b){{b.setAttribute("aria-pressed",String(b.dataset.c===v));}});}}
f.addEventListener("click",function(ev){{var b=ev.target.closest("button");if(!b)return;setC(b.dataset.c);b.scrollIntoView({{block:"nearest",inline:"center"}});reset();}});
var tm;q.addEventListener("input",function(){{clearTimeout(tm);tm=setTimeout(reset,120);}});x.addEventListener("click",function(){{q.value="";q.focus();reset();}});
y.addEventListener("change",reset);so.addEventListener("change",reset);cb.addEventListener("change",reset);mb.addEventListener("click",function(){{lim+=50;run();}});
try{{var p=new URLSearchParams(location.search);if(p.get("q"))q.value=p.get("q");if(p.get("y"))y.value=p.get("y");if(p.get("s")==="old")so.value="old";if(p.get("cur"))cb.checked=true;if(p.get("c"))setC(p.get("c"));}}catch(e){{}}
mn.textContent="({GQ_FIRST} / {len(gitems):,})";
fetch("list.json").then(function(r){{return r.json();}}).then(function(d){{D=d;run();}}).catch(function(){{mb.hidden=true;}});}})();</script>"""
        write("laws/qa/index.html", page(site, "../../", "laws/qa/", "고용노동부 질의회시 모음 — 산업안전보건법", qa_body,
              desc=f"산업안전보건법 관련 고용노동부 질의회시(행정해석) {len(gitems):,}건을 주제별로 정리. 선임·교육·도급·건설·위험성평가 등 질의요지와 회답 전문.", active="laws/"))
        side3 = gq_side("../../../")
        for i, x in enumerate(gitems):
            same = [y for y in gitems if y is not x and y["c"] == x["c"]][:6]
            rl = "".join(f'<li><a href="../{y["id"]}/"><time>{e(y["d"][:7].replace("-", ".") or "-")}</time><span>{e(y["t"])}</span></a></li>' for y in same)
            newer, older = (gitems[i - 1] if i > 0 else None), (gitems[i + 1] if i + 1 < len(gitems) else None)
            nav = "".join(f'<a class="bdn-{k}" href="../{y["id"]}/"><span>{lab}</span>{e(y["t"])}</a>' for k, lab, y in (("prev", "← 최근 회신", newer), ("next", "이전 회신 →", older)) if y)
            tools = "".join(f'<a class="btn btn-sm btn-ghost" href="../../../{h}">{e(nm)}</a>' for h, nm in gm["tools"].get(x["c"], gm["tools"]["기타"]))
            law = f'<div class="gq-law"><b>관련 법령</b> {e(x["l"])}</div>' if x.get("l") else ""
            old = (f'<div class="gq-alert" role="note"><b>구법 기준 해석</b><p>{fmt_date(x["d"])} 회신으로, 2020년 1월 16일 산업안전보건법 전부개정 <u>전</u> 법령을 기준으로 답했습니다. 조문 번호와 내용이 현행과 다를 수 있으니 현행 법령으로 다시 확인하세요.</p></div>'
                   if x["d"] and x["d"] < OLD else "")
            dd = fmt_date(x["d"]) if x["d"] else "회신일 미상"
            body = f"""
<section class="phead gq-vhead"><div class="wrap">
  <p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">법령</a><span>/</span><a href="../">질의회시</a><span>/</span><a href="../?c={quote(x["c"])}">{e(x["c"])}</a></p>
  <p class="gq-vcat"><a href="../?c={quote(x["c"])}">{e(x["c"])}</a></p>
  <h1>{e(x["t"])}</h1>
  <p class="gq-vm"><span>고용노동부 회신</span><time datetime="{e(x["d"])}">{e(dd)}</time>{'<span class="gq-old">구법 기준</span>' if old else ''}<button type="button" class="gq-copy" data-copy>링크 복사</button></p>
</div></section>
<div class="wrap layout-detail gq-layout"><section class="col-main"><article class="gq-v">
  {old}
  <section class="gq-blk gq-q" aria-labelledby="gqQh"><h2 id="gqQh"><span class="gq-qa">Q</span>질의 요지</h2><div class="gq-tx">{gq_paras(x["q"])}</div></section>
  <section class="gq-blk gq-a" aria-labelledby="gqAh"><h2 id="gqAh"><span class="gq-qa">A</span>고용노동부 회답</h2><div class="gq-tx">{gq_paras(x["a"])}</div>{law}</section>
  <section class="gq-ai" id="gqAI"><div class="gq-ai-h"><b>✦ AI로 쉽게 풀이 · 현행 법령과 대조</b><button type="button" class="btn btn-sm gq-ai-go" id="gqAIGo">풀이 보기</button></div>
    <p class="gq-ai-st" id="gqAISt">회답을 쉬운 말로 요약하고, 지금 시행 중인 조문과 비교해 달라진 점이 있는지 알려 줍니다(내 Gemini 키 · 참고용).</p><div id="gqAIOut"></div></section>
  <p class="btns gq-btns"><a class="btn" href="{e(gm["item_url"].format(id=x["id"]))}" target="_blank" rel="noopener">국가법령정보센터 원문 ↗</a><a class="btn btn-ghost" href="../../../tools/law-ai/">현행 법령으로 물어보기</a><a class="btn btn-ghost" href="../?c={quote(x["c"])}">같은 주제 목록</a></p>
  <details class="gq-note"><summary>{CHK_SVG} 이 해석을 볼 때 꼭 알아 둘 점</summary><p>{e(gq_note)}</p></details>
  <section class="gq-tools"><h2 class="h-sm">이 주제에 쓰는 무료 도구</h2><p class="btns">{tools}</p></section>
  {f'<nav class="bdn" aria-label="이전·다음 질의회시">{nav}</nav>' if nav else ''}
  {f'<section class="bdr"><h2 class="h-sm">같은 주제 질의회시 · {e(x["c"])}</h2><ul>{rl}</ul></section>' if rl else ''}
</article></section>{side3}</div>
<script src="../../../assets/ai.js"></script>
<script>(function(){{var go=document.getElementById("gqAIGo"),st=document.getElementById("gqAISt"),out=document.getElementById("gqAIOut"),busy=false;if(!go)return;
function E(t){{return window.SPAI?SPAI.esc(t):String(t);}}
function tx(sel){{var el=document.querySelector(sel);return el?[].map.call(el.querySelectorAll("p"),function(p){{return p.textContent.trim();}}).join("\\n"):"";}}
go.addEventListener("click",function(){{if(busy)return;if(!window.SPAI){{st.textContent="AI 모듈을 불러오지 못했습니다. 새로고침해 주세요.";return;}}SPAI.css();
if(!SPAI.hasKey()){{SPAI.ensureKey().then(function(ok){{if(ok)go.click();}});return;}}
busy=true;go.disabled=true;st.innerHTML='<span class="spai-busy">관련 현행 조문을 찾고 풀이하는 중…</span>';
var title=document.querySelector(".gq-vhead h1").textContent.trim(),date=(document.querySelector(".gq-vm time")||{{}}).textContent||"",old=!!document.querySelector(".gq-alert"),q=tx(".gq-q .gq-tx"),a=tx(".gq-a .gq-tx"),law=[];
SPAI.law.search(title+" "+q.slice(0,400),{{k:6}}).then(function(L){{law=L;
return SPAI.json({{system:"너는 고용노동부 행정해석(질의회시)을 현장 실무자에게 설명하는 한국 산업안전보건 전문가다. 회답 내용을 왜곡하지 말고 쉬운 말로 요약한다. 현행 조문은 아래 [번호] 조문만 근거로 비교하며, 제공된 조문만으로 판단할 수 없으면 그렇다고 쓴다. 질의회시는 법적 구속력이 없는 부처 해석임을 전제로 한다.",
prompt:"질의회시: 「"+title+"」 회신일 "+date+(old?" (2020.1.16 산업안전보건법 전부개정 전 법령 기준)":"")+"\\n\\n질의요지:\\n"+q.slice(0,2500)+"\\n\\n회답:\\n"+a.slice(0,3500)+"\\n\\n현행 조문:\\n"+SPAI.law.ctx(law,1000)+"\\n\\nsummary: 회답 결론을 쉬운 말 2~3문장. points: 실무 포인트 2~4개. now: 지금 시행 중인 조문과 비교한 내용 2~4문장(조문 번호가 바뀌었거나 내용이 달라졌으면 구체적으로, 근거 문장 끝에 [번호]). cites: now에 쓴 조문 번호.",
schema:{{type:"OBJECT",properties:{{summary:{{type:"STRING"}},points:{{type:"ARRAY",items:{{type:"STRING"}}}},now:{{type:"STRING"}},cites:{{type:"ARRAY",items:{{type:"INTEGER"}}}}}},required:["summary","now"]}},temperature:0.2,maxTokens:4000,timeout:90000,label:"AI가 회시를 쉬운 말로 풀이하는 중"}});
}}).then(function(r){{var used={{}};(r.cites||[]).forEach(function(n){{if(n>=1&&n<=law.length)used[n]=law[n-1];}});
var now=E(r.now||"").replace(/\\[(\\d{{1,2}})\\]/g,function(m,n){{var c=law[n-1];if(!c)return"";used[n]=c;return'<sup><a href="'+E(c.url)+'" target="_blank" rel="noopener">['+n+']</a></sup>';}});
out.innerHTML='<div class="gq-ai-box"><p><b>한눈에</b> '+E(r.summary||"")+'</p>'+((r.points||[]).length?'<ul>'+r.points.map(function(x){{return"<li>"+E(x)+"</li>";}}).join("")+"</ul>":"")+'<p><b>현행 법령과 비교</b> '+now+'</p><p class="gq-ai-src">'+Object.keys(used).map(function(n){{var c=used[n];return'<a href="'+E(c.url)+'" target="_blank" rel="noopener">['+n+'] '+E(c.label)+"</a>";}}).join(" ")+'</p><p class="gq-ai-src">'+E(SPAI.NOTICE)+" 원문과 현행 조문을 꼭 확인하세요.</p></div>";
st.textContent="풀이를 만들었습니다.";}}).catch(function(e){{st.textContent=(e&&e.message)||"AI 요청이 실패했습니다.";}}).then(function(){{busy=false;go.disabled=false;}});}});}})();</script>
<script>(function(){{var b=document.querySelector("[data-copy]");if(!b)return;b.addEventListener("click",function(){{var u=location.href.split("#")[0];(navigator.clipboard?navigator.clipboard.writeText(u):Promise.reject()).then(function(){{b.textContent="복사했습니다";setTimeout(function(){{b.textContent="링크 복사";}},1600);}},function(){{prompt("아래 주소를 복사하세요",u);}});}});}})();</script>"""
            write(f"laws/qa/{x['id']}/index.html", page(site, "../../../", f"laws/qa/{x['id']}/", f'{x["t"]} — 고용노동부 질의회시', body,
                  desc=(f'[{x["c"]}] ' + re.sub(r"\s+", " ", x["q"]))[:150], active="laws/"))
    else:
        warn("data/gov_qa.json 이 없음 → 질의회시 모음(laws/qa/)을 만들지 않음")

    # ---- 게시판(커뮤니티 · Q&A): 글·회원은 Supabase 에 있고, 여기서는 빈 화면 틀만 만든다(assets/community.js 가 채운다)
    cmc = site.get("community") or {}
    cm_url, cm_key = safe_url(cmc.get("supabase_url")), str(cmc.get("supabase_anon_key") or "").strip()
    cm_on = bool(cm_url and cm_key)
    if not cm_on:
        warn("community.supabase_url / supabase_anon_key 가 비어 있음 → 게시판은 '준비 중'으로 표시(README '게시판 열기' 참고)")
    elif not ((site.get("operator") or {}).get("contact_url")):
        warn("게시판이 켜졌는데 operator.contact_url 이 비어 있음 → 개인정보 처리방침·삭제 요청 창구가 '준비 중'으로 나감. 회원을 받기 전에 반드시 입력")
    if "service_role" in cm_key or cm_key.startswith("sb_secret_"):
        sys.exit("config/site.json community.supabase_anon_key 에 비밀 키(service_role/secret)가 들어 있습니다. 브라우저에 공개되는 값이므로 anon(publishable) 키만 넣으세요.")
    cm_cats = cmc.get("categories") or {}

    BP = fetch_board_posts(cm_url, cm_key) if cm_on else None   # 글별 정적 페이지용(아래)

    def cm_page(sub, kind, title, lead, rel, desc, wide=False):
        conf = json.dumps({"url": cm_url if cm_on else "", "key": cm_key if cm_on else "", "root": rel, "cats": cm_cats, "chat": OPENCHAT, "jobPost": JOB_POST, "jobsOpen": JOBS_OPEN, "jobNo": ((site.get("operator") or {}).get("job_info_no") or ""), "jobOrg": ((site.get("operator") or {}).get("job_info_org") or ""), "built": BOARD_BUILT if (BP and BP.get("posts")) else ""}, ensure_ascii=False).replace("</", "<\\/")
        crumb = f'<a href="{rel}board/">게시판</a><span>/</span>{e(title)}' if sub else "게시판"
        side = f"""<aside class="col-side stack">
    <div class="side-box"><h2 class="h-sm">게시판 안내</h2><ul class="bul hint">
      <li><b>커뮤니티</b> — 현장 이야기, 정보 공유, 자료 요청.</li>
      <li><b>Q&amp;A</b> — 실무·법령 질문과 답변. 질문자가 답변을 채택할 수 있습니다.</li>
      <li><b>채용공고</b> — {"회원이 직접 올리는 안전·보건 직무 공고. 하루 5건까지." if JOB_POST else "안전·보건 직무 공고. 공고 등록은 현재 준비 중입니다."}</li>
      <li>읽기는 누구나, 쓰기는 이메일 인증을 마친 회원만 할 수 있습니다. 이름·전화번호는 받지 않습니다.</li>
      <li>개인·사업장을 알아볼 수 있는 정보는 적지 마세요.</li>
    </ul><p class="btns" style="margin-top:12px"><a class="btn btn-sm btn-ghost" href="{rel}board/rules/">이용수칙</a></p></div>
    <div class="side-box"><h2 class="h-sm">답변을 볼 때</h2><p>게시판의 답변은 회원 개인의 의견입니다. 법 적용 여부는 <a href="{rel}laws/">법령 원문</a>과 소관 기관에서 확인하세요.</p></div></aside>"""
        body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="{rel}">홈</a><span>/</span>{crumb}</p>
  <h1>{e(title)}</h1>
  <p>{e(lead)}</p>
</div></section>
<div class="wrap {'cm-narrow' if wide else 'layout-detail cm-layout'}"><section class="col-main"><div id="cm" class="cm" data-page="{kind}"><noscript><p class="cm-note">게시판을 보려면 자바스크립트를 켜야 합니다.</p></noscript></div></section>{'' if wide else side}</div>
<script>window.ST_CM={conf};</script>
{f'<script src="{rel}assets/vendor/supabase.js?v={ASSET_VER}"></script>' if cm_on else ''}
<script src="{rel}assets/community.js?v={ASSET_VER}"></script>"""
        write(f"board/{sub}index.html", page(site, rel, f"board/{sub}", title, body, desc=desc, active="board/"))

    cm_page("", "list", "게시판", "안전·보건 일을 하는 사람들이 묻고 답하고 나누는 곳입니다. 커뮤니티와 Q&A 두 게시판이 있습니다.", "../",
            "안전관리자·보건관리자가 현장 이야기와 실무 질문을 나누는 SafePlum 커뮤니티·Q&A 게시판.")
    cm_page("view/", "view", "글 보기", "게시판의 글과 답변은 회원 개인의 의견입니다.", "../../", "SafePlum 게시판 글 보기.")
    cm_page("write/", "write", "글쓰기", "제목과 내용을 적어 등록합니다. 개인·사업장을 알아볼 수 있는 정보는 적지 마세요.", "../../", "SafePlum 게시판 글쓰기.", wide=True)
    cm_page("admin/", "admin", "운영 관리", "신고 처리, 회원 글쓰기 정지, 삭제한 글 복구, 처리 기록. 운영자 계정으로 로그인해야 보입니다.", "../../", "SafePlum 게시판 운영 관리(운영자 전용).", wide=True)
    cm_page("account/", "account", "로그인 · 마이페이지", "누구나 무료로 가입합니다. 이메일 인증만 하면 되고 이름·전화번호는 받지 않습니다.", "../../", "SafePlum 로그인·회원가입·마이페이지.", wide=True)

    # ---- 게시판 글별 정적 페이지(board/post/{id}/): 검색엔진·자바스크립트를 끈 사용자도 실제 글 내용을 읽을 수 있게.
    #      화면의 게시판(board/view/?id=)과 같은 공개 글만 담고, 댓글 쓰기·추천 같은 기능은 게시판 화면으로 연결한다.
    BOARD_NAMES = {"free": "커뮤니티", "qna": "Q&A"}
    POST_LM = {}
    if BP and BP.get("posts"):
        cm_by = {}
        for c in BP.get("comments") or []:
            cm_by.setdefault(c["post_id"], []).append(c)
        def bp_nick(r):   # 화면 게시판(community.js nick)과 같은 규칙: 작성자 정보가 없으면 '탈퇴한 회원', 있으면 쓸 당시 닉네임
            if not r.get("author"):
                return "탈퇴한 회원"
            return r.get("author_nick") or r["author"].get("nickname") or "탈퇴한 회원"
        def bp_date(v):
            return str(v or "")[:10]
        def bp_text(t):
            # 글 본문: 그대로 옮기고 주소만 링크(화면 게시판과 같은 rel="nofollow ugc")
            out = []
            for para in re.split(r"\n{2,}", str(t or "").strip()):
                lines = []
                for ln in para.split("\n"):
                    parts, last = [], 0
                    for m in re.finditer(r"https?://[^\s<>\"']+", ln):
                        u = re.sub(r"[.,)\]]+$", "", m.group(0))
                        parts.append(e(ln[last:m.start()])); parts.append(f'<a href="{e(u)}" target="_blank" rel="nofollow ugc noopener">{e(u)}</a>'); last = m.start() + len(u)
                    parts.append(e(ln[last:])); lines.append("".join(parts))
                out.append("<p>" + "<br>".join(lines) + "</p>")
            return "".join(out)
        posts = [p for p in BP["posts"] if p.get("board") in BOARD_NAMES]
        base = (site.get("base_url") or "").rstrip("/")
        for bk in BOARD_NAMES:
            plist = [p for p in posts if p["board"] == bk]
            for i, p in enumerate(plist):
                pid = int(p["id"]); cms = cm_by.get(pid, [])
                word = "답변" if bk == "qna" else "댓글"
                desc_txt = re.sub(r"\s+", " ", str(p.get("body") or "")).strip()[:150]
                newer, older = (plist[i - 1] if i > 0 else None), (plist[i + 1] if i + 1 < len(plist) else None)
                nav = "".join(f'<a class="bdn-{k}" href="../{x["id"]}/"><span>{lab}</span>{e(x["title"])}</a>' for k, lab, x in (("prev", "← 최근 글", newer), ("next", "이전 글 →", older)) if x)
                rel_list = "".join(f'<li><a href="../{x["id"]}/"><time>{e(bp_date(x.get("created_at")))}</time><span>{e(x["title"])}</span></a></li>' for x in [y for y in plist if y is not p][:8])
                cm_html = "".join(f'<li class="bpc{" bpc-acc" if p.get("accepted_comment_id") == c["id"] else ""}"><p class="bpc-m"><b>{e(bp_nick(c))}</b> · <time datetime="{e(str(c.get("created_at") or ""))}">{e(bp_date(c.get("created_at")))}</time>{" · <span class=bpc-badge>채택된 답변</span>" if p.get("accepted_comment_id") == c["id"] else ""}</p><div class="bpc-b">{bp_text(c.get("body"))}</div></li>' for c in cms)
                url_c = f"{base}/board/post/{pid}/" if base else ""
                ld = {"@context": "https://schema.org", "@type": "DiscussionForumPosting", "headline": p["title"], "text": str(p.get("body") or "")[:5000],
                      "datePublished": p.get("created_at"), "author": {"@type": "Person", "name": bp_nick(p)}, "commentCount": len(cms),
                      "comment": [{"@type": "Comment", "text": str(c.get("body") or "")[:2000], "datePublished": c.get("created_at"), "author": {"@type": "Person", "name": bp_nick(c)}} for c in cms[:30]]}
                if p.get("updated_at"): ld["dateModified"] = p["updated_at"]
                if url_c: ld["url"] = url_c; ld["mainEntityOfPage"] = url_c
                ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
                body = f"""
<section class="phead bp-head"><div class="wrap">
  <p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">게시판</a><span>/</span><a href="../../?b={bk}">{e(BOARD_NAMES[bk])}</a></p>
  <p class="bp-cat"><a href="../../?b={bk}">{e(BOARD_NAMES[bk])}</a>{(" · " + e(p.get("category") or "")) if p.get("category") else ""}{" · 공지" if p.get("notice") else ""}</p>
  <h1>{e(p["title"])}</h1>
  <p class="bp-m"><b>{e(bp_nick(p))}</b> · <time datetime="{e(str(p.get("created_at") or ""))}">{e(bp_date(p.get("created_at")))}</time>{" · 수정됨" if p.get("updated_at") else ""} · {word} {len(cms)}</p>
</div></section>
<div class="wrap layout-detail bp-layout"><section class="col-main"><article class="bp">
  <div class="bp-body">{bp_text(p.get("body"))}</div>
  <p class="btns bp-act"><a class="btn" href="../../view/?id={pid}">게시판에서 {word} 쓰기·보기</a><a class="btn btn-ghost" href="../../?b={bk}">{e(BOARD_NAMES[bk])} 목록</a></p>
  <section class="bp-cms"><h2 class="h-sm">{word} {len(cms)}</h2>{f'<ol class="bp-cl">{cm_html}</ol>' if cm_html else f'<p class="hint">아직 {word}이 없습니다. <a href="../../view/?id={pid}">게시판에서 {word}을 남겨 주세요.</a></p>'}</section>
  <p class="hint bp-note">게시판의 글과 {word}은 회원 개인의 의견입니다. 법 적용 여부는 법령 원문과 소관 기관에서 확인하세요. 이 페이지는 하루 한 번 이상 게시판 내용으로 갱신되며, 최신 {word}은 게시판 화면에서 볼 수 있습니다.</p>
  {f'<nav class="bdn" aria-label="이전·다음 글">{nav}</nav>' if nav else ''}
  {f'<section class="bdr"><h2 class="h-sm">{e(BOARD_NAMES[bk])}의 다른 글</h2><ul>{rel_list}</ul></section>' if rel_list else ''}
</article></section><aside class="col-side stack"><div class="side-box"><h2 class="h-sm">게시판 안내</h2><ul class="bul hint"><li>읽기는 누구나, 쓰기는 이메일 인증을 마친 회원만 할 수 있습니다.</li><li>개인·사업장을 알아볼 수 있는 정보는 적지 마세요.</li></ul><p class="btns" style="margin-top:12px"><a class="btn btn-sm btn-ghost" href="../../rules/">이용수칙</a><a class="btn btn-sm btn-ghost" href="../../write/">글쓰기</a></p></div></aside></div>
<script type="application/ld+json">{ld_json}</script>"""
                write(f"board/post/{pid}/index.html", page(site, "../../../", f"board/post/{pid}/", f'{p["title"]} — {BOARD_NAMES[bk]}', body, desc=desc_txt or p["title"], active="board/"))
                POST_LM[f"board/post/{pid}/"] = bp_date(p.get("updated_at") or p.get("created_at"))
        # 게시판 첫 화면(자바스크립트가 목록을 그리기 전·검색엔진용): 최근 글 링크. 화면 목록이 그려지면 이 부분은 대신 바뀐다
        recent = sorted(posts, key=lambda x: str(x.get("created_at") or ""), reverse=True)[:40]
        BOARD_STATIC = '<div class="cm-static"><h2 class="h-sm">최근 글</h2><ul class="bd-list">' + "".join(
            f'<li><a href="post/{p["id"]}/"><span class="nb-cat">{e(BOARD_NAMES[p["board"]])}</span> {e(p["title"])} <time>{e(bp_date(p.get("created_at")))}</time></a></li>' for p in recent) + "</ul></div>"
        b_src = (out / "board/index.html").read_text(encoding="utf-8")
        b_src = b_src.replace('<div id="cm" class="cm" data-page="list"><noscript>', '<div id="cm" class="cm" data-page="list">' + BOARD_STATIC + "<noscript>", 1)
        (out / "board/index.html").write_text(b_src, encoding="utf-8")
        print(f"  게시판 글 정적 페이지 {len(POST_LM)}개")

    op_line = operator_html(site, "../../")
    _po = (site.get("operator") or {}).get("privacy_officer") or {}
    _po_mail = str(_po.get("email") or "").strip()
    if cm_on and not re.match(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[a-z]{2,}$", _po_mail):
        warn("operator.privacy_officer.email 이 비어 있거나 형식이 틀림 → 개인정보 처리방침에 보호책임자 연락처가 빠짐")
        _po_mail = ""
    po_html = (f'<p><b>개인정보 보호책임자</b>: {e(_po.get("title") or "운영자")} · 이메일 <a href="mailto:{e(_po_mail)}">{e(_po_mail)}</a><br>'
               '개인정보 열람·정정·삭제·처리정지 요청과 불만 처리는 위 이메일로 접수합니다.</p>') if _po_mail else ""
    rules_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">게시판</a><span>/</span>이용수칙</p>
  <h1>게시판 이용수칙</h1>
  <p>SafePlum 게시판(커뮤니티 · Q&amp;A · 채용공고)을 쓰는 모든 회원에게 적용됩니다. 글을 등록하면 이 수칙에 동의한 것으로 봅니다.</p>
</div></section>
<div class="wrap legal-doc" style="max-width:860px;padding-bottom:48px">
  <h2>1. 가입과 계정</h2>
  <p>이메일 인증을 마치면 가입됩니다. 이름·전화번호는 받지 않으며, 글에는 닉네임만 공개됩니다. 만 14세 이상만 가입할 수 있습니다. 계정은 본인만 쓰고 다른 사람에게 넘기지 않습니다.</p>
  <h2>2. 올리면 안 되는 글</h2>
  <ul class="bul">
    <li>사람 이름·연락처·주민등록번호·얼굴 사진 등 개인을 알아볼 수 있는 정보(본인 것 포함)</li>
    <li>특정 사업장·회사·개인을 알아볼 수 있게 적은 사고·위반 사례, 근거 없는 비방, 명예를 훼손하는 글</li>
    <li>재해자·환자의 건강정보 등 민감한 정보</li>
    <li>얼굴·명찰·차량번호·사업장 간판 등 개인이나 회사를 알아볼 수 있는 것이 찍힌 사진, 다른 사람이 찍은 사진을 허락 없이 올린 것. 글 하나에 사진은 3장까지 붙일 수 있습니다.</li>
    <li>광고·홍보·도배, 같은 내용의 반복 등록</li>
    <li>다른 사람의 저작물(유료 교재·기사 전문·타 사이트 자료 등)을 허락 없이 옮긴 글. 필요한 만큼만 인용하고 출처를 적어 주세요.</li>
    <li>욕설·혐오·차별 표현, 음란물, 불법 행위를 권하거나 법 위반을 숨기는 방법을 알려 주는 글</li>
  </ul>
  <h2>3. 질문과 답변</h2>
  <p>Q&amp;A의 답변은 회원 개인의 경험과 의견입니다. 법령 해석은 원문과 관할 기관 안내를 기준으로 하세요. 답변할 때는 근거(법 조문·고시·공식 자료)를 함께 적어 주세요. 법 적용 여부와 행정 처분에 관한 판단은 법령 원문과 고용노동부 등 소관 기관에서 확인해야 합니다.</p>
  <h2>4. 채용공고</h2>
  {"" if JOB_POST else "<p><b>채용공고 등록은 현재 준비 중이며, 준비가 끝나면 다시 엽니다.</b> 아래 내용은 등록이 열려 있을 때 적용됩니다.</p>"}<p>채용공고 게시판에는 회원이 자기 회사(또는 채용을 맡은 회사)의 안전·보건 직무 공고를 직접 올립니다. SafePlum은 구인자와 구직자를 소개·알선하지 않으며, 공고 내용의 사실 여부를 보증하지 않습니다.</p>
  <ul class="bul">
    <li>회사명, 지원 방법(채용 페이지 주소 등)을 반드시 적고, 근무 조건은 사실대로 적습니다. 거짓·과장 공고는 삭제합니다.</li>
    <li>성별·나이·출신 지역·신체 조건·혼인 여부 등 직무와 관계없는 조건으로 차별하는 공고는 올릴 수 없습니다.</li>
    <li>구직자에게 돈(교육비·보증금·물품 구입 등)이나 통장·카드·비밀번호를 요구하는 공고, 다단계·대출·명의 대여 모집은 올릴 수 없습니다.</li>
    <li>공고 글에 지원자의 주민등록번호·가족 관계 등 직무와 관계없는 개인정보를 내라고 적지 않습니다.</li>
    <li>회사(구인자)가 누구인지 확인할 수 없는 공고, 최저임금에 못 미치는 조건의 공고, 채용을 가장한 물품 판매·수강생 모집·부업 알선·투자 권유는 올릴 수 없습니다.</li>
    <li>SafePlum은 이력서를 대신 전달하거나 취업을 추천·상담하지 않습니다. 지원은 공고에 적힌 회사의 접수 방법으로 직접 해 주세요.</li>
    <li>같은 공고를 반복해 올리지 않습니다. 한 계정은 하루 5건까지 등록할 수 있습니다. 채용이 끝나면 공고를 고치거나 삭제해 주세요.</li>
  </ul>
  <h2>5. 글의 책임과 권리</h2>
  <p>글의 내용에 대한 책임은 글을 쓴 회원에게 있습니다. 글의 저작권은 쓴 회원에게 있으며, SafePlum은 게시판 운영에 필요한 범위(게시·검색·목록 표시)에서 글을 보여 줍니다.</p>
  <h2>6. 삭제·이용 제한</h2>
  <p>이 수칙에 어긋나거나 신고가 들어온 글은 운영자가 확인한 뒤 알리지 않고 가리거나 삭제할 수 있습니다. 위반이 반복되면 기간을 정해 글쓰기를 정지하거나, 정도가 심하면 강제로 탈퇴시키고 다시 가입하지 못하게 할 수 있습니다. 정지된 회원은 마이페이지에서 기간과 사유를 확인할 수 있고, 이의가 있으면 문의 창구로 알려 주세요. 회원은 자기 글과 댓글을 언제든 삭제할 수 있습니다.</p>
  <h2>7. 권리 침해 신고</h2>
  <p>내 권리(명예·사생활·저작권 등)를 침해하는 글을 발견하면 글의 '신고' 버튼 또는 아래 문의 창구로 알려 주세요. 회원이 아니어도 문의 창구로 요청할 수 있습니다. 확인한 뒤 가림·삭제 등 필요한 조치를 합니다.</p>
  <p>{op_line}</p>
  <h2>8. 탈퇴</h2>
  <p>'마이페이지'에서 언제든 탈퇴할 수 있습니다. 탈퇴하면 계정과 이메일은 바로 삭제되고, 쓴 글과 댓글은 작성자가 '탈퇴한 회원'으로 바뀐 채 남습니다. 남기고 싶지 않은 글은 탈퇴 전에 직접 삭제하세요.</p>
  <p class="src-note">시행일 {e(cmc.get("rules_effective") or today)}. 수칙이 바뀌면 이 페이지에 알립니다.</p>
</div>"""
    write("board/rules/index.html", page(site, "../../", "board/rules/", "게시판 이용수칙", rules_body, desc="SafePlum 커뮤니티·Q&A·채용공고 게시판 이용수칙.", active="board/"))

    pv = cmc.get("privacy") or {}
    def pv_val(k):
        return e(pv[k]) if pv.get(k) else '<span class="lst lst-chk" tabindex="0">확인 필요</span> 운영자가 아직 입력하지 않았습니다'
    privacy_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>개인정보 처리방침</p>
  <h1>개인정보 처리방침</h1>
  <p>SafePlum이 게시판 회원가입과 운영을 위해 어떤 개인정보를 어떻게 다루는지 알립니다. 작성 도구에 입력한 문서 내용은 서버로 보내지 않으며 이 방침의 수집 항목에 들어가지 않습니다.</p>
</div></section>
<div class="wrap legal-doc" style="max-width:860px;padding-bottom:48px">
  <h2>1. 수집하는 항목과 목적</h2>
  <div class="cm-tblw"><table class="cm-tbl"><thead><tr><th>항목</th><th>목적</th><th>수집 시점</th></tr></thead><tbody>
    <tr><th>이메일 주소</th><td>본인 확인(인증 메일), 로그인, 비밀번호 재설정, 이용 제한·강제 탈퇴 등 운영 조치</td><td>회원가입</td></tr>
    <tr><th>비밀번호</th><td>로그인. 원문이 아닌 암호화(해시)된 값으로 저장됩니다.</td><td>회원가입</td></tr>
    <tr><th>닉네임</th><td>글·댓글의 작성자 표시(공개)</td><td>회원가입</td></tr>
    <tr><th>글·댓글·첨부 사진·신고 내용</th><td>게시판 제공, 신고 처리. 첨부 사진은 올릴 때 다시 저장되어 촬영 위치 등 사진 속 부가 정보(EXIF)는 남지 않습니다.</td><td>작성할 때</td></tr>
    <tr><th>접속 기록(접속 일시·IP 주소 등)</th><td>부정 이용 방지, 장애 대응. 인증·호스팅 서비스가 자동으로 남깁니다.</td><td>이용할 때 자동</td></tr>
  </tbody></table></div>
  <p>이름·전화번호·주민등록번호 등은 받지 않습니다. 외부 광고·분석 도구는 쓰지 않습니다. 하루 방문자 수를 세기 위해, 브라우저가 그날 처음 접속할 때 그날만 쓰는 임의 번호를 한 번 보냅니다. 이 번호는 매일 새로 만들어지고 계정·이메일과 연결하지 않으며, 날짜별 개수만 집계합니다.</p>
  <h2>2. 보유 기간</h2>
  <p>회원 정보(이메일·비밀번호·닉네임)는 탈퇴할 때까지 보유하고, 탈퇴하면 바로 삭제합니다. 이용수칙 위반으로 강제 탈퇴된 경우에는 같은 이메일로 다시 가입하는 것을 막기 위해, 이메일 주소를 원래 값으로 되돌릴 수 없게 바꾼 값(해시)만 따로 보관할 수 있습니다. 글과 댓글은 회원이 삭제하거나 탈퇴할 때 작성자 정보와의 연결이 끊어집니다. 삭제한 글은 화면에서 바로 사라지며, 분쟁·신고 대응을 위해 운영자만 볼 수 있는 상태로 보관한 뒤 파기합니다. 보관 기간: {pv_val("deleted_retention")}.</p>
  <h2>3. 처리 위탁과 보관 위치</h2>
  <div class="cm-tblw"><table class="cm-tbl"><thead><tr><th>맡기는 곳</th><th>맡기는 일</th><th>보관 위치</th></tr></thead><tbody>
    <tr><th>Supabase Inc.</th><td>회원 인증, 게시판 데이터베이스·첨부 사진 저장소 운영</td><td>{pv_val("db_region")}</td></tr>
    <tr><th>인증 메일 발송 서비스</th><td>가입 인증·비밀번호 재설정 메일 발송</td><td>{pv_val("mail_provider")}</td></tr>
    <tr><th>GitHub, Inc. (GitHub Pages)</th><td>웹사이트 파일 호스팅(접속 기록)</td><td>해당 사업자 정책에 따름</td></tr>
  </tbody></table></div>
  <p>위 사업자가 국외 법인이므로 개인정보가 국외에서 처리·보관될 수 있습니다. 넘어가는 항목은 이메일 주소·암호화된 비밀번호·닉네임·글과 댓글·접속 기록이며, 회원가입과 게시판 이용 시점에 암호화된 통신(HTTPS)으로 전송됩니다. 위탁받은 사업자는 회원 탈퇴 또는 위탁 종료 때까지 위 목적으로만 보관합니다. 국외 처리·보관을 원하지 않으면 가입하지 않거나 탈퇴할 수 있으며, 그 경우 게시판 글쓰기는 이용할 수 없습니다(읽기와 작성 도구는 가입 없이 이용 가능).</p>
  <div class="cm-tblw"><table class="cm-tbl"><thead><tr><th>국외 처리 항목</th><th>내용</th></tr></thead><tbody>
    <tr><th>이전되는 항목</th><td>이메일 주소, 암호화된 비밀번호, 닉네임, 글·댓글·첨부 사진, 접속 기록</td></tr>
    <tr><th>이전되는 국가·시기·방법</th><td>데이터는 대한민국(AWS 서울 리전)에 저장됩니다. 수탁 사업자의 본사가 있는 미국 등에서 운영·장애 대응을 위해 접근·처리될 수 있습니다. 회원가입·게시판 이용 시점에 암호화된 통신(HTTPS)으로 전송됩니다.</td></tr>
    <tr><th>이전받는 자</th><td>Supabase Inc. (미국 · supabase.com) — 데이터베이스·회원 인증·파일 저장·인증 메일 발송</td></tr>
    <tr><th>이용 목적·보유 기간</th><td>위 위탁 업무 수행. 회원 탈퇴 또는 위탁 종료 때까지</td></tr>
    <tr><th>거부 방법·효과</th><td>가입하지 않거나 '마이페이지'에서 탈퇴하면 됩니다. 이 경우 게시판 글쓰기를 이용할 수 없습니다(읽기와 작성 도구는 가입 없이 이용 가능).</td></tr>
  </tbody></table></div>
  <p>근거: 「개인정보 보호법」 제28조의8제1항제3호(계약 이행을 위한 처리위탁·보관으로서 처리방침에 공개하는 경우).</p>
  <p>법령에 따른 요청이 있는 경우를 빼고 제3자에게 제공하지 않습니다.</p>
  <p>'안전보건 영상'은 유튜브(YouTube, 개인정보 보호 강화 모드)·틱톡(TikTok)이 제공하는 플레이어로 보여 줍니다. 방문자가 재생 버튼을 누르기 전에는 유튜브·틱톡에 접속하지 않으며, 재생하면 해당 서비스가 쿠키 등으로 정보를 수집할 수 있고 이에는 각 서비스의 개인정보 처리방침이 적용됩니다. SafePlum은 이 과정에서 회원 정보를 보내지 않습니다.</p>
  <p>법령 AI 질문, TBM·위험성평가 AI 초안 같은 <b>AI 기능</b>은 이용자가 직접 입력한 본인의 Google Gemini API 키로 브라우저에서 Google에 바로 요청합니다. 키는 그 브라우저에만 저장되고 SafePlum 서버로 보내지 않습니다. AI 기능을 쓰면 입력한 질문·작업 내용이 Google(미국 Google LLC)로 전송되어 처리되며, 이에는 Google의 Gemini API 약관과 개인정보 처리방침이 적용됩니다. SafePlum은 이 내용을 받거나 보관하지 않습니다. 회사명·실명·사고 피해자 정보 같은 개인정보나 기밀은 AI 입력란에 넣지 마세요. AI 기능을 쓰지 않으면 이 전송은 일어나지 않습니다.</p>
  <h2>4. 회원의 권리</h2>
  <p>'마이페이지'에서 닉네임·비밀번호를 바꾸고 탈퇴(삭제)할 수 있습니다. 열람·정정·삭제·처리정지를 직접 하기 어려우면 아래 문의 창구로 요청하세요. 만 14세 미만은 가입할 수 없습니다.</p>
  <h2>5. 안전 조치</h2>
  <p>비밀번호는 암호화해 저장하고, 전송 구간은 HTTPS로 암호화합니다. 운영자가 회원 정보를 조회하거나 계정을 삭제한 기록(일시·접속 IP·한 일)은 따로 남겨 보관합니다. 이메일 주소는 다른 회원에게 공개되지 않으며, 데이터베이스는 본인 글만 고치거나 지울 수 있도록 행 단위 접근 규칙으로 보호합니다.</p>
  <h2>6. 개인정보 보호책임자·문의</h2>
  {po_html}
  <p>{operator_html(site, "../")}</p>
  <p>개인정보 침해에 대한 상담은 개인정보침해신고센터(privacy.kisa.or.kr, 국번 없이 118), 개인정보분쟁조정위원회(kopico.go.kr)에서도 받을 수 있습니다.</p>
  <p class="src-note">시행일 {pv_val("effective")}. 내용이 바뀌면 이 페이지에 알립니다.</p>
</div>"""
    write("privacy/index.html", page(site, "../", "privacy/", "개인정보 처리방침", privacy_body, desc="SafePlum 개인정보 처리방침."))

    # ---- 서비스 소개·문의(about/): 확인된 운영 정보와 실제로 연결되는 문의 채널만 싣는다(사업자 정보·답변 기한 등은 확인되지 않아 싣지 않음)
    _op = site.get("operator") or {}
    _cu = _op.get("contact_url") or ""
    _cu_ok = _cu.startswith("mailto:") or bool(safe_url(_cu))
    _pm = ((_op.get("privacy_officer") or {}).get("email") or "").strip()
    _err_post = next((p for p in ((BP or {}).get("posts") or []) if p.get("board") == "free" and "오류 신고" in p.get("title", "") and str(p.get("title", "")).startswith("[운영팀]")), None)
    _err_href = f"../board/post/{_err_post['id']}/" if _err_post else "../board/?b=free"
    _gq_n = len(load("data/gov_qa.json")["items"]) if (ROOT / "data/gov_qa.json").exists() else 0
    def _ch(title, desc_, links):
        return f'<li class="ab-ch"><div><b>{e(title)}</b><span>{e(desc_)}</span></div><p class="btns">{"".join(links)}</p></li>'
    _kakao = (f'<a class="btn btn-sm" href="{e(_cu)}"{"" if _cu.startswith("mailto:") else " target=_blank rel=noopener"}>{e(_op.get("contact_label") or "문의하기")}</a>') if _cu_ok else ""
    _chs = []
    if _kakao:
        _chs.append(_ch("서비스 이용 문의", "도구·서식 사용법, 게시판 이용 등 궁금한 점", [_kakao]))
    _chs.append(_ch("기능 오류 신고", "화면이 깨지거나 계산·판정·법령 근거가 틀린 것 같을 때 — 페이지 주소와 함께 알려 주세요", ([_kakao] if _kakao else []) + [f'<a class="btn btn-sm btn-ghost" href="{_err_href}">게시판 오류 신고 글</a>']))
    _chs.append(_ch("개선 의견 제안", "필요한 서식·기능, 불편한 점", [f'<a class="btn btn-sm btn-ghost" href="{_err_href}">게시판에 남기기</a>'] + ([_kakao] if _kakao else [])))
    if _pm:
        _chs.append(_ch("개인정보 관련 문의", "회원 정보 열람·정정·삭제·처리정지 요청, 개인정보 처리에 관한 문의", [f'<a class="btn btn-sm" href="mailto:{e(_pm)}">이메일 {e(_pm)}</a>', '<a class="btn btn-sm btn-ghost" href="../privacy/">개인정보 처리방침</a>']))
    about_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>서비스 소개·문의</p>
  <h1>서비스 소개 · 문의</h1>
  <p>{e(site['name'])}(세이프플럼)은 안전관리자·보건관리자 등 산업안전보건 실무자가 법정 서류를 쉽고 빠르게 작성하고, 법령과 실무 정보를 한곳에서 찾을 수 있도록 만든 무료 서비스입니다.</p>
</div></section>
<div class="wrap layout-detail ab-layout"><section class="col-main stack">
  <section><h2 class="h-sm">주요 기능</h2><ul class="ab-feat">
    <li><a href="../tools/forms/"><b>작성기 {WRITER_N}종</b><span>TBM 일지·위험성평가서·교육일지·점검표·작업계획서·중대재해처벌법 이행 서식 등. 회원가입 없이 쓰고 A4로 인쇄·PDF 저장</span></a></li>
    <li><a href="../tools/"><b>계산·조회 도구</b><span>적용범위 판정, 법정교육 시간, 산업안전보건관리비, 과태료 기준, 안전검사 주기 등</span></a></li>
    <li><a href="../laws/"><b>법령</b><span>산업안전보건법령·중대재해처벌법령 현행 조문{f", 고용노동부 질의회시 {_gq_n:,}건" if _gq_n else ""}</span></a></li>
    <li><a href="../tools/ai/"><b>AI 도구</b><span>법령 AI 질문, 서식 AI 작성 도우미 등 — Google Gemini API 키(무료 발급)가 필요한 기능</span></a></li>
    <li><a href="../board/"><b>게시판</b><span>커뮤니티·Q&amp;A·채용공고. 읽기는 누구나, 쓰기는 이메일 인증 회원</span></a></li>
    <li><a href="../brief/"><b>브리핑·소식</b><span>법령 개정·입법예고 등 안전보건 소식</span></a></li>
  </ul></section>
  <section><h2 class="h-sm">문의 · 오류 신고 · 제안</h2><p class="hint">목적에 맞는 창구를 골라 주세요. 회사명·실명·연락처 같은 개인정보는 꼭 필요한 경우가 아니면 적지 마세요.</p><ul class="ab-chs">{"".join(_chs)}</ul></section>
  <section><h2 class="h-sm">운영 정보</h2><table class="ab-t"><tbody>
    <tr><th scope="row">서비스명</th><td>{e(site['name'])} (세이프플럼) · <a href="{e((site.get('base_url') or '').rstrip('/') + '/')}">{e((site.get('base_url') or '').replace('https://', ''))}</a></td></tr>
    <tr><th scope="row">운영</th><td>{e(_op.get("name") or site["name"])}</td></tr>
    <tr><th scope="row">개인정보 보호책임자</th><td>{e((_op.get("privacy_officer") or {}).get("title") or "운영자")}{f' · <a href="mailto:{e(_pm)}">{e(_pm)}</a>' if _pm else ""}</td></tr>
    <tr><th scope="row">요금</th><td>무료(회원가입 없이 작성기·도구 이용 가능). AI 기능은 이용자 본인의 Google API 키로 동작하며 사용 한도는 Google 정책을 따릅니다.</td></tr>
    <tr><th scope="row">입력 내용 저장</th><td>작성기·도구에 입력한 내용은 이용자의 브라우저에만 저장되고 SafePlum 서버로 보내지 않습니다(AI 기능을 쓸 때만 입력 내용이 Google로 전송). 게시판 글과 회원 정보는 게시판 서비스(Supabase)에 저장됩니다.</td></tr>
  </tbody></table></section>
  <section><h2 class="h-sm">정책</h2><ul class="bul">
    <li><a href="../privacy/">개인정보 처리방침</a></li>
    <li><a href="../board/rules/">게시판 이용수칙</a></li>
    <li><a href="../legal/">법령정보·면책 안내</a></li>
  </ul></section>
</section><aside class="col-side stack"><div class="side-box"><h2 class="h-sm">알아 두세요</h2><p class="hint">SafePlum의 정보와 서식은 현장 참고용입니다. 법 적용 여부는 법령 원문과 관할 지방고용노동관서(국번 없이 1350) 안내를 따르세요.</p></div></aside></div>"""
    write("about/index.html", page(site, "../", "about/", "서비스 소개·문의", about_body, desc=f"{site['name']}(세이프플럼) 서비스 소개, 주요 기능, 문의·오류 신고·개선 제안·개인정보 문의 창구와 운영 정보."))

    # ---- 법령정보·면책 안내
    man = manifest()
    need = [(l["name"], l.get("note", "")) for l in man["laws"] if "확인 필요" in (l.get("note") or "")]
    need += [(n["name"] + " " + n["no"], n.get("note", "")) for n in man.get("notices", []) if n.get("status") != "verified"]
    need += [(x["name"], x["note"]) for x in man.get("open_items", [])]
    need_html = "".join(f"<li><b>{e(a)}</b> — {e(b)}</li>" for a, b in need) or "<li>현재 표시할 항목이 없습니다.</li>"
    src_rows = "".join(f'<tr><th>{e(l["name"])}</th><td>{e(l["current"]["no"])} · 시행 {e(l["current"]["effective"])}</td><td>{e(l.get("checked_at", ""))}</td><td><a href="{e(l["current"].get("source_url") or l.get("history_url") or "")}" target="_blank" rel="noopener">국가법령정보센터 ↗</a></td></tr>' for l in man["laws"])
    src_rows += "".join(f'<tr><th>{e(n["name"])}</th><td>{e(n["no"])}</td><td>{e(n.get("checked_at", ""))}</td><td><a href="{e(n["source_url"])}" target="_blank" rel="noopener">국가법령정보센터 ↗</a></td></tr>' for n in man.get("notices", []))
    op_html = operator_html(site, "../")
    legal_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>법령정보·면책 안내</p>
  <h1>법령정보·면책 안내</h1>
  <p>SafePlum이 보여 주는 법령 정보, 판정·계산 결과, 양식이 어떤 성격의 자료인지 정리했습니다. 법령 데이터 기준일 {e(man.get("checked_at", ""))}.</p>
</div></section>
<div class="wrap legal-doc" style="max-width:860px;padding-bottom:48px">
  <h2 id="info">1. 법령정보 안내</h2>
  <p>SafePlum의 법령 본문·별표·서식은 국가법령정보센터에 공개된 원문을 옮겨 실은 것이고, 그 밖의 요약·분류·판정 기준·계산식·예시 문구는 SafePlum이 정리한 참고 자료입니다. 두 가지는 화면에서 구분해 표시합니다. 현재 시행 중인 내용, 공포되었지만 아직 시행 전인 내용, 국회를 통과했거나 입법예고 중인 내용은 서로 다른 상태로 나누어 보여 줍니다.</p>
  <p class="lst-legend">상태 표시: <span class="lst lst-cur">현재 시행</span> · <span class="lst lst-next">시행 예정</span> · <span class="lst lst-bill">법안·입법 동향</span> · <span class="lst lst-rec">권장사항</span> · <span class="lst lst-chk lst-keep">확인 필요</span></p>
  <h2 id="source">2. 법령 원문 출처</h2>
  <div class="table-wrap"><table class="lvt"><thead><tr><th>법령·고시</th><th>SafePlum이 쓰는 버전</th><th>공식 확인일</th><th>원문</th></tr></thead><tbody>{src_rows}</tbody></table></div>
  <p>법적 근거로는 국가법령정보센터, 고용노동부, 한국산업안전보건공단 등 공식 기관의 자료만 사용합니다. 언론 보도는 '참고 보도'로만 표시하며 법령·정책의 근거로 쓰지 않습니다. 확인일로부터 {int(man.get("stale_after_days", 45))}일이 지나면 화면에 '공식 원문 재확인 필요'가 표시됩니다.</p>
  <h2 id="limit">3. 자가진단 도구의 한계</h2>
  <p>적용범위 판정, 유해위험방지계획서 대상 확인, 기계·설비 의무 조회 등의 결과는 입력조건과 현행 법령 데이터를 이용한 자가진단 결과이며, 최종 판단은 관할 행정기관의 해석과 처분을 따릅니다. 업종 분류, 상시근로자 수 산정, 도급 관계처럼 사실관계 판단이 필요한 부분은 도구가 대신 판단할 수 없습니다. 결과는 적용 · 조건부 · 확인 필요 · 적용 제외 네 단계로만 표시합니다.</p>
  <h2 id="calc">4. SafePlum 계산 결과의 성격</h2>
  <p>과태료, 산업안전보건관리비, 상시근로자 수, 교육시간, 체감온도 등의 계산 결과는 참고 계산입니다. 과태료의 최종 처분 금액은 실제 위반사실과 감경·가중사유를 기준으로 관할 행정기관이 판단합니다. 상시근로자 수 산정방법은 적용 법령별로 별도 확인이 필요합니다. 위험성평가의 가능성·중대성 척도와 등급 구간은 'SafePlum 기본 위험성평가 예시 기준'이며 사업장이 정한 방법으로 바꿔 쓸 수 있습니다.</p>
  <h2 id="health">5. 건강정보 도구 안내</h2>
  <p>뇌·심혈관질환 발병위험도 평가 등 건강 관련 도구의 결과는 건강관리를 돕는 참고 자료입니다. 정확한 진단과 업무 적합성·사후관리 판단은 의사 등 보건의료 전문가의 평가를 받으세요. 이 결과만을 근거로 채용·배치·해고 등 고용상 불이익을 주어서는 안 됩니다. 건강정보는 민감정보이므로 다른 사람의 정보를 입력할 때에는 사업장에서 정한 절차와 본인 동의 등 개인정보 보호법상 요건을 사업장이 직접 확인해야 합니다. 공용 PC에서는 사용 후 '작성 내용 백업 · 삭제'에서 데이터를 지우세요.</p>
  <h2 id="forms">6. SafePlum 자체 양식의 법적 지위</h2>
  <p>서식은 세 가지로 구분합니다. <span class="fkind fkind-a">법령 별지 서식 원본</span>은 국가법령정보센터의 별지 서식 파일로 연결됩니다. <span class="fkind fkind-b">SafePlum 자체 제공 양식</span>(작성기, TBM 일지, 위험성평가서, 산업안전보건위원회 회의록, LOTO 꼬리표, 현장 안내 게시물 등)은 관련 조문을 참고해 만든 실무용 보조양식입니다(법령 별지 서식과는 별개). <span class="fkind fkind-c">사업장 예시</span>(예시로 채우기, 자동 입력 문구)는 실제 내용으로 바꿔 쓰는 예시입니다. 자체 양식을 작성한 것만으로 법령상 의무를 이행했다고 볼 수 없습니다.</p>
  <p>결재란의 서명은 인쇄용 서명 이미지입니다. 기관에 전자로 제출할 때는 해당 기관이 정한 인증·서명 방식을 따르세요.</p>
  <h2 id="links">7. 외부 링크 책임범위</h2>
  <p>기관 누리집, 채용 플랫폼, 공단 자료 등 외부 링크의 내용과 접속 가능 여부는 각 운영 주체가 관리합니다. 주소가 바뀌거나 내용이 달라질 수 있으며, SafePlum은 외부 사이트의 내용을 보증하지 않습니다.</p>
  <h2 id="jobs">8. 채용공고 책임범위</h2>
  <p>채용정보는 외부 채용 플랫폼과 공공 채용 사이트로 연결합니다. SafePlum은 공고를 직접 받거나 게시하지 않으며, 채용 조건·마감일은 각 플랫폼의 공고 원문과 채용 기업이 책임집니다.</p>
  <h2 id="data">9. 데이터 저장 방식</h2>
  <p>작성 도구에 입력한 내용, 서명 이미지, 첨부 사진은 SafePlum 서버로 전송하지 않고 사용 중인 브라우저(localStorage·IndexedDB)에 저장합니다. 브라우저 기록을 지우거나 기기를 바꾸면 사라지므로 필요하면 화면 아래 '작성 내용 백업'으로 파일을 내려받아 두세요. 다만 사이트는 GitHub Pages에서 제공되고 글꼴 등 일부 자원을 외부 CDN에서 불러오므로, 접속 기록(IP 주소 등)에는 해당 제공자의 정책이 적용됩니다. </p>
  <h2 id="report">10. 오류 신고 방법</h2>
  <p>법령 내용·시행일·판정 결과·계산식의 오류를 발견하면 알려 주세요. 해당 화면 주소와 근거 조문을 함께 적어 주시면 확인이 빠릅니다.</p>
  <p>{op_html}</p>
  <h2 id="check">확인 필요로 남겨 둔 데이터</h2>
  <p>공식 원문으로 다시 확인하지 못해 임의로 고치지 않고 표시만 해 둔 항목입니다.</p>
  <ul class="bul">{need_html}</ul>
  <h2 id="priority">11. 국가법령정보센터 원문 우선 원칙</h2>
  <p>SafePlum의 내용과 법령 원문이 다르면 언제나 <a href="https://www.law.go.kr/" target="_blank" rel="noopener">국가법령정보센터</a>의 현행 원문이 우선합니다. 실제 적용 여부와 해석은 관할 지방고용노동관서 등 행정기관에 확인하시기 바랍니다.</p>
</div>"""
    write("legal/index.html", page(site, "../", "legal/", "법령정보·면책 안내", legal_body,
          desc="SafePlum 법령 정보의 출처와 기준일, 자가진단·계산 결과의 한계, 자체 양식의 법적 지위, 데이터 저장 방식, 오류 신고 방법."))

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
        main = jobs_empty
        side = ""
    jobs_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>채용정보</p>
  <h1>안전·보건 채용정보</h1>
  <p>안전관리자·보건관리자·EHS·소방 채용 공고를 채용 플랫폼과 공공 채용 사이트에서 바로 찾을 수 있게 연결합니다. 지원 조건은 공고 원문을 확인하세요.</p>
</div></section>
<div class="wrap layout-list{' no-side' if not side else ''}">
  {f'<aside class="col-filter">{side}</aside>' if side else ''}
  <section class="col-list">{job_info_html(site, "job-no")}<a class="job-today" href="today/"><b>오늘의 채용 모음</b> 대기업·공공기관·외국계·중견기업 마감 전 공고만 업종별로 보기 →</a>{chat_banner()}
    {'<p class="job-member"><b>우리 회사 공고를 직접 올릴 수 있습니다.</b> 회원이면 누구나 무료로 등록합니다. <a class="btn btn-sm" href="../board/?b=job">회원 채용공고 보기 · 등록</a></p>' if JOB_POST else '<p class="job-member"><b>회원 채용공고 등록은 현재 준비 중입니다.</b> 준비가 끝나면 다시 열겠습니다. <a class="btn btn-sm btn-ghost" href="../board/?b=job">회원 채용공고 보기</a></p>'}
    {main}
    {f'<div class="more-box"><p>다른 채용 사이트에서 더 찾기</p><div class="jchips">{job_chips}</div></div>' if jobs else ''}
  </section>
</div>"""
    write("jobs/index.html", page(site, "../", "jobs/", "채용정보", jobs_body,
                                  desc="안전관리자·보건관리자·EHS·소방 채용공고를 직무·기업분류·업종별로 찾아보세요.", active="jobs/"))

    # ---- 채용 상세
    def apply_html(j):
        src = safe_url(j.get("source_url"))
        if src:
            return f'<a class="btn btn-block" href="{e(src)}" target="_blank" rel="noopener nofollow">공고 원문에서 지원 ↗</a>'
        ap = str(j.get("apply") or "").strip()
        m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", ap)
        btn = f'<a class="btn btn-block" href="mailto:{e(m.group(0))}">이메일로 지원</a>' if m else ""
        return f'<p class="apply-how"><b>지원 방법</b>{e(ap)}</p>{btn}'

    for j in jobs:
        def lines(v):
            return "".join(f"<li>{e(x.strip())}</li>" for x in str(v or "").split("|") if x.strip())
        dl = str(j.get("deadline", "") or "")
        rows = [("기업 구분", j.get("company_type")), ("계열", j.get("group")), ("업종", j.get("industry")), ("직무", " · ".join(j["jobs_list"])),
                ("근무지", j.get("region")), ("근무지 주소", j.get("address")), ("경력", career_txt(j)), ("학력", j.get("education")), ("고용형태", j.get("employment")), ("근무기간", j.get("term") or ("원문 확인" if j.get("employment") == "계약직" else "")),
                ("채용인원", f'{j["headcount"]:g}명' if isinstance(j.get("headcount"), (int, float)) and j["headcount"] else ""),
                ("NCS 직무", j.get("ncs")),
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
      <p class="tags">{grade_tag(j)}{''.join(f'<span class="tag tag-job">{e(x)}</span>' for x in j["jobs_list"])}{f'<span class="tag">{e(j.get("region"))}</span>' if j.get("region") else ''}</p>
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
    {'<p class="src-note">이 공고는 채용 기업이 SafePlum에 직접 등록했고 운영자가 확인한 뒤 게시했습니다. 내용의 정확성은 등록 기업에 책임이 있습니다.</p>' if j.get('origin') == 'user' else ''}
    {'<p class="src-note">' + e(j.get('source_name') or '채용 사이트') + '에 게시된 공고 중 안전·보건 직무를 SafePlum 운영자가 골라 기본 정보(회사·근무지·경력·마감일)만 옮기고 원문으로 연결했습니다. 담당 업무·자격요건·급여·지원 방법은 원문에서 확인하세요. SafePlum은 채용을 알선하지 않습니다.</p>' if j.get('origin') == 'curated' else ''}
    <p class="src-note">출처: {e(j.get('source_name') or '공고 원문')}{' — 재정경제부 공공기관 채용정보 API(공공데이터포털, 이용허락범위 제한 없음)로 자동 수집' if j.get('origin') == 'alio' else ''} · 조건과 일정은 원문이 우선합니다.</p>
  </article>
  <aside class="col-side">
    <div class="apply-card" data-deadline="{e(dl)}">
      <p class="apply-label">마감</p>
      <p class="apply-dl"><span data-dl-text>{e(dl_txt)}</span> {dl_badge(j)}</p>
      {apply_html(j)}
      <a class="btn btn-block btn-ghost" href="../">다른 공고 보기</a>
    </div>
    {company_box(j)}
  </aside>
</div>"""
        write(f"jobs/{j['id']}/index.html", page(site, "../../", f"jobs/{j['id']}/", f"{j['company']} {j['title']}", body,
                                                  desc=f"{j['company']} · {j.get('region','')} · {career_txt(j)} · 마감 {dl}", active="jobs/"))

    # ---- 오늘의 채용 모음(카카오톡 오픈채팅 공유용): 대기업·공공·외국계·중견 공고 중 마감 전, 업종별
    write("jobs/today/index.html", page(site, "../../", "jobs/today/", "오늘의 안전·보건 채용 모음", jobs_today_body(site, jobs, today),
                                        desc="대기업·공공기관·외국계·중견기업의 안전관리자·보건관리자·EHS 채용 중 마감 전 공고를 업종별로 모았습니다. 매일 아침 갱신.", active="jobs/"))

    # ---- 서식·자료
    CAT_ORDER = ["법정 서식", "웹 작성 서식", "무료 작성 도구", "법정 기준표(별표)", "고시·지침", "공단 자료", "Mallo 서식", "기관·행정용"]
    corder = {c: i for i, c in enumerate(CAT_ORDER)}
    resources.sort(key=lambda r: (0 if r.get("popular") else 1, corder.get(r.get("category"), 99)))
    cats = sorted({r["category"] for r in resources if r.get("category")}, key=lambda c: corder.get(c, 99))
    catnav = (f'<button type="button" class="chip" data-value="" aria-pressed="true">전체 <span class="n">{len(resources)}</span></button>'
              + "".join(f'<button type="button" class="chip" data-value="{e(c)}" aria-pressed="false">{e(c)} <span class="n">{sum(1 for r in resources if r.get("category")==c)}</span></button>' for c in cats))
    topics = [t for t, _ in LF_TOPICS if any(r.get("topic") == t for r in resources)]
    topicnav = ('<button type="button" class="chip" data-value="" aria-pressed="true">전체</button>'
                + "".join(f'<button type="button" class="chip" data-value="{e(t)}" aria-pressed="false">{e(t)}</button>' for t in topics))
    n_law = sum(1 for r in resources if r.get("byl_no"))
    n_web = sum(1 for r in resources if r.get("category") == "웹 작성 서식")
    res_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>서식·자료</p>
  <h1>서식·자료</h1>
  <p data-landing>법정 서식·별표 {n_law}건은 국가법령정보센터 현행 원본으로 열리고(개정되면 같은 버튼이 최신본을 엽니다), 웹 작성 서식 {n_web}건은 여기서 바로 작성·인쇄합니다.</p>
</div></section>
<section class="wrap" style="padding-top:16px" data-landing>{tools_cta.format(rel="../")}</section>
<section class="wrap ftools-page" style="padding-top:8px" data-landing>
  <div class="ftools">
    <a class="ftool" href="../tools/forms/"><span class="ftool-tag">바로 작성</span><strong>작성기 {WRITER_N}종</strong><span class="ftool-desc">교육일지·점검표 19종·작업계획서·허가서를 웹에서 작성하고 A4로 인쇄. 회원가입 없음.</span><span class="ftool-go">서식 작성 →</span></a>
    <a class="ftool" href="templates/"><span class="ftool-tag">엑셀·PPT</span><strong>무료 양식 내려받기 {len(downloads())}종</strong><span class="ftool-desc">위험성평가표·TBM 일지·작업계획서 4종·순회점검표·교육일지 엑셀과 산업안전보건위원회·개선 전후 보고 PPT.</span><span class="ftool-go">양식 받기 →</span></a>
    <a class="ftool" href="signs/"><span class="ftool-tag">20개 언어</span><strong>안전보건표지 40종</strong><span class="ftool-desc">금지·경고·지시·안내 표지를 찾아 A4 한 장으로 바로 인쇄. 외국어 파일까지.</span><span class="ftool-go">표지 보기 →</span></a>
    <a class="ftool" href="library/"><span class="ftool-tag">공공누리 {n_kosha:,}건</span><strong>안전보건 자료실</strong><span class="ftool-desc">공단 OPS·포스터·책자·교안·동영상을 주제·형태·외국어로 찾고 원본으로 바로 이동. 이달의 계절 자료까지.</span><span class="ftool-go">자료 찾기 →</span></a>
  </div>
</section>
<section class="wrap" style="padding-top:28px" data-landing>
  {sec_head("상황별로 찾기", sub="지금 하려는 일을 고르면 필요한 법정 서식·기준표·작성 도구를 모아 보여줍니다.")}
  <div class="sit-grid">{situation_cards(resources, "../", site.get("free_tools"))}</div>
</section>
<div class="wrap layout-list" id="res-list">
  <aside class="col-filter">
    <details class="fpanel" data-fpanel open><summary>분류·주제 필터</summary><div class="fpanel-body">
      <div class="fgroup"><p class="fgroup-label">분류</p><div class="chips catnav" data-filter="cat" role="group" aria-label="분류">{catnav}</div></div>
      <div class="fgroup"><p class="fgroup-label">주제</p><div class="chips topicnav" data-filter="topic" role="group" aria-label="주제">{topicnav}</div></div>
      <label class="switch"><input type="checkbox" class="only-fav"><span>★ 즐겨찾기만</span></label>
      <button type="button" class="btn btn-sm btn-ghost fpanel-reset" data-reset>필터 초기화</button>
    </div></details>
  </aside>
  <section class="col-list">
    <div class="listbar"><div class="search-inline">
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input type="search" class="filter-q" placeholder="예: 재해조사표, 선임, 도급, 작업환경측정, 별지 30" aria-label="서식 검색"></div></div>
    <p class="count" aria-live="polite">자료 <strong data-count>{len(resources)}</strong>건</p>
    <ul class="rlist" data-list data-page-size="30">{''.join(resource_row(r, site, '../') for r in resources)}</ul>
    <p class="more-wrap" data-more-wrap hidden><button type="button" class="btn btn-ghost btn-block" data-more>더 보기</button></p>
    {empty_box("조건에 맞는 서식·자료가 없습니다. 낱말을 줄이거나 다른 말로 찾아보세요.", '<div class="btns"><button type="button" class="btn btn-sm" data-reset>전체 자료 보기</button><a class="btn btn-sm btn-ghost" href="library/" data-q-href="library/">공단 자료실에서 찾기</a><a class="btn btn-sm btn-ghost" href="../tools/">무료 도구에서 찾기</a></div>').replace('class="empty"', 'class="empty" data-empty hidden')}
    <p class="src-line" style="margin-top:14px">법정 서식·별표 목록 확인일 {e(load("data/lawforms.json")["checked"])} · 국가법령정보센터 법령 본문의 별표·서식 목록 기준. 법령 원문은 누구나 자유롭게 인용·활용할 수 있습니다.</p>
  </section>
</div>"""
    for pid, src, name, title, desc in [
        ("signs", "apps/signs.body.html", "signs", "안전보건표지 40종", "산업안전보건법 시행규칙 별표 6 안전보건표지 40종을 찾아 A4로 인쇄. 한국어·영어 등 20개 언어 원본 파일."),
        ("library", "apps/library.body.html", "library", "안전보건 자료실", "안전보건공단 공공누리 자료(OPS·포스터·책자·교안·동영상) 9천여 건을 검색하고 원본으로 연결."),
    ]:
        body = inject_data((ROOT / src).read_text(encoding="utf-8"), [name], src)
        if pid == "signs":
            body = body.replace("<!--@DUCK@-->", duck_signs_html(site, write))
        write(f"resources/{pid}/index.html", page(site, "../../", f"resources/{pid}/", title, body, desc=desc, active="resources/"))
    for r in resources:
        if r.get("detail"):
            write(f"{r['detail']}index.html", page(site, "../../../", r["detail"], f'{r["title"]} ({r.get("form_no","")})',
                  resource_detail(r, resources, LIDX, LFILES, site),
                  desc=f'{r["law"]} {r.get("form_no","")} {r["title"]} — 근거 조문과 원본 바로가기', active="resources/"))
    write("resources/index.html", page(site, "../", "resources/", "서식·자료", res_body,
                                       desc="산업재해조사표, 안전관리자 선임 보고서 등 산업안전보건 법정 서식을 원본으로 바로 여세요.", active="resources/"))


    # ---- 안전뉴스 (공공데이터포털 공식 API로 받은 목록만)
    def news_li(n):
        sub = f'<p>{e(n["sub"])}</p>' if n.get("sub") else ""
        text = " ".join([n["title"], n.get("sub", ""), n.get("ministry", "")])
        return (f'<li class="nrow" data-item data-text="{e(text)}">'
                f'<time>{fmt_date(n.get("date", ""))}</time><div><a href="{e(n["url"])}" target="_blank" rel="noopener">{e(n["title"])} ↗</a>'
                f'{sub}<p class="nmeta">{e(n.get("ministry", ""))} · 공공누리 제{e(n.get("kogl", ""))}유형 · 출처 정책브리핑(www.korea.kr)</p></div></li>')
    news_items = auto_news["items"]
    acc_items = auto_acc["items"]
    news_list = (f'<ul class="nlist" data-list>{"".join(news_li(n) for n in news_items)}</ul>'
                 + empty_box("검색 결과가 없습니다.").replace('class="empty"', 'class="empty" data-empty hidden')) if news_items else empty_box(
        "정책뉴스 자동 수집이 아직 설정되지 않았습니다. 설정되면 매일 새 기사가 올라옵니다.",
        '<div class="btns"><a class="btn btn-sm btn-ghost" href="https://www.korea.kr/briefing/pressReleaseList.do" target="_blank" rel="noopener">정책브리핑 보도자료 ↗</a>'
        '<a class="btn btn-sm btn-ghost" href="https://www.moel.go.kr/news/enews/report/enewsList.do" target="_blank" rel="noopener">고용노동부 보도자료 ↗</a></div>')
    acc_lis = "".join(f"<li>{e(a['text'])}</li>" for a in acc_items[:30])
    acc_list = (f'<ul class="alist">{acc_lis}</ul>'
                f'<p class="src-line">출처: 한국산업안전보건공단 사고사망 게시판(공공데이터포털 API, 이용허락범위 제한 없음) · 수집일 {e(auto_acc.get("fetched",""))}</p>') if acc_items else empty_box(
        "사고사망 속보 자동 수집이 아직 설정되지 않았습니다.",
        '<div class="btns"><a class="btn btn-sm btn-ghost" href="https://portal.kosha.or.kr/" target="_blank" rel="noopener">산업안전포털 ↗</a></div>')
    news_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>안전뉴스</p>
  <h1>안전뉴스</h1>
  <p>정부 정책뉴스 가운데 산업안전 관련 기사와 안전보건공단 사고사망 속보를 모았습니다. 모두 공공데이터포털 공식 API로 받은 공개 자료이며, 제목을 누르면 원문이 열립니다.</p>
</div></section>
<div class="wrap layout-detail">
  <section class="col-main stack">
    {sec_head("정책뉴스", sub=(f"산업안전 관련 {len(news_items)}건 · 최근 30일 · 수집일 {auto_news.get('fetched','')}" if news_items else None))}
    {('<div class="listbar"><div class="search-inline"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="search" class="filter-q" placeholder="예: 중대재해, 폭염, 추락" aria-label="뉴스 검색"></div></div><p class="count" aria-live="polite">기사 <strong data-count>' + str(len(news_items)) + '</strong>건</p>') if news_items else ''}
    {news_list}
    <div style="margin-top:28px">{sec_head("법령 개정 소식", "../laws/", sub="산업안전보건법령 개정 내용을 원문 링크와 함께 정리합니다.")}
    <ul class="ulist">{"".join(update_row(u) for u in updates[:5])}</ul></div>
  </section>
  <aside class="col-side">
    {acc_trend_html(auto_acc, today)}
    <section class="side-box">{sec_head("사고사망 속보", ("../" + ACC_PAGE) if acc_items else None)}{acc_list}</section>
    <section class="side-box"><p class="hint">SafePlum은 기사 본문을 옮기지 않습니다. 제목·부제·부처·날짜만 싣고 원문으로 연결합니다. 민간 언론사 기사와 다른 사이트의 게시물은 싣지 않습니다.</p></section>
  </aside>
</div>"""
    if auto_acc.get("items"):
        write(ACC_PAGE + "index.html", page(site, "../", ACC_PAGE, "사고사망 속보", acc_page_body(auto_acc, today),
                                            desc="안전보건공단 사고사망 속보를 발생일·재해유형별로 정리 — 최근 사고 사례를 TBM·위험성평가에 반영하세요.", active="brief/"))
    if (site.get("features") or {}).get("public_api", False):
      write("news/index.html", page(site, "../", "news/", "안전뉴스", news_body,
                                  desc="산업안전 관련 정부 정책뉴스와 안전보건공단 사고사망 속보 — 공식 공공데이터 API로 수집.", active="news/"))

    # ---- 법령: 홈(검색·주제별·개정 소식) + 법령별 전문 페이지
    import lawpages
    LAWS = lawpages.load_laws()
    MANIFEST = lawpages.load_manifest()
    byl_map = {}
    for r in resources:
        if r.get("byl_no") and r.get("detail"):
            byl_map[(r["law"], r.get("byl_cls", "BF"), r["byl_no"], r.get("byl_br", "00"))] = r["detail"]

    def byl_href(law, cls, no, br, rel):
        d = byl_map.get((law, cls, str(no).zfill(4), str(br or 0).zfill(2)))
        return rel + d if d else None

    rev = lawpages.reverse_index(LAWS)
    for k in LAWS:
        body, n_art = lawpages.law_page(k, LAWS, rev, byl_href, law_url, MANIFEST, today)
        d = LAWS[k]
        write(f"laws/{k}/index.html", page(site, "../../", f"laws/{k}/", f'{d["law"]} 전문', body,
              desc=f'{d["law"]} 현행 전문 {n_art}개 조문 — 목차, 조문 검색, 인용 조문 바로가기, 하위 법령 역참조. {d["version"]}', active="laws/"))
    (out / "assets/data").mkdir(parents=True, exist_ok=True)
    (out / "assets/data/lawidx.js").write_text(lawpages.search_index(LAWS), encoding="utf-8")
    statutes = "".join(
        f'<li><a href="{e(law_url(s["name"], s.get("type","법령")))}" target="_blank" rel="noopener"><span class="badge {"badge-navy" if s.get("type")=="행정규칙" else "badge-line"}">{e(s.get("type"))}</span><strong>{e(s["name"])}</strong><span class="arr" aria-hidden="true">↗</span></a></li>'
        for s in laws.get("statutes", []) if s.get("type") != "법령" or s["name"] not in lawpages.BY_NAME)
    upd_filter = """<div class="listbar"><div class="search-inline">
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input type="search" class="filter-q" placeholder="법령명, 내용" aria-label="개정 소식 검색"></div></div>"""
    in_force = [u for u in updates if not u.get("effective") or u["effective"] <= today]
    def upd_brow(n, u):
        src = safe_url(u.get("source_url"))
        arts = " · ".join(e(x) for x in u.get("affected_articles", []) or [])
        tbl = lawpages.change_table(LAWS, u.get("law"), u.get("date", ""), u.get("effective", ""), u.get("affected_articles") or [], today)
        det = (f'<p>{e(u.get("summary"))}</p>' + (tbl or (f'<p><b>대상 조문</b> {arts}</p>' if arts else ""))
               + (f'<p><b>실무 영향</b> {e(u["practical_impact"])}</p>' if u.get("practical_impact") else "")
               + '<p class="brow-f">' + " · ".join(x for x in (
                   f'<a href="{e(src)}" target="_blank" rel="noopener">{e(u.get("source_name") or "원문")} ↗</a>' if src else "",
                   f'근거 {e(u["basis"])}' if u.get("basis") else "",
                   '<span class="brow-chk">확인 필요</span>' if u.get("verify") else "",
                   f'원문 확인 {fmt_date(u.get("checked"))}' if u.get("checked") else "") if x) + "</p>")
        meta = " · ".join(x for x in (e(u.get("kind") or ""), ("시행 " + lawpages.kdate(u["effective"])) if u.get("effective") else "", "공포일 순") if x and x != "공포일 순")
        d = u.get("date", "")
        return lawpages.brow(n, f'{e(u.get("law"))} <span class="brow-s">{e(u["title"])}</span>', meta, ("공포 " + lawpages.kdate(d)) if d else "", det,
                             attrs=f' data-item data-text="{e(u.get("title", "") + " " + u.get("summary", "") + " " + u.get("law", ""))}"')
    law_body = lawpages.hub_page(LAWS, "".join(upd_brow(len(in_force) - i, u) for i, u in enumerate(in_force)), len(in_force), statutes, upd_filter, MANIFEST, today)
    write("laws/index.html", page(site, "../", "laws/", "법령", law_body,
                                  desc="산업안전보건법·시행령·시행규칙·안전보건규칙·중대재해처벌법 현행 전문 검색, 주제별 조문, 개정 소식.", active="laws/"))

    # ---- 작성기 허브 (전용 작성기 + data/forms.json + 별표 3 점검표)
    lawref = load("data/lawref.json")
    catalog = load("data/catalog.json")
    # '제공 안 함'(skip) 항목은 화면에 싣지 않는다 — 데이터에는 이유와 함께 남겨 둔다(같은 기능 요청이 오면 참고)
    for _c in catalog["categories"]:
        _c["items"] = [x for x in _c["items"] if x.get("status") != "skip"]
    catalog["categories"] = [_c for _c in catalog["categories"] if _c["items"]]
    groups, forms = all_forms(lawref)
    form_src = (ROOT / "apps/form.body.html").read_text(encoding="utf-8")
    for f in forms:
        body = form_src.replace("/*@DATA@*/null", json.dumps(f, ensure_ascii=False).replace("</", "<\\/")) + dl_section("../../../", form=f["id"]) + lawver_html("forms", "../../../")
        write(f"tools/forms/{f['id']}/index.html", page(site, "../../../", f"tools/forms/{f['id']}/", f["title"], body, desc=f.get("desc"), active="tools/"))
    # ---- 작업계획서 선택 화면: 작업 종류를 고르면 해당 작업계획서 작성기로 간다
    _fb = {f["id"]: f for f in forms}
    _krule = {a["jo"]: a for a in load("data/lawtext/krule.json")["articles"]}
    def wp_card(f):
        lead = "제39조" in f.get("law", "")
        no = re.search(r"제38조제1항(제\d+호(?:·제\d+호)?)", f.get("law", ""))
        return (f'<a class="ftool" href="../{e(f["id"])}/">{"<span class=ftool-tag>작업지휘자 지정</span>" if lead else ""}<strong>{e(f["short"] if f.get("short") else f["title"])}</strong>'
                f'<span class="ftool-desc">{e(f["title"])} — {e(one_sentence(f.get("desc", "")))}</span>'
                f'<span class="ftool-law">제38조제1항{e(no.group(1)) if no else ""}</span><span class="ftool-go">바로 작성 →</span></a>')
    wp_secs = "".join(f'<section class="wrap ftools-page">{sec_head(g)}<div class="ftools">{"".join(wp_card(_fb[i]) for i in ids if i in _fb)}</div></section>' for g, ids in WORKPLAN_GROUPS)
    _a38 = _krule.get("제38조", {}).get("text", "")
    assert "작업계획서를 작성하고 그 계획에 따라 작업을 하도록 해야 한다" in _a38 and "작업계획서의 내용을 해당 근로자에게 알려야 한다" in _a38, "제38조 원문 확인"
    wp_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">무료 도구</a><span>/</span><a href="../">작성기</a><span>/</span>작업계획서</p>
  <h1>작업계획서 — 작업 종류를 고르세요</h1>
  <p>지게차·중량물·고소작업대처럼 안전보건규칙 제38조제1항에 해당하는 작업은 사전조사를 하고 그 결과를 기록·보존한 뒤, 별표 4의 사항을 포함한 작업계획서를 작성해 그 계획에 따라 작업하도록 해야 합니다. 작성한 내용은 해당 근로자에게 알려야 합니다(같은 조 제2항). 작업 종류를 고르면 별표 4 포함 사항이 들어간 작성기가 열리고, 작성기 안에서도 종류를 바꿀 수 있습니다.</p>
</div></section>
{wp_secs}
<section class="wrap"><div class="lawbox"><h3>함께 알아 둘 것</h3>
  <p><b>작업지휘자</b> — 제38조제1항제2호(차량계 하역운반기계등)·제6호·제8호·제10호·제11호(중량물 취급) 작업계획서를 작성한 경우 작업지휘자를 지정해 계획서에 따라 지휘하도록 해야 합니다(제39조제1항, 같은 항 단서의 예외 확인). 위 카드의 '작업지휘자 지정' 표시가 그 작업입니다.</p>
  <p><b>항타기·항발기</b> — 조립·해체·변경·이동 작업은 작업방법과 절차를 정해 근로자에게 주지시켜야 합니다(제38조제3항). 별도 작성기는 없으니 사업장 양식으로 남기세요.</p>
  <p><b>이 작성기의 지위</b> — 법령에 별지 서식이 정해져 있지 않아 별표 4 포함 사항을 담아 만든 실무용 보조양식입니다. 양식을 채운 것만으로 의무를 다했다고 볼 수는 없으며, 실제 사전조사와 계획에 따른 작업이 함께 이뤄져야 합니다.</p>
  <p class="src-line">원문: 산업안전보건기준에 관한 규칙 제38조·제39조, 별표 4 — <a href="{e(law_url("산업안전보건기준에 관한 규칙"))}" target="_blank" rel="noopener">국가법령정보센터 ↗</a></p>
</div></section>
{dl_section("../../../", form="workplan")}"""
    write("tools/forms/workplan/index.html", page(site, "../../../", "tools/forms/workplan/", "작업계획서 — 작업 종류 선택", wp_body,
                                                  desc="지게차·중량물·고소작업대·굴착기 등 안전보건규칙 제38조 작업계획서 14종을 작업 종류별로 골라 무료로 작성·인쇄. 별표 4 포함 사항 반영.", active="tools/"))
    # ---- 무료 양식 내려받기 모음
    _dls = downloads()
    tpl_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">서식·자료</a><span>/</span>무료 양식 내려받기</p>
  <h1>무료 양식 내려받기 (엑셀·PPT {len(_dls)}종)</h1>
  <p>현장에서 바로 고쳐 쓰도록 만든 엑셀·PowerPoint 양식입니다. 회원가입 없이 내려받고, 회사 이름·결재란·항목은 사업장에 맞게 고쳐 쓰세요. 화면에서 작성하고 인쇄하려면 각 양식과 짝을 이루는 <a href="../../tools/forms/">작성기</a>를 쓰면 됩니다.</p>
</div></section>
<section class="wrap" style="margin-top:8px">{DL_CSS}<div class="spdl" style="max-width:none;padding:0;margin:8px 0 0"><div class="spdl-g">{"".join(dl_card(x, "../../") for x in _dls)}</div></div>
<div class="lawbox" style="margin-top:24px"><h3>쓰기 전에</h3>
  <p>법령에 별지 서식이 정해져 있지 않은 실무 기록(작업계획서·TBM·순회점검·아차사고 등)을 위한 보조양식입니다. 양식을 채운 것만으로 법령상 의무를 다했다고 볼 수는 없으니, 서식 안에 적힌 근거 조문과 사업장 사정을 함께 확인하세요.</p>
  <p class="src-line">엑셀 파일은 Microsoft Excel·한컴오피스 한셀·Google 스프레드시트에서 열립니다. 자동 계산·목록 선택은 프로그램에 따라 다르게 보일 수 있습니다.</p>
</div></section>"""
    write("resources/templates/index.html", page(site, "../../", "resources/templates/", "무료 양식 내려받기 (엑셀·PPT)", tpl_body,
                                                 desc="위험성평가표·TBM 일지·작업계획서(지게차·중량물)·순회점검표·교육일지·아차사고·보호구 대장 엑셀과 산업안전보건위원회·개선 전후 보고 PPT 무료 양식.", active="resources/"))
    def wcard(kind, x):
        if kind == "tool":
            return (f'<a class="ftool" href="../{e(x["id"])}/"><strong>{e(x["name"].replace(" 작성기", ""))}</strong><span class="ftool-desc">{e(x.get("desc", ""))}</span>'
                    f'<span class="ftool-law">{e(x.get("law", ""))}</span><span class="ftool-go">바로 작성 →</span></a>')
        f = x
        tag = '<span class="ftool-tag">자동 채우기</span>' if f.get("auto", {}).get("pickers") else ('<span class="ftool-tag">자동 계산</span>' if f.get("auto", {}).get("calc") or f.get("auto", {}).get("next") else '')
        return (f'<a class="ftool" href="{e(f["id"])}/">{tag}<strong>{e(f["title"].replace("작업시작 전 점검표 — ", ""))}</strong><span class="ftool-desc">{e(f.get("desc",""))}</span>'
                f'<span class="ftool-law">{e(f.get("law",""))}</span><span class="ftool-go">바로 작성 →</span></a>')
    wg = writer_groups(site, groups, forms)
    fsecs = [f'<section class="wrap ftools-page" id="{WRITER_GID.get(g, "w" + str(i))}">{sec_head(g + " (" + str(len(items)) + ")", **({"href": "workplan/", "more": "작업 종류로 고르기"} if g == "작업계획서" else {}))}<div class="ftools">{"".join(wcard(k, x) for k, x in items)}</div></section>'
             for i, (g, items) in enumerate(wg)]
    wjump = "".join(f'<a href="#{WRITER_GID.get(g, "w" + str(i))}">{e(g)} <span>{len(items)}</span></a>' for i, (g, items) in enumerate(wg))
    forms_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">무료 도구</a><span>/</span>작성기</p>
  <h1>작성기 {WRITER_N}종</h1>
  <p>TBM 일지·위험성평가서부터 교육일지·점검표·작업계획서·중대재해처벌법 이행 서식까지, 화면에서 채우고 A4로 인쇄하거나 PDF로 저장합니다. 회원가입 없이 쓰고, 입력 내용은 이 브라우저에만 저장됩니다.</p>
  <form class="gq-search wsearch" role="search" onsubmit="return false"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="search" id="wQ" placeholder="작성기 찾기 (예: 지게차, 교육, 협의체, 밀폐공간)" aria-label="작성기 검색" autocomplete="off" enterkeyhint="search"><button type="button" class="gq-x" id="wX" aria-label="검색어 지우기" hidden>×</button></form>
  <nav class="wjump" aria-label="작성기 묶음">{wjump}</nav>
</div></section>
<p class="wrap empty" id="wE" hidden style="margin-top:24px">맞는 작성기가 없습니다. 다른 낱말로 찾아 보거나 <a href="../../board/?b=free">게시판</a>에 필요한 서식을 요청해 주세요.</p>
{"".join(fsecs)}
<script>(function(){{var q=document.getElementById("wQ"),x=document.getElementById("wX"),E=document.getElementById("wE"),cards=[].slice.call(document.querySelectorAll(".ftools-page .ftool")),secs=[].slice.call(document.querySelectorAll(".ftools-page"));
cards.forEach(function(c){{c._t=c.textContent.toLowerCase().replace(/\\s+/g," ");}});
function run(){{var t=q.value.toLowerCase().split(/\\s+/).filter(Boolean),n=0;x.hidden=!q.value;cards.forEach(function(c){{var ok=t.every(function(w){{return c._t.indexOf(w)>=0;}});c.hidden=!ok;if(ok)n++;}});secs.forEach(function(s){{s.hidden=!s.querySelector(".ftool:not([hidden])");}});E.hidden=n>0;}}
q.addEventListener("input",run);x.addEventListener("click",function(){{q.value="";q.focus();run();}});try{{var v=new URLSearchParams(location.search).get("q");if(v){{q.value=v;run();}}}}catch(e){{}}}})();</script>"""
    write("tools/forms/index.html", page(site, "../../", "tools/forms/", "작성기", forms_body,
                                         desc=f"교육일지, 협의체 회의록, 순회점검표, 작업계획서, 작업시작 전 점검표 등 안전보건 서식 {len(forms)}종을 무료로 작성·인쇄.", active="tools/"))

    # ---- 도구
    n_ok = sum(1 for c in catalog["categories"] for x in c["items"] if x["status"] in ("ok", "external"))
    n_all = sum(len(c["items"]) for c in catalog["categories"])
    kind_secs = ""
    for k, c, sub in TOOL_KINDS:
        extra = (tool_card("forms/", "작성기", f"작성기 전체 {WRITER_N}종", "업무일지·교육일지·회의록·점검표·작업계획서·작업시작 전 점검표·중처법 이행 서식까지 한곳에.",
                           "산안법·안전보건규칙·중처법 시행령 각 조문", "결재·사진", ico="../assets/img/ico/write.webp") if k == "작성기" else "")
        kind_secs += f'<section class="wrap ftools-page" id="{c}">{sec_head(k, sub=sub)}<div class="tgrid">{free_tool_cards(site, "../", kind=k, ids=(["tbm", "risk", "edu-log", "patrol", "permit"] if k == "작성기" else None))}{extra}</div></section>'
    tools_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>무료 도구</p>
  <h1>무료 안전관리 도구</h1>
  <p>회원가입도 서버도 없습니다. 입력한 내용은 내 브라우저 안에서만 처리됩니다. 법령 원문을 기준으로 만들었고 각 도구에 근거 조문과 확인일을 적어 두었습니다.</p>
  <p class="hint">작성기는 <a href="forms/">작성기 {WRITER_N}종</a> 한 곳에 모두 모았습니다. 아래에는 자주 쓰는 작성기와 계산기·조회 도구를 보여 줍니다.</p>
</div></section>
<section class="wrap ftools-page">
  <nav class="tkinds" aria-label="도구 종류">{"".join(f'<a class="tbadge-l {c}" href="#{c}">{e(k)} <span>{sum(1 for t in site.get("free_tools", []) if t.get("cat") == k) + (1 if k == "작성기" else 0) if k != "작성기" else WRITER_N}</span></a>' for k, c, _ in TOOL_KINDS)}</nav>
</section>
{kind_secs}
<section class="wrap ftools-page" id="catalog">
  {sec_head("법령 순서로 찾기", sub=f"산업안전보건법·중대재해처벌법 조문 순서대로 정리했습니다. 지금 바로 쓸 수 있는 것 {n_ok}개 / 전체 {n_all}개")}
  {catalog_html(catalog, "")}
</section>
<div class="wrap layout-detail">
  <section class="col-main">{(sec_head("기록까지 관리하려면") + tool_panel(site, "../", big=True)) if tool_panel(site, "../") else ""}</section>
  <aside class="col-side"><section class="side-box">
    <h2 class="h-sm">왜 서버가 없나요?</h2>
    <p>안전관리 기록에는 사고·건강 정보처럼 민감한 내용이 많습니다. 서버에 모으지 않으면 유출 위험과 운영비가 함께 사라집니다.</p>
    <p>대신 여러 PC 사이 자동 동기화는 되지 않습니다. 옮길 때는 백업 파일이나 구글 스프레드시트 연동을 씁니다.</p>
  </section></aside>
</div>"""
    write("tools/index.html", page(site, "../", "tools/", "도구", tools_body, active="tools/"))

    # ---- 무료 작성 도구 (각각 한 파일로 완결)
    for t in site.get("free_tools", []):
        # 본문 조각(*.body.html)은 반드시 공통 레이아웃(page)으로 감싸야 한다 — kind 누락 시 CSS·메뉴 없는 페이지가 배포됨
        if t["src"].endswith(".body.html") and t.get("kind") != "page":
            sys.exit(f"config/site.json 도구 {t['id']}: 본문 조각인데 kind가 'page'가 아닙니다")
        write(f"tools/{t['id']}/index.html", render_free_tool(t, hazards, site, penalties))

    # ---- 404 (어느 깊이의 주소에서 열려도 되도록 <base> 를 사이트 루트로 맞춘다)
    base = (site.get("base_url") or "").rstrip("/")
    base_js = ("<script>document.write('<base href=\"'+(/\\.github\\.io$/.test(location.hostname)?'/'+location.pathname.split('/')[1]+'/':'/')+'\">')</script>")
    nf = page(site, "", "404.html", "페이지를 찾을 수 없습니다",
        '<section class="phead"><div class="wrap"><img src="assets/img/ico/fix.webp" width="120" height="120" alt=""><h1>페이지를 찾을 수 없습니다</h1><p>주소가 바뀌었거나 없는 페이지입니다.</p><p class="btns" style="margin-top:14px"><a class="btn" href="./">홈으로</a><a class="btn btn-ghost" href="tools/">무료 도구</a><a class="btn btn-ghost" href="resources/">서식·자료</a><a class="btn btn-ghost" href="laws/">법령</a><a class="btn btn-ghost" href="board/">게시판</a></p></div></section>')
    (out / "404.html").write_text(nf.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + base_js, 1), encoding="utf-8")

    if base:
        # 로그인·글쓰기·운영 관리처럼 검색에 나올 필요가 없는 화면은 사이트맵에서 뺀다
        urls = [u for u in urls if not re.match(r"^board/(admin|account|write|view)/", u)]
        # lastmod 는 날짜를 아는 글(브리핑·소식)에만 넣는다. 빌드할 때마다 모든 주소를 오늘로 바꾸면 검색엔진이 lastmod 를 믿지 않게 된다
        _lm = {f"brief/n/{x['id']}/": x["date"] for x in BOARD if re.match(r"^\d{4}-\d{2}-\d{2}$", x.get("date", ""))}
        _lm.update({f"brief/{b['date']}/": b["date"] for b in briefs})
        _lm.update(POST_LM)
        sm = "".join(f"<url><loc>{e(base + '/' + u)}</loc>" + (f"<lastmod>{_lm[u]}</lastmod>" if u in _lm else "") + "</url>" for u in urls)
        (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>', encoding="utf-8")
    # ---- RSS (브리핑·소식). 네이버 서치어드바이저 등에 제출할 수 있다
    if base:
        from email.utils import format_datetime
        def _rfc(dstr):
            try:
                return format_datetime(dt.datetime.strptime(dstr, "%Y-%m-%d").replace(hour=9, tzinfo=dt.timezone(dt.timedelta(hours=9))))
            except Exception:
                return ""
        _items = "".join(
            f"<item><title>{e(x['title'])}</title><link>{e(base)}/brief/</link><guid isPermaLink=\"false\">{e(base)}/brief/#{e(x['date'])}-{i}</guid>"
            f"<pubDate>{_rfc(x['date'])}</pubDate><category>{e(x.get('cat', ''))}</category><description>{e(x.get('summary', ''))}</description></item>"
            for i, x in enumerate(BOARD[:50]))
        (out / "rss.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(site["name"])} 브리핑·소식</title><link>{e(base)}/brief/</link>'
            f'<description>산업안전보건 정책·점검·법령·지원사업 소식 요약</description><language>ko</language>{_items}</channel></rss>', encoding="utf-8")
    # ---- IndexNow 키 파일(빙·네이버 등에 변경 사실을 알릴 때 소유 확인용)
    _ink = str(site.get("indexnow_key") or "")
    if re.match(r"^[a-f0-9]{16,64}$", _ink):
        (out / f"{_ink}.txt").write_text(_ink, encoding="utf-8")
    # 구글 서치콘솔 'HTML 파일' 방식 소유 확인 파일 (google<16자리>.html)
    _gf = str((site.get("search_verification") or {}).get("google_file") or "").strip()
    if re.match(r"^google[a-f0-9]{16}$", _gf):
        (out / f"{_gf}.html").write_text(f"google-site-verification: {_gf}.html", encoding="utf-8")
    _daum = str((site.get("search_verification") or {}).get("daum") or "").strip()
    _daum_line = f"#DaumWebMasterTool:{_daum}\n" if re.match(r"^[A-Za-z0-9:_-]{8,200}$", _daum) else ""
    (out / "robots.txt").write_text(_daum_line + "User-agent: *\nAllow: /\nDisallow: /board/admin/\nDisallow: /board/account/\nDisallow: /board/write/\n" + (f"Sitemap: {base}/sitemap.xml\n" if base else ""), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"완료: 페이지 {len(urls)}개(무료 도구 {len(site.get('free_tools', []))}개 포함), 채용 {len(jobs)}건(진행 {len(open_jobs)}), 자료 {len(resources)}건, "
          f"개정소식 {len(updates)}건, 전체 {total/1024:.0f}KB → {out}")
    if WARNINGS:
        print(f"경고 {len(WARNINGS)}건 (위 참고)")


def make_local(out):
    """더블클릭(file://)으로 열어도 페이지 이동이 되도록 폴더 링크를 index.html 로 바꾼다.

    웹 서버는 'jobs/' 를 'jobs/index.html' 로 알아서 열어 주지만, 파일로 열면 폴더 목록이 뜨기 때문.
    배포용(_site)에는 쓰지 않는다 — 주소가 지저분해지고 검색엔진 주소도 달라진다.
    """
    pat = re.compile(r'((?:href|action)=")((?!https?:|mailto:|#|data:)[^"]*?)(/?)(\?[^"]*)?"')

    def fix(m):
        attr, path, slash, query = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        full = path + slash
        if full in ("./", ""):
            return f'{attr}index.html{query}"'
        if full.endswith("/"):
            return f'{attr}{full}index.html{query}"'
        return m.group(0)

    n = 0
    for f in out.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        t2 = pat.sub(fix, t)
        # 홈 검색창의 범위 전환 값(jobs/ ↔ resources/)도 파일 경로로
        t2 = t2.replace('value="resources/"', 'value="resources/index.html"').replace('value="jobs/"', 'value="jobs/index.html"')
        if t2 != t:
            f.write_text(t2, encoding="utf-8"); n += 1
    print(f"로컬 미리보기용 링크 변환: {n}개 파일")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--today", default=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat())
    ap.add_argument("--local", action="store_true", help="더블클릭으로 여는 미리보기용(폴더 링크 → index.html)")
    a = ap.parse_args()
    build(ROOT / a.out, a.today)
    if a.local:
        make_local(ROOT / a.out)
