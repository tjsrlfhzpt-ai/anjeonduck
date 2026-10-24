# -*- coding: utf-8 -*-
"""data/form_auto.json 읽기·쓰기 — 서식 하나를 한 줄로 쓰는 기존 모양을 유지한다(변경 비교가 쉽게)."""
import json
from pathlib import Path
P = Path(__file__).resolve().parents[1] / "data/form_auto.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def save(d):
    head = {k: v for k, v in d.items() if k != "forms"}
    lines = ["{"] + [f' {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)},' for k, v in head.items()]
    lines.append(' "forms": {')
    items = list(d["forms"].items())
    for i, (k, v) in enumerate(items):
        lines.append(f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}' + ("," if i < len(items) - 1 else ""))
    lines += [" }", "}"]
    P.write_text("\n".join(lines) + "\n", encoding="utf-8")
