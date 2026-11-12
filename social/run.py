"""세이프플럼 SNS 자동 운영 — 실행 명령.

  python3 -m social.run plan                 오늘 주제 선정 → 원고 작성 → 검증 → 카드·표지 제작 → 대기열
  python3 -m social.run publish blogger      대기 중인 글 게시(blogger | instagram | facebook)
  python3 -m social.run collect              성과 수집
  python3 -m social.run report [YYYY-MM]     월간 보고서
  python3 -m social.run approve <ID>         보류된 글 승인 / discard <ID> 폐기
  python3 -m social.run preflight            연결 점검(게시하지 않음)
  python3 -m social.run status               현황 표

환경 변수: SOCIAL_DRY=1(게시 API 를 부르지 않음) · SOCIAL_MOCK=1(OpenAI 없이 모의 원고) · SOCIAL_NOW=2026-11-12T08:00(시험용 시각)
"""
import datetime, os, sys, traceback
from .common import cfg, now, today, log, mask, STATE, Missing, ApiError
from . import evidence as ev, compose, verify, cards, store, publish

SLOT = "abcdefgh"


def summary_out(text):
    print(text)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def used_topic_ids(lg):
    since = (now().date() - datetime.timedelta(days=cfg()["no_repeat_days"])).isoformat()
    return {i["topic_id"] for i in lg["items"] if i["date"] >= since or i["topic_id"].startswith(("law:", "bill:", "brief:"))}


def make_item(topic, item_id, titles):
    """주제 하나를 원고 → 검증 → (한 번 고쳐 쓰기) → 이미지까지 만든다."""
    item = {"id": item_id, "date": today(), "topic_id": topic["id"], "cat": topic["cat"], "risk": topic["risk"], "title": topic["title"],
            "tools": topic["tools"], "sources": topic["sources"], "created_at": now().isoformat(timespec="seconds"), "attempts": 0}
    feedback = ""
    for attempt in (1, 2):
        item["attempts"] = attempt
        item["raw"] = compose.generate(topic, feedback)
        if verify.run(item, topic, titles):
            break
        v = item["verification"]
        feedback = "\n".join(v["rule_issues"] + v["ai_issues"])[:3000]
        log(f"검증 불합격({attempt}차):", feedback[:400])
    if "blog" in item["raw"]:
        item["title"] = item["raw"]["blog"]["title"]
    c = cfg()
    v = item["verification"]
    reason = ""
    if not v["passed"]:
        reason = "검증 불합격: " + "; ".join((v["rule_issues"] + v["ai_issues"])[:6])
    elif topic.get("hold_reason"):
        reason = topic["hold_reason"]
    elif not c["auto_publish"].get(topic["risk"], False):
        reason = f"'{topic['risk']}' 등급은 자동 게시를 꺼 둠(config.json auto_publish)"
    item["status"] = "held" if reason else "queued"
    item["hold_reason"] = reason
    item["platforms"] = {p: {"status": "queued", "attempts": 0} for p, on in c["platforms"].items() if on}
    # 이미지 — 보류된 글도 만들어 둔다(승인하면 바로 나갈 수 있게)
    mdir = STATE / "media" / item_id
    if "instagram" in item["raw"]:
        specs = compose.card_specs(item)
        cards.render_all(specs, mdir)
        item["card_count"] = len(specs)
    if "blog" in item["raw"]:
        cards.render_cover(item["raw"]["blog"]["title"], ev.CAT_LABEL[item["cat"]], mdir / "cover.jpg")
    return item


def hold_issue(item):
    t = compose.flat_text(item)
    v = item["verification"]
    body = (f"**보류 사유**: {item['hold_reason']}\n\n**분야** {ev.CAT_LABEL[item['cat']]} · **주제 ID** `{item['topic_id']}` · **글 ID** `{item['id']}`\n\n"
            "이 글은 자동 게시되지 않았습니다. 내용을 확인한 뒤 이 이슈에 댓글로 답해 주세요(저장소 소유자만 가능).\n\n"
            "- `/승인` — 다음 게시 시각에 세 플랫폼에 올립니다\n- `/폐기` — 올리지 않고 닫습니다\n\n"
            + ("**걸린 점**\n" + "\n".join(f"- {x}" for x in v["rule_issues"] + v["ai_issues"]) + "\n\n" if not v["passed"] else "")
            + "**근거 출처**\n" + "\n".join(f"- {s['label']}" + (f" — {s['url']}" if s.get("url") else "") for s in item["sources"]) + "\n\n"
            + "".join(f"<details><summary>{k} 원고</summary>\n\n```\n{txt}\n```\n</details>\n\n" for k, txt in t.items()))
    return store.open_issue(f"[SNS 보류] {item['id']} {item['title'][:50]}", body, "social-hold")


