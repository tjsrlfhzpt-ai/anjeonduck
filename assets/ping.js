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
