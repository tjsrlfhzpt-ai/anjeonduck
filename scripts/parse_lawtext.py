#!/usr/bin/env python3
"""국가법령정보센터 본문(lsInfoP.do) 텍스트 → data/lawtext/<key>.json (편·장·절 목차 + 조문 + 별표 목록).

입력: data/lawraw/<key>.txt  (브라우저에서 본문 페이지 전체 텍스트를 그대로 저장한 것)
사용: python3 scripts/parse_lawtext.py            # 전부
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "lawraw", ROOT / "data" / "lawtext"

LAWS = {
    "act": ("산업안전보건법", "산안법", 283449),
    "yeong": ("산업안전보건법 시행령", "산안법 시행령", 288347),
    "rule": ("산업안전보건법 시행규칙", "산안법 시행규칙", 288431),
    "krule": ("산업안전보건기준에 관한 규칙", "안전보건규칙", 273603),
    "sapa": ("중대재해 처벌 등에 관한 법률", "중대재해처벌법", 228817),
    "sapa_dec": ("중대재해 처벌 등에 관한 법률 시행령", "중대재해처벌법 시행령", 277417),
}

HEAD_RE = re.compile(r"^\s*(제\d+(?:편|장|절|관)(?:의\d+)?)\s+(.+?)\s*(<[^>]*>)?\s*$")
ART_RE = re.compile(r"^\s?(제\d+조(?:의\d+)?)(?:\(([^)\n]{1,80})\))?\s?(.*)$")
BYL_RE = re.compile(r"^\s*\[별표\s*(\d+)(?:의(\d+))?\]\s*(.+?)\s*$")
# 국가법령정보센터 본문은 아직 시행 전인 개정 조문을 현행 조문 바로 아래에 한 번 더 싣고 "[시행일: 2026. 12. 8.] 제6조" 로 닫는다.
PEND_RE = re.compile(r"^\s*\[시행일\s*:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\]\s*(제\d+조(?:의\d+)?)?\s*$")
PEND_HEAD_RE = re.compile(r"^(제\d+(?:편|장|절|관)(?:의\d+)?)\s+(.+?)\s*(<[^>]*>)?\s*$")
AMEND_RE = re.compile(r"(?:개정|신설|본조신설|전문개정|제목개정)\s*((?:\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.(?:,\s*)?)+)")


def iso(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def amend_dates(text):
    out = set()
    for grp in AMEND_RE.findall(text):
        for y, m, d in re.findall(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", grp):
            out.add(iso(y, m, d))
    return sorted(out)


def parse(key):
    name, short, seq = LAWS[key]
    t = (RAW / f"{key}.txt").read_text(encoding="utf-8").replace("\xa0", " ")
    ver = re.search(r"\[시행\s*([\d. ]+?)\.\]\s*\[([^\]]+)\]", t)
    # 본문 시작: 담당부처 연락처 다음 처음 나오는 '제1장/제1편' 또는 '제1조(목적)'
    lines = t.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^\s{4,}제1(편|장)\s", ln) or re.match(r"^\s?제1조\(목적\)\s", ln):
            # 목차(조문 선택) 영역은 들여쓰기가 1칸이고 본문 목록은 '제1조(목적)'만 단독으로 나온다 → 본문은 내용이 붙어 있다
            if re.match(r"^\s?제1조\(목적\)\s*$", ln):
                continue
            if i > 0 and any("한눈보기" in x for x in lines[max(0, i - 400):i]):
                start = i
                break
    if start is None:
        raise SystemExit(f"{key}: 본문 시작을 찾지 못함")
    body = lines[start:]
    end = next((i for i, ln in enumerate(body) if re.match(r"^\s*부\s+칙", ln)), len(body))
    tail, body = body[end:], body[:end]

    toc, arts, cur, path = [], [], None, {}
    level = {"편": 0, "장": 1, "절": 2, "관": 3}
    em = re.match(r"\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", ver.group(1)) if ver else None
    law_eff = iso(*em.groups()) if em else "0000-00-00"
    pend, pend_head = None, None   # pend: 현행 조문 아래 다시 실린 '시행 전 개정 조문' 모으는 중
    for ln in body:
        s = ln.rstrip()
        if not s.strip():
            continue
        pm = PEND_RE.match(s)
        if pm:
            eff = iso(pm.group(1), pm.group(2), pm.group(3))
            if eff <= law_eff:            # 이미 지난 시행일 표기(예: 중처법 제16조)는 현행 조문에 붙은 안내일 뿐
                pend, pend_head = None, None
                continue
            if pm.group(4) and cur and pm.group(4) == cur["jo"]:
                if pend is not None:      # 현행 + 시행 예정 두 벌
                    cur["pending"] = {"effective": eff, "title": pend["title"], "text": pend["text"]}
                else:                     # 한 벌뿐 = 아직 시행 전인 신설 조문
                    cur["pending"] = {"effective": eff, "title": cur["title"], "text": cur["text"]}
                    cur["text"], cur["not_in_force"] = "", True
            elif not pm.group(4) and pend_head and toc:
                tgt = next((t for t in reversed(toc) if t["no"] == pend_head[0]), None)
                if tgt:
                    tgt["pending"] = {"effective": eff, "title": pend_head[1]}
            pend, pend_head = None, None
            continue
        ph = PEND_HEAD_RE.match(s) if not s.startswith(" ") else None
        if ph and not ART_RE.match(s) :
            pend_head = (ph.group(1), ph.group(2).strip())
            continue
        h = HEAD_RE.match(s) if s.startswith("    ") else None
        if h and not ART_RE.match(s.strip()):
            kind = re.search(r"(편|장|절|관)", h.group(1)).group(1)
            lv = level[kind]
            path = {k: v for k, v in path.items() if k < lv}
            path[lv] = f"{h.group(1)} {h.group(2)}"
            toc.append({"lv": lv, "no": h.group(1), "title": h.group(2).strip(), "first": None})
            continue
        a = ART_RE.match(s) if s.startswith(" 제") or s.startswith("제") else None
        if a and (a.group(2) or re.match(r"^\s*삭제", a.group(3) or "")) and (not cur or a.group(1) != cur["jo"]):
            jo, title, rest = a.group(1), (a.group(2) or "").strip(), (a.group(3) or "").strip()
            cur = {"jo": jo, "title": title, "text": rest, "path": [path[k] for k in sorted(path)]}
            if title == "" and rest.startswith("삭제"):
                cur["deleted"] = True
            arts.append(cur)
            for tt in toc:
                if tt["first"] is None:
                    tt["first"] = jo
            continue
        if a and cur and a.group(1) == cur["jo"] and a.group(2) and not s.startswith(" "):
            pend = {"title": a.group(2).strip(), "text": (a.group(3) or "").strip()}
            continue
        if pend is not None:
            pend["text"] += "\n" + s.strip()
        elif cur:
            cur["text"] += "\n" + s.strip()
    assert pend is None, f"{key}: 닫히지 않은 시행 예정 조문 — {cur and cur['jo']}"
    for a in arts:
        a["text"] = re.sub(r"\n{2,}", "\n", a["text"]).strip()
        if a.get("pending"):
            a["pending"]["text"] = re.sub(r"\n{2,}", "\n", a["pending"]["text"]).strip()
        am = amend_dates(a["text"] + "\n" + (a.get("pending") or {}).get("text", ""))
        if am:
            a["amended"] = am
        if not a.get("deleted") and re.fullmatch(r"삭제\s*<[^>]*>", a["text"]):
            a["deleted"] = True
    # 부칙: 최근 공포분만(시행일·적용례 원문 확인용)
    addenda, cur_add = [], None
    for ln in tail:
        st = ln.strip()
        hm = re.match(r"^부\s+칙\s*<([^,>]+),\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.>", st)
        if hm:
            cur_add = {"no": hm.group(1).strip(), "date": iso(hm.group(2), hm.group(3), hm.group(4)), "text": ""}
            addenda.append(cur_add)
            continue
        if BYL_RE.match(ln) or st.startswith("Tab Context") or st.startswith("- Executed") or st.startswith("- Available") or st.startswith("•"):
            cur_add = None
            continue
        if cur_add is not None and st:
            cur_add["text"] += ("\n" if cur_add["text"] else "") + st
    addenda = [x for x in addenda if x["date"] >= "2025-01-01" and x["text"]]
    byl = []
    for ln in tail:
        m = BYL_RE.match(ln)
        if m:
            byl.append({"no": m.group(1), "br": m.group(2) or "", "title": m.group(3)})
    # 이어진 편·장이 여러 개 연속해서 조문 없이 나오면 first 가 다음 조문으로 들어간다(정상)
    nums = [a["jo"] for a in arts]
    assert len(nums) == len(set(nums)), f"{key}: 조문 번호 중복"
    return {
        "key": key, "law": name, "short": short, "lsiSeq": seq,
        "effective": ver.group(1).strip() if ver else "", "effective_iso": law_eff, "version": ver.group(2).strip() if ver else "",
        "url": f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={seq}",
        "checked": "2026-09-30", "source": f"국가법령정보센터 lsInfoP.do?lsiSeq={seq} 본문",
        "toc": toc, "articles": arts, "byl": byl, "addenda": addenda,
    }


def main(keys):
    for k in keys:
        d = parse(k)
        live = [a for a in d["articles"] if not a.get("deleted")]
        (OUT / f"{k}.json").write_text(json.dumps(d, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"{k:9} {d['version'][:34]:36} 목차 {len(d['toc']):3}  조문 {len(d['articles']):4} (삭제 {len(d['articles']) - len(live)})  별표 {len(d['byl'])}  {d['articles'][0]['jo']}~{d['articles'][-1]['jo']}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(LAWS))
