// 작성기·도구 전수 자동 점검 (2026-11-23)
// 사용: node scripts/check_writers.mjs <사이트 주소, 예: http://localhost:8765/> [결과 JSON 경로]
// 필요: puppeteer-core, Chrome(환경변수 CHROME_PATH, 기본 /usr/bin/google-chrome)
// 점검: ① 스크립트 오류(pageerror·console.error) ② 휴대폰(390px) 가로 넘침 ③ '예시' 버튼 누른 뒤 오류
//       ④ 인쇄 모드에서 A4 폭을 넘는 요소 ⑤ 입력 → 새로 고침 후 남아 있는지(브라우저 저장)
// 외부 서비스(게시판·광고·글꼴 등) 연결 실패는 오류로 세지 않는다.
import puppeteer from "puppeteer-core";
import fs from "node:fs";

const BASE = (process.argv[2] || "http://localhost:8765/").replace(/\/?$/, "/");
const OUT = process.argv[3] || "";
const ROOT = process.env.SITE_DIR || "_site";
const ONLY = process.env.ONLY ? new RegExp(process.env.ONLY) : null;

function pages() {
  const out = [];
  const walk = (d) => {
    for (const n of fs.readdirSync(d, { withFileTypes: true })) {
      const p = `${d}/${n.name}`;
      if (n.isDirectory()) walk(p);
      else if (n.name === "index.html") out.push(p.slice(ROOT.length + 1, -"index.html".length));
    }
  };
  walk(`${ROOT}/tools`);
  return out.filter((p) => !ONLY || ONLY.test(p)).sort();
}

const IGNORE = /supabase|googlesyndication|google-analytics|googletagmanager|fonts\.g|ERR_TUNNEL|ERR_NAME|ERR_CONNECTION|net::ERR|Failed to load resource|favicon|status of 40[34]|kakao|naver|youtube|ping/i;

