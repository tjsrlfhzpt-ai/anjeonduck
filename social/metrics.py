"""성과 수집 — 플랫폼 반응(도달·좋아요·댓글·저장·공유), 세이프플럼 유입(UTM), 방문자·가입·커뮤니티 활동, 검색 노출.

각 수집기는 따로 실패할 수 있고, 하나가 실패해도 나머지는 계속한다. 값이 없으면 0 이 아니라 빈칸으로 둔다(수집 실패와 0 을 구분).
"""
import datetime, urllib.parse
from .common import cfg, env, http, load, save, log, mask, now, today, STATE, ROOT, Missing
from . import store
from .publish import G, google_token


def supabase_stats(d_from, d_to):
    site = load(ROOT / "config" / "site.json")["community"]
    r = http("POST", site["supabase_url"].rstrip("/") + "/rest/v1/rpc/social_stats",
             headers={"apikey": site["supabase_anon_key"], "Authorization": "Bearer " + site["supabase_anon_key"], "Content-Type": "application/json"},
             json_body={"p_key": env("SOCIAL_STATS_KEY", True), "p_from": d_from, "p_to": d_to})
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError("social_stats: " + str(r["error"]) + " (SOCIAL_STATS_KEY 가 social_keys 표의 값과 같은지 확인)")
    return r


def ig_metrics(mid):
    tok = env("META_PAGE_TOKEN", True)
    out = {}
    b = http("GET", G(mid), params={"fields": "like_count,comments_count", "access_token": tok})
    out["likes"], out["comments"] = b.get("like_count"), b.get("comments_count")
    try:
        ins = http("GET", G(f"{mid}/insights"), params={"metric": "reach,saved,shares,views", "access_token": tok}, tries=1).get("data", [])
        for m in ins:
            out[m["name"]] = (m.get("values") or [{}])[0].get("value")
    except Exception as e:
        log("인스타그램 인사이트 일부 실패:", mask(e)[:160])
    return out


def fb_metrics(pid):
    tok = env("META_PAGE_TOKEN", True)
    out = {}
    b = http("GET", G(pid), params={"fields": "shares,likes.summary(true).limit(0),comments.summary(true).limit(0)", "access_token": tok})
    out["likes"] = (b.get("likes") or {}).get("summary", {}).get("total_count")
    out["comments"] = (b.get("comments") or {}).get("summary", {}).get("total_count")
    out["shares"] = (b.get("shares") or {}).get("count", 0)
    try:
        ins = http("GET", G(f"{pid}/insights"), params={"metric": "post_impressions_unique,post_clicks", "access_token": tok}, tries=1).get("data", [])
        for m in ins:
            out["reach" if m["name"] == "post_impressions_unique" else "clicks"] = (m.get("values") or [{}])[0].get("value")
    except Exception as e:
        log("페이스북 인사이트 일부 실패:", mask(e)[:160])
    return out


def blogger_metrics(pid):
    r = http("GET", f"https://www.googleapis.com/blogger/v3/blogs/{env('BLOGGER_BLOG_ID', True)}/posts/{pid}",
             headers={"Authorization": "Bearer " + google_token()}, params={"fields": "replies/totalItems"})
    return {"comments": int((r.get("replies") or {}).get("totalItems", 0))}      # Blogger API 는 글별 조회수를 주지 않는다


def blog_pageviews():
    r = http("GET", f"https://www.googleapis.com/blogger/v3/blogs/{env('BLOGGER_BLOG_ID', True)}/pageviews",
             headers={"Authorization": "Bearer " + google_token()}, params={"range": "30DAYS"})
    return int((r.get("counts") or [{}])[0].get("count", 0))


def search_console(d_from, d_to):
    """세이프플럼 검색 노출·클릭(서치콘솔). 구글 토큰에 webmasters.readonly 권한이 있어야 한다."""
    site = env("GSC_SITE_URL") or cfg()["base_url"].rstrip("/") + "/"
    r = http("POST", f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query",
             headers={"Authorization": "Bearer " + google_token()}, json_body={"startDate": d_from, "endDate": d_to, "dimensions": ["query"], "rowLimit": 15})
    rows = r.get("rows", [])
    tot = http("POST", f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query",
               headers={"Authorization": "Bearer " + google_token()}, json_body={"startDate": d_from, "endDate": d_to}).get("rows", [{}])
    t = tot[0] if tot else {}
    return {"clicks": t.get("clicks"), "impressions": t.get("impressions"), "ctr": t.get("ctr"), "position": t.get("position"),
            "top_queries": [{"query": x["keys"][0], "clicks": x["clicks"], "impressions": x["impressions"]} for x in rows]}


def _try(name, fn, problems):
    try:
        return fn()
    except Missing as e:
        problems.append(f"{name}: 미연결({e})")
    except Exception as e:
        problems.append(f"{name}: {mask(e)[:200]}")
    return None


def collect(days=35):
    lg = store.ledger()
    t = now().date()
    d_from = (t - datetime.timedelta(days=days)).isoformat()
    problems = []
    stats = _try("유입 집계", lambda: supabase_stats(d_from, t.isoformat()), problems) or {}
    by = {}
    for u in stats.get("utm", []):
        by.setdefault(u["content"], {}).setdefault(u["source"], 0)
        by[u["content"]][u["source"]] += u["hits"]
    fns = {"instagram": ig_metrics, "facebook": fb_metrics, "blogger": blogger_metrics}
    for it in lg["items"]:
        if it["date"] < d_from:
            continue
        m = it.setdefault("metrics", {})
        for p, ps in it.get("platforms", {}).items():
            if ps.get("status") == "published" and ps.get("post_id"):
                r = _try(f"{p} {it['id']}", lambda p=p, ps=ps: fns[p](ps["post_id"]), problems)
                if r is not None:
                    m[p] = r
        if stats:
            v = by.get(it["id"], {})
            m["visits"] = v
            m["visits_total"] = sum(v.values())
    snap = {"date": t.isoformat(), "site": {k: stats.get(k) for k in ("signups", "posts", "comments")} if stats else {},
            "visitors_today": next((x["visitors"] for x in stats.get("visitors", []) if x["day"] == t.isoformat()), None),
            "utm_today": [u for u in stats.get("utm", []) if u["day"] == t.isoformat()],
            "blog_pageviews_30d": _try("블로그 조회수", blog_pageviews, problems),
            "search": _try("서치콘솔", lambda: search_console((t - datetime.timedelta(days=9)).isoformat(), (t - datetime.timedelta(days=3)).isoformat()), problems),
            "problems": problems}
    save(STATE / "metrics" / f"{t.isoformat()}.json", snap)
    store.save_ledger(lg)
    store.sheet_mirror(lg)
    return snap
