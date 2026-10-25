# -*- coding: utf-8 -*-
"""작성기 전수 개선 2단계: 관리대장·중대재해처벌법 이행·점검·허가 서식에 공통 확인 도우미(qa) 설정과 연결 칸을 넣는다.

- 표 열은 '뒤에 덧붙이기'만 한다(열 번호로 저장된 사용자 입력이 어긋나지 않게).
- 같은 스크립트를 두 번 돌려도 결과가 같다(이미 있는 열·칸은 다시 넣지 않음).
실행: python3 scripts/upgrade_qa.py
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fa_io

fj = json.loads((ROOT / "data/forms.json").read_text(encoding="utf-8"))
fa = fa_io.load()
F = {f["id"]: f for f in fj["forms"]}


def sec(fid, k):
    return next(s for s in F[fid]["sections"] if s.get("k") == k)


def add_cols(fid, k, cols):
    s = sec(fid, k)
    have = [c["label"] for c in s["cols"]]
    for c in cols:
        if c["label"] not in have:
            s["cols"].append(c)
    return {c["label"]: i for i, c in enumerate(s["cols"])}


def add_field(fid, title_or_idx, field, after=None):
    for s in F[fid]["sections"]:
        if s["type"] != "fields":
            continue
        if (isinstance(title_or_idx, int) and F[fid]["sections"].index(s) == title_or_idx) or s.get("title") == title_or_idx:
            if any(f["k"] == field["k"] for f in s["fields"]):
                return
            if after:
                i = next(i for i, f in enumerate(s["fields"]) if f["k"] == after)
                s["fields"].insert(i + 1, field)
            else:
                s["fields"].append(field)
            return
    raise KeyError((fid, title_or_idx))


def qa(fid, cfg, calc=None):
    a = fa["forms"].setdefault(fid, {})
    a["qa"] = cfg
    if calc:
        old = [c for c in a.get("calc", []) if c["type"] not in {x["type"] for x in calc}]
        a["calc"] = old + calc


STATUS = ["계획", "진행", "완료", "지연", "보류"]

# ---------------------------------------------------------------- 관리대장
ix = add_cols("cert-ledger", "list", [{"label": "유효·갱신 기한", "w": 11}, {"label": "증빙(사본) 보관 위치"}])
qa("cert-ledger", {"tables": {"list": {"tools": True, "evidence": True, "csv": "자격관리대장", "req": [1, 3], "uid": [3, 4],
   "date": [5, 6, ix["유효·갱신 기한"]], "due": {"col": ix["유효·갱신 기한"], "warn": 60}}}})

ix = add_cols("edu-ledger", "list", [{"label": "이수증 보관 위치"}])
qa("edu-ledger", {"tables": {"list": {"tools": True, "evidence": True, "csv": "직무교육관리대장", "req": [1, 2], "uid": [1, 2], "date": [3, 4, 5]}}})

ix = add_cols("ppe-ledger", "list", [{"label": "사용기한·교체 예정일", "w": 11}])
ix2 = add_cols("ppe-ledger", "chk", [{"label": "다음 점검일", "w": 11}])
qa("ppe-ledger", {"tables": {
    "list": {"tools": True, "evidence": True, "csv": "보호구지급대장", "req": [1, 3, 4], "date": [1, ix["사용기한·교체 예정일"]], "num": [6], "due": {"col": ix["사용기한·교체 예정일"], "warn": 30}},
    "chk": {"tools": True, "evidence": True, "date": [0, ix2["다음 점검일"]], "due": {"col": ix2["다음 점검일"], "warn": 14}}}})

# ---------------------------------------------------------------- 중대재해처벌법 이행
# 목표 → 실행과제·예산·담당·기한·상태·증빙을 한 줄에 연결
ix = add_cols("sapa-policy", "goals", [{"label": "예산(원)", "w": 10}, {"label": "기한", "w": 10}, {"label": "상태", "w": 9, "options": STATUS}, {"label": "이행 증빙"}])
sec("sapa-policy", "goals")["title"] = "안전보건 목표 · 실행과제 (목표 → 지표 → 과제 → 담당 → 예산·기한 → 상태·증빙)"
qa("sapa-policy", {"tables": {"goals": {"tools": True, "evidence": True, "csv": "안전보건목표", "req": [1, 2, 4], "num": [ix["예산(원)"]], "date": [ix["기한"]],
   "due": {"col": ix["기한"], "warn": 30, "done": ix["상태"], "doneWords": ["완료"]}}}},
   calc=[{"type": "track", "table": "goals", "due": ix["기한"], "done": ix["상태"], "doneWords": ["완료"], "label": "실행과제"}])

ix = add_cols("sapa-budget", "rows", [{"label": "연결 목표 번호", "w": 8}, {"label": "담당", "w": 9}, {"label": "집행 기한", "w": 10}])
qa("sapa-budget", {"tables": {"rows": {"tools": True, "evidence": True, "csv": "안전보건예산", "req": [0, 1, 2], "num": [2, 3], "date": [ix["집행 기한"]],
   "due": {"col": ix["집행 기한"], "warn": 30, "done": 5}}}})

ix = add_cols("sapa-voice", "list", [{"label": "조치 기한", "w": 10}, {"label": "완료일", "w": 10}, {"label": "후속 확인(확인자·결과)"}, {"label": "제안자 회신일", "w": 10}])
sec("sapa-voice", "list")["title"] = "의견 → 개선 조치 → 후속 확인"
qa("sapa-voice", {"tables": {"list": {"tools": True, "evidence": True, "csv": "종사자의견대장", "req": [1, 3], "date": [1, ix["조치 기한"], ix["완료일"], ix["제안자 회신일"]],
   "due": {"col": ix["조치 기한"], "warn": 14, "done": ix["완료일"]}}}},
   calc=[{"type": "track", "table": "list", "due": ix["조치 기한"], "done": ix["완료일"], "label": "개선 조치"}])

s = sec("sapa-contractor", "score")
if len(s["cols"]) == 4:
    s["cols"].append({"label": "평가 기준(점수 부여 방법 — 사업장 기준으로 고쳐 쓰기)", "w": 30})
    crit = ["방침·목표 문서화 5 · 안전보건 담당자 지정 5 · 경영자 서명·게시 5",
            "최근 1년 정기평가 기록 10 · 근로자 참여·결과 공유 기록 5 · 개선 이행 확인 5",
            "정기교육 계획·실시 기록 10 · 채용 시·특별교육 기록 5",
            "최근 3년 사망재해 없음 10 · 재해 건수 감소 추세 10 (사망 발생 시 0점)",
            "작업별 안전작업 절차서 10 · 필요 장비·보호구 보유·검사 기록 10",
            "비상연락망·대응 절차 5 · 최근 1년 훈련 기록 5"]
    for i, row in enumerate(s["defaults"]):
        while len(row) < 4:
            row.append("")
        row.append(crit[i])
for fs in F["sapa-contractor"]["sections"]:
    if fs.get("title") == "평가 결과":
        for f in fs["fields"]:
            if f["k"] == "total":
                f["label"] = "총점(자동)"
            if f["k"] == "result":
                f["label"] = "최종 판정(평가자)"
add_field("sapa-contractor", "평가 결과", {"k": "cut", "label": "적격 기준 점수(사업장 기준)", "default": "80"}, after="total")
add_field("sapa-contractor", "평가 결과", {"k": "auto_judge", "label": "점수 기준 판정(자동, 참고)"}, after="cut")
qa("sapa-contractor", {"fields": {"num": ["f.cut"]}, "tables": {"score": {"num": [1, 2]}}},
   calc=[{"type": "score", "table": "score", "col": 2, "max": 1, "target": "f.total", "judge": "f.auto_judge", "cut": "f.cut", "pass": "적격", "fail": "부적격 또는 조건부(보완 요구)"}])

ix = add_cols("sapa-emergency", "check", [{"label": "다음 점검 예정일", "w": 11}])
qa("sapa-emergency", {"tables": {"check": {"date": [0, ix["다음 점검 예정일"]], "due": {"col": ix["다음 점검 예정일"], "warn": 30}}}})
qa("sapa-eval", {"progress": True})
qa("sapa-half", {"gate": {"checks": ["h"], "bad": ["미흡"], "label": "반기 점검 결과 — 경영책임자 보고 전 확인"}})

# ---------------------------------------------------------------- 점검·허가(공통 서식판)
ix = add_cols("patrol", "fix", [{"label": "담당", "w": 10}, {"label": "완료일", "w": 10}, {"label": "개선 결과"}])
qa("patrol", {"tables": {"fix": {"tools": True, "evidence": True, "date": [3, ix["완료일"]], "req": [1], "due": {"col": 3, "warn": 3, "done": ix["완료일"]}}},
   "gate": {"checks": ["chk"], "bad": ["불량"], "label": "점검 결과 — 불량 항목은 지적 사항 표로 옮겨 조치하세요"}},
   calc=[{"type": "track", "table": "fix", "due": 3, "done": ix["완료일"], "label": "지적 사항"}])
ix = add_cols("joint", "res", [{"label": "담당", "w": 10}])
qa("joint", {"tables": {"res": {"tools": True, "evidence": True, "date": [4], "req": [2], "due": {"col": 4, "warn": 7, "done": 5}}}},
   calc=[{"type": "track", "table": "res", "due": 4, "done": 5, "label": "지적 사항"}])
add_field("permit", "작업 개요", {"k": "valid", "label": "허가 유효기간(시작~종료, 연장 시 재발급)"}, after="to")
add_field("permit", "작업 개요", {"k": "scope", "label": "적용 범위(이 허가로 할 수 있는 작업·구역)", "span": 2}, after="valid")
qa("permit", {"gate": {"checks": ["pre"], "bad": ["부적합", "불량"], "need": ["f.kind", "f.place", "f.lead", "f.approver", "f.valid"], "label": "허가 승인 전 확인"},
   "gas": {"table": "gas", "o2": 1, "lel": 2, "co": 3, "h2s": 4, "lelMax": 10}, "fields": {"req": ["f.kind", "f.place", "f.valid"]}})

# 작업계획서 14종: 사전조사·작업시작 전 점검·TBM 확인을 승인 전 확인으로
for fid in F:
    if fid.startswith("wp-"):
        checks = [x["k"] for x in F[fid]["sections"] if x.get("type") == "check"]
        qa(fid, {"gate": {"checks": checks, "bad": ["보완 필요", "불량", "부적합"], "need": ["f.name", "f.place"], "label": "작업 시작 전 확인(작업계획서 승인 전)"},
                 "fields": {"req": ["f.name", "f.place", "f.leader"] if any(f["k"] == "leader" for s in F[fid]["sections"] if s["type"] == "fields" for f in s["fields"]) else ["f.name", "f.place"]}})

(ROOT / "data/forms.json").write_text(json.dumps(fj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
fa_io.save(fa)
print("ok")
