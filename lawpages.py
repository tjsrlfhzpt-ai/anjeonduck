"""법령 전문 페이지(laws/<key>/)와 법령 홈(laws/) 생성.

data/lawtext/*.json (scripts/parse_lawtext.py 로 국가법령정보센터 본문에서 만든 것)을 읽어
- 편·장·절 목차, 조문 앵커(#j38, #j619-2), 이 법령 안 검색
- 조문 속 인용(「산업안전보건법」 제17조, 법 제29조, 영 제16조, 제38조)을 해당 조문으로 연결
- 하위 법령이 이 조문을 인용한 곳(시행령·시행규칙) 역참조
- 별표·별지 서식 언급을 SafePlum 서식 상세 페이지로 연결
을 만든다. 조문 원문은 저작권 보호 대상이 아니다(저작권법 제7조).
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
ORDER = ["act", "yeong", "rule", "krule", "sapa", "sapa_dec"]
FAMILY = {"act": "sanan", "yeong": "sanan", "rule": "sanan", "krule": "sanan", "sapa": "sapa", "sapa_dec": "sapa"}
PARENT = {"yeong": "act", "rule": "act", "krule": "act", "sapa_dec": "sapa"}
LEVEL_LABEL = {"act": "법률", "yeong": "대통령령", "rule": "고용노동부령", "krule": "고용노동부령", "sapa": "법률", "sapa_dec": "대통령령"}
BY_NAME = {"산업안전보건법": "act", "산업안전보건법 시행령": "yeong", "산업안전보건법 시행규칙": "rule",
           "산업안전보건기준에 관한 규칙": "krule", "중대재해 처벌 등에 관한 법률": "sapa",
           "중대재해 처벌 등에 관한 법률 시행령": "sapa_dec"}

# 주제별로 자주 찾는 조문 (제목은 빌드 때 본문에서 가져오므로 번호만 적는다)
TOPICS = [
    ("안전관리 조직·선임", "책임자·관리감독자·안전/보건관리자 선임과 업무",
     [("act", "제15조"), ("act", "제16조"), ("act", "제17조"), ("act", "제18조"), ("yeong", "제16조"), ("yeong", "제18조"), ("rule", "제11조")]),
    ("산업안전보건위원회", "구성 대상·위원·회의·공지",
     [("act", "제24조"), ("yeong", "제34조"), ("yeong", "제35조"), ("yeong", "제37조"), ("yeong", "제39조")]),
    ("안전보건교육", "근로자 교육, 건설업 기초교육, 직무교육",
     [("act", "제29조"), ("act", "제31조"), ("act", "제32조"), ("rule", "제26조"), ("rule", "제27조"), ("rule", "제29조")]),
    ("위험성평가", "실시 의무, 방법·절차·시기, 근로자 참여·기록",
     [("act", "제36조"), ("rule", "제37조"), ("rule", "제37조의2"), ("rule", "제37조의3"), ("rule", "제37조의4")]),
    ("작업중지·중대재해", "작업중지, 중대재해 보고, 산업재해 기록·보고",
     [("act", "제51조"), ("act", "제52조"), ("act", "제54조"), ("act", "제57조"), ("rule", "제3조"), ("rule", "제67조"), ("rule", "제73조")]),
    ("도급·협의체", "도급인의 안전조치, 협의체, 합동점검",
     [("act", "제58조"), ("act", "제62조"), ("act", "제63조"), ("act", "제64조"), ("rule", "제79조"), ("rule", "제80조"), ("rule", "제82조")]),
    ("건설공사", "발주자 의무, 공기 연장, 설계변경, 산업안전보건관리비",
     [("act", "제67조"), ("act", "제70조"), ("act", "제71조"), ("act", "제72조"), ("act", "제73조"), ("rule", "제89조")]),
    ("기계·설비", "방호조치, 안전인증·자율안전확인·안전검사",
     [("act", "제80조"), ("act", "제84조"), ("act", "제89조"), ("act", "제93조"), ("yeong", "제74조"), ("yeong", "제78조")]),
    ("화학물질·MSDS", "물질안전보건자료 작성·제공·게시·경고표시",
     [("act", "제110조"), ("act", "제111조"), ("act", "제114조"), ("act", "제115조")]),
    ("작업환경·건강진단", "작업환경측정, 일반·특수건강진단, 근로시간 제한",
     [("act", "제125조"), ("act", "제129조"), ("act", "제130조"), ("act", "제132조"), ("act", "제139조")]),
    ("추락·밀폐·온열 (안전보건규칙)", "현장 기준 조문",
     [("krule", "제13조"), ("krule", "제38조"), ("krule", "제42조"), ("krule", "제43조"), ("krule", "제619조"), ("krule", "제619조의2"), ("krule", "제559조"), ("krule", "제566조")]),
    ("중대재해처벌법 의무", "경영책임자 의무, 안전보건관리체계, 서면 보관",
     [("sapa", "제4조"), ("sapa", "제5조"), ("sapa", "제6조"), ("sapa_dec", "제4조"), ("sapa_dec", "제5조"), ("sapa_dec", "제13조")]),
    ("벌칙·과태료", "산업안전보건법 벌칙과 과태료",
     [("act", "제167조"), ("act", "제168조"), ("act", "제169조"), ("act", "제173조"), ("act", "제175조"), ("sapa", "제7조")]),
]


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def anchor(jo):
    m = re.match(r"제(\d+)조(?:의(\d+))?", jo)
    return "j" + m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")


def jo_key(jo):
    return [int(x) for x in re.findall(r"\d+", jo)]


def load_laws():
    laws = {}
    for k in ORDER:
        p = ROOT / "data" / "lawtext" / f"{k}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if "toc" in d:
                laws[k] = d
    return laws


def load_manifest():
    return json.loads((ROOT / "data" / "law_manifest.json").read_text(encoding="utf-8"))


def kdate(iso):
    y, m, d = iso.split("-")
    return f"{y}. {int(m)}. {int(d)}."


# ------------------------------------------------------------------ 인용 연결
REF_RE = re.compile(r"(「([^」]{2,40})」\s*|(?<![가-힣])(법|영|규칙)\s+|같은\s*(?:법|영|규칙)\s*(?:시행령|시행규칙)?\s*)?제(\d+)조(?:의(\d+))?")
GAP_OK = re.compile(r"^(?:\s|제\d+항|제\d+호|[가-하]목|각\s*호|각\s*목|부터|까지|,|및|ㆍ|·|또는|와|과|이나|나|의|본문|단서|후단|전단|\(|\))*$")
BYL_RE = re.compile(r"(별표\s*(\d+)(?:의(\d+))?)|(별지\s*제\s*(\d+)호(?:의(\d+))?\s*서식)")


def resolve_refs(text, cur):
    """text 안의 조문 인용 → [(start, end, key or None, jo)]"""
    out, prev_key, prev_end = [], cur, None
    for m in REF_RE.finditer(text):
        jo = f"제{m.group(4)}조" + (f"의{m.group(5)}" if m.group(5) else "")
        if m.group(2):
            key = BY_NAME.get(m.group(2).strip())
        elif m.group(3):
            key = {"법": PARENT.get(cur), "영": "yeong" if cur in ("rule", "krule") else None, "규칙": None}[m.group(3)]
        elif m.group(1):  # 같은 법 …
            key = None
        else:
            gap = text[prev_end:m.start()] if prev_end is not None else None
            key = prev_key if (gap is not None and GAP_OK.match(gap)) else cur
            # 「다른 법」 바로 뒤 조문(그 법 조문)인데 위에서 못 잡은 경우 대비: 앞 12자에 」가 있으면 그 법
            if gap is None or not GAP_OK.match(gap):
                if "」" in text[max(0, m.start() - 3):m.start()]:
                    key = None
        out.append((m.start(), m.end(), key, jo))
        prev_key, prev_end = key, m.end()
    return out


def linkify(text, cur, href_of, byl_href):
    """조문 문장(평문) → 링크가 들어간 HTML."""
    spans = []
    for s, t, key, jo in resolve_refs(text, cur):
        h = href_of(key, jo) if key else None
        if h:
            spans.append((s, t, f'<a class="xref" href="{e(h)}">', "</a>"))
    for m in BYL_RE.finditer(text):
        if "」" in text[max(0, m.start() - 14):m.start()]:
            continue
        if m.group(1):
            h = byl_href(cur, "BE", m.group(2), m.group(3))
        else:
            h = byl_href(cur, "BF", m.group(5), m.group(6))
        if h:
            spans.append((m.start(), m.end(), f'<a class="xref xbyl" href="{e(h)}">', "</a>"))
    spans.sort()
    res, pos = [], 0
    for s, t, a, b in spans:
        if s < pos:
            continue
        res.append(e(text[pos:s]) + a + e(text[s:t]) + b)
        pos = t
    res.append(e(text[pos:]))
    out = "".join(res)
    # 개정 이력 표시는 흐리게
    return re.sub(r"(&lt;(?:개정|신설|전문개정|제목개정|본조신설|타법개정)[^&]*?&gt;|\[(?:본조신설|전문개정|제목개정|종전|시행일|본조제목개정|제\d+조에서 이동)[^\]]*\])",
                  r'<span class="amd">\1</span>', out)


PARA_CLS = [(re.compile(r"^[①-⑳㉑-㉟]"), "hang"), (re.compile(r"^\d+(?:의\d+)?\.\s"), "ho"), (re.compile(r"^[가-하]\.\s"), "mok"),
            (re.compile(r"^\d+\)\s"), "sub"), (re.compile(r"^[가-하]\)\s"), "sub2")]


def para_html(line, cur, href_of, byl_href):
    cls = next((c for r, c in PARA_CLS if r.match(line)), "")
    attr = f' class="{cls}"' if cls else ""
    return f"<p{attr}>{linkify(line, cur, href_of, byl_href)}</p>"


# ------------------------------------------------------------------ 역참조(하위 법령이 인용한 곳)
def reverse_index(laws):
    rev = {}
    for k, d in laws.items():
        for a in d["articles"]:
            for _, _, key, jo in resolve_refs(a["text"], k):
                if key and key != k:
                    rev.setdefault((key, jo), [])
                    if (k, a["jo"]) not in rev[(key, jo)]:
                        rev[(key, jo)].append((k, a["jo"]))
    return rev


# ------------------------------------------------------------------ 페이지
def law_page(k, laws, rev, byl_href, law_url, manifest=None, today=""):
    d = laws[k]
    mf = next((x for x in (manifest or {}).get("laws", []) if x["key"] == k), None)
    idx = {kk: {a["jo"]: a for a in dd["articles"]} for kk, dd in laws.items()}

    def href_of(key, jo):
        if key not in laws or jo not in idx[key]:
            return None
        return ("" if key == k else f"../{key}/") + "#" + anchor(jo)

    def byl(cur, cls, no, br):
        return byl_href(laws[cur]["law"], cls, no, br, "../../")

    # 목차
    toc_items = []
    for t in d["toc"]:
        if not t["first"]:
            continue
        toc_items.append(f'<li class="lv{t["lv"]}"><a href="#{anchor(t["first"])}">{e(t["no"])} {e(t["title"])}</a></li>')
    # 본문
    body, last_path = [], []
    for a in d["articles"]:
        if a["path"] != last_path:
            for i, p in enumerate(a["path"]):
                if i >= len(last_path) or last_path[i] != p:
                    lv = next((t["lv"] for t in d["toc"] if f'{t["no"]} {t["title"]}' == p), i)
                    body.append(f'<h2 class="lhead lh{lv}">{e(p)}</h2>')
            last_path = a["path"]
        aid = anchor(a["jo"])
        if a.get("deleted"):
            body.append(f'<article class="lart del" id="{aid}" data-jo="{e(a["jo"])}"><h3><a class="lart-no" href="#{aid}">{e(a["jo"])}</a> <span class="muted">{e(a["text"])}</span></h3></article>')
            continue
        paras = "".join(para_html(ln, k, href_of, byl) for ln in a["text"].split("\n") if ln.strip())
        pd = a.get("pending")
        pend_html, pend_attr, st_badge = "", "", ""
        if pd:
            pparas = "".join(para_html(ln, k, href_of, byl) for ln in pd["text"].split("\n") if ln.strip())
            pend_attr = f' data-eff="{e(pd["effective"])}"' + (' data-new="1"' if a.get("not_in_force") else "")
            st_badge = f'<span class="lst lst-next" data-st>시행 예정 · {e(kdate(pd["effective"]))}</span>'
            ttl = f' <b>{e(pd["title"])}</b>' if pd.get("title") and pd["title"] != a["title"] else ""
            pend_html = (f'<div class="lpend" data-pend><p class="lpend-h"><span class="lst lst-next">시행 예정</span> {e(kdate(pd["effective"]))} 부터 적용되는 조문{ttl}</p>'
                         f'<div class="lart-b">{pparas}</div></div>')
            if a.get("not_in_force"):
                paras = f'<p class="lnotyet" data-notyet>이 조문은 {e(kdate(pd["effective"]))} 부터 시행합니다. 그 전에는 적용되지 않습니다.</p>'
        down = rev.get((k, a["jo"]), [])
        down_html = ""
        if down:
            grp = {}
            for kk, jj in sorted(down, key=lambda x: (ORDER.index(x[0]), jo_key(x[1]))):
                grp.setdefault(kk, []).append(jj)
            chips = " ".join(f'<span class="lrev-g"><b>{e(laws[kk]["short"])}</b> ' + ", ".join(f'<a href="../{kk}/#{anchor(j)}">{e(j)}</a>' for j in js) + "</span>" for kk, js in grp.items())
            down_html = f'<div class="lrev"><span class="lrev-l">이 조문을 인용한 하위 법령</span>{chips}</div>'
        src = law_url(d["law"]) + "/" + quote(a["jo"])
        body.append(
            f'<article class="lart{" lart-pend" if pd else ""}" id="{aid}" data-jo="{e(a["jo"])}"{pend_attr}>'
            f'<h3><a class="lart-no" href="#{aid}">{e(a["jo"])}</a> <span class="lart-t">{e(a["title"])}</span> {st_badge}</h3>'
            f'<div class="lart-b" data-cur>{paras}</div>{pend_html}{down_html}'
            f'<p class="lart-f"><button type="button" class="lnk" data-copy="#{aid}">링크 복사</button>'
            f'<a class="lnk" href="{e(src)}" target="_blank" rel="noopener">국가법령정보센터 ↗</a></p></article>')
    live = [a for a in d["articles"] if not a.get("deleted")]
    cur_attr = ' aria-current="page"'
    sibs = "".join(f'<a class="lsib{" on" if kk == k else ""}" href="../{kk}/"{cur_attr if kk == k else ""}>{e(laws[kk]["short"])}</a>'
                   for kk in ORDER if kk in laws and FAMILY[kk] == FAMILY[k])
    byl_list = ""
    if d.get("byl"):
        lis = []
        for b in d["byl"]:
            h = byl_href(d["law"], "BE", b["no"], b["br"], "../../")
            lab = f'별표 {b["no"]}' + (f'의{b["br"]}' if b["br"] else "")
            a_open = f'<a href="{e(h)}">' if h else ""
            lis.append(f'<li>{a_open}<b>{e(lab)}</b> {e(b["title"])}{"</a>" if h else ""}</li>')
        byl_list = f'<details class="lbyl"><summary>별표 {len(d["byl"])}개</summary><ul>{"".join(lis)}</ul></details>'
    n_pend = sum(1 for a in d["articles"] if a.get("pending"))
    ver_rows = ""
    if mf:
        c = mf["current"]
        ver_rows += (f'<tr class="cur"><td><span class="lst lst-cur">현재 시행</span></td><td>{e(kdate(c["effective"]))}</td><td>{e(c["no"])} · {e(kdate(c["promulgated"]))} {e(c["kind"])}</td>'
                     f'<td>이 페이지 본문</td><td><a href="{e(c["source_url"])}" target="_blank" rel="noopener">원문 ↗</a></td></tr>')
        for u in sorted(mf.get("upcoming", []), key=lambda x: x["effective"]):
            where = "본문에 '시행 예정'으로 함께 표시" if u.get("text") == "inline" else "본문 미수록 — 원문에서 확인"
            ver_rows += (f'<tr data-up="{e(u["effective"])}"><td><span class="lst lst-next">시행 예정</span></td><td>{e(kdate(u["effective"]))}</td><td>{e(u["no"])} · {e(kdate(u["promulgated"]))} {e(u["kind"])}<br><span class="muted">{e(u.get("summary", ""))}</span></td>'
                         f'<td>{e(where)}</td><td><a href="{e(u["source_url"])}" target="_blank" rel="noopener">원문 ↗</a></td></tr>')
    add_html = ""
    if d.get("addenda"):
        blocks = "".join(f'<details class="ladd"><summary>부칙 &lt;{e(x["no"])}, {e(kdate(x["date"]))}&gt;</summary><div class="lart-b">' + "".join(f"<p>{e(ln)}</p>" for ln in x["text"].split("\n")) + "</div></details>"
                         for x in reversed(d["addenda"]))
        add_html = f'<section class="ladds" id="addenda"><h2 class="lhead lh1">최근 부칙 (시행일·적용례)</h2><p class="hint">2025년 이후 공포분만 실었습니다. 조문별 시행일이 다를 때는 부칙이 기준입니다.</p>{blocks}</section>'
    ver_box = (f'<section class="lver" id="versions"><div class="lver-h"><h2 class="h-sm">법령 버전 · 기준일</h2>'
               f'<label class="lasof">기준일 <input type="date" id="lAsof" value="{e(today)}" min="{e(mf["current"]["effective"])}"></label></div>'
               f'<div class="table-wrap"><table class="lvt"><thead><tr><th>상태</th><th>시행일</th><th>공포</th><th>SafePlum 수록</th><th>출처</th></tr></thead><tbody>{ver_rows}</tbody></table></div>'
               f'<p class="hint" id="lAsofMsg">기준일을 바꾸면 그날 적용되는 조문으로 본문이 바뀝니다. 이전 연혁은 <a href="{e(mf.get("history_url") or d["url"])}" target="_blank" rel="noopener">국가법령정보센터 연혁 ↗</a>에서 확인하세요. 마지막 공식 확인일 {e(mf["checked_at"])}.</p></section>') if mf else ""
    body_html = f"""
