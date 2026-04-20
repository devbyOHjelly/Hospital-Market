/* DOM delegation for leaderboard + chip-remove (postMessage is installed from dash_app clientside_callback). */
(function () {
  function setProps(id, props) {
    try {
      var dc = window.dash_clientside;
      if (dc && typeof dc.set_props === "function") {
        dc.set_props(id, props);
      }
    } catch (e) {
      console.warn("dash_bridge set_props failed", e);
    }
  }

  document.addEventListener("click", function (e) {
    var row = e.target.closest(".leaderboard-zip");
    if (row) {
      var zip = row.getAttribute("data-zip");
      var state = row.getAttribute("data-state");
      setProps("bridge-leaderboard-click", { data: { zipcode: zip, state: state } });
      window._pendingFocusZip = String(zip);
      window._focusBlinkDone = false;
      var attempts = 0;
      function tryFocus() {
        if (window._focusBlinkDone || attempts >= 24) return;
        var iframe = document.getElementById("map_frame");
        if (iframe && iframe.contentWindow) {
          iframe.contentWindow.postMessage({ type: "focus_blink", zipcode: window._pendingFocusZip }, "*");
        }
        attempts++;
        setTimeout(tryFocus, 500);
      }
      tryFocus();
    }
    var chip = e.target.closest(".chip-remove");
    if (chip) {
      e.preventDefault();
      e.stopPropagation();
      var z = chip.getAttribute("data-zip");
      setProps("bridge-chip-remove", { data: { zipcode: String(z) } });
      var iframe2 = document.getElementById("map_frame");
      if (iframe2 && iframe2.contentWindow) {
        iframe2.contentWindow.postMessage({ type: "deselect_zip", zipcode: String(z) }, "*");
      }
    }
  });

  document.addEventListener("click", function (e) {
    var tab = e.target.closest('[role="tab"]');
    if (!tab || !tab.closest(".hm-sidebar")) return;
    setTimeout(function () {
      var iframe = document.getElementById("map_frame");
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({ type: "clear_focus_highlight" }, "*");
      }
    }, 50);
  });
})();
