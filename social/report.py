"""월간 성과 보고서(마크다운 표). social-data 브랜치 reports/YYYY-MM.md 로 저장하고 깃허브 이슈로도 알린다."""
import calendar, datetime
from .common import load, now, STATE
from . import store, evidence as ev
from .metrics import supabase_stats, _try


def _n(v):
    return "" if v is None else (f"{v:,}" if isinstance(v, (int, float)) else str(v))


def table(head, rows):
    if not rows:
        return "_자료 없음_\n"
    return "| " + " | ".join(head) + " |\n|" + "|".join(["---"] * len(head)) + "|\n" + "\n".join("| " + " | ".join(_n(c).replace("|", "/") for c in r) + " |" for r in rows) + "\n"


def build(month=None):
    t = now().date()
    if not month:
        first = t.replace(day=1) - datetime.timedelta(days=1)
        month = first.strftime("%Y-%m")
    y, m = map(int, month.split("-"))
    d_from, d_to = f"{month}-01", f"{month}-{calendar.monthrange(y, m)[1]:02d}"
    items = [i for i in store.ledger()["items"] if i["date"].startswith(month)]
    problems = []
    stats = _try("유입 집계", lambda: supabase_stats(d_from, d_to), problems) or {}
    P = store.PLATFORMS
    name = {"blogger": "블로그", "instagram": "인스타그램", "facebook": "페이스북"}
    out = [f"# 세이프플럼 SNS 월간 성과 보고서 — {y}년 {m}월", f"작성 {t.isoformat()} · 집계 기간 {d_from} ~ {d_to}", ""]

    out.append("## 1. 게시 현황\n")
    rows = []
    for p in P:
        st = [i["platforms"].get(p, {}).get("status") for i in items]
        rows.append([name[p], st.count("published"), st.count("failed"), st.count("queued"), st.count("skipped")])
    out.append(table(["플랫폼", "게시 완료", "실패", "대기", "건너뜀"], rows))
    held = [i for i in items if i["status"] in ("held", "discarded")]
    out.append(f"- 만든 주제 {len(items)}건 · 검증에서 보류 {len(held)}건(그중 폐기 {sum(1 for i in held if i['status'] == 'discarded')}건)\n")

    out.append("## 2. 플랫폼 반응\n")
    rows = []
    for p in P:
        ms = [i.get("metrics", {}).get(p) or {} for i in items]
        s = lambda k: (sum(x.get(k) or 0 for x in ms) if any(x.get(k) is not None for x in ms) else None)
        rows.append([name[p], s("reach"), s("views"), s("likes"), s("comments"), s("shares"), s("saved"), s("clicks")])
    out.append(table(["플랫폼", "도달", "조회", "좋아요", "댓글", "공유", "저장", "링크 클릭"], rows))
    out.append("빈칸은 그 플랫폼 API 가 주지 않는 값이거나 수집에 실패한 값입니다(0 과 다릅니다). Blogger API 는 글별 조회수를 주지 않습니다.\n")

    out.append("## 3. 세이프플럼 유입 (UTM)\n")
    utm = stats.get("utm", [])
    agg = {}
    for u in utm:
        agg[u["source"]] = agg.get(u["source"], 0) + u["hits"]
    out.append(table(["유입 채널", "방문 수"], sorted(agg.items(), key=lambda x: -x[1])))
    cagg = {}
    for u in utm:
        cagg[u["campaign"]] = cagg.get(u["campaign"], 0) + u["hits"]
    slug_name = {v: k for k, v in ev.CAT_SLUG.items()}
    out.append("### 분야별\n")
    out.append(table(["분야", "방문 수"], [[ev.CAT_LABEL.get(slug_name.get(k, ""), k or "(없음)"), v] for k, v in sorted(cagg.items(), key=lambda x: -x[1])]))
    vis = sum(v["visitors"] for v in stats.get("visitors", []))
    out.append("### 사이트 전체\n")
    out.append(table(["항목", "값"], [["하루 방문자 합계(월)", vis if stats else None], ["SNS·블로그 유입 방문", sum(agg.values()) if stats else None],
                                    ["신규 회원 가입", stats.get("signups")], ["커뮤니티 새 글", stats.get("posts")], ["커뮤니티 새 댓글", stats.get("comments")]]))

    out.append("## 4. 게시물별 전환 (유입 많은 순 20건)\n")
    rows = []
    for i in sorted(items, key=lambda i: -(i.get("metrics", {}).get("visits_total") or 0))[:20]:
        v = i.get("metrics", {}).get("visits", {})
        rows.append([i["date"], ev.CAT_LABEL.get(i["cat"], i["cat"]), i["title"][:40], v.get("blogger"), v.get("instagram"), v.get("facebook"), i.get("metrics", {}).get("visits_total")])
    out.append(table(["날짜", "분야", "제목", "블로그→", "인스타→", "페이스북→", "유입 합계"], rows))

    out.append("## 5. 분야별 성적 — 어떤 주제가 방문으로 이어졌나\n")
    cat = {}
    for i in items:
        c = cat.setdefault(i["cat"], [0, 0])
        c[0] += 1
        c[1] += i.get("metrics", {}).get("visits_total") or 0
    out.append(table(["분야", "글 수", "유입 합계", "글 1건당 유입"], [[ev.CAT_LABEL.get(k, k), n, v, round(v / n, 1) if n else 0] for k, (n, v) in sorted(cat.items(), key=lambda x: -(x[1][1] / max(x[1][0], 1)))]))

    snaps = sorted((STATE / "metrics").glob(f"{month}-*.json"))
    last = load(snaps[-1]) if snaps else {}
    if last.get("search"):
        s = last["search"]
        out.append("## 6. 검색 (구글 서치콘솔, 최근 집계 7일)\n")
        out.append(table(["노출", "클릭", "평균 순위"], [[s.get("impressions"), s.get("clicks"), round(s["position"], 1) if s.get("position") else None]]))
        out.append(table(["검색어", "클릭", "노출"], [[q["query"], q["clicks"], q["impressions"]] for q in s.get("top_queries", [])]))
    errs = []
    ep = STATE / "logs" / "errors.jsonl"
    if ep.exists():
        import json
        errs = [json.loads(l) for l in ep.read_text(encoding="utf-8").splitlines() if l.strip() and l[8:15] == month]
    out.append(f"## 7. 오류\n\n- 이번 달 기록된 오류 {len(errs)}건" + ("".join(f"\n- {e['at'][:16]} {e['where']}: {e['error'][:120]}" for e in errs[-8:]) if errs else "") + "\n")
    if problems:
        out.append("## 수집하지 못한 항목\n\n" + "\n".join(f"- {p}" for p in problems) + "\n")
    text = "\n".join(out)
    p = STATE / "reports" / f"{month}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return month, text