<section class="phead lphead"><div class="wrap">
  <p class="crumbs"><a href="../../">홈</a><span>/</span><a href="../">법령</a><span>/</span>{e(d["short"])}</p>
  <nav class="lsibs" aria-label="같은 법령 체계">{sibs}</nav>
  <h1>{e(d["law"])}</h1>
  <p class="lmeta"><span class="badge badge-line">{e(LEVEL_LABEL[k])}</span> {e(d["version"])} · 시행 {e(d["effective"])}. · 조문 {len(live)}개{f" · 시행 예정 조문 {n_pend}개" if n_pend else ""} · 원문 확인 {e((mf or {}).get("checked_at") or d["checked"])}</p>
</div></section>
<div class="wrap lwrap">
  <aside class="ltoc">
    <details class="ltoc-box" open data-ltoc><summary>목차</summary>
      <ol>{"".join(toc_items)}</ol>
      {byl_list}
    </details>
  </aside>
  <section class="lmain">
    <div class="lbar">
      <div class="search-inline">
        <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input type="search" class="lq" placeholder="이 법령에서 찾기 (예: 안전난간, 교육시간)" aria-label="이 법령에서 찾기">
      </div>
      <form class="ljump" data-ljump><label class="sr" for="ljump">조문 번호로 이동</label><span>제</span><input id="ljump" inputmode="numeric" placeholder="38" autocomplete="off"><span>조</span><button class="btn btn-sm" type="submit">이동</button></form>
    </div>
    <p class="lcount" aria-live="polite" hidden></p>
    {ver_box}
    <div class="lbody">{"".join(body)}</div>
    {add_html}
    <p class="src-line">원문: 국가법령정보센터 <a href="{e(d["url"])}" target="_blank" rel="noopener">{e(d["law"])} ({e(d["version"])}) ↗</a> · 확인일 {e(d["checked"])}.
    별표 본문과 2024년 이전 부칙은 원문에서 확인하세요. 법령 원문은 누구나 자유롭게 인용·활용할 수 있습니다. 파란 글씨 조문 번호를 누르면 해당 조문으로 이동합니다.</p>
  </section>