def cmd_plan():
    lg = store.ledger()
    todays = [i for i in lg["items"] if i["date"] == today()]
    n = cfg()["posts_per_day"]
    if len([i for i in todays if not i.get("extra")]) >= n:
        summary_out(f"오늘({today()}) 주제 {len(todays)}건이 이미 만들어져 있습니다 — 새로 만들지 않습니다.")
        return 0
    used = used_topic_ids(lg)
    topics = ev.pick(n - len(todays), used)
    extra = ev.held_news(used) if not todays else []
    titles = [i["title"] for i in lg["items"][-400:]]
    rows, k = [], len(todays)
    for topic in topics + extra:
        item_id = today().replace("-", "") + SLOT[k]
        k += 1
        try:
            item = make_item(topic, item_id, titles)
        except Missing as e:
            summary_out(f"OpenAI 연결이 안 되어 원고를 만들 수 없습니다(없는 값: {e}). 매뉴얼 3장을 확인하세요.")
            return 0
        except Exception as e:
            store.error("plan", item_id, e)
            store.error_issue(f"{today()} 원고 작성 실패 ({topic['id']})", f"```\n{mask(e)[:1200]}\n```\n다음 예약 실행 때 다른 주제로 다시 시도합니다.")
            continue
        if topic in extra:
            item["extra"] = True
        if item["status"] == "held":
            item["issue"] = hold_issue(item)
        store.save_item(item)
        store.upsert(lg, item)
        if item.get("extra"):
            lg["items"][-1]["extra"] = True
        titles.append(item["title"])
        rows.append(f"| {item['id']} | {ev.CAT_LABEL[item['cat']]} | {item['title'][:44]} | {'대기' if item['status'] == 'queued' else '보류'} | {item['hold_reason'][:70]} |")
    store.save_ledger(lg)
    summary_out(f"### {today()} 주제 선정·원고 작성\n\n| ID | 분야 | 제목 | 상태 | 보류 사유 |\n|---|---|---|---|---|\n" + "\n".join(rows))
    return 0


def cmd_publish(platform):
    c = cfg()
    lg = store.ledger()
    limit = (now() - datetime.timedelta(hours=c["retry"]["give_up_hours"])).strftime("%Y-%m-%d")
    rows, failed = [], 0
    for s in lg["items"]:
        ps = s.get("platforms", {}).get(platform)
        if not ps or s["status"] != "queued" or ps["status"] not in ("queued", "failed"):
            continue
        if s["date"] < limit:                                   # 이틀 넘게 못 올린 글은 포기(묵은 글이 뒤늦게 올라가지 않게)
            ps.update(status="skipped", error=(ps.get("error") or "") + " · 기한 초과로 건너뜀")
            continue
        if ps["attempts"] >= c["retry"]["max_attempts"]:
            continue
        if not publish.connected(platform) and os.environ.get("SOCIAL_DRY") != "1":
            rows.append(f"| {s['id']} | 미연결 | {platform} 비밀값이 아직 없습니다 |")
            continue
        item = store.load_item(s["id"])
        ps["attempts"] += 1
        try:
            pid, url = publish.PUBLISHERS[platform](item)
            if pid == "dry":
                ps["attempts"] -= 1
                rows.append(f"| {s['id']} | 드라이런 | 게시하지 않음 |")
                continue
            ps.update(status="published", post_id=pid, url=url, at=now().isoformat(timespec="seconds"), error="")
            rows.append(f"| {s['id']} | 게시 완료 | {url} |")
        except Missing as e:
            ps["attempts"] -= 1
            rows.append(f"| {s['id']} | 미연결 | 없는 값: {e} |")
            continue
        except Exception as e:
            failed += 1
            rec = store.error(f"publish:{platform}", s["id"], e)
            ps.update(status="failed", error=rec["error"][:300])
            left = c["retry"]["max_attempts"] - ps["attempts"]
            rows.append(f"| {s['id']} | 실패({ps['attempts']}회) | {rec['error'][:120]} |")
            auth = getattr(e, "status", None) in (401, 403) or "OAuthException" in str(e) or "invalid_grant" in str(e)
            if left <= 0 or auth:
                store.error_issue(f"{platform} 게시 실패 — {s['id']} {s['title'][:40]}",
                                  f"```\n{rec['error'][:1200]}\n```\n" + ("토큰·권한 문제로 보입니다. 매뉴얼의 해당 플랫폼 장에서 토큰을 다시 발급해 Secret 을 바꿔 주세요.\n" if auth else "")
                                  + (f"자동 재시도 {left}회 남음." if left > 0 else "자동 재시도를 모두 썼습니다. 원인을 고친 뒤 Actions 에서 수동 실행하면 `retry` 입력으로 다시 시도합니다."))
        item["platforms"][platform] = ps
        store.save_item(item)
    for s in lg["items"]:                                       # 세 플랫폼이 모두 끝난 글은 완료 처리
        if s["status"] == "queued" and all(p["status"] in ("published", "skipped") for p in s["platforms"].values()):
            s["status"] = "done"
    store.save_ledger(lg)
    store.sheet_mirror(lg)
    summary_out(f"### {platform} 게시 ({now().strftime('%Y-%m-%d %H:%M')} KST)\n\n| ID | 결과 | 주소·사유 |\n|---|---|---|\n" + ("\n".join(rows) or "| - | 게시할 글 없음 | |"))
    return 1 if failed else 0


