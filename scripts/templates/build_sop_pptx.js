// SafePlum 표준안전작업절차 교육자료(PPT) — node scripts/templates/build_sop_pptx.js
// 예시 작업: 컨베이어 벨트 청소(잠금·표지). 내용은 apps 작성기(data/form_auto.json sop 예시)와 같은 흐름.
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("/mnt/skills/public/pptx/scripts/apply_theme.js");
const fs = require("fs");
const D = __dirname + "/img/";

const THEME = {
  name: "SafePlum SOP", headFontFace: "맑은 고딕", bodyFontFace: "맑은 고딕",
  colors: { dk1: "1B2433", lt1: "FFFFFF", dk2: "0E1B2E", lt2: "F2F4F7", accent1: "FFC400", accent2: "D92D20", accent3: "079455", accent4: "2E5AAC", accent5: "667085", accent6: "F79009", hlink: "2E5AAC", folHlink: "6941C6" },
};
const HEX = THEME.colors;
async function icon(Comp, color) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: "256" }));
  return "image/png;base64," + (await sharp(Buffer.from(svg)).png().toBuffer()).toString("base64");
}
const img = (f) => "image/png;base64," + fs.readFileSync(D + f).toString("base64");

const STEPS = [
  ["작업 전 회의·보호구 착용", "작업 순서를 모른 채 시작", "TBM에서 청소 구간·담당·잠금 순서 공유, 보호구 착용 서로 확인"],
  ["운전 정지·전원 차단", "다른 사람이 운전 스위치를 켬", "정지 버튼으로 멈춘 뒤 해당 컨베이어 차단기를 내림"],
  ["잠금·표지 부착", "청소 중 갑자기 가동되어 손이 끼임", "차단기에 본인 자물쇠 + 꼬리표(성명·시간), 열쇠는 본인이 보관"],
  ["정지 상태 확인", "관성·잔류 에너지로 벨트가 움직임", "기동 버튼을 눌러 움직이지 않는지, 벨트·롤러가 완전히 멈췄는지 확인"],
  ["덮개 열고 청소", "롤러 사이 끼임, 모서리 베임, 미끄러짐", "손 대신 스크레이퍼, 물기·이물은 바로 치움, 덮개는 정해진 곳에"],
  ["복구·잠금 해제·시운전", "덮개 없이 가동, 주변 사람 접근 중 가동", "덮개·공구 확인 → 인원 철수 확인 → 건 사람이 해제 → 알리고 시운전"],
];

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "표준안전작업절차 교육자료";
  pres.author = "SafePlum"; pres.company = "SafePlum";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;
  const W = 13.333, H = 7.5, M = 0.6;
  const I = {
    hat: await icon(fa.FaHardHat, HEX.dk2), glasses: await icon(fa.FaGlasses, HEX.dk2), boot: await icon(fa.FaShoePrints, HEX.dk2), glove: await icon(fa.FaHandPaper, HEX.dk2),
    lock: await icon(fa.FaLock, HEX.dk2), check: await icon(fa.FaCheck, "FFFFFF"), warn: await icon(fa.FaExclamationTriangle, HEX.dk2), ban: await icon(fa.FaBan, "FFFFFF"),
    stop: await icon(fa.FaStopCircle, HEX.dk2), bell: await icon(fa.FaBullhorn, HEX.dk2), phone: await icon(fa.FaPhoneAlt, HEX.dk2), amb: await icon(fa.FaAmbulance, HEX.dk2),
    hand: await icon(fa.FaHandHoldingMedical, HEX.dk2), cut: await icon(fa.FaCut, HEX.dk2), slip: await icon(fa.FaWater, HEX.dk2), q: await icon(fa.FaQuestion, HEX.dk2),
    copy: await icon(fa.FaClone, HEX.dk2), image: await icon(fa.FaImage, HEX.dk2), pen: await icon(fa.FaPen, HEX.dk2), sign: await icon(fa.FaSignature, HEX.dk2), arrow: await icon(fa.FaArrowRight, "98A2B3"),
  };
  const PH = img("ph_scene.png");

  pres.defineSlideMaster({
    title: "COVER", background: { color: HEX.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 2.0, w: 7.4, h: 1.9, fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: M, y: 4.0, w: 7.0, h: 0.9, fontSize: 18, color: "C9D3E3", valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { color: HEX.lt1 }, margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.38, w: 9.6, h: 0.7, fontSize: 26, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "표준안전작업절차 교육 — 컨베이어 벨트 청소(예시)", options: { x: M, y: H - 0.42, w: 7, h: 0.3, fontSize: 9, color: "98A2B3", margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.3, fontSize: 9, color: "98A2B3", align: "right" },
  });
  const pill = (s, text, x, y, w, fillc, color = "FFFFFF", h = 0.36, fs = 12, name) =>
    s.addText(text, { x, y, w, h, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: h / 2, fill: { color: fillc }, color, fontSize: fs, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: name });
  const dot = (s, data, x, y, d = 0.5, fillc = HEX.accent1, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fillc }, line: { color: fillc }, objectName: name ? name + "_dot" : undefined });
    s.addImage({ data, x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52, objectName: name ? name + "_icon" : undefined });
  };
  const card = (s, x, y, w, h, fillc = HEX.lt2, name, line) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fillc }, line: { color: line || fillc, width: line ? 1 : 0 }, objectName: name });
  const T = (s, t, o) => s.addText(t, Object.assign({ margin: 0, isTextBox: true }, o));
  const sec = (s, t) => pill(s, t, W - M - 2.2, 0.5, 2.2, HEX.lt2, "475467", 0.38, 12);

  // 1. 표지
  {
    const s = pres.addSlide({ masterName: "COVER" });
    pill(s, "표준안전작업절차 교육", M, 1.3, 2.8, HEX.accent1, HEX.dk2, 0.42, 14, "표지_구분");
    s.addText("컨베이어 벨트 청소\n표준안전작업절차", { placeholder: "title" });
    s.addText("잠금·표지로 끼임 사고를 막는 6단계", { placeholder: "body" });
    const x = 8.35, y = 1.3, w = 4.4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 4.95, rectRadius: 0.16, fill: { color: "FFFFFF", transparency: 92 }, line: { color: "FFFFFF", transparency: 80 }, objectName: "표지_정보카드" });
    [["문서번호", "예: SOP-생산-012 (개정 0)"], ["교육 일시", "2026. 10. 00 (요일) 16:00"], ["교육 대상", "예: 포장 2라인 신규 배치자 3명"], ["교육 구분", "예: 작업내용 변경 시 교육"], ["교육자", "관리감독자 · 성명"]].forEach(([k, v], i) => {
      T(s, k, { x: x + 0.35, y: y + 0.35 + i * 0.9, w: 3.7, h: 0.3, fontSize: 11, bold: true, color: HEX.accent1 });
      T(s, v, { x: x + 0.35, y: y + 0.65 + i * 0.9, w: 3.7, h: 0.4, fontSize: 16, color: "FFFFFF", objectName: "표지_" + k });
    });
    dot(s, I.lock, M, 5.45, 0.62, HEX.accent1, "표지_아이콘");
    T(s, [{ text: "정지 → 잠금 → 확인 → 작업", options: { bold: true, breakLine: true } }, { text: "자물쇠는 건 사람만 풉니다", options: { color: "C9D3E3" } }], { x: M + 0.8, y: 5.42, w: 5, h: 0.7, fontSize: 13, color: "FFFFFF" });
    s.addNotes("표지: 작업명·문서번호·교육 일시·대상·교육자를 바꿔 쓰세요. 이 자료는 SafePlum 표준안전작업절차서(작성기·엑셀)의 내용을 화면으로 설명하기 위한 것입니다. 예시 작업(컨베이어 벨트 청소)은 사업장 작업으로 바꿔 쓰세요.");
  }

  // 2. 왜 이 절차인가
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("왜 이 절차를 지켜야 하나요", { placeholder: "title" });
    sec(s, "1. 이 작업의 위험");
    card(s, M, 1.4, W - 2 * M, 1.3, "FEF3F2", "핵심위험", "FECDCA");
    dot(s, I.warn, M + 0.3, 1.68, 0.74, HEX.accent1, "핵심위험_아이콘");
    T(s, [{ text: "청소·정비 중 기계가 갑자기 움직이면 손이 롤러 사이로 말려 들어갑니다", options: { bold: true, breakLine: true, fontSize: 20, color: "B42318" } },
      { text: "그래서 청소 전에는 반드시 운전을 멈추고, 다른 사람이 켜지 못하게 잠급니다 (안전보건규칙 제92조)", options: { fontSize: 14, color: "475467" } }],
    { x: M + 1.3, y: 1.5, w: W - 2 * M - 1.6, h: 1.1, valign: "middle" });
    const hz = [[I.hand, "끼임", "롤러·벨트 사이에 손·옷이 말려 들어감", "운전 정지 + 잠금·표지"], [I.cut, "베임", "덮개·프레임 모서리, 스크레이퍼 날", "장갑 착용, 손 대신 도구 사용"], [I.slip, "넘어짐", "청소 물기·이물로 바닥이 미끄러움", "미끄럼 방지 안전화, 바로 치우기"]];
    const cw = (W - 2 * M - 2 * 0.3) / 3;
    hz.forEach(([ic, t, d, fix], i) => {
      const x = M + i * (cw + 0.3), y = 3.0;
      card(s, x, y, cw, 2.85, HEX.lt2, "위험_" + t);
      dot(s, ic, x + 0.3, y + 0.3, 0.62, HEX.accent1, "위험아이콘_" + t);
      T(s, t, { x: x + 1.1, y: y + 0.36, w: cw - 1.4, h: 0.5, fontSize: 20, bold: true, color: C.text2, valign: "middle" });
      T(s, d, { x: x + 0.3, y: y + 1.15, w: cw - 0.6, h: 0.75, fontSize: 14, color: "475467", valign: "top" });
      pill(s, "대책", x + 0.3, y + 2.05, 0.8, HEX.accent3, "FFFFFF", 0.32, 11);
      T(s, fix, { x: x + 1.2, y: y + 2.0, w: cw - 1.5, h: 0.42, fontSize: 14, bold: true, color: "05603A", valign: "middle" });
    });
    T(s, [{ text: "우리 사업장 사례  ", options: { bold: true, color: C.text2 } }, { text: "예: 작년 2라인에서 롤러 이물 제거 중 손 끼임 아차사고 1건 — 사업장 사례로 바꿔 쓰세요", options: { color: "98A2B3", italic: true } }],
      { x: M, y: 6.1, w: W - 2 * M, h: 0.5, fontSize: 13, valign: "middle", objectName: "사업장사례" });
    s.addNotes("실제 사고·아차사고 사례가 있으면 맨 아래 줄에 적고 이야기하세요. 근로자에게 '왜'를 먼저 설명하면 절차를 더 잘 지킵니다.");
  }

  // 3. 작업 개요·보호구
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("작업 개요와 필수 보호구", { placeholder: "title" });
    sec(s, "2. 작업 개요");
    const info = [["작업명", "컨베이어 벨트 청소"], ["설비", "포장 2라인 이송 컨베이어"], ["장소", "2공장 포장실"], ["주기", "매일 생산 종료 후"], ["인원", "2명 (청소 1 · 확인 1)"], ["소요 시간", "약 30분"], ["필요 교육", "잠금·표지 절차 교육 이수자"], ["관리감독자", "포장반장"]];
    const lw = 6.0;
    info.forEach(([k, v], i) => {
      const y = 1.45 + i * 0.6;
      s.addShape(pres.shapes.RECTANGLE, { x: M, y, w: lw, h: 0.56, fill: { color: i % 2 ? "FFFFFF" : HEX.lt2 }, line: { color: "E4E7EC", width: 0.75 } });
      T(s, k, { x: M + 0.25, y, w: 1.5, h: 0.56, fontSize: 13, bold: true, color: "475467", valign: "middle" });
      T(s, v, { x: M + 1.85, y, w: lw - 2.1, h: 0.56, fontSize: 15, color: "1D2939", valign: "middle", objectName: "개요_" + k });
    });
    const rx = M + lw + 0.5, rw = W - M - rx;
    T(s, "필수 보호구", { x: rx, y: 1.45, w: rw, h: 0.4, fontSize: 16, bold: true, color: C.text2 });
    const gear = [[I.hat, "위생모·안전모"], [I.glasses, "보안경"], [I.boot, "미끄럼 방지 안전화"], [I.glove, "내수 장갑"]];
    const gw = (rw - 0.3) / 2;
    gear.forEach(([ic, t], i) => {
      const x = rx + (i % 2) * (gw + 0.3), y = 2.0 + Math.floor(i / 2) * 1.75;
      card(s, x, y, gw, 1.5, HEX.lt2, "보호구_" + t);
      dot(s, ic, x + gw / 2 - 0.42, y + 0.2, 0.84, HEX.accent1, "보호구아이콘_" + (i + 1));
      T(s, t, { x: x + 0.1, y: y + 1.1, w: gw - 0.2, h: 0.32, fontSize: 14, bold: true, color: "344054", align: "center" });
    });
    card(s, rx, 5.6, rw, 0.85, "FFF6D6", "장비");
    T(s, [{ text: "준비물  ", options: { bold: true, color: C.text2 } }, { text: "개인 자물쇠·꼬리표, 스크레이퍼, 고무 밀대, 손전등", options: { color: "475467" } }], { x: rx + 0.25, y: 5.65, w: rw - 0.5, h: 0.75, fontSize: 13, valign: "middle" });
    s.addNotes("보호구는 실제로 착용한 모습을 보여 주며 설명하세요. 보호구 아이콘은 우클릭 → [그림 바꾸기]로 사업장 보호구 사진으로 바꿀 수 있습니다.");
  }

  // 4. 작업 전 확인
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("작업 전에 확인할 것", { placeholder: "title" });
    sec(s, "3. 작업 전 확인");
    const items = ["작업 구역 정리, 통로 확보", "보호구 상태 확인·착용", "잠금장치·꼬리표 등 필요한 도구 준비", "비상정지 스위치 위치·비상연락 방법 확인", "함께 일하는 사람에게 오늘 작업 순서·위험 공유(TBM)"];
    items.forEach((t, i) => {
      const y = 1.5 + i * 0.92;
      card(s, M, y, 7.6, 0.76, i % 2 ? "FFFFFF" : HEX.lt2, "확인_" + (i + 1), "E4E7EC");
      dot(s, I.check, M + 0.2, y + 0.14, 0.48, HEX.accent3, "확인아이콘_" + (i + 1));
      T(s, t, { x: M + 0.9, y, w: 6.5, h: 0.76, fontSize: 17, color: "1D2939", valign: "middle" });
    });
    const rx = M + 8.0, rw = W - M - rx;
    card(s, rx, 1.5, rw, 4.44, HEX.dk2, "잠금카드");
    dot(s, I.lock, rx + 0.35, 1.8, 0.78, HEX.accent1, "잠금아이콘");
    T(s, "잠금·표지 4원칙", { x: rx + 0.35, y: 2.75, w: rw - 0.7, h: 0.45, fontSize: 18, bold: true, color: "FFFFFF" });
    T(s, [{ text: "① 내 자물쇠는 내가 건다", options: { breakLine: true } }, { text: "② 꼬리표에 성명·시간을 쓴다", options: { breakLine: true } }, { text: "③ 열쇠는 내가 가지고 있는다", options: { breakLine: true } }, { text: "④ 건 사람만 푼다", options: {} }],
      { x: rx + 0.35, y: 3.3, w: rw - 0.7, h: 2.4, fontSize: 16, color: "E4E7EC", valign: "top", paraSpaceAfter: 10 });
    s.addNotes("잠금·표지(LOTO)는 '다른 사람이 기계를 켜지 못하게 하는 조치'입니다(안전보건규칙 제92조제2항: 기동장치에 잠금장치를 하고 그 열쇠를 별도 관리하거나 표지판을 설치하는 등). 사업장 잠금 절차가 있으면 그 내용으로 바꾸세요.");
  }

  // 5~6. 작업 절차
  const stepSlide = (from, title) => {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText(title, { placeholder: "title" });
    sec(s, "4. 작업 절차");
    const cw = (W - 2 * M - 2 * 0.3) / 3;
    STEPS.slice(from, from + 3).forEach(([t, hz, pt], j) => {
      const i = from + j, x = M + j * (cw + 0.3), y = 1.35;
      card(s, x, y, cw, 5.35, "FFFFFF", "단계카드_" + (i + 1), "E4E7EC");
      s.addImage({ data: PH, x: x + 0.15, y: y + 0.15, w: cw - 0.3, h: (cw - 0.3) / 1.73, objectName: "단계사진_" + (i + 1) });
      const ty = y + 0.3 + (cw - 0.3) / 1.73;
      T(s, String(i + 1), { x: x + 0.2, y: ty, w: 0.5, h: 0.5, fontSize: 18, bold: true, color: HEX.dk2, align: "center", valign: "middle", shape: pres.shapes.OVAL, fill: { color: HEX.accent1 } });
      T(s, t, { x: x + 0.82, y: ty, w: cw - 1.0, h: 0.5, fontSize: 17, bold: true, color: C.text2, valign: "middle", objectName: "단계명_" + (i + 1) });
      pill(s, "위험", x + 0.2, ty + 0.7, 0.75, HEX.accent2, "FFFFFF", 0.3, 11);
      T(s, hz, { x: x + 1.05, y: ty + 0.62, w: cw - 1.25, h: 0.62, fontSize: 13, color: "B42318", valign: "top", objectName: "위험_" + (i + 1) });
      pill(s, "이렇게", x + 0.2, ty + 1.4, 0.75, HEX.accent3, "FFFFFF", 0.3, 11);
      T(s, pt, { x: x + 1.05, y: ty + 1.32, w: cw - 1.25, h: 1.0, fontSize: 13, bold: true, color: "05603A", valign: "top", objectName: "안전포인트_" + (i + 1) });
    });
    s.addNotes("사진은 우클릭 → [그림 바꾸기]로 실제 설비 사진으로 바꾸세요(크기·위치 유지). 가능하면 현장에서 실제로 시연하면서 설명합니다.");
  };
  stepSlide(0, "작업 절차 ① — 멈추고 잠그기");
  stepSlide(3, "작업 절차 ② — 확인하고 청소하고 되돌리기");

  // 7. 하지 말 것
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("절대 하지 말 것", { placeholder: "title" });
    sec(s, "5. 금지 사항");
    const dn = ["운전 중인 벨트·롤러에 손이나 도구를 넣지 않는다", "다른 사람의 자물쇠를 풀지 않는다", "덮개나 연동장치를 뗀 채 운전하지 않는다", "운전 중인 컨베이어 위로 넘어가지 않는다"];
    const cw = (W - 2 * M - 0.3) / 2;
    dn.forEach((t, i) => {
      const x = M + (i % 2) * (cw + 0.3), y = 1.5 + Math.floor(i / 2) * 2.45;
      card(s, x, y, cw, 2.15, "FEF3F2", "금지_" + (i + 1), "FECDCA");
      dot(s, I.ban, x + 0.35, y + 0.6, 0.95, HEX.accent2, "금지아이콘_" + (i + 1));
      T(s, t, { x: x + 1.6, y: y + 0.3, w: cw - 1.9, h: 1.55, fontSize: 20, bold: true, color: "912018", valign: "middle", objectName: "금지문구_" + (i + 1) });
    });
    s.addNotes("금지 사항은 짧고 분명하게. 각 항목이 왜 위험한지 한 문장씩 덧붙여 설명하세요(예: 덮개를 뗀 채 운전하면 회전부가 그대로 드러납니다).");
  }

  // 8. 비상 시
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("이상·비상 시 이렇게", { placeholder: "title" });
    sec(s, "6. 비상 조치");
    const fl = [[I.stop, "멈춘다", "가장 가까운 비상정지 스위치"], [I.bell, "알린다", "큰 소리로 주변에 알림"], [I.phone, "보고한다", "관리감독자 · 사내 비상연락\n내선 ○○○"], [I.amb, "119", "부상자는 무리하게 빼내지 말고\n119 지시에 따름"]];
    const cw = 2.6, gap = (W - 2 * M - 4 * cw) / 3;
    fl.forEach(([ic, t, d], i) => {
      const x = M + i * (cw + gap), y = 1.7;
      card(s, x, y, cw, 3.5, i === 0 ? "FEF3F2" : HEX.lt2, "비상_" + (i + 1), i === 0 ? "FECDCA" : undefined);
      dot(s, ic, x + cw / 2 - 0.5, y + 0.35, 1.0, i === 0 ? HEX.accent2 : HEX.accent1, "비상아이콘_" + (i + 1));
      T(s, t, { x: x + 0.15, y: y + 1.55, w: cw - 0.3, h: 0.55, fontSize: 22, bold: true, color: C.text2, align: "center" });
      T(s, d, { x: x + 0.15, y: y + 2.2, w: cw - 0.3, h: 1.1, fontSize: 13.5, color: "475467", align: "center", valign: "top", objectName: "비상설명_" + (i + 1) });
      if (i < 3) s.addImage({ data: I.arrow, x: x + cw + gap / 2 - 0.17, y: y + 1.6, w: 0.34, h: 0.34 });
    });
    card(s, M, 5.6, W - 2 * M, 0.85, "FFF6D6", "비상위치");
    T(s, [{ text: "비상정지 스위치 위치  ", options: { bold: true, color: C.text2 } }, { text: "예: 컨베이어 양 끝단·중간 조작반 3곳 — 사업장 위치로 바꿔 쓰세요", options: { color: "98A2B3", italic: true } }], { x: M + 0.3, y: 5.65, w: W - 2 * M - 0.6, h: 0.75, fontSize: 14, valign: "middle", objectName: "비상정지위치" });
    s.addNotes("비상정지 스위치 위치는 현장에서 직접 눌러 보게 하는 것이 가장 좋습니다(컨베이어 비상정지장치: 안전보건규칙 제192조). 사내 비상연락 번호를 꼭 바꿔 적으세요.");
  }

  // 9. 이해도 확인
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("이해도 확인", { placeholder: "title" });
    sec(s, "7. 확인 질문");
    const qs = [["청소 전에 차단기에 무엇을 해야 하나요?", "본인 자물쇠 잠금 + 꼬리표 부착"], ["잠금은 누가 풀 수 있나요?", "자물쇠를 건 본인만"], ["작업 중 끼임이 생기면 가장 먼저 무엇을 하나요?", "비상정지 스위치 → 주변에 알림"]];
    qs.forEach(([q], i) => {
      const y = 1.5 + i * 1.45;
      card(s, M, y, W - 2 * M, 1.2, HEX.lt2, "질문_" + (i + 1));
      T(s, "Q" + (i + 1), { x: M + 0.3, y: y + 0.27, w: 0.9, h: 0.66, fontSize: 22, bold: true, color: HEX.dk2, align: "center", valign: "middle", shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.12, fill: { color: HEX.accent1 } });
      T(s, q, { x: M + 1.45, y, w: W - 2 * M - 4.2, h: 1.2, fontSize: 20, bold: true, color: "1D2939", valign: "middle", objectName: "질문문구_" + (i + 1) });
      T(s, "답: ____________", { x: W - M - 2.9, y, w: 2.6, h: 1.2, fontSize: 15, color: "98A2B3", valign: "middle", align: "right" });
    });
    s.addNotes("정답 — " + qs.map(([q, a], i) => `Q${i + 1}. ${a}`).join(" / ") + ". 틀린 사람은 그 자리에서 다시 설명하고, 교육 확인서의 '이해 확인' 칸에 '재교육'으로 표시하세요.");
  }

  // 10. 마무리·사용 방법
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("교육 확인과 이 자료 고쳐 쓰는 법", { placeholder: "title" });
    const steps = [[I.sign, "교육 확인 서명", "교육이 끝나면 이해도 질문 결과와 참석자 서명을 남깁니다. SafePlum 표준안전작업절차서 작성기나 엑셀 양식의 '교육 확인 서명부'를 쓰세요."],
      [I.pen, "작업 바꾸기", "표지·개요·단계 장의 글자를 사업장 작업으로 바꿉니다. 단계가 더 있으면 '작업 절차' 장을 Ctrl+D로 복제하세요."],
      [I.image, "사진 넣기", "단계 사진 칸을 우클릭 → [그림 바꾸기]로 실제 설비 사진을 넣습니다. 크기·위치는 그대로 유지됩니다."],
      [I.copy, "절차서와 맞추기", "이 자료의 내용은 표준안전작업절차서(문서)와 같아야 합니다. 절차서를 개정하면 이 자료도 함께 고치세요."]];
    const cw = (W - 2 * M - 3 * 0.3) / 4;
    steps.forEach(([ic, t, d], i) => {
      const x = M + i * (cw + 0.3), y = 1.45;
      card(s, x, y, cw, 3.75, HEX.lt2, "방법_" + (i + 1));
      dot(s, ic, x + 0.3, y + 0.35, 0.7, HEX.accent1, "방법아이콘_" + (i + 1));
      T(s, String(i + 1).padStart(2, "0"), { x: x + cw - 0.95, y: y + 0.38, w: 0.65, h: 0.5, fontSize: 22, bold: true, color: "D0D5DD", align: "right" });
      T(s, t, { x: x + 0.3, y: y + 1.3, w: cw - 0.6, h: 0.45, fontSize: 17, bold: true, color: C.text2 });
      T(s, d, { x: x + 0.3, y: y + 1.85, w: cw - 0.6, h: 1.8, fontSize: 13, color: "475467", valign: "top" });
    });
    card(s, M, 5.5, W - 2 * M, 0.95, "FFF6D6", "방법_안내");
    T(s, [{ text: "작성기  ", options: { bold: true, color: C.text2 } }, { text: "safeplum.com/tools/forms/sop — 예시 작업 고르기, 단계별 사진, 이해도 질문·서명까지 화면에서 작성하고 A4로 인쇄. 이 장은 교육 전에 지우세요.", options: { color: "475467" } }],
      { x: M + 0.3, y: 5.6, w: W - 2 * M - 0.6, h: 0.75, fontSize: 13, valign: "middle" });
    s.addNotes("채용 시·작업내용 변경 시 교육 내용에는 '기계·기구의 위험성과 작업의 순서 및 동선', '작업 개시 전 점검', '사고 발생 시 긴급조치'가 들어 있습니다(산업안전보건법 시행규칙 별표 5). 교육시간·대상은 교육일지로 따로 기록하세요.");
  }

  const out = __dirname + "/../../assets/files/templates/SafePlum_sop_training.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("ok", out);
})();
