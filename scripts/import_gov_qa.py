# -*- coding: utf-8 -*-
"""고용노동부 질의회시(중앙부처 1차 해석) 원자료 → data/gov_qa.json

원자료: 국가법령정보센터(law.go.kr) '중앙부처 1차 해석' 중 고용노동부, 본문 검색어 '산업안전보건법'.
        법제처가 공공데이터로 개방한 자료(공공누리 제1유형: 출처표시)이며, 브라우저에서 목록·본문을 받아 JSON 으로 저장한 것.
사용법: python3 scripts/import_gov_qa.py 원자료.json
- 같은 안건명·같은 회신일의 중복 글은 하나만 남긴다(본문이 긴 쪽).
- 주제는 안건명·질의요지의 낱말로 나눈다(자동 분류 — 화면에 '자동 분류'라고 밝힌다).
- 질의·회답 본문은 고치지 않고 줄바꿈만 넣는다.
"""
import json, re, sys, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFI = "350101"  # 고용노동부

# 주제: (이름, 낱말들). 위에서부터 먼저 맞는 것으로 정한다.
TOPICS = [
    ("공정안전보고서(PSM)", ["공정안전보고서", "공정안전관리", "PSM", "공정안전 보고서"]),
    ("유해위험방지계획서", ["유해위험방지계획서", "유해·위험방지계획서", "유해ㆍ위험방지계획서", "유해·위험 방지계획서", "방지계획서"]),
    ("중대재해·재해보고", ["중대재해", "산업재해조사표", "재해 발생 보고", "재해발생보고", "산재 발생", "산업재해 발생", "재해조사", "산업재해 기록", "재해율"]),
    ("위험성평가", ["위험성평가", "위험성 평가"]),
    ("안전보건교육", ["교육", "강사", "이수"]),
    ("선임·안전보건관리체제", ["안전관리자", "보건관리자", "안전보건관리책임자", "관리감독자", "안전보건관리담당자", "산업보건의", "선임", "겸직", "전담", "대행", "위탁", "안전관리전문기관", "보건관리전문기관", "안전보건총괄책임자"]),
    ("산업안전보건위원회·협의체", ["산업안전보건위원회", "노사협의체", "협의체", "노사협의회", "명예산업안전감독관", "안전보건관리규정"]),
    ("도급·건설", ["도급", "수급인", "하청", "발주", "건설", "공사", "산업안전보건관리비", "안전관리비", "유해위험방지계획서", "기술지도", "타워크레인"]),
    ("기계·설비·인증검사", ["안전인증", "자율안전", "안전검사", "방호", "크레인", "리프트", "프레스", "지게차", "압력용기", "컨베이어", "기계", "설비", "곤돌라", "승강기", "고소작업대", "비계", "추락", "사다리", "전기"]),
    ("화학물질·MSDS·작업환경", ["물질안전보건자료", "MSDS", "msds", "경고표지", "화학물질", "유해물질", "작업환경측정", "국소배기", "석면", "허용기준", "노출기준", "공정안전", "PSM", "분진", "소음", "밀폐공간", "가스"]),
    ("건강진단·보건", ["건강진단", "건강검진", "특수검진", "배치전", "근골격계", "직무스트레스", "휴게", "보건조치", "질병", "건강관리", "폭염", "온열", "보호구"]),
]
TOOL_LINKS = {
    "공정안전보고서(PSM)": [("tools/msds/", "MSDS 관리 · 경고표지"), ("tools/permit/", "안전작업허가서 작성기"), ("tools/law-register/", "법규 등록대장")],
    "유해위험방지계획서": [("tools/hpp/", "유해위험방지계획서 대상 진단"), ("tools/law-register/", "법규 등록대장")],
    "중대재해·재해보고": [("tools/forms/accident/", "산업재해·아차사고 조사 기록"), ("resources/f/form-accident-report/", "산업재해조사표 서식")],
    "위험성평가": [("tools/risk/", "위험성평가서 작성기"), ("tools/tbm/", "TBM 일지 작성기")],
    "안전보건교육": [("tools/edu-hours/", "법정교육 시간 조회"), ("tools/edu-log/", "안전보건교육 일지 작성기")],
    "선임·안전보건관리체제": [("tools/selection/", "산안법·중처법 적용범위 판정"), ("tools/duties/", "안전보건 관계자 직무·책임 조회"), ("tools/headcount/", "상시근로자 수 계산기")],
    "산업안전보건위원회·협의체": [("tools/committee/", "산업안전보건위원회 문서 작성기"), ("tools/council/", "안전보건 협의체 회의록 작성기")],
    "도급·건설": [("tools/joint/", "합동 안전·보건점검 작성기"), ("tools/safety-cost/", "산업안전보건관리비 계산기"), ("tools/hpp/", "유해위험방지계획서 대상 진단")],
    "기계·설비·인증검사": [("tools/machines/", "기계·기구 법정 의무 조회"), ("tools/inspect/", "안전검사 대상·다음 검사일"), ("tools/gear-cert/", "보호구·방호장치 인증 확인")],
    "화학물질·MSDS·작업환경": [("tools/msds/", "MSDS 관리 · 경고표지"), ("tools/confined/", "밀폐공간 가스농도 측정 기록")],
    "건강진단·보건": [("tools/cvd/", "뇌·심혈관질환 발병위험도 평가"), ("tools/heat/", "폭염작업 체감온도 기록")],
    "기타": [("tools/law-ai/", "법령 AI 질문"), ("laws/act/", "산업안전보건법 전문")],
}