</div>
<script>{LAW_JS}</script>"""
    return body_html, len(live)


LAW_JS = r"""
(function(){
  var arts=[].slice.call(document.querySelectorAll('.lart')), q=document.querySelector('.lq'), cnt=document.querySelector('.lcount');
  var heads=[].slice.call(document.querySelectorAll('.lhead'));
  function norm(s){return String(s||'').replace(/\s+/g,'').toLowerCase();}
  function clearMarks(){[].slice.call(document.querySelectorAll('.lbody mark.lhit')).forEach(function(m){var t=document.createTextNode(m.textContent);m.parentNode.replaceChild(t,m);});}
  function mark(el,w){var walk=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null),n,list=[];while((n=walk.nextNode()))list.push(n);
    list.forEach(function(t){var i=t.nodeValue.toLowerCase().indexOf(w);if(i<0)return;var r=document.createRange();r.setStart(t,i);r.setEnd(t,i+w.length);var m=document.createElement('mark');m.className='lhit';r.surroundContents(m);});}
  var tm;
  if(q)q.addEventListener('input',function(){clearTimeout(tm);tm=setTimeout(run,160);});
  function run(){
    clearMarks();var v=q.value.trim(),ws=v.toLowerCase().split(/\s+/).filter(Boolean),n=0;
    arts.forEach(function(a){var t=norm(a.textContent);var ok=!ws.length||ws.every(function(w){return t.indexOf(norm(w))>=0;});a.hidden=!ok;if(ok)n++;
      if(ok&&ws.length)ws.forEach(function(w){if(w.length>1)mark(a.querySelector('.lart-b')||a,w);});});
    heads.forEach(function(h){h.hidden=!!ws.length;});
    cnt.hidden=!ws.length;cnt.textContent=ws.length?('"'+v+'" 포함 조문 '+n+'개'):'';
  }
  var jf=document.querySelector('[data-ljump]');
  if(jf)jf.addEventListener('submit',function(ev){ev.preventDefault();var v=jf.querySelector('input').value.trim().replace(/[^0-9의\-]/g,'').replace('의','-');if(!v)return;
    var el=document.getElementById('j'+v);if(!el){jf.querySelector('input').setCustomValidity('없는 조문입니다');jf.querySelector('input').reportValidity();setTimeout(function(){jf.querySelector('input').setCustomValidity('');},1500);return;}
    if(q&&q.value){q.value='';run();}location.hash='j'+v;});
  document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copy]');if(!b)return;
    var u=location.href.split('#')[0]+b.getAttribute('data-copy');
    (navigator.clipboard?navigator.clipboard.writeText(u):Promise.reject()).then(function(){b.textContent='복사됨';setTimeout(function(){b.textContent='링크 복사';},1400);},function(){window.prompt('링크를 복사하세요',u);});});
  function flash(){var h=location.hash.slice(1);if(!h)return;var el=document.getElementById(h);if(el&&el.classList.contains('lart')){el.hidden=false;el.classList.add('lflash');setTimeout(function(){el.classList.remove('lflash');},1800);}}
  window.addEventListener('hashchange',flash);flash();
  var asof=document.getElementById('lAsof'), amsg=document.getElementById('lAsofMsg'), base=amsg?amsg.innerHTML:'';
  function kd(s){var p=s.split('-');return p[0]+'. '+(+p[1])+'. '+(+p[2])+'.';}
  function applyAsof(){
    if(!asof||!asof.value)return; var v=asof.value, n=0;
    [].slice.call(document.querySelectorAll('.lart[data-eff]')).forEach(function(a){
      var on=a.getAttribute('data-eff')<=v, cur=a.querySelector('[data-cur]'), pd=a.querySelector('[data-pend]'), st=a.querySelector('[data-st]'), h=pd&&pd.querySelector('.lpend-h');
      a.classList.toggle('lart-on',on); if(on)n++;
      if(st){st.textContent=(on?'기준일 현재 시행 · ':'시행 예정 · ')+kd(a.getAttribute('data-eff'));st.className='lst '+(on?'lst-cur':'lst-next');}
      if(cur)cur.hidden=on; 
      if(h)h.firstChild.textContent=on?'기준일 적용':'시행 예정';
      if(h)h.firstChild.className='lst '+(on?'lst-cur':'lst-next');
    });
    [].slice.call(document.querySelectorAll('.lvt tr[data-up]')).forEach(function(r){var on=r.getAttribute('data-up')<=v, b=r.querySelector('.lst');b.textContent=on?'기준일 현재 시행':'시행 예정';b.className='lst '+(on?'lst-cur':'lst-next');});
    var miss=[].slice.call(document.querySelectorAll('.lvt tr[data-up]')).filter(function(r){return r.getAttribute('data-up')<=v&&/미수록/.test(r.textContent);}).length;
    if(amsg)amsg.innerHTML=(v===asof.defaultValue?'':'<strong>기준일 '+kd(v)+'</strong> — 시행 예정 조문 '+n+'개를 적용해 표시합니다.'+(miss?' <strong class="lwarn">이 기준일에 시행되는 개정 중 '+miss+'건은 본문에 수록되지 않았습니다. 원문에서 확인하세요.</strong> ':' '))+base;
  }
  if(asof){asof.addEventListener('change',applyAsof);applyAsof();}
  var tb=document.querySelector('[data-ltoc]');if(tb&&window.matchMedia('(max-width: 960px)').matches)tb.open=false;
  if(tb)tb.addEventListener('click',function(ev){if(ev.target.closest('a')&&window.matchMedia('(max-width: 960px)').matches)tb.open=false;});
})();
"""


def search_index(laws):
    rows = []
    for k in ORDER:
        if k not in laws:
            continue
        for a in laws[k]["articles"]:
            if a.get("deleted"):
                continue
            t = re.sub(r"<(?:개정|신설|전문개정|제목개정|타법개정)[^>]*>|\[[^\]]*(?:개정|신설|시행일|이동)[^\]]*\]", "", a["text"])
            if a.get("not_in_force"):
                t = f'[{kdate(a["pending"]["effective"])} 시행 예정] ' + a["pending"]["text"]
            rows.append([k, a["jo"], a["title"], re.sub(r"\s+", " ", t).strip()])
    meta = {k: {"short": laws[k]["short"], "law": laws[k]["law"]} for k in laws}
    return "window.ANJEONDUCK_LAWIDX=" + json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";"


STAGES = ["법안", "국회 통과", "공포", "시행 예정", "시행 중"]


def status_panel(laws, manifest, today, rel=""):
    """법령별 현재 시행본·시행 예정본 표. 홈과 법령 허브가 같이 쓴다."""
    rows, n_up, n_chk = "", 0, 0
    for l in manifest["laws"]:
        if l["key"] not in laws:
            continue
        c = l["current"]
        ups = [u for u in l.get("upcoming", []) if u["effective"] > today]
        n_up += len(ups)
        chk = "확인 필요" if "확인 필요" in (l.get("note") or "") else ""
        n_chk += 1 if chk else 0
        chk_html = f'<br><span class="lst-chk" tabindex="0">확인 필요</span> <span class="muted">{e(l["note"])}</span>' if chk else ""
        up_txt = "<br>".join(f'<span class="lst lst-next">시행 예정</span> {e(kdate(u["effective"]))} {e(u["no"])}' for u in sorted(ups, key=lambda x: x["effective"])) or '<span class="muted">확인된 시행 예정 없음</span>'
        rows += (f'<tr><th><a href="{rel}{l["key"]}/">{e(l["name"])}</a></th><td><span class="lst lst-cur">현재 시행</span> {e(kdate(c["effective"]))}<br><span class="muted">{e(c["no"])} · {e(kdate(c["promulgated"]))} {e(c["kind"])}</span></td>'
                 f'<td>{up_txt}{chk_html}</td><td>{e(l["checked_at"])}</td></tr>')
    table = f'<div class="table-wrap"><table class="lvt lvt-hub"><thead><tr><th>법령</th><th>현재 시행본</th><th>시행 예정</th><th>공식 확인일</th></tr></thead><tbody>{rows}</tbody></table></div>'
    return table, n_up, n_chk


def upcoming_html(manifest, today, rel=""):
    items = []
    for l in manifest["laws"]:
        for u in l.get("upcoming", []):
            if u["effective"] > today:
                items.append((u["effective"], l, u))
    out = ""
    for eff, l, u in sorted(items, key=lambda x: x[0]):
        arts = " · ".join(e(x) for x in u.get("articles", []))
        imp = f'<p class="lup-i"><b>실무 영향</b> {e(u["impact"])}</p>' if u.get("impact") else ""
        out += (f'<li class="lup"><div class="lup-d"><span class="lst lst-next">시행 예정</span><b>{e(kdate(eff))}</b></div><div><p class="lup-t"><a href="{rel}{l["key"]}/#versions">{e(l["name"])}</a> <span class="muted">{e(u["no"])} · {e(kdate(u["promulgated"]))} {e(u["kind"])}</span></p>'
                f'<p>{e(u.get("summary", ""))}</p>{f"<p class=lup-a>대상 조문: {arts}</p>" if arts else ""}{imp}'
                f'<p class="urow-foot"><a class="link-ext" href="{e(u["source_url"])}" target="_blank" rel="noopener">국가법령정보센터 ↗</a><span>근거 {e(u.get("basis", ""))}</span>'
                f'<span>{"본문에 함께 수록" if u.get("text") == "inline" else "개정 조문 본문은 원문에서 확인"}</span></p></div></li>')
    return out, len(items)


def bills_html(manifest):
    out = ""
    for b in manifest.get("bills", []):
        steps = "".join(f'<span class="lstage{" on" if st == b.get("stage") else ""}">{e(st)}</span>' for st in STAGES)
        src = f'<a class="link-ext" href="{e(b["source_url"])}" target="_blank" rel="noopener">{e(b.get("source_name") or "출처")} ↗</a>' if str(b.get("source_url", "")).startswith("https://") else '<span class="lst-chk" tabindex="0">확인 필요</span> <span class="muted">공식 출처</span>'
        out += (f'<li class="lup"><div class="lup-d"><span class="lst lst-bill">입법 동향</span><b>{e(kdate(b["stage_date"]))}</b></div><div><p class="lup-t">{e(b["title"])}</p><p class="lstages">{steps}</p>'
                f'<p>{e(b.get("summary", ""))}</p><p class="urow-foot">{src}<span>{e(b.get("note", ""))}</span></p></div></li>')
    return out


def hub_page(laws, updates_html, n_updates, statutes_html, update_filter_html, manifest=None, today=""):
    idx = {k: {a["jo"]: a for a in d["articles"]} for k, d in laws.items()}
    cards = {}
    for k in ORDER:
        if k not in laws:
            continue
        d = laws[k]
        live = sum(1 for a in d["articles"] if not a.get("deleted"))
        chs = sum(1 for t in d["toc"] if t["lv"] <= 1)
        cards[k] = (f'<a class="lcard" href="{k}/"><span class="lcard-lv">{e(LEVEL_LABEL[k])}</span>'
                    f'<strong>{e(d["law"])}</strong><span class="lcard-m">{e(d["version"].split(",")[0])} · 시행 {e(d["effective"])}.</span>'
                    f'<span class="lcard-n">조문 {live}개{f" · {chs}개 편·장" if chs else ""}</span><span class="lcard-go">전문 보기 →</span></a>')
    topics = []
    for title, sub, refs in TOPICS:
        lis = []
        for k, jo in refs:
            a = idx.get(k, {}).get(jo)
            if not a:
                continue
            lis.append(f'<li><a href="{k}/#{anchor(jo)}"><span class="lt-law">{e(laws[k]["short"])}</span> <b>{e(jo)}</b> {e(a["title"])}</a></li>')
        if lis:
            topics.append(f'<section class="ltopic"><h3>{e(title)}</h3><p>{e(sub)}</p><ul>{"".join(lis)}</ul></section>')
    total = sum(1 for d in laws.values() for a in d["articles"] if not a.get("deleted"))
    status_sec = ""
    if manifest:
        table, n_up, n_chk = status_panel(laws, manifest, today)
        up, _ = upcoming_html(manifest, today)
        bills = bills_html(manifest)
        status_sec = f"""<section class="wrap lstat" id="status">
  <div class="sec-head"><div><h2>A · 현재 시행 법령</h2><p>법령 데이터 기준일 <strong>{e(manifest["checked_at"])}</strong> · 국가법령정보센터 연혁과 대조. 조문마다 시행일이 다르면 법령 전체 시행일 하나로 표시하지 않고 조문에 '시행 예정'을 따로 붙입니다.</p></div></div>
  {table}
