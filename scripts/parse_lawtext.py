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
    for ln in body:
        s = ln.rstrip()
        if not s.strip():
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
        if cur:
            cur["text"] += "\n" + s.strip()
    for a in arts:
        a["text"] = re.sub(r"\n{2,}", "\n", a["text"]).strip()
        if not a.get("deleted") and re.fullmatch(r"삭제\s*<[^>]*>", a["text"]):
            a["deleted"] = True
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
        "effective": ver.group(1).strip() if ver else "", "version": ver.group(2).strip() if ver else "",
        "url": f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={seq}",
        "checked": "2026-09-30", "source": f"국가법령정보센터 lsInfoP.do?lsiSeq={seq} 본문",
        "toc": toc, "articles": arts, "byl": byl,
    }


def main(keys):
    for k in keys:
        d = parse(k)
        live = [a for a in d["articles"] if not a.get("deleted")]
        (OUT / f"{k}.json").write_text(json.dumps(d, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"{k:9} {d['version'][:34]:36} 목차 {len(d['toc']):3}  조문 {len(d['articles']):4} (삭제 {len(d['articles']) - len(live)})  별표 {len(d['byl'])}  {d['articles'][0]['jo']}~{d['articles'][-1]['jo']}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(LAWS))