def tidy(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    # 번호·글머리 앞에서 줄을 바꾼다(본문 낱말은 고치지 않는다)
    # '…입니다. 2. …' 는 나누고, 날짜('99. 7. 6일)는 건드리지 않는다
    s = re.sub(r"(?<=[다요음됨함임까]\.)\s*(?=\d{1,2}\.\s*\D)", "\n", s)
    s = re.sub(r"(?<=[^\s○●□△])\s*(?=[○●□■▶※①-⑳](?![○△□]))", "\n", s)  # '○○의원' 같은 가림 표시는 나누지 않음
    s = re.sub(r"(?<=[다요음됨함임까]\.)\s*(?=- )", "\n", s)
    # '…드립니다1) …?2) …' 처럼 붙어 있는 번호 질문을 나눈다('1)' 앞이 문장 끝일 때만)
    s = re.sub(r"(?<=[다요까?？])\s*(?=\(?\d{1,2}\)\s*\S)", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def topic(t, q):
    txt = t + " " + q[:300]
    head = t + " " + q[:150]  # PSM·유해위험방지계획서는 앞부분에 나올 때만(본문 뒤쪽에 지나가듯 나온 글은 다른 주제로)
    for name, kws in TOPICS:
        if name in ("공정안전보고서(PSM)", "유해위험방지계획서"):
            if any(k in head for k in kws):
                return name
            continue
        if any(k in txt for k in kws):
            return name
    return "기타"


def main(src):
    raw = json.load(open(src, encoding="utf-8"))
    items = raw["items"] if isinstance(raw, dict) else raw
    best = {}
    for x in items:
        t = re.sub(r"\s+", " ", x.get("t", "")).strip()
        if not t or not (x.get("q") or x.get("a")):
            continue
        k = (re.sub(r"\W", "", t), x.get("d", ""))
        if k not in best or len(x.get("a", "")) > len(best[k].get("a", "")):
            best[k] = x
    out = []
    for x in best.values():
        t = re.sub(r"\s+", " ", x["t"]).strip()
        q, a = tidy(x.get("q", "")), tidy(x.get("a", ""))
        d = x.get("d", "") if re.match(r"^\d{4}-\d{2}-\d{2}$", x.get("d", "")) else ""
        out.append({"id": str(x["id"]), "t": t, "d": d, "c": topic(t, q), "q": q, "a": a, "l": re.sub(r"\s+", " ", x.get("l", "")).strip()})
    out.sort(key=lambda x: (x["d"] or "0000", x["id"]), reverse=True)
    meta = {"source": "국가법령정보센터 중앙부처 1차 해석 — 고용노동부(본문 검색어: 산업안전보건법)",
            "license": "공공누리 제1유형(출처표시) — 법제처가 공공데이터로 개방",
            "src_url": "https://www.law.go.kr/LSW/cgmExpcSc.do?menuId=11&subMenuId=729&tabMenuId=733&upperOfiClsCd=010501&ofiClsCd=" + OFI,
            "item_url": "https://www.law.go.kr/LSW/cgmExpcInfoP.do?mode=9&cgmExpcDatSeq={id}&ofiClsCd=" + OFI,
            "collected": (raw.get("collected", "") if isinstance(raw, dict) else "")[:10],
            "topics": [n for n, _ in TOPICS] + ["기타"], "tools": TOOL_LINKS}
    (ROOT / "data/gov_qa.json").write_text(json.dumps({"checked": meta["collected"], "meta": meta, "items": out}, ensure_ascii=False, indent=0), encoding="utf-8")
    c = collections.Counter(x["c"] for x in out)
    print(len(items), "→", len(out), dict(c))


if __name__ == "__main__":
    main(sys.argv[1])