</section>
<section class="wrap lstat" id="upcoming">
  <div class="sec-head"><div><h2>B · 공포됐지만 아직 시행 전</h2><p>이미 공포돼 시행일이 정해진 개정입니다. 시행일 전에는 적용되지 않습니다.</p></div></div>
  <ul class="lups">{up or '<li class="lup"><div></div><div><p>확인된 시행 예정 개정이 없습니다.</p></div></li>'}</ul>
</section>
<section class="wrap lstat" id="bills">
  <div class="sec-head"><div><h2>입법 동향</h2><p>국회 통과안·입법예고는 <strong>공포돼야 법령이 됩니다.</strong> 내용과 시행일은 공포문으로 확정됩니다.</p></div></div>
  <ul class="lups">{bills or '<li class="lup"><div></div><div><p>등록된 입법 동향이 없습니다.</p></div></li>'}</ul>
</section>"""
    return f"""
<section class="phead lhero"><div class="wrap">
  <p class="crumbs"><a href="../">홈</a><span>/</span>법령</p>
  <h1>산업안전 법령</h1>
  <p>산업안전보건법령 4종과 중대재해처벌법령 2종의 현행 전문 {total:,}개 조문을 SafePlum 안에서 바로 읽고 찾습니다. 조문 속 인용 번호를 누르면 해당 조문으로 이동하고, 법률 조문마다 그 조문을 인용한 시행령·시행규칙이 함께 표시됩니다.</p>
  <div class="lsearch" data-lsearch>
    <div class="hsearch-box">
      <label for="lsq" class="sr">법령 전체 검색</label>
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input id="lsq" type="search" placeholder="예: 안전난간, 관리감독자 교육, 밀폐공간, 경영책임자" autocomplete="off">
    </div>
    <div class="lsr" data-lsr hidden></div>
  </div>
