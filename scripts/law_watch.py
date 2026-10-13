#!/usr/bin/env python3
"""법령 변경 자동 감지 — 국가법령정보센터 OPEN API(시행일 법령 목록)로 새 공포번호를 찾는다.

  LAW_OC=<인증키> python3 scripts/law_watch.py [--dry-run] [--report 경로]

- data/law_manifest.json 의 법령마다 시행 예정·현행 목록을 받아, 매니페스트(current·upcoming·recent)와
  data/laws.json 개정 소식 어디에도 없는 공포번호가 있으면 laws.json updates 맨 앞에 '확인 필요' 항목을 넣는다.
- 항목에는 API 목록에서 읽은 사실(공포번호·공포일·시행일·제개정 구분)만 적는다. 개정 내용은 적지 않는다.
- law_manifest.json·lawtext 등 다른 파일은 고치지 않는다. 법령 본문 갱신은 운영자가 한다.
- 법령 하나라도 조회에 실패하면 결과에 '확인 못 함'으로 남기고 failed 수를 GITHUB_OUTPUT 에 쓴다.
  (조회 실패를 '변경 없음'으로 보고하지 않는다.)
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://www.law.go.kr/DRF/lawSearch.do"
KST = dt.timezone(dt.timedelta(hours=9))
VERIFY = "자동 감지 — 공포번호와 시행일만 확인했습니다. 개정 내용은 원문에서 확인하세요."
NW = ("2", "3")  # 시행일 법령 목록의 nw: 2=시행예정, 3=현행


class ApiError(Exception):
    pass


def iso(yyyymmdd):
    s = re.sub(r"\D", "", str(yyyymmdd or ""))
    if len(s) != 8:
        raise ApiError(f"날짜 형식이 예상과 다름: {yyyymmdd!r}")
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def dotted(d):
    y, m, dd = d.split("-")
    return f"{int(y)}. {int(m)}. {int(dd)}."


def fetch(oc, name, nw):
    q = urllib.parse.urlencode({"OC": oc, "target": "eflaw", "type": "XML", "query": name,
                                "display": 100, "nw": nw})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "anjeonduck-law-watch/1.0"})
    last = None
    for attempt in range(2):  # 일시 오류에 한 번만 재시도
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as ex:  # 인증키가 URL에 있으므로 주소는 로그에 남기지 않는다
            last = ex
            time.sleep(3)
    raise ApiError(f"접속 실패({type(last).__name__})")


def parse(xml_text):
    """목록 XML → [{공포번호, 공포일자, 시행일자, ...}]. 형식이 예상과 다르면 ApiError."""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml_text))[:120]
        raise ApiError(f"XML이 아닌 응답(인증 실패·미승인 가능): {snippet.strip()}")
    rows = []
    for el in root.iter():
        if el.find("공포번호") is not None:
            rows.append({c.tag: (c.text or "").strip() for c in el})
    return root, rows


def known_numbers(law, updates):
    nums = set()
    for k in ("current",):
        if law.get(k):
            nums.update(re.findall(r"제(\d+)호", law[k].get("no", "")))
    for k in ("upcoming", "recent"):
        for e in law.get(k) or []:
            nums.update(re.findall(r"제(\d+)호", e.get("no", "")))
    for u in updates:
        if u.get("law") == law["name"]:
            nums.update(re.findall(r"제(\d+)호", u.get("title", "")))
            m = re.match(r"^[a-z_]+-(\d+)-", u.get("id", ""))
            if m:
                nums.add(m.group(1))
    return {str(int(n)) for n in nums}


def check_law(oc, law, updates):
    """반환: (새 항목 목록, 메모). 실패하면 ApiError."""
    rows, total_seen, snippet = [], 0, ""
    for nw in NW:
        text = fetch(oc, law["name"], nw)
        root, got = parse(text)
        total_seen += len(got)
        rows += got
        if not got:
            snippet = re.sub(r"\s+", " ", "".join(root.itertext())).strip()[:120]
    mine = [r for r in rows if r.get("법령명한글", "").strip() == law["name"]]
    if law.get("lsId"):
        want = int(law["lsId"])
        mine = [r for r in mine if re.sub(r"\D", "", r.get("법령ID", "")) and int(re.sub(r"\D", "", r["법령ID"])) == want]
    if not mine:
        raise ApiError(f"목록에서 이 법령을 찾지 못함(응답 {total_seen}건)" + (f" — 응답 내용: {snippet}" if snippet else ""))
    note = ""
    if not law.get("lsId"):
        ids = sorted({r.get("법령ID", "") for r in mine if r.get("법령ID")})
        note = f"API 법령ID {', '.join(ids)} — law_manifest.json lsId 로 등록 가능"
    known = known_numbers(law, updates)
    by_no = {}
    for r in mine:
        n = re.sub(r"\D", "", r.get("공포번호", ""))
        if not n:
            raise ApiError("공포번호가 비어 있는 행이 있음")
        by_no.setdefault(str(int(n)), []).append(r)
    found = []
    for n, rs in sorted(by_no.items(), key=lambda x: int(x[0])):
        if n in known:
            continue
        r0 = rs[0]
        prom = iso(r0.get("공포일자"))
        effs = sorted({iso(r.get("시행일자")) for r in rs})
        kind = r0.get("제개정구분명", "").strip() or "구분 확인 필요"
        ltype = r0.get("법령구분명", "").strip() or (re.match(r"^(\S+)", law["current"]["no"]).group(1))
        name_q = urllib.parse.quote(law["name"])
        eff_txt = " · ".join(dotted(d) for d in effs)
        found.append({
            "id": f"{law['key']}-{n}-{effs[0].replace('-', '')}",
            "date": prom,
            "law": law["name"],
            "kind": kind,
            "effective": effs[0],
            "title": f"{ltype} 제{n}호({kind}) — {dotted(effs[0])} 시행",
            "summary": (f"국가법령정보센터 목록에서 확인한 사실: {ltype} 제{n}호, {kind}, "
                        f"공포 {dotted(prom)}, 시행 {eff_txt} — 개정 내용은 아직 확인하지 않았습니다."),
            "affected_articles": [],
            "practical_impact": "",
            "source_name": "국가법령정보센터",
            "source_url": f"https://www.law.go.kr/%EB%B2%95%EB%A0%B9/{name_q}/({n},{prom.replace('-', '')})",
            "basis": "국가법령정보센터 OPEN API 시행일 법령 목록",
            "verify": VERIFY,
            "checked": dt.datetime.now(KST).date().isoformat(),
        })
    return found, note


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    report = args[args.index("--report") + 1] if "--report" in args else None
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        print("LAW_OC 가 설정되지 않았습니다 — 저장소 Settings → Secrets → Actions 에 LAW_OC 를 등록하세요.")
        return 2
    manifest = json.loads((ROOT / "data/law_manifest.json").read_text(encoding="utf-8"))
    laws_path = ROOT / "data/laws.json"
    laws = json.loads(laws_path.read_text(encoding="utf-8"))
    updates = laws["updates"]
    lines, new_all, failed = [], [], 0
    for law in manifest["laws"]:
        try:
            found, note = check_law(oc, law, updates)
        except ApiError as ex:
            failed += 1
            lines.append(f"- {law['name']}: 확인 못 함 — {ex}")
            continue
        if found:
            new_all += found
            lines.append(f"- {law['name']}: 새 공포번호 " + ", ".join(f"제{f['id'].split('-')[1]}호(시행 {f['effective']})" for f in found))
        else:
            lines.append(f"- {law['name']}: 변경 없음")
        if note:
            lines.append(f"  - {note}")
    if new_all and not dry:
        laws["updates"] = new_all + updates
        laws_path.write_text(json.dumps(laws, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    head = f"법령 변경 자동 감지 {dt.datetime.now(KST).date().isoformat()} — 새 항목 {len(new_all)}건, 확인 못 함 {failed}건" + (" (dry-run, 파일 변경 안 함)" if dry else "")
    text = head + "\n\n" + "\n".join(lines) + "\n"
    if new_all:
        text += "\n운영자 할 일: 위 새 공포번호의 원문(본문·부칙)을 확인해 law_manifest.json·data/lawtext 를 갱신하고, laws.json 항목의 요약·영향을 채운 뒤 verify 를 비우세요.\n"
    print(text)
    if report:
        pathlib.Path(report).write_text(text, encoding="utf-8")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"new={len(new_all)}\nfailed={failed}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
