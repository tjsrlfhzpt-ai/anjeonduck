#!/usr/bin/env python3
"""구글 스프레드시트(웹에 게시한 CSV) → data/*.json 변환.

- 서버 없이 사이트 내용을 고치는 통로: 시트를 고치면 다음 빌드 때 반영된다.
- 시트를 못 읽으면(네트워크 오류, 비공개 전환 등) 기존 JSON을 그대로 두고 경고만 남긴다.
  → 시트 장애로 사이트가 빈 화면이 되는 일을 막기 위함.
- 행 수가 기존보다 50% 넘게 줄면 실수로 지운 것으로 보고 반영하지 않는다(--force로 무시 가능).
"""
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORCE = "--force" in sys.argv


def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "anjeonduck-sync"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8-sig")
    if raw.lstrip().startswith("<"):
        raise ValueError("CSV가 아니라 HTML이 왔습니다(게시 안 됨 또는 로그인 필요)")
    rows = [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(io.StringIO(raw))]
    return [r for r in rows if any(r.values()) and "example.com" not in r.get("source_url", "") + r.get("url", "")]


def safe_write(path, new, label):
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    old_n = len(old["updates"]) if isinstance(old, dict) else len(old)
    new_n = len(new["updates"]) if isinstance(new, dict) else len(new)
    if old_n >= 4 and new_n < old_n * 0.5 and not FORCE:
        print(f"  {label}: {old_n}건 → {new_n}건으로 급감 — 반영 보류(--force 로 강제)")
        return
    path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {label}: {new_n}건 반영")


# 구글 설문지 응답 시트 → 채용공고. 질문 제목에 아래 낱말이 들어 있으면 그 칸으로 읽는다(순서대로 먼저 맞는 것).
POST_COLS = [("승인", "approved"), ("요청", "req"), ("타임스탬프", "ts"), ("Timestamp", "ts"), ("회사", "company"), ("제목", "title"),
             ("기업분류", "company_type"), ("업종", "industry"), ("직무", "job"), ("근무지", "region"), ("경력", "career"),
             ("고용형태", "employment"), ("마감", "deadline"), ("원문", "source_url"), ("지원 방법", "apply"), ("요약", "summary"),
             ("주요 업무", "duties"), ("자격", "requirements")]
LIMITS = {"company": 60, "title": 80, "company_type": 20, "industry": 30, "job": 40, "region": 40, "career": 40, "employment": 20,
          "apply": 200, "summary": 200, "duties": 600, "requirements": 600}
YES = {"y", "yes", "true", "1", "o", "ㅇ", "예", "승인", "게시"}


def map_post(row):
    out = {}
    for head, val in row.items():
        for word, key in POST_COLS:
            if word in head and key not in out:
                out[key] = val
                break
    return out


def norm_deadline(v):
    v = v.strip()
    m = re.match(r"^(\d{4})[.\-/ ]+\s*(\d{1,2})[.\-/ ]+\s*(\d{1,2})", v)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return v if v in ("상시", "채용 시") else ""


def job_posts(rows):
    """승인 칸에 표시된 '신규' 요청만 공고로 만든다. 승인 전·수정·삭제 요청 행은 사이트에 나가지 않는다."""
    out, skipped = [], 0
    for row in rows:
        r = map_post(row)
        if r.get("approved", "").strip().lower() not in YES or ("수정" in r.get("req", "") or "삭제" in r.get("req", "")):
            skipped += 1
            continue
        if not r.get("company") or not r.get("title"):
            skipped += 1
            continue
        j = {k: re.sub(r"\s*[\r\n]+\s*", "|", r.get(k, "").strip())[:n] for k, n in LIMITS.items()}
        url = r.get("source_url", "").strip()
        j["source_url"] = url if url.startswith("https://") else ""
        if not j["source_url"] and url and not j["apply"]:
            j["apply"] = url[:200]
        j["deadline"] = norm_deadline(r.get("deadline", ""))
        m = re.match(r"^(\d{4})[.\-/ ]+\s*(\d{1,2})[.\-/ ]+\s*(\d{1,2})", r.get("ts", ""))
        j["posted"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
        j["id"] = "u-" + hashlib.sha1((r.get("ts", "") + "|" + j["company"] + "|" + j["title"]).encode("utf-8")).hexdigest()[:10]
        j["source_name"] = "기업 직접 등록"
        out.append(j)
    print(f"  직접 등록 공고: 승인 {len(out)}건 / 미승인·요청·형식 미달 {skipped}건")
    return out


def main():
    src = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
    ok = True
    if src.get("jobs_csv"):
        try:
            safe_write(ROOT / "data/jobs.json", fetch_csv(src["jobs_csv"]), "채용")
        except Exception as ex:  # noqa: BLE001
            ok = False
            print(f"  채용 시트 읽기 실패 — 기존 데이터 유지: {ex}")
    posts_url = os.environ.get("JOB_POSTS_CSV") or src.get("job_posts_csv")
    if posts_url:
        try:
            # 승인 취소·마감 정리로 건수가 줄어드는 것이 정상이라 급감 보호를 쓰지 않는다
            (ROOT / "data/job_posts.json").write_text(json.dumps(job_posts(fetch_csv(posts_url)), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as ex:  # noqa: BLE001
            ok = False
            print(f"  직접 등록 공고 시트 읽기 실패 — 기존 데이터 유지: {ex}")
    if src.get("law_updates_csv"):
        try:
            laws_path = ROOT / "data/laws.json"
            laws = json.loads(laws_path.read_text(encoding="utf-8"))
            laws["updates"] = fetch_csv(src["law_updates_csv"])
            safe_write(laws_path, laws, "법령 개정 소식")
        except Exception as ex:  # noqa: BLE001
            ok = False
            print(f"  법령 시트 읽기 실패 — 기존 데이터 유지: {ex}")
    if src.get("resources_csv"):
        try:
            rows = fetch_csv(src["resources_csv"])
            for r in rows:
                r["tags"] = [t for t in r.get("tags", "").split("|") if t]
                r["popular"] = r.get("popular", "").lower() in ("true", "1", "y", "예")
            safe_write(ROOT / "data/resources.json", rows, "서식·자료")
        except Exception as ex:  # noqa: BLE001
            ok = False
            print(f"  자료 시트 읽기 실패 — 기존 데이터 유지: {ex}")
    if not posts_url and not any(src.get(k) for k in ("jobs_csv", "law_updates_csv", "resources_csv")):
        print("  시트 주소가 설정되지 않음 — data/*.json 그대로 사용")
    # 시트 실패는 빌드를 막지 않는다(기존 데이터로 계속 배포)
    return 0 if ok else 0


if __name__ == "__main__":
    sys.exit(main())
