// SafePlum 산업안전보건위원회 회의 자료(보고용 PPT) — node scripts/templates/build_committee_pptx.js
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("/mnt/skills/public/pptx/scripts/apply_theme.js");
const fs = require("fs");
const D = __dirname + "/img/";

const THEME = {
  name: "SafePlum Committee", headFontFace: "맑은 고딕", bodyFontFace: "맑은 고딕",
  colors: { dk1: "1B2433", lt1: "FFFFFF", dk2: "0E1B2E", lt2: "F2F4F7", accent1: "FFC400", accent2: "D92D20", accent3: "079455", accent4: "2E5AAC", accent5: "667085", accent6: "F79009", hlink: "2E5AAC", folHlink: "6941C6" },
};
const HEX = THEME.colors;
async function icon(Comp, color) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: "256" }));
  return "image/png;base64," + (await sharp(Buffer.from(svg)).png().toBuffer()).toString("base64");
}
const img = (f) => "image/png;base64," + fs.readFileSync(D + f).toString("base64");

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "산업안전보건위원회 회의 자료";
  pres.author = "SafePlum"; pres.company = "SafePlum";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;
  const W = 13.333, H = 7.5, M = 0.6;
  const I = {
    users: await icon(fa.FaUsers, HEX.dk2), list: await icon(fa.FaListOl, HEX.dk2), check: await icon(fa.FaClipboardCheck, HEX.dk2),
    chart: await icon(fa.FaChartBar, HEX.dk2), gavel: await icon(fa.FaGavel, HEX.dk2), cal: await icon(fa.FaCalendarAlt, HEX.dk2),
    arrow: await icon(fa.FaArrowRight, HEX.dk2), copy: await icon(fa.FaClone, HEX.dk2), pen: await icon(fa.FaPen, HEX.dk2), pdf: await icon(fa.FaFilePdf, HEX.dk2), shield: await icon(fa.FaHardHat, HEX.dk2),
  };
  const P = { before: img("ph_before_s.png"), after: img("ph_after_s.png") };

  pres.defineSlideMaster({
    title: "COVER", background: { color: HEX.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 2.05, w: 7.4, h: 1.9, fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: M, y: 4.0, w: 7.0, h: 0.9, fontSize: 18, color: "C9D3E3", valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { color: HEX.lt1 }, margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.38, w: 8.6, h: 0.7, fontSize: 26, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "산업안전보건위원회 회의 자료", options: { x: M, y: H - 0.42, w: 6, h: 0.3, fontSize: 9, color: "98A2B3", margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.3, fontSize: 9, color: "98A2B3", align: "right" },
  });
  const pill = (s, text, x, y, w, fillc, color = "FFFFFF", h = 0.36, fs = 12, name) =>
    s.addText(text, { x, y, w, h, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: h / 2, fill: { color: fillc }, color, fontSize: fs, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: name });
  const dot = (s, data, x, y, d = 0.5, fillc = HEX.accent1, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fillc }, line: { color: fillc }, objectName: name ? name + "_dot" : undefined });
    s.addImage({ data, x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52, objectName: name ? name + "_icon" : undefined });
  };
  const card = (s, x, y, w, h, fillc = HEX.lt2, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fillc }, line: { color: fillc }, objectName: name });
  const label = (s, t, x, y, w, color = "667085", fs = 11) => s.addText(t, { x, y, w, h: 0.28, fontSize: fs, bold: true, color, margin: 0, isTextBox: true });
  const guide = (s, t, x, y, w, h, fs = 14, name) => s.addText(t, { x, y, w, h, fontSize: fs, color: "98A2B3", italic: true, valign: "top", margin: 0, isTextBox: true, objectName: name, paraSpaceAfter: 4 });
  const hc = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 }, align: "center", valign: "middle", fontSize: 12 } });
  const approval = (s, x, y) => {
    const cols = ["작성", "검토", "승인"], cw = 0.95;
    s.addTable([cols.map((t) => ({ text: t, options: { bold: true, fontSize: 10, color: "344054", fill: { color: HEX.lt2 }, align: "center", valign: "middle" } })), cols.map(() => ({ text: "" }))],
      { x, y, w: cw * 3, colW: [cw, cw, cw], rowH: [0.3, 0.62], border: { type: "solid", pt: 0.75, color: "D0D5DD" }, objectName: "결재란" });
  };

  // 1. 표지
  {
    const s = pres.addSlide({ masterName: "COVER" });
    pill(s, "2026년 4분기 정기회의", M, 1.35, 2.6, HEX.accent1, HEX.dk2, 0.42, 14, "표지_회차");
    s.addText("산업안전보건위원회\n회의 자료", { placeholder: "title" });
    s.addText("안건 보고 · 심의·의결 · 후속 조치", { placeholder: "body" });
    const x = 8.35, y = 1.35, w = 4.4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 4.9, rectRadius: 0.16, fill: { color: "FFFFFF", transparency: 92 }, line: { color: "FFFFFF", transparency: 80 }, objectName: "표지_정보카드" });
    [["사업장", "예: (주)○○ 2공장"], ["일시", "2026. 10. 00 (요일) 14:00"], ["장소", "본관 2층 대회의실"], ["위원장", "소속 · 성명"], ["간사", "안전관리자 · 성명"]].forEach(([k, v], i) => {
      s.addText(k, { x: x + 0.35, y: y + 0.35 + i * 0.88, w: 3.7, h: 0.3, fontSize: 11, bold: true, color: HEX.accent1, margin: 0, isTextBox: true });
      s.addText(v, { x: x + 0.35, y: y + 0.65 + i * 0.88, w: 3.7, h: 0.4, fontSize: 16, color: "FFFFFF", margin: 0, isTextBox: true, objectName: "표지_" + k });
    });
    dot(s, I.users, M, 5.45, 0.62, HEX.accent1, "표지_아이콘1");
    s.addText([{ text: "근로자위원 · 사용자위원 같은 수", options: { bold: true, breakLine: true } }, { text: "각 과반수 출석으로 개의", options: { color: "C9D3E3" } }], { x: M + 0.8, y: 5.42, w: 3.4, h: 0.7, fontSize: 13, color: "FFFFFF", margin: 0, isTextBox: true });
    dot(s, I.cal, M + 4.0, 5.45, 0.62, HEX.accent1, "표지_아이콘2");
    s.addText([{ text: "정기회의는 분기마다", options: { bold: true, breakLine: true } }, { text: "회의록은 2년간 보존", options: { color: "C9D3E3" } }], { x: M + 4.8, y: 5.42, w: 3.2, h: 0.7, fontSize: 13, color: "FFFFFF", margin: 0, isTextBox: true });
    s.addNotes("표지: 회차·사업장·일시·장소·위원장·간사를 바꿔 쓰세요. 정기회의는 분기마다 위원장이 소집합니다(시행령 제37조제1항).");
  }

  // 2. 위원 출석·안건
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("위원 출석 및 오늘의 안건", { placeholder: "title" });
    approval(s, W - M - 2.85, 0.32);
    // 출석
    const lw = 5.2;
    card(s, M, 1.4, lw, 4.85, HEX.lt2, "출석카드");
    dot(s, I.users, M + 0.25, 1.55, 0.46, HEX.accent1, "출석아이콘");
    s.addText("위원 출석 현황", { x: M + 0.85, y: 1.57, w: 3, h: 0.42, fontSize: 15, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    const cc = (t, o = {}) => ({ text: t, options: Object.assign({ align: "center", valign: "middle", fontSize: 13, color: "344054", fill: { color: "FFFFFF" } }, o) });
    s.addTable([[hc("구분"), hc("위원 수"), hc("출석"), hc("과반")], [cc("사용자위원", { bold: true }), cc("3명"), cc("3명"), cc("충족", { bold: true, color: HEX.accent3 })], [cc("근로자위원", { bold: true }), cc("3명"), cc("2명"), cc("충족", { bold: true, color: HEX.accent3 })]],
      { x: M + 0.25, y: 2.2, w: lw - 0.5, colW: [1.55, 1.05, 1.05, 1.05], rowH: 0.48, border: { type: "solid", pt: 0.75, color: "E4E7EC" }, objectName: "출석표" });
    s.addText("근로자위원·사용자위원 각 과반수 출석으로 개의하고, 출석위원 과반수 찬성으로 의결합니다(시행령 제37조제2항). 대리 출석자가 있으면 성명을 함께 적습니다.", { x: M + 0.25, y: 3.85, w: lw - 0.5, h: 0.8, fontSize: 11, color: "667085", margin: 0, isTextBox: true });
    label(s, "참석 위원 명단", M + 0.25, 4.75, 3, "344054", 12);
    guide(s, "예: 사용자 — 공장장, 안전관리자, 보건관리자 / 근로자 — 근로자대표, 명예산업안전감독관, 근로자위원", M + 0.25, 5.05, lw - 0.5, 1.0, 13, "명단");
    // 안건
    const rx = M + lw + 0.45, rw = W - M - rx;
    label(s, "심의·의결 안건 (법 제24조제2항)", rx, 1.4, rw, "344054", 13);
    const items = ["산업재해 예방계획의 수립", "안전보건관리규정의 작성 및 변경", "안전보건교육", "작업환경측정 등 작업환경의 점검 및 개선", "근로자의 건강진단 등 건강관리",
      "산업재해에 관한 통계의 기록 및 유지", "중대재해의 원인 조사 및 재발 방지대책 수립", "유해·위험 기계·기구·설비 도입 시 안전·보건조치", "그 밖에 근로자의 안전·보건 유지·증진에 필요한 사항"];
    items.forEach((t, i) => {
      const y = 1.8 + i * 0.49;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: rx, y, w: rw, h: 0.42, rectRadius: 0.08, fill: { color: i % 2 ? "FFFFFF" : HEX.lt2 }, line: { color: "E4E7EC", width: 0.75 }, objectName: "안건행_" + (i + 1) });
      s.addText(String(i + 1), { x: rx + 0.12, y: y + 0.06, w: 0.3, h: 0.3, fontSize: 11, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0, shape: pres.shapes.OVAL, fill: { color: HEX.dk2 }, isTextBox: true });
      s.addText(t, { x: rx + 0.55, y, w: rw - 2.0, h: 0.42, fontSize: 13, color: "344054", margin: 0, valign: "middle", isTextBox: true });
      s.addText(i < 3 ? "심의" : "보고", { x: rx + rw - 1.25, y: y + 0.07, w: 1.05, h: 0.28, fontSize: 10.5, bold: true, color: i < 3 ? HEX.dk2 : "667085", align: "center", valign: "middle", margin: 0, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.14, fill: { color: i < 3 ? "FFE58A" : "EAECF0" }, isTextBox: true, objectName: "안건구분_" + (i + 1) });
    });
    s.addNotes("오른쪽 안건 목록은 법 제24조제2항의 심의·의결 사항입니다. 이번 회의에서 다룰 안건만 남기고 '심의/보고' 표시를 바꾸세요.");
  }

  // 3. 지난 회의 이행 확인
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("지난 회의 의결사항 이행 확인", { placeholder: "title" });
    const kpi = [["의결사항", "0", HEX.dk2], ["이행 완료", "0", HEX.accent3], ["진행 중", "0", HEX.accent6], ["미이행", "0", HEX.accent2]];
    const kw = (W - 2 * M - 3 * 0.3) / 4;
    kpi.forEach(([k, v, col], i) => {
      const x = M + i * (kw + 0.3);
      card(s, x, 1.4, kw, 1.2, HEX.lt2, "이행_" + k);
      s.addText(k, { x: x + 0.3, y: 1.55, w: kw - 0.6, h: 0.3, fontSize: 13, bold: true, color: "475467", margin: 0, isTextBox: true });
      s.addText([{ text: v, options: { fontSize: 36, bold: true, color: col } }, { text: " 건", options: { fontSize: 14, color: "667085" } }], { x: x + 0.3, y: 1.85, w: kw - 0.6, h: 0.65, margin: 0, valign: "bottom", isTextBox: true, objectName: "이행값_" + k });
    });
    const head = ["No.", "지난 회의 의결사항", "담당", "기한", "이행 결과", "상태"];
    const ex = ["1", "하반기 지게차·보행자 동선 분리 (예산 500만원)", "물류팀", "10. 31", "보행 통로 펜스 설치 완료, 바닥 구획선 재도색", "완료"].map((t, i) => ({ text: t, options: { color: "98A2B3", italic: true, fontSize: 12, align: i === 1 || i === 4 ? "left" : "center", valign: "middle" } }));
    const rows = [head.map(hc), ex];
    for (let r = 2; r <= 6; r++) rows.push(head.map((_, i) => ({ text: i === 0 ? String(r) : "", options: { fontSize: 12, align: i === 1 || i === 4 ? "left" : "center", valign: "middle", color: "344054", fill: { color: r % 2 ? "FFFFFF" : "F9FAFB" } } })));
    s.addTable(rows, { x: M, y: 2.9, w: W - 2 * M, colW: [0.6, 4.4, 1.5, 1.1, 3.333, 1.2], rowH: 0.48, border: { type: "solid", pt: 0.75, color: "E4E7EC" }, objectName: "이행표" });
    s.addNotes("지난 회의록의 의결사항을 옮겨 적고 이행 결과를 확인합니다. 미이행 건은 사유와 새 기한을 '후속 조치' 장에 다시 적으세요.");
  }

  // 4. 산업재해 현황
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("산업재해 · 아차사고 현황", { placeholder: "title" });
    const kpi = [["산업재해", "0", "건 (이번 분기)", HEX.accent2], ["아차사고 보고", "0", "건", HEX.accent6], ["순회점검 지적", "0", "건", HEX.accent4], ["지적 조치율", "0", "%", HEX.accent3]];
    kpi.forEach(([k, v, u, col], i) => {
      const y = 1.4 + i * 1.18;
      card(s, M, y, 3.6, 1.0, HEX.lt2, "현황_" + k);
      s.addText(k, { x: M + 0.25, y: y + 0.12, w: 3.1, h: 0.3, fontSize: 12, bold: true, color: "475467", margin: 0, isTextBox: true });
      s.addText([{ text: v, options: { fontSize: 30, bold: true, color: col } }, { text: " " + u, options: { fontSize: 12, color: "667085" } }], { x: M + 0.25, y: y + 0.38, w: 3.1, h: 0.55, margin: 0, valign: "bottom", isTextBox: true, objectName: "현황값_" + k });
    });
    const labels = ["1분기", "2분기", "3분기", "4분기"];
    s.addChart(pres.charts.BAR, [{ name: "산업재해", labels, values: [1, 0, 1, 0] }, { name: "아차사고", labels, values: [3, 5, 4, 6] }], {
      x: M + 4.0, y: 1.35, w: W - 2 * M - 4.0, h: 4.6, barDir: "col", barGrouping: "clustered",
      chartColors: [HEX.accent2, HEX.accent6], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: "344054", dataLabelFontFace: "+mn-lt",
      showLegend: true, legendPos: "t", legendFontSize: 11, legendFontFace: "+mn-lt",
      showTitle: true, title: "분기별 재해·아차사고 건수 (예시 숫자 — 차트 우클릭 → 데이터 편집)", titleFontSize: 12, titleColor: "344054", titleFontFace: "+mn-lt",
      catAxisLabelColor: "667085", valAxisLabelColor: "667085", catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
      valGridLine: { color: "E4E7EC", size: 0.75 }, catGridLine: { style: "none" }, objectName: "재해차트",
    });
    s.addText("산업재해 통계의 기록·유지는 위원회 심의·의결 사항입니다(법 제24조제2항). 재해 유형·원인별로 나눠 보면 다음 분기 예방계획이 구체적으로 나옵니다.", { x: M + 4.0, y: 6.05, w: W - 2 * M - 4.0, h: 0.6, fontSize: 11, color: "667085", margin: 0, isTextBox: true });
    s.addNotes("차트를 우클릭 → [데이터 편집]에서 실제 건수로 바꾸세요. 왼쪽 숫자 카드도 함께 고칩니다.");
  }

  // 5. 안건 심의 (1안건/장)
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText([{ text: "안건 1   ", options: { color: HEX.accent4 } }, { text: "산업재해 예방계획의 수립" }], { placeholder: "title" });
    pill(s, "심의·의결", W - M - 1.6, 0.55, 1.6, HEX.accent1, HEX.dk2, 0.36, 12, "안건_구분");
    const lw = 7.3;
    card(s, M, 1.4, lw, 2.35, HEX.lt2, "보고카드");
    dot(s, I.list, M + 0.25, 1.55, 0.46, HEX.accent1, "보고아이콘");
    s.addText("보고 내용", { x: M + 0.85, y: 1.57, w: 3, h: 0.42, fontSize: 15, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    guide(s, "예: 하반기 지게차·보행자 충돌 위험 감소 — 하역장 보행 통로 펜스 분리(500만원), 후방 감지기·경광등 설치(지게차 6대), 신호수 배치 기준 마련", M + 0.3, 2.15, lw - 0.6, 1.5, 14, "보고내용");
    card(s, M, 3.95, lw, 2.35, HEX.lt2, "의견카드");
    dot(s, I.users, M + 0.25, 4.1, 0.46, HEX.accent1, "의견아이콘");
    s.addText("위원 의견", { x: M + 0.85, y: 4.12, w: 3, h: 0.42, fontSize: 15, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    guide(s, "예: 근로자위원 — 야간 하역 시 조명도 함께 개선 요청 / 사용자위원 — 조명 추가는 이번 예산에 포함하기로 함", M + 0.3, 4.7, lw - 0.6, 1.5, 14, "위원의견");
    const rx = M + lw + 0.4, rw = W - M - rx;
    card(s, rx, 1.4, rw, 4.9, "FFFFFF", "의결카드");
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: rx, y: 1.4, w: rw, h: 4.9, rectRadius: 0.12, fill: { color: "FFFFFF" }, line: { color: "D0D5DD", width: 1 }, objectName: "의결카드선" });
    dot(s, I.gavel, rx + 0.3, 1.6, 0.56, HEX.accent1, "의결아이콘");
    s.addText("의결 결과", { x: rx + 1.0, y: 1.65, w: 3, h: 0.45, fontSize: 16, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    pill(s, "원안 의결", rx + 0.3, 2.4, rw - 0.6, HEX.accent3, "FFFFFF", 0.5, 16, "의결결과");
    s.addText("원안 의결 · 수정 의결 · 보고 · 보류 · 의결하지 못함 중 하나로 바꾸세요", { x: rx + 0.3, y: 3.0, w: rw - 0.6, h: 0.5, fontSize: 10.5, color: "98A2B3", margin: 0, isTextBox: true });
    [["찬성", "0명"], ["반대", "0명"], ["담당", "부서 · 성명"], ["이행 기한", "2026. 00. 00"]].forEach(([k, v], i) => {
      const y = 3.65 + i * 0.6;
      label(s, k, rx + 0.3, y, 1.4, "667085", 11);
      s.addText(v, { x: rx + 1.6, y: y - 0.05, w: rw - 1.9, h: 0.38, fontSize: 14, color: "344054", margin: 0, valign: "middle", isTextBox: true, objectName: "의결_" + k });
    });
    s.addNotes("안건마다 이 장을 복제(Ctrl+D)해 씁니다. 의결하지 못했거나 해석·이행 방법에 의견이 다르면 노사 합의로 정한 중재기구 등 법 제25조 절차를 따릅니다.");
  }

  // 6. 위험성평가·개선 결과
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("위험성평가 · 개선 결과 보고", { placeholder: "title" });
    const pw = 3.55, ph = 2.45, py = 1.4;
    [["개선 전", P.before, HEX.accent2, M], ["개선 후", P.after, HEX.accent3, M + pw + 0.55]].forEach(([t, d, col, x]) => {
      s.addImage({ data: d, x, y: py, w: pw, h: ph, objectName: t + " 사진" });
      pill(s, t, x + 0.15, py + 0.15, 1.05, col, "FFFFFF", 0.34, 12, t + "_라벨");
    });
    dot(s, I.arrow, M + pw + 0.06, py + ph / 2 - 0.22, 0.44, HEX.accent1, "화살표");
    card(s, M, 4.05, pw * 2 + 0.55, 2.2, HEX.lt2, "개선카드");
    label(s, "유해·위험요인", M + 0.25, 4.2, 3, HEX.accent2, 12);
    guide(s, "예: 컨베이어 회전부 방호덮개가 없어 점검·청소 중 손이 말려 들어갈 위험", M + 0.25, 4.5, pw * 2, 0.6, 14, "요인");
    label(s, "감소대책 · 결과", M + 0.25, 5.15, 3, HEX.accent3, 12);
    guide(s, "예: 고정식 방호덮개 설치, 덮개 열면 설비가 멈추는 연동장치 — 위험성 12(높음) → 4(낮음)", M + 0.25, 5.45, pw * 2, 0.7, 14, "대책");
    const rx = M + pw * 2 + 0.95, rw = W - M - rx;
    label(s, "위험성 등급별 개선 현황", rx, 1.4, rw, "344054", 13);
    s.addChart(pres.charts.BAR, [{ name: "개선 전", labels: ["매우 높음", "높음", "보통", "낮음 이하"], values: [1, 4, 7, 12] }, { name: "개선 후", labels: ["매우 높음", "높음", "보통", "낮음 이하"], values: [0, 1, 4, 19] }], {
      x: rx, y: 1.75, w: rw, h: 4.5, barDir: "bar", barGrouping: "clustered", chartColors: [HEX.accent2, HEX.accent3],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 10, dataLabelColor: "344054", dataLabelFontFace: "+mn-lt",
      showLegend: true, legendPos: "t", legendFontSize: 10, legendFontFace: "+mn-lt", catAxisLabelColor: "667085", valAxisLabelColor: "667085",
      catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 9, valGridLine: { color: "E4E7EC", size: 0.75 }, catGridLine: { style: "none" }, objectName: "위험성차트",
    });
    s.addNotes("왼쪽 사진은 우클릭 → [그림 바꾸기]. 오른쪽 차트는 위험성평가표의 등급별 건수(개선 전·후)로 바꾸세요(예시 숫자).");
  }

  // 7. 후속 조치·다음 회의
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("의결사항 후속 조치 · 다음 회의", { placeholder: "title" });
    const head = ["No.", "조치 사항", "담당", "기한", "근로자 공지 방법"];
    const ex = ["1", "하역장 보행 통로 펜스·조명 설치", "물류팀", "11. 30", "게시판 · TBM"].map((t, i) => ({ text: t, options: { color: "98A2B3", italic: true, fontSize: 12, align: i === 1 ? "left" : "center", valign: "middle" } }));
    const rows = [head.map(hc), ex];
    for (let r = 2; r <= 6; r++) rows.push(head.map((_, i) => ({ text: i === 0 ? String(r) : "", options: { fontSize: 12, align: i === 1 ? "left" : "center", valign: "middle", color: "344054", fill: { color: r % 2 ? "FFFFFF" : "F9FAFB" } } })));
    s.addTable(rows, { x: M, y: 1.4, w: 8.3, colW: [0.6, 3.7, 1.3, 1.1, 1.6], rowH: 0.5, border: { type: "solid", pt: 0.75, color: "E4E7EC" }, objectName: "후속조치표" });
    const rx = M + 8.7, rw = W - M - rx;
    card(s, rx, 1.4, rw, 2.4, HEX.lt2, "다음회의카드");
    dot(s, I.cal, rx + 0.25, 1.55, 0.5, HEX.accent1, "다음회의아이콘");
    s.addText("다음 정기회의", { x: rx + 0.9, y: 1.58, w: rw - 1.1, h: 0.45, fontSize: 15, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    s.addText("2027. 01. 00 (요일) 14:00", { x: rx + 0.3, y: 2.25, w: rw - 0.6, h: 0.45, fontSize: 17, bold: true, color: "344054", margin: 0, isTextBox: true, objectName: "다음회의일시" });
    s.addText("장소: 본관 2층 대회의실", { x: rx + 0.3, y: 2.75, w: rw - 0.6, h: 0.4, fontSize: 13, color: "475467", margin: 0, isTextBox: true, objectName: "다음회의장소" });
    card(s, rx, 4.0, rw, 2.25, "FFF6D6", "공지안내");
    s.addText([{ text: "회의 결과 알리기", options: { bold: true, color: C.text2, breakLine: true } }, { text: "위원장은 회의 결과를 사내방송·사내보·게시·정례조회 등으로 근로자에게 신속히 알립니다(시행령 제39조). 회의록은 2년간 보존합니다(법 제164조).", options: { color: "475467" } }],
      { x: rx + 0.3, y: 4.15, w: rw - 0.6, h: 1.95, fontSize: 12.5, margin: 0, valign: "top", isTextBox: true, paraSpaceAfter: 6 });
    s.addNotes("의결사항마다 담당·기한을 정하고, 다음 회의의 '이행 확인' 장으로 옮깁니다.");
  }

  // 8. 사용 방법
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("양식 사용 방법", { placeholder: "title" });
    const steps = [[I.copy, "안건 장 늘리기", "'안건 1' 장을 선택하고 Ctrl+D로 복제해 안건 수만큼 늘립니다. 제목의 안건 번호·이름을 바꾸세요."],
      [I.chart, "숫자 · 차트 바꾸기", "차트를 우클릭 → [데이터 편집]에서 실제 건수로 바꿉니다. 회색 기울임 글씨는 예시이니 지우고 쓰세요."],
      [I.pen, "회의록과 함께", "회의 내용은 SafePlum 산업안전보건위원회 작성기에서 회의록·개최 공고·결과 보고서로 바로 만들 수 있습니다."],
      [I.pdf, "보고 · 보관", "[파일] → [내보내기] → PDF로 저장해 위원에게 배포하고 회의록과 함께 보관합니다."]];
    const cw = (W - 2 * M - 3 * 0.3) / 4;
    steps.forEach(([ic, t, d], i) => {
      const x = M + i * (cw + 0.3), y = 1.5;
      card(s, x, y, cw, 3.6, HEX.lt2, "방법_" + (i + 1));
      dot(s, ic, x + 0.3, y + 0.35, 0.7, HEX.accent1, "방법아이콘_" + (i + 1));
      s.addText(String(i + 1).padStart(2, "0"), { x: x + cw - 0.95, y: y + 0.38, w: 0.65, h: 0.5, fontSize: 22, bold: true, color: "D0D5DD", align: "right", margin: 0, isTextBox: true });
      s.addText(t, { x: x + 0.3, y: y + 1.3, w: cw - 0.6, h: 0.45, fontSize: 17, bold: true, color: C.text2, margin: 0, isTextBox: true });
      s.addText(d, { x: x + 0.3, y: y + 1.85, w: cw - 0.6, h: 1.6, fontSize: 13, color: "475467", margin: 0, valign: "top", isTextBox: true });
    });
    card(s, M, 5.45, W - 2 * M, 0.95, "FFF6D6", "방법_안내");
    s.addText([{ text: "회의록 작성기  ", options: { bold: true, color: C.text2 } }, { text: "safeplum.com/tools/committee — 위원 출석·과반 확인, 안건별 의결, 후속 조치, 개최 공고까지 자동 정리. 이 장은 배포 전에 지우세요.", options: { color: "475467" } }],
      { x: M + 0.3, y: 5.55, w: W - 2 * M - 0.6, h: 0.75, fontSize: 13, margin: 0, valign: "middle", isTextBox: true });
  }

  const out = __dirname + "/../../assets/files/templates/SafePlum_committee_meeting.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("ok", out);
})();
