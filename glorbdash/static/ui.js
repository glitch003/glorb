"use strict";
// Dashboard-only UI wiring. Everything that draws the car lives in the
// lights package's app.js, which this deliberately does not touch.
(function () {
  // 52 patterns is more than fits in a glance, so let the list be searched
  // rather than scrolled. Buttons are read live because app.js builds them
  // asynchronously once /state comes back.
  var filter = document.getElementById("patternFilter");
  var list = document.getElementById("patterns");
  if (!filter || !list) return;

  function applyFilter() {
    var q = filter.value.trim().toLowerCase();
    var buttons = list.querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) {
      var name = (buttons[i].dataset.name || buttons[i].textContent || "")
        .toLowerCase();
      buttons[i].classList.toggle("hidden", q !== "" && name.indexOf(q) === -1);
    }
  }

  filter.addEventListener("input", applyFilter);
  // Enter picks the only remaining match, so filtering is a one-handed
  // "type three letters and go" on a phone.
  filter.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var visible = [];
    var buttons = list.querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) {
      if (!buttons[i].classList.contains("hidden")) visible.push(buttons[i]);
    }
    if (visible.length) {
      visible[0].click();
      filter.blur();
    }
  });

  // app.js populates the grid after its first fetch; re-apply once it lands.
  new MutationObserver(applyFilter).observe(list, { childList: true });
})();
