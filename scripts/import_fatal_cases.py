"""중대재해 사고백서(2023~2025년 발간) 부록 '사망사고 일람'(2022~2024년 사망사고 1,748건) 정리본(엑셀)을 data/fatal_cases.json 으로 옮긴다.
실행: python3 scripts/import_fatal_cases.py 정리본.xlsx  (시트 '사망사고 원자료(22-24)')
- 연도·업종별 건수/사망자 수는 고용노동부가 공표한 연도별 재해조사 대상 사고사망(2022 611건 644명, 2023 584건 598명, 2024 553건 589명)과 같은지 확인한다.
- 재해 유형은 SafePlum이 재해개요 낱말로 나눈 것(원문 분류 아님)."""
import json, re, sys, collections
from pathlib import Path
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = {"2022": (611, 644), "2023": (584, 598), "2024": (553, 589)}
FIX = [("추 락", "추락"), ("차 량계", "차량계"), ("중 량물", "중량물"), ("작 업", "작업"), ("사 다리", "사다리"), ("정 비", "정비"), ("L OTO", "LOTO"), ("T ag", "Tag")]
TYPES = [  # 위에서부터 먼저 맞는 것
    ("질식·중독", r"질식|중독|산소결핍|황화수소|일산화탄소"),
    ("화재·폭발", r"폭발|화재|화염|화상|불꽃|인화"),
    ("감전", r"감전|전기에 접촉|충전부"),
    ("끼임", r"끼[여임이었]|끼어|협착|말려"),
    ("무너짐", r"무너|붕괴|매몰|도괴"),
    ("떨어짐", r"떨어[져짐졌]|추락|실족"),
    ("깔림", r"깔[려림렸]|전도되[는며어]|넘어[지진져]+.*(깔|맞)"),
    ("맞음", r"맞[아음았]|낙하|날아"),
    ("부딪힘", r"부딪|충돌|치[여임었]|받[혀힘]"),
    ("넘어짐", r"넘어[져짐졌]|미끄러"),
    ("절단·베임", r"절단|베[여임]|잘[려림]"),
    ("물에 빠짐·잠수", r"익사|물에 빠|바다에 빠|바다로 빠|잠수"),
    ("온열·질병", r"더위|온열|열사병|열탈진|쓰러[짐져]$"),
]


def kind(txt):
    for name, pat in TYPES:
        if re.search(pat, txt):
            return name
    return "기타"


def clean(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    for a, b in FIX:
        s = s.replace(a, b)
    return s


def main(src):
    wb = openpyxl.load_workbook(src, data_only=True, read_only=True)
    rows = [r for r in list(wb["사망사고 원자료(22-24)"].iter_rows(values_only=True))[3:] if r and r[0]]
    out = []
    for r in rows:
        y, no, md, reg, ind_raw, grp, dead, desc, meas = r[:9]
        sub = re.search(r"\(([^)]+)\)", str(ind_raw or ""))
        sub = re.sub(r"\s+", "", sub.group(1)).replace(",", ", ") if sub else ""
        g = {"제조": "제조", "건설": "건설"}.get(str(grp), "기타")
        m = [x.strip(" •·-") for x in re.split(r"\s*•\s*", clean(meas)) if x.strip(" •·-")]
        out.append({"y": str(y), "n": int(no), "d": f"{y}-{md}" if re.match(r"^\d\d-\d\d$", str(md)) else str(y), "r": clean(reg), "g": g, "s": sub,
                    "k": kind(clean(desc)), "dead": int(dead or 1), "t": clean(desc), "m": m})
    # 공표 통계와 대조
    by = collections.defaultdict(lambda: [0, 0])
    for x in out:
        by[x["y"]][0] += 1; by[x["y"]][1] += x["dead"]
    for y, (n, dd) in OFFICIAL.items():
        assert tuple(by[y]) == (n, dd), (y, by[y], (n, dd))
    meta = {"title": "중대재해 사고백서 부록 사망사고 일람(2022~2024년)",
            "source": "고용노동부 「중대재해 사고백서」(2023·2024·2025년 발간) 부록 사망사고 일람 — 이용자가 보내 준 정리본을 SafePlum이 옮김",
            "check": "연도별 건수·사망자 수가 고용노동부 공표 재해조사 대상 사고사망(2022년 611건 644명, 2023년 584건 598명, 2024년 553건 589명)과 일치함을 확인",
            "note": "재해개요·예방대책 문구는 백서 일람의 요약이며 사고 조사 결론이 아닙니다. 재해 유형은 SafePlum이 개요 낱말로 자동 분류한 것입니다.",
            "checked": "2026-11-03"}
    (ROOT / "data/fatal_cases.json").write_text(json.dumps({"checked": meta["checked"], "meta": meta, "items": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(len(out), dict(collections.Counter(x["g"] for x in out)), collections.Counter(x["k"] for x in out).most_common())


if __name__ == "__main__":
    main(sys.argv[1])