def cmd_decide(item_id, action):
    lg = store.ledger()
    for s in lg["items"]:
        if s["id"] == item_id:
            if s["status"] != "held":
                summary_out(f"{item_id} 는 보류 상태가 아닙니다(현재 {s['status']}).")
                return 0
            item = store.load_item(item_id)
            new = "queued" if action == "approve" else "discarded"
            for x in (s, item):
                x["status"] = new
                x["decided_at"] = now().isoformat(timespec="seconds")
            if action == "approve":
                s["date"] = item["date"] = today()            # 승인한 날 기준으로 게시 기한을 다시 센다
            store.save_item(item)
            store.save_ledger(lg)
            if s.get("issue"):
                store.gh("issue", "close", str(s["issue"]), "--comment", "승인했습니다. 다음 게시 시각에 올라갑니다." if action == "approve" else "폐기했습니다.")
            summary_out(f"{item_id} → {'승인(대기열)' if action == 'approve' else '폐기'}")
            return 0
    summary_out(f"{item_id} 를 장부에서 찾지 못했습니다.")
    return 1


def cmd_retry():
    """실패 횟수를 0 으로 되돌려 다음 게시 실행에서 다시 시도하게 한다."""
    lg = store.ledger()
    n = 0
    for s in lg["items"]:
        for p in s.get("platforms", {}).values():
            if p["status"] == "failed":
                p["attempts"] = 0
                n += 1
        if s["status"] == "queued":
            s["date"] = max(s["date"], today())
    store.save_ledger(lg)
    summary_out(f"실패한 게시 {n}건의 재시도 횟수를 초기화했습니다.")
    return 0


def cmd_status():
    lg = store.ledger()
    rows = []
    for s in lg["items"][-14:]:
        p = s.get("platforms", {})
        rows.append(f"| {s['id']} | {ev.CAT_LABEL.get(s['cat'], s['cat'])} | {s['title'][:36]} | {s['status']} | " + " | ".join(p.get(x, {}).get("status", "-") for x in store.PLATFORMS) + f" | {s.get('metrics', {}).get('visits_total', '')} |")
    summary_out("### 최근 14건\n\n| ID | 분야 | 제목 | 상태 | 블로그 | 인스타 | 페이스북 | 유입 |\n|---|---|---|---|---|---|---|---|\n" + "\n".join(rows))
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        if cmd == "plan":
            return cmd_plan()
        if cmd == "publish":
            return cmd_publish(argv[2])
        if cmd in ("approve", "discard"):
            return cmd_decide(argv[2], cmd)
        if cmd == "retry":
            return cmd_retry()
        if cmd == "collect":
            from . import metrics
            snap = metrics.collect()
            summary_out(f"### 성과 수집 {snap['date']}\n\n- 오늘 방문자: {snap.get('visitors_today')}\n- 오늘 SNS 유입 기록: {len(snap.get('utm_today') or [])}줄\n"
                        + ("- 수집하지 못한 항목:\n" + "\n".join(f"  - {p}" for p in snap["problems"]) if snap["problems"] else "- 모든 항목 수집 완료"))
            return 0
        if cmd == "report":
            from . import report
            month, text = report.build(argv[2] if len(argv) > 2 and argv[2] else None)
            store.open_issue(f"[SNS 월간 보고서] {month}", text[:60000], "social-report")
            summary_out(text)
            return 0
        if cmd == "preflight":
            rows = publish.preflight()
            summary_out("### 연결 점검\n\n| 서비스 | 상태 | 내용 |\n|---|---|---|\n" + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows))
            return 0
        if cmd == "status":
            return cmd_status()
        print(__doc__)
        return 2
    except Exception as e:
        store.error(cmd, "", e)
        log(mask(traceback.format_exc())[-1500:])
        store.error_issue(f"`{cmd}` 실행 중단", f"```\n{mask(e)[:1200]}\n```")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
