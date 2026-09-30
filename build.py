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


def form_url(law, byl_no, byl_br="00", cls="BF"):
    # 법령명+서식번호로 연결하는 고정 주소. 서식이 개정돼도 항상 현행본을 연다. BF=서식(별지), BE=별표
    return (f"https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?bylCls={cls}"
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
             ("선임·관리체제", ["선임", "해임", "관리자", "관리 업무", "관리규정", "업무계약", "책임자", "위원회"]),
             ("점검·작업허가", ["점검", "작업허가"]),
             ("작업계획서", ["작업계획"]),
             ("유해위험방지계획서", ["유해위험방지계획서", "공사 개요서", "자체심사"]),
             ("도급·건설", ["도급", "공사", "건설", "설계변경", "기술지도", "관리비", "타워크레인", "대여"]),
             ("기계·설비 인증·검사", ["안전인증", "자율안전", "안전검사", "자율검사", "제조업체", "제조사업", "합격표시", "방호조치", "기계ㆍ기구"]),
             ("화학물질·석면", ["화학물질", "물질안전보건자료", "금지물질", "허가대상", "허가신청", "석면", "유해성", "위험물질"]),
             ("작업환경·건강", ["작업환경", "건강진단", "건강관리", "휴게", "유해인자", "노출", "사후관리"]),
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


def situation_cards(resources, rel):
    out = []
    for title, topic, sub in SITUATIONS:
        items = [r for r in resources if r.get("topic") == topic and r.get("category") in CAT_RANK]
        if not items:
            continue
        items.sort(key=lambda r: (0 if r.get("popular") else 1, CAT_RANK[r["category"]]))
        lis = "".join(
            f'<li><a href="{rel}{e(r["detail"]) if r.get("detail") else rel + "tools/" + e(r.get("free_tool","")) + "/"}">{e(r["title"])}</a></li>'
            for r in items[:4] if r.get("detail") or r.get("free_tool"))
        n = sum(1 for r in resources if r.get("topic") == topic)
        out.append(f'<section class="sit"><h3>{e(title)}</h3><p class="sit-sub">{e(sub)}</p><ul>{lis}</ul>'
                   f'<a class="sit-all" href="?topic={quote(topic)}" data-topic-go="{e(topic)}">{n}건 모두 보기 →</a></section>')
    return "".join(out)


# ---------------------------------------------------------------- 서식·별표 상세 페이지
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
        tool = f'<a class="btn btn-block btn-green" href="{rel_root}tools/{e(r["free_tool"])}/">안전duck 도구로 바로 계산·작성</a>'
    if r.get("page_link"):
        tool = f'<a class="btn btn-block btn-green" href="{rel_root}{e(r["page_link"])}">안전duck에서 바로 보기</a>'
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
        arts += (f'<p class="hint">{e(", ".join(missing))} 원문은 아직 안전duck에 수록하지 않았습니다. '
                 f'<a href="{e(law_url(r["law"]))}" target="_blank" rel="noopener">국가법령정보센터에서 {e(r["law"])} 보기 ↗</a></p>')
    elif not hits:
        full = r.get("law") in idx and len(idx[r["law"]]) > 50
        msg = (f'{r["law"]} 본문에는 이 {kind}를 직접 언급한 조문이 없습니다. 고용노동부 고시 등 다른 규정에서 쓰도록 정한 {kind}일 수 있습니다.'
               if full else "관련 조문 원문은 아직 안전duck에 수록하지 않았습니다.")
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
      <p class="hint">법령 서식은 저작권 보호 대상이 아닙니다(저작권법 제7조). 개정되면 원본 버튼이 최신본을 엽니다.</p>
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

NAV = [("tools/", "무료 도구"), ("jobs/", "채용정보"), ("resources/", "서식·자료"), ("news/", "안전뉴스"), ("laws/", "법령")]

LOGO_SVG = ('<svg class="logo-mark" viewBox="0 0 40 40" aria-hidden="true">'
            '<rect width="40" height="40" rx="11" fill="#1F6FD1"/>'
            '<circle cx="19" cy="24" r="10.5" fill="#FFD23F"/>'
            '<path d="M8.5 22.5a10.5 9.5 0 0 1 21 0z" fill="#F58A1F"/>'
            '<rect x="6.5" y="21" width="25" height="3" rx="1.5" fill="#D86F0C"/>'
            '<circle cx="23" cy="26.5" r="1.6" fill="#17365D"/>'
            '<path d="M28 28.5q5 .3 5.2 1.9-2 1.7-5.7 1.1z" fill="#F58A1F"/></svg>')

AVATAR_COLORS = ["#1F6FD1", "#17365D", "#0E8A6A", "#8A4FD6", "#C2571A", "#3B6E8F"]
HOME_FORMS = ["lf-f29-288431", "lf-f35-288431", "lf-f102-288431", "lf-f50-288431", "lf-f5-288431"]
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
    on_news = (site.get("features") or {}).get("public_api", False)
    nav = "".join(f'<a href="{rel_root}{href}"{cur if active == href else ""}>{e(label)}</a>' for href, label in NAV if on_news or href != "news/")
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
<script src="{rel_root}assets/docs.js"></script>
</head>
<body>
<a class="skip" href="#main">본문으로 바로가기</a>
<div class="nbar"><div class="wrap nbar-in"><span class="nbar-ico" aria-hidden="true">🛡️</span><span>모든 작업 내역은 안전하게 현재 기기에만 저장됩니다.</span><button type="button" class="nbar-btn" data-mydata>내 데이터 관리</button></div></div>
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
  <div class="wrap ft-data">
    <div><strong>내 데이터 관리</strong><p>작성한 서식·도구 입력값·서명·사진은 서버가 아니라 이 기기의 브라우저에만 있습니다. 브라우저 기록을 지우거나 기기를 바꾸기 전에 백업 파일로 내보내 두세요.</p></div>
    <button type="button" class="btn btn-sm btn-ghost" data-mydata>JSON 내보내기 / 불러오기</button>
  </div>
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
            acts.append(f'<a class="btn btn-sm btn-accent" href="{e(link)}" target="_blank" rel="noopener">덕희에서 작성</a>')
        elif r.get("category") == "SAFE 덕희 서식":
            acts.append('<span class="btn btn-sm btn-disabled" aria-disabled="true">도구 주소 준비 중</span>')
    meta = [x for x in [r.get("law"), r.get("form_no"), (r.get("rel") + " 관련") if r.get("rel") else ""] if x]
    tags = r.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split("|") if t]
    text = " ".join([r.get("title", ""), r.get("summary", ""), r.get("law", ""), r.get("form_no", ""), r.get("basis", ""), " ".join(tags)])
    cat = r.get("category", "")
    cat_cls = {"법정 서식": "badge-blue", "고시·지침": "badge-navy", "SAFE 덕희 서식": "badge-orange", "무료 작성 도구": "badge-green",
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


TOOL_KINDS = [("작성기", "k-write", "바로 작성해 A4로 인쇄·PDF 저장"), ("계산기", "k-calc", "법령 기준으로 대상·시간·금액 계산"),
              ("조회·일정", "k-find", "의무·주기·과태료를 찾아보고 일정 관리")]
ARROW = '<svg class="tcard-arr" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'


def tool_card(href, kind, name, desc, law="", sub=""):
    cls = next((c for k, c, _ in TOOL_KINDS if k == kind), "k-write")
    return (f'<a class="tcard {cls}" href="{href}"><span class="tcard-top"><span class="tbadge">{e(kind)}</span>'
            f'{f"<span class=tcard-sub>{e(sub)}</span>" if sub else ""}</span>'
            f'<strong class="tcard-t">{e(name)}</strong><span class="tcard-d">{e(desc)}</span>'
            f'<span class="tcard-f"><span class="tcard-law">{e(law) or "&nbsp;"}</span>{ARROW}</span></a>')


def free_tool_cards(site, rel_root, group=None, limit=None, ids=None, kind=None):
    tools = [t for t in site.get("free_tools", []) if (group is None or t.get("group") == group) and (kind is None or t.get("kind") == kind)]
    if ids:
        by = {t["id"]: t for t in tools}
        tools = [by[i] for i in ids if i in by]
    return "".join(tool_card(f'{rel_root}tools/{e(t["id"])}/', t.get("kind", "작성기"), t["name"], t.get("desc", ""), t.get("law", ""), t.get("tag", ""))
                   for t in tools[:limit])


def inject_data(src, names, where):
    """빌드 때 data/*.json 을 페이지 안에 넣는다. 첫 번째는 /*@DATA@*/, 나머지는 /*@이름@*/ 자리."""
    for i, name in enumerate(names):
        payload = json.dumps(load(f"data/{name}.json"), ensure_ascii=False).replace("</", "<\\/")
        mark = "/*@DATA@*/null" if i == 0 and "/*@DATA@*/null" in src else f"/*@{name.upper()}@*/null"
        assert mark in src, f"{where}: {mark} 자리가 없음"
        src = src.replace(mark, payload)
    return src


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
        return page(site, "../../", f"tools/{t['id']}/", t["name"], src, desc=t.get("desc"), active="tools/")
    if t.get("inject") == "hazards":
        payload = json.dumps(hazards, ensure_ascii=False).replace("</", "<\\/")
        assert "/*@HAZARDS@*/null" in src, t["src"]
        src = src.replace("/*@HAZARDS@*/null", payload)
    elif t.get("inject") == "tailwind":
        css = (ROOT / t["css"]).read_text(encoding="utf-8").replace("</style", "<\\/style")
        assert "/*@TAILWIND@*/" in src, t["src"]
        src = src.replace("/*@TAILWIND@*/", css)
    return src


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
    parts = []
    acts = []
    for c in cat["categories"]:
        if c["act"] not in acts:
            acts.append(c["act"])
    for act in acts:
        cats = [c for c in cat["categories"] if c["act"] == act]
        n_ok = sum(1 for c in cats for x in c["items"] if x["status"] in ("ok", "external"))
        n_all = sum(len(c["items"]) for c in cats)
        blocks = []
        for c in cats:
            rows = []
            for x in c["items"]:
                cls, lab = STATUS_LABEL[x["status"]]
                if x["status"] == "ok":
                    name = f'<a href="{rel}{e(x["link"])}">{e(x["name"])}</a>'
                elif x["status"] == "external":
                    name = f'<a href="{e(x["link"])}" target="_blank" rel="noopener">{e(x["name"])} ↗</a>'
                else:
                    name = f'<span>{e(x["name"])}</span>'
                note = f'<span class="cat-note">{e(x["note"])}</span>' if x.get("note") else ""
                rows.append(f'<li class="cat-i st-{x["status"]}"><span class="badge {cls}">{lab}</span><div>{name}<span class="cat-basis">{e(x["basis"])}</span>{note}</div></li>')
            ok = sum(1 for x in c["items"] if x["status"] in ("ok", "external"))
            blocks.append(f'<section class="cat-box"><h3>{e(c["cat"])} <span class="muted">{ok} / {len(c["items"])}</span></h3><ul class="cat-list">{"".join(rows)}</ul></section>')
        parts.append(f'<section class="cat-act"><h2 class="h-sm">{e(act)} <span class="muted">사용 가능 {n_ok} / 전체 {n_all}</span></h2><div class="cat-grid">{"".join(blocks)}</div></section>')
    return "".join(parts)


def empty_box(msg, extra=""):
    return f'<div class="empty"><p>{e(msg)}</p>{extra}</div>'


def duck_signs_html(site, write):
    """안전duck 자체 제작 현장 안내 게시물 — 목록(표지 페이지 상단) + 한 장씩 A4 인쇄 페이지."""
    d = load("data/duck_signs.json")
    cards = []
    for it in d["items"]:
        pid = f"resources/signs/duck-{it['id']}/"
        cards.append(f'<li class="dk-card"><a href="duck-{e(it["id"])}/"><img src="../../{e(it["thumb"])}" width="240" height="240" alt="{e(it["title"])} 안내 게시물 미리보기" loading="lazy">'
                     f'<strong>{e(it["title"])}</strong><span>{e(" · ".join(it.get("langs", [])))}</span></a></li>')
        body = f"""
<section class="phead no-print"><div class="wrap">
  <p class="crumbs"><a href="../../../">홈</a><span>/</span><a href="../../">서식·자료</a><span>/</span><a href="../#duck">안전보건표지</a><span>/</span>{e(it["title"])}</p>
  <h1>{e(it["title"])} <span class="muted" style="font-size:.6em">안전duck 안내 게시물</span></h1>
  <p>{e(it.get("desc", ""))}</p>
  <p class="btns" style="margin-top:14px"><button type="button" class="btn" onclick="window.print()">A4 인쇄 · PDF 저장</button>
  <a class="btn btn-ghost" href="../../../{e(it["print"])}" download="안전duck_{e(it["title"])}.png">원본 이미지 내려받기</a>
  {f'<a class="btn btn-ghost" href="../../../{e(it["law_href"])}">근거 조문 보기</a>' if it.get("law_href") else ""}</p>
  <p class="hint" style="margin-top:10px">근거: {e(it.get("basis", ""))} · 법정 안전보건표지(시행규칙 별표 6)가 아니라 현장 안내용 게시물입니다.</p>
</div></section>
<div class="dk-sheet"><img src="../../../{e(it["print"])}" alt="{e(it["title"])} 안내 게시물"></div>"""
        write(f"{pid}index.html", page(site, "../../../", pid, f'{it["title"]} 안내 게시물', body, desc=it.get("desc"), active="resources/"))
    return (f'<section class="dk-sec" id="duck"><div class="dk-head"><div><h2>안전duck 현장 안내 게시물</h2>'
            f'<p>현장에 바로 붙이는 다국어 안내 게시물입니다. 누르면 A4 한 장으로 인쇄할 수 있습니다. 법정 안전보건표지(아래 40종)를 대신하지는 않습니다.</p></div></div>'
            f'<ul class="dk-grid">{"".join(cards)}</ul></section>')


# ---------------------------------------------------------------- 페이지

def build(out, today):
    site = load("config/site.json")
    base_res = load("data/resources.json")
    _groups, _forms = all_forms(load("data/lawref.json"))
    web_forms = [{"id": "wf-" + f["id"], "category": "웹 작성 서식", "title": f["title"], "law": "", "form_no": f.get("group", ""),
                  "summary": f.get("desc", ""), "tags": [f.get("group", ""), f.get("short", "")], "topic": WF_TOPIC.get(f.get("group", ""), "기타"),
                  "free_tool": "forms/" + f["id"], "basis": f.get("law", "")} for f in _forms]
    resources = [resolve_resource(r) for r in base_res + web_forms + lawform_resources(base_res) if r.get("category") != "무료 작성 도구"]
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
    jobs = validate_jobs(load("data/jobs.json") + pubjobs["items"], today)
    auto_news, auto_acc = load_auto("news.json"), load_auto("accidents.json")
    hazards = load("data/hazards.json")
    hazards = {"groups": hazards["groups"], "items": hazards["items"]}
    penalties = load("data/penalties.json")

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
    shutil.copytree(ROOT / "assets", out / "assets")
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
    jobs_empty = (f'<div class="jempty"><div class="jempty-ico" aria-hidden="true">🕵️‍♂️</div>'
                  f'<p class="jempty-t">현재 안전duck에 직접 등록된 공고는 없어요.</p>'
                  f'<p class="jempty-d">하지만 아래 통합 채용 플랫폼에서 실시간 공고를 바로 확인할 수 있습니다!</p>'
                  f'<div class="jchips">{job_chips}</div></div>')
    updates = sorted(laws.get("updates", []), key=lambda u: u.get("date", ""), reverse=True)
    official_list = "".join(
        f'<li><a href="{e(safe_url(s["url"]))}" target="_blank" rel="noopener"><strong>{e(s["name"])}</strong><span>{e(s["desc"])}</span></a></li>'
        for s in sites.get("official", []) if safe_url(s.get("url")))

    n_forms = len(_forms)
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
    home_jobs = f'<ul class="jlist">{"".join(job_row(j, "./") for j in open_jobs[:6])}</ul>' if open_jobs else jobs_empty
    home = f"""
<section class="hero">
  <div class="wrap hero-in">
   <div class="hero-txt">
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
   <a class="hero-duck" href="resources/signs/#duck" aria-label="안전duck 현장 안내 게시물 보기"><img src="assets/img/duck-hero.webp" width="420" height="481" alt="안전모를 쓰고 구급상자를 든 안전duck 캐릭터" fetchpriority="high"></a>
  </div>
</section>
<section class="wrap ftools-home">
  {sec_head("무료 안전관리 도구", "tools/", more="모두 보기", sub="회원가입 없이 바로 쓰는 서류 작성기와 계산기. 입력 내용은 서버로 가지 않습니다.")}
  <div class="tgrid">{free_tool_cards(site, "./", ids=site.get("home_tools"))}{tool_card("tools/forms/", "작성기", f"서식 작성기 {n_forms}종", "교육일지·협의체 회의록·순회점검표·작업계획서·작업시작 전 점검표·중처법 이행 서식. 결재·서명·사진 첨부까지.", "산안법·안전보건규칙·중처법 시행령 각 조문", "결재·사진")}</div>
</section>
<div class="wrap layout-home">
  <section class="col-main">
    {sec_head("최신 채용정보", "jobs/", sub=(f"진행 중 {len(open_jobs)}건" if open_jobs else None))}
    {home_jobs}
    {sec_head("자주 찾는 서식·자료", "resources/")}
    <ul class="rlist">{"".join(resource_row(r, site, "./") for r in popular)}</ul>
    {tools_cta.format(rel="./")}
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
        main = jobs_empty
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
    {f'<div class="more-box"><p>다른 채용 사이트에서 더 찾기</p><div class="jchips">{job_chips}</div></div>' if jobs else ''}
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
    <p class="src-note">출처: {e(j.get('source_name') or '공고 원문')}{' — 재정경제부 공공기관 채용정보 API(공공데이터포털, 이용허락범위 제한 없음)로 자동 수집' if j.get('origin') == 'alio' else ''} · 조건과 일정은 원문이 우선합니다.</p>
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
    CAT_ORDER = ["법정 서식", "웹 작성 서식", "무료 작성 도구", "법정 기준표(별표)", "고시·지침", "공단 자료", "SAFE 덕희 서식", "기관·행정용"]
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
  <p>법정 서식·별표 {n_law}건은 국가법령정보센터 현행 원본으로 열리고(개정되면 같은 버튼이 최신본을 엽니다), 웹 작성 서식 {n_web}건은 여기서 바로 작성·인쇄합니다.</p>
</div></section>
<section class="wrap" style="padding-top:16px">{tools_cta.format(rel="../")}</section>
<section class="wrap ftools-page" style="padding-top:8px">
  <div class="ftools">
    <a class="ftool" href="../tools/forms/"><span class="ftool-tag">바로 작성</span><strong>웹 서식 작성기 {n_web}종</strong><span class="ftool-desc">교육일지·점검표 19종·작업계획서·허가서를 웹에서 작성하고 A4로 인쇄. 회원가입 없음.</span><span class="ftool-go">서식 작성 →</span></a>
    <a class="ftool" href="signs/"><span class="ftool-tag">20개 언어</span><strong>안전보건표지 40종</strong><span class="ftool-desc">금지·경고·지시·안내 표지를 찾아 A4 한 장으로 바로 인쇄. 외국어 파일까지.</span><span class="ftool-go">표지 보기 →</span></a>
    <a class="ftool" href="library/"><span class="ftool-tag">공공누리 {n_kosha:,}건</span><strong>안전보건 자료실</strong><span class="ftool-desc">공단 OPS·포스터·책자·교안·동영상을 주제·형태·외국어로 찾고 원본으로 바로 이동. 이달의 계절 자료까지.</span><span class="ftool-go">자료 찾기 →</span></a>
  </div>
</section>
<section class="wrap" style="padding-top:28px">
  {sec_head("상황별로 찾기", sub="지금 하려는 일을 고르면 필요한 법정 서식·기준표·작성 도구를 모아 보여줍니다.")}
  <div class="sit-grid">{situation_cards(resources, "../")}</div>
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
    {empty_box("검색 결과가 없습니다.").replace('class="empty"', 'class="empty" data-empty hidden')}
    <p class="src-line">법정 서식·별표 목록 확인일 {e(load("data/lawforms.json")["checked"])} · 국가법령정보센터 법령 본문의 별표·서식 목록 기준. 법령 원문은 저작권 보호 대상이 아닙니다(저작권법 제7조).</p>
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
    <section class="side-box">{sec_head("사고사망 속보")}{acc_list}</section>
    <section class="side-box"><p class="hint">안전duck은 기사 본문을 옮기지 않습니다. 제목·부제·부처·날짜만 싣고 원문으로 연결합니다. 민간 언론사 기사와 다른 사이트의 게시물은 싣지 않습니다.</p></section>
  </aside>
</div>"""
    if (site.get("features") or {}).get("public_api", False):
      write("news/index.html", page(site, "../", "news/", "안전뉴스", news_body,
                                  desc="산업안전 관련 정부 정책뉴스와 안전보건공단 사고사망 속보 — 공식 공공데이터 API로 수집.", active="news/"))

    # ---- 법령: 홈(검색·주제별·개정 소식) + 법령별 전문 페이지
    import lawpages
    LAWS = lawpages.load_laws()
    byl_map = {}
    for r in resources:
        if r.get("byl_no") and r.get("detail"):
            byl_map[(r["law"], r.get("byl_cls", "BF"), r["byl_no"], r.get("byl_br", "00"))] = r["detail"]

    def byl_href(law, cls, no, br, rel):
        d = byl_map.get((law, cls, str(no).zfill(4), str(br or 0).zfill(2)))
        return rel + d if d else None

    rev = lawpages.reverse_index(LAWS)
    for k in LAWS:
        body, n_art = lawpages.law_page(k, LAWS, rev, byl_href, law_url)
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
    law_body = lawpages.hub_page(LAWS, "".join(update_row(u) for u in updates), len(updates), statutes, upd_filter)
    write("laws/index.html", page(site, "../", "laws/", "법령", law_body,
                                  desc="산업안전보건법·시행령·시행규칙·안전보건규칙·중대재해처벌법 현행 전문 검색, 주제별 조문, 개정 소식.", active="laws/"))

    # ---- 서식 작성기 (data/forms.json + 별표 3 점검표)
    lawref = load("data/lawref.json")
    catalog = load("data/catalog.json")
    groups, forms = all_forms(lawref)
    form_src = (ROOT / "apps/form.body.html").read_text(encoding="utf-8")
    for f in forms:
        body = form_src.replace("/*@DATA@*/null", json.dumps(f, ensure_ascii=False).replace("</", "<\\/"))
        write(f"tools/forms/{f['id']}/index.html", page(site, "../../../", f"tools/forms/{f['id']}/", f["title"], body, desc=f.get("desc"), active="tools/"))
    gid = {"작업시작 전 점검(별표 3)": "pre"}
    fsecs = []
    for g in groups:
        fs = [f for f in forms if f["group"] == g]
        if not fs:
            continue
        cards = "".join(f'''<a class="ftool" href="{e(f["id"])}/">{'<span class="ftool-tag">자동 채우기</span>' if f.get("auto", {}).get("pickers") else ('<span class="ftool-tag">자동 계산</span>' if f.get("auto", {}).get("calc") or f.get("auto", {}).get("next") else '')}<strong>{e(f["title"].replace("작업시작 전 점검표 — ", ""))}</strong><span class="ftool-desc">{e(f.get("desc",""))}</span><span class="ftool-law">{e(f.get("law",""))}</span><span class="ftool-go">바로 작성 →</span></a>''' for f in fs)
        fsecs.append(f'<section class="wrap ftools-page" id="{gid.get(g, "g" + str(groups.index(g)))}">{sec_head(g + " (" + str(len(fs)) + ")")}<div class="ftools">{cards}</div></section>')
    forms_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">무료 도구</a><span>/</span>서식 작성기</p>
  <h1>서식 작성기</h1>
  <p>법령이 요구하는 기재 사항을 빠짐없이 담은 A4 서식 {len(forms)}종입니다. 화면에서 바로 채우고 인쇄하거나 PDF로 저장하세요. 결재란·점검 항목·표 문구까지 모두 고칠 수 있고, 입력 내용은 이 브라우저에만 저장됩니다.</p>
</div></section>
{"".join(fsecs)}"""
    write("tools/forms/index.html", page(site, "../../", "tools/forms/", "서식 작성기", forms_body,
                                         desc=f"교육일지, 협의체 회의록, 순회점검표, 작업계획서, 작업시작 전 점검표 등 안전보건 서식 {len(forms)}종을 무료로 작성·인쇄.", active="tools/"))

    # ---- 도구
    n_ok = sum(1 for c in catalog["categories"] for x in c["items"] if x["status"] in ("ok", "external"))
    n_all = sum(len(c["items"]) for c in catalog["categories"])
    kind_secs = ""
    for k, c, sub in TOOL_KINDS:
        extra = (tool_card("forms/", "작성기", f"서식 작성기 {len(forms)}종", "교육일지·협의체 회의록·순회점검표·작업계획서·작업시작 전 점검표·중처법 이행 서식까지. 결재·서명·사진 첨부.",
                           "산안법·안전보건규칙·중처법 시행령 각 조문", "결재·사진") if k == "작성기" else "")
        kind_secs += f'<section class="wrap ftools-page" id="{c}">{sec_head(k, sub=sub)}<div class="tgrid">{free_tool_cards(site, "../", kind=k)}{extra}</div></section>'
    tools_body = f"""
<section class="phead"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>무료 도구</p>
  <h1>무료 안전관리 도구</h1>
  <p>회원가입도 서버도 없습니다. 입력한 내용은 내 브라우저 안에서만 처리됩니다. 법령 원문을 기준으로 만들었고 각 도구에 근거 조문과 확인일을 적어 두었습니다.</p>
</div></section>
<section class="wrap ftools-page">
  <nav class="tkinds" aria-label="도구 종류">{"".join(f'<a class="tbadge-l {c}" href="#{c}">{e(k)} <span>{sum(1 for t in site.get("free_tools", []) if t.get("kind") == k) + (1 if k == "작성기" else 0)}</span></a>' for k, c, _ in TOOL_KINDS)}</nav>
</section>
{kind_secs}
<section class="wrap ftools-page" id="catalog">
  {sec_head("법령 순서로 찾기", sub=f"산업안전보건법·중대재해처벌법 조문 순서대로 정리했습니다. 지금 바로 쓸 수 있는 것 {n_ok}개 / 전체 {n_all}개")}
  {catalog_html(catalog, "")}
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
        write(f"tools/{t['id']}/index.html", render_free_tool(t, hazards, site, penalties))

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