</div></section>
<section class="wrap lfam">
  <div class="lfam-g">
    <h2 class="h-sm">산업안전보건법령</h2>
    <div class="lcards">{cards.get("act","")}{cards.get("yeong","")}{cards.get("rule","")}{cards.get("krule","")}</div>
    <p class="hint">법률이 큰 원칙을 정하고 → 시행령(대통령령)이 대상·범위를 → 시행규칙(부령)이 절차·서식을 → 안전보건규칙이 현장의 구체적 안전·보건 기준을 정합니다.</p>
  </div>
  <div class="lfam-g">
    <h2 class="h-sm">중대재해처벌법령</h2>
    <div class="lcards">{cards.get("sapa","")}{cards.get("sapa_dec","")}</div>
  </div>
</section>
{status_sec}
<section class="wrap" style="padding-top:28px">
  <div class="sec-head"><div><h2>주제별 조문 찾기</h2><p>실무에서 자주 찾는 조문을 주제별로 모았습니다. 제목은 현행 본문 그대로입니다.</p></div></div>
  <div class="ltopics">{"".join(topics)}</div>
</section>
<div class="wrap layout-detail" style="padding-top:28px">
  <section class="col-main" id="updates">
    <div class="sec-head"><div><h2>C · 시행 중인 최근 개정</h2><p>공포일 순서. 요약은 조문 개정 표기와 부칙을 읽고 정리한 것입니다. 적용 여부는 원문으로 확인하세요.</p></div></div>
    {update_filter_html}
    <ul class="ulist" data-list>{updates_html}</ul>
    <div class="empty" data-empty hidden><p>검색 결과가 없습니다.</p></div>
  </section>
  <aside class="col-side">
    <section class="side-box" id="past"><div class="sec-head"><div><h2>D · 과거 법령</h2></div></div><p>개정 전 조문과 연혁은 SafePlum에 싣지 않습니다. 각 법령 페이지의 '국가법령정보센터 연혁'에서 시행일별 본문을 확인하세요.</p></section>
    <section class="side-box" id="statutes"><div class="sec-head"><div><h2>고시·관련 법령 원문</h2></div></div><ul class="llist">{statutes_html}</ul></section>
  </aside>