async function check(browser, path) {
  const r = { path, errors: [], warn: [] };
  const page = await browser.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push("pageerror: " + String(e.message || e).slice(0, 300)));
  page.on("console", (m) => { if (m.type() === "error" && !IGNORE.test(m.text())) errs.push("console: " + m.text().slice(0, 300)); });
  page.on("dialog", (d) => d.dismiss().catch(() => {}));
  const url = BASE + path;
  try {
    // ① 데스크톱
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 });
    await new Promise((s) => setTimeout(s, 600));
    // ③ 예시 버튼
    const ex = await page.evaluate(() => {
      const bs = [...document.querySelectorAll("button, a.btn, [role=button]")].filter((b) => /예시로 채우기|예시 채우기|예시 불러오기|예시로|다른 예시/.test(b.textContent || "") && b.offsetParent);
      const n = bs.length;
      bs.slice(0, 3).forEach((b) => { try { b.click(); } catch (e) {} });
      return n;
    });
    r.example_buttons = ex;
    await new Promise((s) => setTimeout(s, 500));
    await page.keyboard.press("Escape").catch(() => {});
    // ⑤ 저장: 첫 번째 빈 글 칸에 표시 문구 입력 → 1.5초 → 새로 고침 → 남았는지
    const tag = "점검" + Date.now().toString().slice(-5);
    const typed = await page.evaluate((tag) => {
      const els = [...document.querySelectorAll("input[type=text], input:not([type]), textarea")].filter((x) => x.offsetParent && !x.readOnly && !x.disabled && !x.value && !x.closest("header, nav, .hd, [role=dialog], dialog, .modal"));
      const el = els[0];
      if (!el) return "";
      el.focus();
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, tag);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.blur();
      return el.id || el.name || el.getAttribute("placeholder") || el.tagName;
    }, tag);
    if (typed) {
      await new Promise((s) => setTimeout(s, 1600));
      await page.reload({ waitUntil: "networkidle2", timeout: 45000 });
      await new Promise((s) => setTimeout(s, 800));
      const kept = await page.evaluate((tag) => [...document.querySelectorAll("input, textarea")].some((x) => x.value === tag) || document.body.innerText.includes(tag), tag);
      r.persist = kept ? "kept" : "lost";
      r.persist_field = typed;
    } else r.persist = "no-field";
    // ④ 인쇄 폭
    await page.emulateMediaType("print");
    await page.setViewport({ width: 794, height: 1123 });
    await new Promise((s) => setTimeout(s, 300));
    const pw = await page.evaluate(() => {
      const W = document.documentElement.clientWidth;
      const bad = [];
      for (const el of document.querySelectorAll("table, img, .page, .a4, section, .sheet")) {
        const cs = getComputedStyle(el);
        if (cs.display === "none" || cs.visibility === "hidden" || !el.getClientRects().length) continue;
        const rc = el.getBoundingClientRect();
        if (rc.width > 0 && rc.right > W + 2) bad.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : ""} right=${Math.round(rc.right)}`);
      }
      return { W, bad: bad.slice(0, 5), n: bad.length };
    });
    if (pw.n) r.warn.push(`인쇄 폭 초과 ${pw.n}곳: ${pw.bad.join(", ")}`);
    // ⑥ 회사 문서로 쓸 수 있는가: 인쇄물에 사이트 홍보 문구·채도 높은 바탕색이 남는지
    const pr = await page.evaluate(() => {
      const txt = document.body.innerText || "";
      const promo = (txt.match(/SafePlum|safeplum|세이프플럼|무료 양식|무료 작성기|보조양식/g) || []);
      const sat = new Map();
      for (const el of document.body.querySelectorAll("*")) {
        if (!el.getClientRects().length) continue;
        const cs = getComputedStyle(el);
        if (cs.display === "none" || cs.visibility === "hidden") continue;
        const m = cs.backgroundColor.match(/rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?/);
        if (!m || (m[4] !== undefined && +m[4] < 0.3)) continue;
        const [R, G, B] = [+m[1], +m[2], +m[3]], mx = Math.max(R, G, B), mn = Math.min(R, G, B);
        const s = mx ? (mx - mn) / mx : 0;
        if (s > 0.35 && mx > 60) { const k = `${R},${G},${B}`; sat.set(k, (sat.get(k) || 0) + 1); }
      }
      return { promo: [...new Set(promo)], colors: [...sat.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6) };
    });
    if (pr.promo.length) r.warn.push(`인쇄물에 홍보성 문구: ${pr.promo.join(", ")}`);
    if (pr.colors.length) r.warn.push(`인쇄물 컬러 바탕 ${pr.colors.length}종: ${pr.colors.map(([k, n]) => `rgb(${k})×${n}`).join(" ")}`);
    r.print_promo = pr.promo; r.print_colors = pr.colors;
    await page.emulateMediaType("screen");
    // ② 휴대폰
    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await page.reload({ waitUntil: "networkidle2", timeout: 45000 });
    await new Promise((s) => setTimeout(s, 600));
    const ov = await page.evaluate(() => {
      const W = window.innerWidth, sw = document.scrollingElement.scrollWidth;
      const wide = [];
      if (sw > W + 1) for (const el of document.body.querySelectorAll("*")) {
        const rc = el.getBoundingClientRect();
        if (rc.right > W + 1 && rc.width > 0 && !el.closest("[style*=overflow], .tbl-wrap, .scroll-x, pre")) {
          let p = el.parentElement, inScroll = false;
          while (p) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") { inScroll = true; break; } p = p.parentElement; }
          if (!inScroll) wide.push(`${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/)[0] : ""}(${Math.round(rc.right)})`);
          if (wide.length >= 4) break;
        }
      }
      return { W, sw, wide };
    });
    if (ov.sw > ov.W + 1) r.errors.push(`휴대폰 가로 넘침 ${ov.sw}px > ${ov.W}px: ${ov.wide.join(", ")}`);
  } catch (e) {
    r.errors.push("점검 실패: " + String(e.message || e).slice(0, 200));
  }
  r.errors.push(...[...new Set(errs)]);
  await page.close();
  return r;
}

const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox", "--disable-gpu"] });
const list = pages();
const results = [];
const CONC = Number(process.env.CONC || 4);
let i = 0;
await Promise.all(Array.from({ length: CONC }, async () => {
  while (i < list.length) {
    const p = list[i++];
    const r = await check(browser, p);
    results.push(r);
    const flag = r.errors.length ? "오류" : r.warn.length ? "주의" : "정상";
    console.log(`[${flag}] ${p}  예시버튼 ${r.example_buttons ?? "-"} · 저장 ${r.persist ?? "-"}${r.errors.length ? "\n   - " + r.errors.join("\n   - ") : ""}${r.warn.length ? "\n   · " + r.warn.join("\n   · ") : ""}`);
  }
}));
await browser.close();
results.sort((a, b) => a.path.localeCompare(b.path));
const bad = results.filter((r) => r.errors.length);
console.log(`\n점검 ${results.length}쪽 · 오류 ${bad.length}쪽 · 주의 ${results.filter((r) => !r.errors.length && r.warn.length).length}쪽 · 저장 안 됨 ${results.filter((r) => r.persist === "lost").length}쪽`);
if (OUT) fs.writeFileSync(OUT, JSON.stringify(results, null, 1));
process.exit(bad.length ? 1 : 0);
