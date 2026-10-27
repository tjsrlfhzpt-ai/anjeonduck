// SafePlum 지적사항 개선 전·후 보고 양식 (위험성평가 · 아차사고 · 순회점검)
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("/mnt/skills/public/pptx/scripts/apply_theme.js");
const fs = require("fs");
const D = __dirname + "/img/";

const THEME = {
  name: "SafePlum Improve",
  headFontFace: "맑은 고딕",
  bodyFontFace: "맑은 고딕",
  colors: {
    dk1: "1B2433", lt1: "FFFFFF", dk2: "0E1B2E", lt2: "F2F4F7",
    accent1: "FFC400", accent2: "D92D20", accent3: "079455", accent4: "2E5AAC", accent5: "667085", accent6: "F79009",
    hlink: "2E5AAC", folHlink: "6941C6",
  },
};
const HEX = THEME.colors;

async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
const img = (f) => "image/png;base64," + fs.readFileSync(D + f).toString("base64");

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
  pres.title = "지적사항 개선 전·후 보고 양식";
  pres.author = "SafePlum";
  pres.company = "SafePlum";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;
  const W = 13.333, H = 7.5, M = 0.6;

  const I = {
    camera: await icon(fa.FaCamera, HEX.dk2), arrow: await icon(fa.FaArrowRight, HEX.dk2), check: await icon(fa.FaCheck, "FFFFFF"),
    warn: await icon(fa.FaExclamationTriangle, HEX.dk2), clip: await icon(fa.FaClipboardCheck, HEX.dk2), user: await icon(fa.FaUserShield, HEX.dk2),
    cog: await icon(fa.FaCogs, HEX.dk2), sitemap: await icon(fa.FaSitemap, HEX.dk2), shield: await icon(fa.FaHardHat, HEX.dk2),
    copy: await icon(fa.FaClone, HEX.dk2), image: await icon(fa.FaImage, HEX.dk2), pen: await icon(fa.FaPen, HEX.dk2), pdf: await icon(fa.FaFilePdf, HEX.dk2),
    bolt: await icon(fa.FaBolt, HEX.dk2),
  };
  const P = { before: img("ph_before.png"), after: img("ph_after.png"), beforeS: img("ph_before_s.png"), afterS: img("ph_after_s.png"), scene: img("ph_scene.png") };

  // ---------- 레이아웃 ----------
  pres.defineSlideMaster({
    title: "COVER",
    background: { color: HEX.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 2.05, w: 7.4, h: 1.9, fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: M, y: 4.0, w: 7.0, h: 0.9, fontSize: 18, color: "C9D3E3", valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: HEX.lt1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.38, w: 8.6, h: 0.7, fontSize: 26, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "SafePlum · 안전보건 서류 무료 작성 safeplum.com", options: { x: M, y: H - 0.42, w: 6, h: 0.3, fontSize: 9, color: "98A2B3", margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.3, fontSize: 9, color: "98A2B3", align: "right" },
  });

  // ---------- 공통 조각 ----------
  const pill = (s, text, x, y, w, fill, color = "FFFFFF", h = 0.36, fs = 12, name) =>
    s.addText(text, { x, y, w, h, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: h / 2, fill: { color: fill }, color, fontSize: fs, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: name });
  const iconDot = (s, data, x, y, d = 0.5, fill = HEX.accent1, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill }, objectName: name ? name + "_dot" : undefined });
    s.addImage({ data, x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52, objectName: name ? name + "_icon" : undefined });
  };
  const card = (s, x, y, w, h, fill = HEX.lt2, name) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill }, objectName: name });
  const label = (s, text, x, y, w, color = "667085", fs = 11) =>
    s.addText(text, { x, y, w, h: 0.28, fontSize: fs, bold: true, color, margin: 0, isTextBox: true });
  const guide = (s, text, x, y, w, h, fs = 14, name) =>
    s.addText(text, { x, y, w, h, fontSize: fs, color: "98A2B3", italic: true, valign: "top", margin: 0, isTextBox: true, objectName: name, paraSpaceAfter: 4 });
  // 결재란: 작성·검토·승인
  const approval = (s, x, y) => {
    const cols = ["작성", "검토", "승인"], cw = 0.95;
    s.addTable([
      cols.map((t) => ({ text: t, options: { bold: true, fontSize: 10, color: "344054", fill: { color: HEX.lt2 }, align: "center", valign: "middle" } })),
      cols.map(() => ({ text: "", options: {} })),
    ], { x, y, w: cw * 3, colW: [cw, cw, cw], rowH: [0.3, 0.62], border: { type: "solid", pt: 0.75, color: "D0D5DD" }, objectName: "결재란" });
  };

  // ========== 1. 표지 ==========
  {
    const s = pres.addSlide({ masterName: "COVER" });
    pill(s, "안전보건 개선 보고", M, 1.35, 2.2, HEX.accent1, HEX.dk2, 0.42, 14, "표지_구분");
    s.addText("지적사항 개선\n전·후 보고서", { placeholder: "title" });
    s.addText("위험성평가 · 아차사고 · 순회·합동점검", { placeholder: "body" });
    // 오른쪽 정보 카드
    const x = 8.35, y = 1.35, w = 4.4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 4.9, rectRadius: 0.16, fill: { color: "FFFFFF", transparency: 92 }, line: { color: "FFFFFF", transparency: 80 }, objectName: "표지_정보카드" });
    const rows = [["사업장", "예: (주)○○ 2공장"], ["점검 구분", "위험성평가 / 아차사고 / 순회점검"], ["점검 기간", "2026. 10. 00 ~ 10. 00"], ["점검자", "소속 · 성명"], ["보고일", "2026. 10. 00"]];
    rows.forEach(([k, v], i) => {
      s.addText(k, { x: x + 0.35, y: y + 0.35 + i * 0.88, w: 3.7, h: 0.3, fontSize: 11, bold: true, color: HEX.accent1, margin: 0, isTextBox: true });
      s.addText(v, { x: x + 0.35, y: y + 0.65 + i * 0.88, w: 3.7, h: 0.4, fontSize: 16, color: "FFFFFF", margin: 0, isTextBox: true, objectName: "표지_" + k });
    });
    // 아래 지표
    iconDot(s, I.camera, M, 5.45, 0.62, HEX.accent1, "표지_아이콘1");
    s.addText([{ text: "개선 전·후 사진 비교", options: { bold: true, breakLine: true } }, { text: "지적 → 조치 → 확인까지 한 장에", options: { color: "C9D3E3" } }],
      { x: M + 0.8, y: 5.42, w: 3.4, h: 0.7, fontSize: 13, color: "FFFFFF", margin: 0, isTextBox: true });
    iconDot(s, I.shield, M + 4.0, 5.45, 0.62, HEX.accent1, "표지_아이콘2");
    s.addText([{ text: "위험성 감소 확인", options: { bold: true, breakLine: true } }, { text: "개선 전 → 개선 후 위험성 비교", options: { color: "C9D3E3" } }],
      { x: M + 4.8, y: 5.42, w: 3.2, h: 0.7, fontSize: 13, color: "FFFFFF", margin: 0, isTextBox: true });
    s.addText("SafePlum · safeplum.com", { x: M, y: H - 0.55, w: 4, h: 0.3, fontSize: 10, color: "8A97AD", margin: 0, isTextBox: true });
    s.addNotes("표지: 오른쪽 카드의 예시 문구를 지우고 사업장·점검 구분·기간·점검자·보고일을 입력하세요.");
  }

  // ========== 2. 개선 현황 요약 ==========
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("개선 현황 요약", { placeholder: "title" });
    approval(s, W - M - 2.85, 0.32);
    const kpi = [["총 지적", "0", HEX.dk2, "건"], ["개선 완료", "0", HEX.accent3, "건"], ["진행 중", "0", HEX.accent6, "건"], ["미착수", "0", HEX.accent2, "건"]];
    const kw = (W - 2 * M - 3 * 0.3) / 4;
    kpi.forEach(([k, v, col, u], i) => {
      const x = M + i * (kw + 0.3), y = 1.45;
      card(s, x, y, kw, 1.35, HEX.lt2, "요약_" + k);
      s.addText(k, { x: x + 0.3, y: y + 0.2, w: kw - 0.6, h: 0.3, fontSize: 13, bold: true, color: "475467", margin: 0, isTextBox: true });
      s.addText([{ text: v, options: { fontSize: 40, bold: true, color: col } }, { text: " " + u, options: { fontSize: 14, color: "667085" } }],
        { x: x + 0.3, y: y + 0.52, w: kw - 0.6, h: 0.7, margin: 0, valign: "bottom", isTextBox: true, objectName: "요약_" + k + "_값" });
    });
    const head = ["No.", "구분", "장소·설비", "지적 내용", "조치 부서", "조치 기한", "상태"];
    const hdr = head.map((t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 }, align: "center", valign: "middle", fontSize: 12 } }));
    const ex = ["1", "위험성평가", "2공장 가공라인", "컨베이어 회전부 방호덮개 미설치", "생산2팀", "10. 31", "완료"].map((t, i) => ({ text: t, options: { color: "98A2B3", italic: true, fontSize: 12, align: i === 3 ? "left" : "center", valign: "middle" } }));
    const rows = [hdr, ex];
    for (let r = 2; r <= 7; r++) rows.push(head.map((_, i) => ({ text: i === 0 ? String(r) : "", options: { fontSize: 12, align: i === 3 ? "left" : "center", valign: "middle", color: "344054", fill: { color: r % 2 ? "FFFFFF" : "F9FAFB" } } })));
    s.addTable(rows, { x: M, y: 3.1, w: W - 2 * M, colW: [0.6, 1.4, 2.0, 4.333, 1.5, 1.2, 1.1], rowH: 0.43, border: { type: "solid", pt: 0.75, color: "E4E7EC" }, objectName: "요약_목록표" });
    s.addNotes("요약: 상단 숫자 4개를 건수로 바꾸고, 표에 지적 건을 한 줄씩 적습니다. 회색 1번 줄은 예시이니 고쳐 쓰거나 지우세요. 줄이 모자라면 표에서 Tab으로 줄을 추가하세요.");
  }

  // ========== 3. 개선 전·후 상세 (1건/장) ==========
  const detail = (no, sectionNote) => {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText([{ text: "No. " + no + "   ", options: { color: HEX.accent4 } }, { text: "지적사항 개선 전·후" }], { placeholder: "title" });
    pill(s, "위험성평가", W - M - 3.9, 0.55, 1.5, HEX.accent1, HEX.dk2, 0.36, 12, "상세_구분");
    pill(s, "예: 2공장 가공라인", W - M - 2.3, 0.55, 2.3, "EAECF0", "344054", 0.36, 12, "상세_장소");
    const pw = (W - 2 * M - 0.9) / 2, ph = 3.15, py = 1.35;
    [["개선 전", P.before, HEX.accent2, M, "문제점", "예: 컨베이어 회전부(풀리·벨트) 방호덮개가 없어 점검·청소 중 손이 말려 들어갈 위험이 있음"],
     ["개선 후", P.after, HEX.accent3, M + pw + 0.9, "개선 내용", "예: 풀리·벨트 전체에 고정식 방호덮개 설치, 덮개를 열면 설비가 멈추도록 연동장치 설치"]].forEach(([t, ph_, col, x, lab, ex]) => {
      s.addImage({ data: ph_, x, y: py, w: pw, h: ph, rounding: false, objectName: t + " 사진" });
      pill(s, t, x + 0.18, py + 0.18, 1.2, col, "FFFFFF", 0.38, 13, t + "_라벨");
      s.addText("촬영일 2026. 10. 00", { x: x + pw - 2.3, y: py + 0.2, w: 2.12, h: 0.32, fontSize: 10, color: "FFFFFF", align: "right", valign: "middle", margin: [0, 6, 0, 6], shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.16, fill: { color: HEX.dk2, transparency: 25 }, isTextBox: true, objectName: t + "_촬영일" });
      label(s, lab, x, py + ph + 0.2, 2.5, col, 12);
      guide(s, ex, x, py + ph + 0.5, pw, 0.85, 14, t + "_설명");
    });
    // 가운데 화살표
    iconDot(s, I.arrow, M + pw + 0.2, py + ph / 2 - 0.25, 0.5, HEX.accent1, "가운데_화살표");
    // 아래 정보 줄
    const iy = 6.0, cells = [["근거", "예: 안전보건규칙 제87조"], ["조치 부서", "예: 생산2팀"], ["조치일 · 조치자", "2026. 10. 00 · 성명"], ["위험성 (전 → 후)", "상 12 → 하 3"], ["상태", ""]];
    const cw = [2.7, 2.3, 2.6, 2.3, 2.233];
    let x = M;
    card(s, M, iy - 0.12, W - 2 * M, 0.98, HEX.lt2, "상세_정보줄");
    cells.forEach(([k, v], i) => {
      label(s, k, x + 0.25, iy - 0.02, cw[i] - 0.3, "667085", 10);
      if (k === "상태") pill(s, "완료", x + 0.25, iy + 0.3, cw[i] - 0.5, HEX.accent3, "FFFFFF", 0.4, 11, "상세_상태");
      else s.addText(v, { x: x + 0.25, y: iy + 0.28, w: cw[i] - 0.35, h: 0.45, fontSize: 14, bold: k.startsWith("위험성"), color: k.startsWith("위험성") ? HEX.accent2 : "344054", margin: 0, valign: "middle", isTextBox: true, objectName: "상세_" + k });
      x += cw[i];
    });
    s.addNotes("상세(1건/장): 사진은 우클릭 → [그림 바꾸기]로 바꾸면 틀 크기가 유지됩니다. 회색 예시 문구는 지우고 쓰세요. 지적 건수만큼 이 슬라이드를 복제(Ctrl+D)하고 No.를 바꾸세요. 상태 칸은 '완료/진행 중/미착수' 중 하나만 남기고, 색은 완료=초록, 진행 중=주황, 미착수=빨강으로 바꾸세요." + (sectionNote || ""));
    return s;
  };
  detail("01");

  // ========== 4. 위험성평가 감소대책 전·후 ==========
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText([{ text: "No. 02   ", options: { color: HEX.accent4 } }, { text: "위험성평가 감소대책 전·후" }], { placeholder: "title" });
    pill(s, "위험성평가", W - M - 3.9, 0.55, 1.5, HEX.accent1, HEX.dk2, 0.36, 12, "위험_구분");
    pill(s, "예: 물류동 하역장", W - M - 2.3, 0.55, 2.3, "EAECF0", "344054", 0.36, 12, "위험_장소");
    const pw = 3.55, ph = 2.45, py = 1.35;
    [["개선 전", P.before, HEX.accent2, M], ["개선 후", P.after, HEX.accent3, M + pw + 0.55]].forEach(([t, d, col, x]) => {
      s.addImage({ data: d, x, y: py, w: pw, h: ph, objectName: t + " 사진" });
      pill(s, t, x + 0.15, py + 0.15, 1.05, col, "FFFFFF", 0.34, 12, t + "_라벨");
    });
    iconDot(s, I.arrow, M + pw + 0.06, py + ph / 2 - 0.22, 0.44, HEX.accent1, "위험_화살표");
    // 왼쪽 아래: 유해·위험요인 / 감소대책
    const lx = M, lw = pw * 2 + 0.55;
    card(s, lx, 4.05, lw, 1.7, HEX.lt2, "위험_요인카드");
    label(s, "유해·위험요인", lx + 0.25, 4.2, 3, HEX.accent2, 12);
    guide(s, "예: 지게차 후진 중 하역장 보행 통로를 지나는 작업자와 부딪힐 위험", lx + 0.25, 4.5, lw - 0.5, 0.45, 14, "위험_요인");
    label(s, "감소대책", lx + 0.25, 5.0, 3, HEX.accent3, 12);
    guide(s, "예: 보행 통로 펜스 분리, 후방 감지기·경광등 설치, 신호수 배치", lx + 0.25, 5.3, lw - 0.5, 0.45, 14, "위험_대책");
    // 오른쪽: 위험성 비교 표
    const rx = M + lw + 0.4, rw = W - M - rx;
    label(s, "위험성 비교", rx, 1.35, 3, "344054", 13);
    const hc = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 }, align: "center", valign: "middle", fontSize: 12 } });
    const cc = (t, o = {}) => ({ text: t, options: Object.assign({ align: "center", valign: "middle", fontSize: 13, color: "344054" }, o) });
    s.addTable([
      [hc("구분"), hc("가능성"), hc("중대성"), hc("위험성")],
      [cc("개선 전", { bold: true, color: HEX.accent2 }), cc("4"), cc("3"), cc("12 · 상", { bold: true, color: "FFFFFF", fill: { color: HEX.accent2 } })],
      [cc("개선 후", { bold: true, color: HEX.accent3 }), cc("1"), cc("3"), cc("3 · 하", { bold: true, color: "FFFFFF", fill: { color: HEX.accent3 } })],
    ], { x: rx, y: 1.7, w: rw, colW: [rw * 0.28, rw * 0.22, rw * 0.22, rw * 0.28], rowH: 0.5, border: { type: "solid", pt: 0.75, color: "E4E7EC" }, objectName: "위험성_비교표" });
    s.addText("위험성 = 가능성 × 중대성 (사업장 위험성평가 기준에 맞게 고쳐 쓰세요)", { x: rx, y: 3.25, w: rw, h: 0.5, fontSize: 10, color: "667085", margin: 0, isTextBox: true });
    label(s, "감소대책 종류", rx, 3.85, 3, "344054", 13);
    const kinds = [["제거 · 대체", I.bolt], ["공학적 대책 (방호·차단)", I.cog], ["관리적 대책 (절차·교육·허가)", I.clip], ["보호구", I.shield]];
    kinds.forEach(([t, ic], i) => {
      const y = 4.2 + i * 0.4;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: rx, y: y + 0.06, w: 0.26, h: 0.26, rectRadius: 0.05, fill: { color: "FFFFFF" }, line: { color: "98A2B3", width: 1 }, objectName: "체크_" + i });
      s.addText(t, { x: rx + 0.4, y, w: rw - 0.4, h: 0.38, fontSize: 13, color: "344054", margin: 0, valign: "middle", isTextBox: true });
    });
    // 아래 정보 줄
    card(s, M, 5.95, W - 2 * M, 0.9, HEX.lt2, "위험_정보줄");
    [["담당자", "소속 · 성명", 0], ["조치 기한", "2026. 10. 00", 3.1], ["재평가일", "2026. 10. 00", 6.0], ["재평가 결과", "허용 가능 / 추가 조치 필요", 8.9]].forEach(([k, v, dx]) => {
      label(s, k, M + 0.25 + dx, 6.03, 2.8, "667085", 10);
      s.addText(v, { x: M + 0.25 + dx, y: 6.33, w: 2.8, h: 0.4, fontSize: 14, color: "344054", margin: 0, valign: "middle", isTextBox: true, objectName: "위험_" + k });
    });
    s.addNotes("위험성평가 전·후: 위험성 비교 표의 숫자를 사업장 기준(예: 5×4, 3×3)에 맞게 고치세요. 감소대책 종류는 해당 칸의 네모를 채우거나 ✓를 입력하세요. 개선 후 위험성이 허용 기준을 넘으면 '재평가 결과'에 추가 조치를 적습니다.");
  }

  // ========== 5. 아차사고 재발방지 전·후 ==========
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText([{ text: "No. 03   ", options: { color: HEX.accent4 } }, { text: "아차사고 재발방지 전·후" }], { placeholder: "title" });
    pill(s, "아차사고", W - M - 3.9, 0.55, 1.5, HEX.accent6, "FFFFFF", 0.36, 12, "아차_구분");
    pill(s, "예: 자재창고 랙 3열", W - M - 2.3, 0.55, 2.3, "EAECF0", "344054", 0.36, 12, "아차_장소");
    // 왼쪽: 발생 개요
    const lw = 5.0;
    card(s, M, 1.35, lw, 2.25, HEX.lt2, "아차_개요카드");
    iconDot(s, I.warn, M + 0.25, 1.5, 0.46, HEX.accent1, "아차_개요아이콘");
    s.addText("발생 개요", { x: M + 0.85, y: 1.52, w: 3, h: 0.42, fontSize: 15, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    [["일시", "2026. 10. 00 (요일) 00:00"], ["작업", "예: 랙 상단 자재 하역"], ["경위", "예: 지게차로 팔레트를 내리던 중 상단 박스가 떨어졌으나 아래에 사람이 없어 다치지 않음"]].forEach(([k, v], i) => {
      label(s, k, M + 0.3, 2.12 + i * 0.42, 0.7, "667085", 11);
      s.addText(v, { x: M + 1.0, y: 2.08 + i * 0.42, w: lw - 1.25, h: i === 2 ? 0.75 : 0.36, fontSize: 12, color: "98A2B3", italic: true, margin: 0, valign: "top", isTextBox: true, objectName: "아차_" + k });
    });
    // 왼쪽 아래: 원인 3가지
    label(s, "원인", M, 3.8, 2, "344054", 13);
    [["인적", I.user, "예: 작업 반경 출입 통제 미흡"], ["물적", I.cog, "예: 팔레트 랩핑 불량"], ["관리적", I.sitemap, "예: 적재 높이 기준 없음"]].forEach(([k, ic, v], i) => {
      const y = 4.15 + i * 0.6;
      iconDot(s, ic, M, y, 0.44, HEX.lt2, "원인_" + k);
      s.addText(k, { x: M + 0.55, y, w: 0.85, h: 0.44, fontSize: 13, bold: true, color: "344054", margin: 0, valign: "middle", isTextBox: true });
      s.addText(v, { x: M + 1.4, y, w: lw - 1.4, h: 0.44, fontSize: 13, color: "98A2B3", italic: true, margin: 0, valign: "middle", isTextBox: true, objectName: "원인_" + k + "_내용" });
    });
    // 오른쪽: 사진 전·후 + 재발방지 대책
    const rx = M + lw + 0.45, rw = W - M - rx, pw = (rw - 0.5) / 2, ph = 2.3;
    [["개선 전", P.beforeS, HEX.accent2, rx], ["개선 후", P.afterS, HEX.accent3, rx + pw + 0.5]].forEach(([t, d, col, x]) => {
      s.addImage({ data: d, x, y: 1.35, w: pw, h: ph, objectName: t + " 사진" });
      pill(s, t, x + 0.14, 1.49, 1.0, col, "FFFFFF", 0.32, 12, t + "_라벨");
    });
    iconDot(s, I.arrow, rx + pw + 0.05, 1.35 + ph / 2 - 0.2, 0.4, HEX.accent1, "아차_화살표");
    card(s, rx, 3.85, rw, 1.85, HEX.lt2, "아차_대책카드");
    label(s, "재발방지 대책", rx + 0.25, 4.0, 3, HEX.accent3, 13);
    guide(s, "예: 랙 상단 적재 높이 1.5m 이하로 제한, 하역 중 랙 아래 출입금지 표시·통제선 설치, 팔레트 랩핑 상태 작업 전 점검 항목에 추가", rx + 0.25, 4.32, rw - 0.5, 1.25, 14, "아차_대책");
    // 아래 정보 줄
    card(s, M, 5.95, W - 2 * M, 0.9, HEX.lt2, "아차_정보줄");
    [["조치 부서", "예: 물류팀", 0], ["조치일 · 조치자", "2026. 10. 00 · 성명", 3.1], ["공유 방법", "TBM · 게시판 · 교육", 6.3], ["위험성평가 반영", "수시평가 반영 / 해당 없음", 9.1]].forEach(([k, v, dx]) => {
      label(s, k, M + 0.25 + dx, 6.03, 2.9, "667085", 10);
      s.addText(v, { x: M + 0.25 + dx, y: 6.33, w: 2.9, h: 0.4, fontSize: 14, color: "344054", margin: 0, valign: "middle", isTextBox: true, objectName: "아차_" + k });
    });
    s.addNotes("아차사고: 다친 사람이 없어도 같은 원인이 반복되면 사고로 이어집니다. 원인은 인적·물적·관리적으로 나눠 적고, 재발방지 대책은 원인과 짝이 맞게 적으세요. 대책을 위험성평가(수시평가)에 반영했는지 아래 칸에 표시합니다. 개인정보(실명·연락처)는 보고 범위에 맞게 적으세요.");
  }

  // ========== 6. 한 장에 2건 (간단 보고) ==========
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("지적사항 개선 전·후 (2건)", { placeholder: "title" });
    const rowH = 2.55;
    [0, 1].forEach((r) => {
      const y = 1.3 + r * (rowH + 0.25);
      card(s, M, y, W - 2 * M, rowH, HEX.lt2, "간단_" + (r + 1) + "_카드");
      pill(s, "No. 0" + (r + 4), M + 0.25, y + 0.25, 1.0, HEX.dk2, "FFFFFF", 0.34, 12, "간단_번호" + (r + 1));
      label(s, "장소 · 지적 내용", M + 0.25, y + 0.75, 3, "667085", 10);
      guide(s, r === 0 ? "예: 가공동 통로 — 바닥에 기름이 흘러 미끄러질 위험" : "예: 용접 작업장 — 소화기 압력 미달", M + 0.25, y + 1.03, 3.5, 0.6, 14, "간단_지적" + (r + 1));
      label(s, "조치 내용", M + 0.25, y + 1.62, 3, HEX.accent3, 10);
      guide(s, r === 0 ? "예: 누유 부위 패킹 교체, 흡착포 비치" : "예: 소화기 교체, 월 1회 압력 점검", M + 0.25, y + 1.9, 3.5, 0.55, 14, "간단_조치" + (r + 1));
      const pw = 3.05, ph = rowH - 0.4, px = M + 4.0;
      [["개선 전", P.beforeS, HEX.accent2, px], ["개선 후", P.afterS, HEX.accent3, px + pw + 0.5]].forEach(([t, d, col, x]) => {
        s.addImage({ data: d, x, y: y + 0.2, w: pw, h: ph, objectName: "간단" + (r + 1) + "_" + t + " 사진" });
        pill(s, t, x + 0.12, y + 0.32, 0.95, col, "FFFFFF", 0.3, 11, "간단" + (r + 1) + "_" + t + "_라벨");
      });
      iconDot(s, I.arrow, px + pw + 0.07, y + 0.2 + ph / 2 - 0.18, 0.36, HEX.accent1, "간단" + (r + 1) + "_화살표");
      const sx = px + 2 * pw + 0.5 + 0.35;
      label(s, "상태", sx, y + 0.3, 1.3, "667085", 10);
      pill(s, "완료", sx, y + 0.6, W - M - sx - 0.25, HEX.accent3, "FFFFFF", 0.38, 12, "간단_상태" + (r + 1));
      label(s, "조치일", sx, y + 1.15, 1.3, "667085", 10);
      s.addText("10. 00", { x: sx, y: y + 1.42, w: W - M - sx - 0.25, h: 0.36, fontSize: 14, color: "344054", margin: 0, isTextBox: true, objectName: "간단_조치일" + (r + 1) });
      label(s, "조치 부서", sx, y + 1.8, 1.3, "667085", 10);
      s.addText("부서명", { x: sx, y: y + 2.05, w: W - M - sx - 0.25, h: 0.36, fontSize: 14, color: "344054", margin: 0, isTextBox: true, objectName: "간단_부서" + (r + 1) });
    });
    s.addNotes("간단 보고(2건/장): 경미한 지적을 묶어 보고할 때 씁니다. 사진은 우클릭 → [그림 바꾸기].");
  }

  // ========== 7. 사용 방법 ==========
  {
    const s = pres.addSlide({ masterName: "CONTENT" });
    s.addText("양식 사용 방법", { placeholder: "title" });
    const steps = [
      [I.copy, "슬라이드 늘리기", "필요한 양식 슬라이드를 선택하고 Ctrl+D로 복제해 지적 건수만큼 늘립니다."],
      [I.image, "사진 바꾸기", "회색 사진 틀을 우클릭 → [그림 바꾸기] → [파일에서]. 틀 크기·위치가 그대로 유지됩니다."],
      [I.pen, "내용 입력", "회색 기울임 글씨는 예시입니다. 지우고 현장 내용으로 바꿔 쓰세요. 상태 색은 완료·진행 중·미착수에 맞게 바꿉니다."],
      [I.pdf, "보고 · 보관", "[파일] → [내보내기] → PDF로 저장해 보고하고, 원본 사진은 따로 보관합니다."],
    ];
    const cw = (W - 2 * M - 3 * 0.3) / 4;
    steps.forEach(([ic, t, d], i) => {
      const x = M + i * (cw + 0.3), y = 1.5;
      card(s, x, y, cw, 3.6, HEX.lt2, "방법_" + (i + 1));
      iconDot(s, ic, x + 0.3, y + 0.35, 0.7, HEX.accent1, "방법아이콘_" + (i + 1));
      s.addText(String(i + 1).padStart(2, "0"), { x: x + cw - 0.95, y: y + 0.38, w: 0.65, h: 0.5, fontSize: 22, bold: true, color: "D0D5DD", align: "right", margin: 0, isTextBox: true });
      s.addText(t, { x: x + 0.3, y: y + 1.3, w: cw - 0.6, h: 0.45, fontSize: 17, bold: true, color: C.text2, margin: 0, isTextBox: true });
      s.addText(d, { x: x + 0.3, y: y + 1.85, w: cw - 0.6, h: 1.6, fontSize: 13, color: "475467", margin: 0, valign: "top", isTextBox: true, paraSpaceAfter: 4 });
    });
    card(s, M, 5.45, W - 2 * M, 0.95, "FFF6D6", "방법_안내");
    s.addText([{ text: "사진이 많다면  ", options: { bold: true, color: C.text2 } }, { text: "SafePlum 개선 전·후 사진대지(safeplum.com/tools/improve)에서 사진을 한 번에 넣어 A4로 출력할 수도 있습니다. 이 슬라이드는 보고 전에 지우세요.", options: { color: "475467" } }],
      { x: M + 0.3, y: 5.55, w: W - 2 * M - 0.6, h: 0.75, fontSize: 13, margin: 0, valign: "middle", isTextBox: true });
  }

  const out = __dirname + "/../../assets/files/SafePlum_improve_report_template.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("ok", out);
})();
