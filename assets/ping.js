/* 하루 방문자 수 집계 */
// 0-1) 하루 방문자 수: 이 브라우저가 오늘 처음 온 것이면 '오늘만 쓰는 임의 번호'를 한 번 보낸다.
  //      번호는 날마다 새로 만들고 계정·기기 정보와 묶지 않는다. 실패해도 화면에는 영향이 없다.
  (function () {
    var cfg = document.currentScript || document.getElementById("stPing"); if (!cfg || !cfg.getAttribute("data-url") || !window.fetch || !window.crypto || navigator.webdriver) return;
    try {
      var d = new Date(new Date().getTime() + 9 * 3600 * 1000).toISOString().slice(0, 10), K = "safetake.visit";
      var cur = JSON.parse(localStorage.getItem(K) || "null");
      if (cur && cur.d === d) return;
      var b = new Uint8Array(12); crypto.getRandomValues(b);
      var id = Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
      localStorage.setItem(K, JSON.stringify({ d: d }));   // 번호는 저장하지 않는다(보내고 버린다)
      fetch(cfg.getAttribute("data-url") + "/rest/v1/rpc/visit_ping", { method: "POST", keepalive: true,
        headers: { "Content-Type": "application/json", apikey: cfg.getAttribute("data-key"), Authorization: "Bearer " + cfg.getAttribute("data-key") },
        body: JSON.stringify({ p_vid: id }) }).catch(function () {});
    } catch (e) {}
  })();

// 0-2) SNS·블로그 유입: 주소에 utm_source 가 붙어 들어온 방문을 채널·분야·게시물별로 '횟수만' 센다(방문자를 구분하는 값은 보내지 않는다).
//      같은 탭에서 같은 게시물 주소는 한 번만 센다. supabase/utm.sql 을 실행하기 전에는 요청이 조용히 실패하고 화면에는 영향이 없다.
  (function () {
    var cfg = document.currentScript || document.getElementById("stPing"); if (!cfg || !cfg.getAttribute("data-url") || !window.fetch || navigator.webdriver) return;
    try {
      var q = new URLSearchParams(location.search), ok = /^[0-9A-Za-z_.-]{1,40}$/, src = q.get("utm_source") || "";
      if (!ok.test(src)) return;
      var f = function (k) { var v = q.get(k) || ""; return ok.test(v) ? v : ""; };
      var b = { p_source: src, p_medium: f("utm_medium"), p_campaign: f("utm_campaign"), p_content: f("utm_content") };
      var K = "safeplum.utm." + b.p_source + "." + b.p_content;
      try { if (sessionStorage.getItem(K)) return; sessionStorage.setItem(K, "1"); } catch (e) {}
      fetch(cfg.getAttribute("data-url") + "/rest/v1/rpc/utm_ping", { method: "POST", keepalive: true,
        headers: { "Content-Type": "application/json", apikey: cfg.getAttribute("data-key"), Authorization: "Bearer " + cfg.getAttribute("data-key") },
        body: JSON.stringify(b) }).catch(function () {});
    } catch (e) {}
  })();
