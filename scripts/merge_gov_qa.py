# -*- coding: utf-8 -*-
"""추가 수집한 질의회시 원자료를 data/gov_qa.json 에 합친다(기존 글은 그대로, 주제는 전체 다시 분류).

원자료: 국가법령정보센터 「중앙부처 1차 해석」 고용노동부 — 본문 검색어 여러 개(공정안전보고서·유해위험방지계획서·작업환경측정 등)로
        목록을 받아 안전·보건 부서 회신만 고른 뒤 본문을 받은 것. [id, 안건명, 회신일, 부서·문서번호, 질의요지, 회답, 관련법령, 출처자료] 배열.
        「산업안전보건법 질의회시집(2022.5.)」, 「물질안전보건자료 질의회시집(2023)」처럼 노동부 누리집 자료집에서 법제처가 수집한 글은 출처자료가 붙어 있다.
사용법: python3 scripts/merge_gov_qa.py 원자료.json 수집일(YYYY-MM-DD)
"""
import json, re, sys, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_gov_qa import tidy, topic, TOPICS, TOOL_LINKS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def src_name(s):
    s = re.sub(r"\.(pdf|hwp|hwpx)$", "", (s or "").strip(), flags=re.I)
    s = re.sub(r"^\(\d{6,8}\)\s*", "", s)
    s = re.sub(r"^\((고용노동부)\)\s*", "", s)
    s = s.replace("산압언전보건법", "산업안전보건법")   # 원 파일명의 오타
    s = re.sub(r"\s*\d{4}년\s*개정판\(최종\)", "", s)
    return s.strip()


def main(src, collected):
    cur = json.load(open(ROOT / "data/gov_qa.json", encoding="utf-8"))
    items = cur["items"]
    have_id = {x["id"] for x in items}
    have_key = {(re.sub(r"\W", "", x["t"]), x.get("d", "")) for x in items}
    raw = json.load(open(src, encoding="utf-8"))
    add = 0
    for r in raw:
        rid, t, d, dep, q, a, l, so = (r + [""] * 8)[:8]
        t = re.sub(r"<[^>]+>", "", t or "")
        t = re.sub(r"\s+", " ", t).strip()
        if not (q or a) or str(rid) in have_id:
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d or ""):
            m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", dep or "")
            d = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
        k = (re.sub(r"\W", "", t), d)
        if k in have_key:
            continue
        if len(t) > 90:  # 자료집 글은 안건명이 질문 전체라 길다 → 앞부분만 제목으로
            t = t[:88].rstrip() + "…"
        x = {"id": str(rid), "t": t, "d": d, "c": "", "q": tidy(q), "a": tidy(a), "l": re.sub(r"\s+", " ", l or "").strip()}
        sn = src_name(so)
        if sn:
            x["s"] = sn
        items.append(x)
        have_id.add(x["id"]); have_key.add(k); add += 1
    for x in items:
        x["c"] = topic(x["t"], x["q"])
    items.sort(key=lambda x: (x["d"] or "0000", x["id"]), reverse=True)
    m = cur["meta"]
    m["source"] = "국가법령정보센터 중앙부처 1차 해석 — 고용노동부(본문 검색어: 산업안전보건법 외 공정안전보고서·유해위험방지계획서·작업환경측정·MSDS 등, 안전·보건 부서 회신)"
    m["collected"] = collected
    m["topics"] = [n for n, _ in TOPICS] + ["기타"]
    m["tools"] = TOOL_LINKS
    cur["checked"] = collected
    (ROOT / "data/gov_qa.json").write_text(json.dumps(cur, ensure_ascii=False, indent=0), encoding="utf-8")
    c = collections.Counter(x["c"] for x in items)
    print("추가", add, "→ 전체", len(items), dict(c))
    print("출처 자료집", collections.Counter(x.get("s", "") for x in items).most_common(8))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