</div>
<script>{HUB_JS}</script>"""


HUB_JS = r"""
(function(){
  var box=document.querySelector('[data-lsearch]');if(!box)return;var inp=box.querySelector('input'),out=box.querySelector('[data-lsr]'),IDX=null,loading=false,tm;
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function load(cb){if(IDX)return cb();if(loading)return;loading=true;out.hidden=false;out.innerHTML='<p class="muted">법령 색인을 불러오는 중…</p>';
    var s=document.createElement('script');s.src='../assets/data/lawidx.js';s.onload=function(){IDX=window.ANJEONDUCK_LAWIDX;loading=false;cb();};
    s.onerror=function(){loading=false;out.innerHTML='<p class="muted">색인을 불러오지 못했습니다. 네트워크를 확인하세요.</p>';};document.head.appendChild(s);}
  function anchor(jo){var m=jo.match(/제(\d+)조(?:의(\d+))?/);return 'j'+m[1]+(m[2]?'-'+m[2]:'');}
  function snip(t,w){var i=t.indexOf(w);if(i<0)return esc(t.slice(0,90))+(t.length>90?'…':'');var s=Math.max(0,i-36);
    return (s?'…':'')+esc(t.slice(s,i))+'<mark>'+esc(t.substr(i,w.length))+'</mark>'+esc(t.slice(i+w.length,i+w.length+60))+'…';}
  function run(){var v=inp.value.trim();if(!v){out.hidden=true;out.innerHTML='';return;}
    load(function(){var ws=v.split(/\s+/).filter(Boolean),res=[];
      var jm=v.match(/^(?:(법|영|시행령|시행규칙|규칙|안전보건규칙|기준규칙|중처법)\s*)?제?\s*(\d+)\s*조?(?:의\s*(\d+))?$/);
      IDX.rows.forEach(function(r){var hay=r[1]+' '+r[2]+' '+r[3],score=0;
        if(jm){var jo='제'+jm[2]+'조'+(jm[3]?'의'+jm[3]:'');if(r[1]!==jo)return;var lk={'법':'act','영':'yeong','시행령':'yeong','시행규칙':'rule','규칙':'rule','안전보건규칙':'krule','기준규칙':'krule','중처법':'sapa'}[jm[1]||''];if(lk&&r[0]!==lk)return;score=10;}
        else{if(!ws.every(function(w){return hay.indexOf(w)>=0;}))return;ws.forEach(function(w){if(r[2].indexOf(w)>=0)score+=5;score+=Math.min(3,hay.split(w).length-1);});}
        res.push([score,r]);});
      res.sort(function(a,b){return b[0]-a[0];});var top=res.slice(0,40);
      out.hidden=false;
      out.innerHTML='<p class="lsr-n">'+res.length+'개 조문'+(res.length>40?' 중 40개':'')+'</p>'+(top.length?'<ul>'+top.map(function(x){var r=x[1];
        return '<li><a href="'+r[0]+'/#'+anchor(r[1])+'"><span class="lt-law">'+esc(IDX.meta[r[0]].short)+'</span> <b>'+esc(r[1])+'</b> '+esc(r[2])+'<span class="lsr-s">'+snip(r[3],ws[0]||'')+'</span></a></li>';}).join('')+'</ul>':'<p class="muted">찾는 조문이 없습니다. 다른 낱말로 찾아보세요.</p>');});}
  inp.addEventListener('input',function(){clearTimeout(tm);tm=setTimeout(run,180);});
  inp.addEventListener('focus',function(){load(function(){});},{once:true});
})();
"""
