"""게시 이력(장부)·대기열·오류 기록 — social-data 브랜치(_social/ 폴더)에 JSON 으로 둔다.

장부가 유일한 원본이다. 구글 시트는 선택 사항인 '보기용 사본'이고, 시트가 고장 나도 게시는 멈추지 않는다.
  state/ledger.json   글 한 건당 한 줄 요약(주제·검증 결과·플랫폼별 상태·게시 주소·성과)
  queue/<id>.json     글 전문(AI 원고, 근거 출처, 링크)
  media/<id>/*.jpg    카드뉴스·블로그 표지
  logs/errors.jsonl   오류 기록
  ledger.csv          장부를 표로 본 것(깃허브에서 바로 열림)
"""
import csv, io, json, os, subprocess
from .common import STATE, load, save, now, today, log, mask, env, http, cfg, Missing

LEDGER = STATE / "state" / "ledger.json"
PLATFORMS = ("blogger", "instagram", "facebook")


def ledger():
    return load(LEDGER, {"items": []})


def save_ledger(lg):
    save(LEDGER, lg)
    cols = ["id", "date", "cat", "risk", "status", "title", "topic_id", "hold_reason"] + [f"{p}_{k}" for p in PLATFORMS for k in ("status", "url", "at", "error")]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for it in lg["items"]:
        row = [it.get(c, "") for c in cols[:8]]
        for p in PLATFORMS:
            ps = it.get("platforms", {}).get(p, {})
            row += [ps.get("status", ""), ps.get("url", ""), ps.get("at", ""), (ps.get("error") or "")[:120]]
        w.writerow(row)
    (STATE / "ledger.csv").write_text("﻿" + buf.getvalue(), encoding="utf-8")


def queue_path(item_id):
    return STATE / "queue" / f"{item_id}.json"


def load_item(item_id):
    return load(queue_path(item_id))


def save_item(item):
    save(queue_path(item["id"]), item)


def summary(item):
    return {"id": item["id"], "date": item["date"], "cat": item["cat"], "risk": item["risk"], "status": item["status"], "title": item["title"],
            "topic_id": item["topic_id"], "hold_reason": item.get("hold_reason", ""), "issue": item.get("issue"),
            "platforms": item["platforms"], "verification": {"passed": item["verification"]["passed"], "claims_checked": item["verification"].get("claims_checked", 0)},
            "metrics": item.get("metrics", {})}


def upsert(lg, item):
    s = summary(item)
    for i, it in enumerate(lg["items"]):
        if it["id"] == s["id"]:
            lg["items"][i] = s
            return
    lg["items"].append(s)


def error(where, item_id, exc):
    p = STATE / "logs" / "errors.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": now().isoformat(timespec="seconds"), "where": where, "item": item_id, "error": mask(exc)[:1500],
           "status": getattr(exc, "status", None), "retryable": getattr(exc, "retryable", None)}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log("오류 기록:", where, item_id, rec["error"][:300])
    return rec


# ---------------------------------------------------------------- 운영자 알림(깃허브 이슈)
def gh(*args, input_text=None):
    """gh CLI. 깃허브 실행 환경 밖(토큰 없음)이면 아무것도 하지 않는다."""
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")) or os.environ.get("SOCIAL_DRY") == "1":
        log("(알림 생략) gh", " ".join(args)[:120])
        return ""
    try:
        r = subprocess.run(["gh", *args], input=input_text, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            log("gh 실패:", r.stderr[:300])
        return r.stdout.strip()
    except Exception as e:                      # 알림 실패가 게시를 막으면 안 된다
        log("gh 실행 실패:", e)
        return ""


def open_issue(title, body, label):
    gh("label", "create", label, "--force", "--color", "B60205" if "error" in label else "FBCA04")
    out = gh("issue", "create", "--title", title, "--body-file", "-", "--label", label, input_text=body)
    return out.rsplit("/", 1)[-1] if out.startswith("http") else None


def error_issue(title, body):
    """오류 알림은 열린 이슈 하나에 댓글로 쌓는다(같은 오류로 이슈가 수십 개 생기지 않게)."""
    num = gh("issue", "list", "--label", "social-error", "--state", "open", "--json", "number", "--jq", ".[0].number // empty")
    if num:
        gh("issue", "comment", num, "--body-file", "-", input_text=f"### {title}\n\n{body}")
    else:
        open_issue("[SNS 자동 운영] 오류 알림", f"### {title}\n\n{body}\n\n해결되면 이 이슈를 닫아 주세요. 새 오류가 생기면 다시 열립니다.", "social-error")


# ---------------------------------------------------------------- 구글 시트 사본(선택)
def sheet_mirror(lg):
    sid = env("SOCIAL_SHEET_ID")
    if not sid or os.environ.get("SOCIAL_DRY") == "1":
        return
    try:
        from .publish import google_token
        rows = [["ID", "날짜", "분야", "등급", "상태", "제목", "보류 사유", "블로그", "블로그 주소", "인스타", "인스타 주소", "페이스북", "페이스북 주소", "유입(전체)"]]
        for it in lg["items"][-1000:]:
            p = it.get("platforms", {})
            rows.append([it["id"], it["date"], it["cat"], it["risk"], it["status"], it["title"], it.get("hold_reason", ""),
                         p.get("blogger", {}).get("status", ""), p.get("blogger", {}).get("url", ""), p.get("instagram", {}).get("status", ""), p.get("instagram", {}).get("url", ""),
                         p.get("facebook", {}).get("status", ""), p.get("facebook", {}).get("url", ""), it.get("metrics", {}).get("visits_total", "")])
        h = {"Authorization": "Bearer " + google_token()}
        base = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/"
        http("POST", base + "A:N:clear", headers=h, json_body={})
        http("PUT", base + "A1", headers=h, params={"valueInputOption": "RAW"}, json_body={"values": rows})
    except Missing:
        pass
    except Exception as e:
        log("구글 시트 사본 갱신 실패(게시에는 영향 없음):", mask(e)[:200])
