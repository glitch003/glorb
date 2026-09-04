"use strict";
// Battery meters for the pinned top bar, plus the detail dialog behind them.
// Reads the same SSE feed the standalone monitor serves, so this file is the
// only thing that knows how the numbers are drawn.
(function () {
  // State-of-charge bands. Green is "carry on", amber is "start thinking
  // about it", red is "deal with this now".
  var WARN_PCT = 50;
  var BAD_PCT = 25;

  var ORDER = ["12v", "24v", "72v"];
  var SHORT = { "12v": "12 V aux", "24v": "24 V lights", "72v": "72 V drive" };

  var metersEl = document.getElementById("meters");
  var dialog = document.getElementById("batteryDialog");
  var bodyEl = document.getElementById("batteryBody");
  var openBtn = document.getElementById("batteryDetail");
  var closeBtn = document.getElementById("batteryClose");
  var latest = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
               "'": "&#39;" }[c];
    });
  }

  function num(v) {
    return typeof v === "number" && isFinite(v) ? v : null;
  }

  function fmt(v, digits, fallback) {
    var n = num(v);
    return n === null ? (fallback === undefined ? "—" : fallback)
                      : n.toFixed(digits === undefined ? 0 : digits);
  }

  function obj(v) { return v && typeof v === "object" ? v : {}; }
  function arr(v) { return Array.isArray(v) ? v : []; }

  // Where each system keeps its state of charge, and whether it is measured
  // or inferred from resting cell voltage.
  function socOf(sys) {
    var pack = obj(sys.pack);
    if (sys.id === "24v") {
      return { pct: num(pack.soc_estimate), estimated: true };
    }
    if (sys.id === "72v") {
      return { pct: num(pack.soc), estimated: false };
    }
    // The 12 V chain reports per-pack SOC; the bank figure is the summary's.
    var entry = arr(sys.summary).filter(function (s) {
      return s && String(s.label).toUpperCase() === "SOC";
    })[0];
    var parsed = entry ? parseFloat(entry.value) : NaN;
    return { pct: isFinite(parsed) ? parsed : null, estimated: false };
  }

  function bandFor(sys, pct) {
    if (sys.state === "fault") return "bad";
    if (sys.state === "down" || sys.state === "stale" || pct === null) {
      return "unknown";
    }
    if (pct < BAD_PCT) return "bad";
    if (pct < WARN_PCT) return "warn";
    return "ok";
  }

  // One line of context under the bar: what the pack is doing right now.
  function subLine(sys) {
    var pack = obj(sys.pack);
    var bits = [];
    var volts = null;
    var amps = null;

    arr(sys.summary).forEach(function (s) {
      if (!s) return;
      var label = String(s.label).toLowerCase();
      var value = parseFloat(s.value);
      if (!isFinite(value)) return;
      if (label === "bus" || label === "bank") volts = value;
      if (label === "current") amps = value;
    });
    if (volts === null) volts = num(pack.bus_voltage) || num(pack.voltage);
    if (amps === null) amps = num(pack.avg_current);

    if (volts !== null) bits.push("<b>" + esc(volts.toFixed(2)) + "</b> V");
    if (amps !== null) {
      var sign = amps > 0 ? "+" : "";
      bits.push("<b>" + esc(sign + amps.toFixed(1)) + "</b> A");
    }
    if (!bits.length) bits.push(esc(sys.status_text || "no data"));
    if (sys.state === "fault") {
      bits.push('<span class="alarm">fault</span>');
    } else if (sys.state === "down" || sys.state === "stale") {
      bits.push('<span class="alarm">' + esc(sys.state) + "</span>");
    }
    return bits.join(" · ");
  }

  function meterHTML(id, sys) {
    if (!sys) {
      return '<div class="meter s-unknown" data-sys="' + esc(id) + '">' +
        '<div class="meter-top"><span class="meter-name">' +
        esc(SHORT[id] || id) + '</span></div>' +
        '<div class="meter-soc">—</div>' +
        '<div class="meter-bar"><div class="meter-fill"></div></div>' +
        '<div class="meter-sub">not reporting</div></div>';
    }
    var soc = socOf(sys);
    var band = bandFor(sys, soc.pct);
    var width = soc.pct === null ? 0 : Math.max(0, Math.min(100, soc.pct));
    // An estimated figure needs its caveat attached to it, not buried in a
    // README: this bank has no current sensor, so it sags under load.
    var tip = sys.status_text || "";
    if (soc.estimated) {
      tip = "Estimated from resting cell voltage (no current sensor on this "
        + "bank), so it reads low under load and high on charge. " + tip;
    }
    var value = soc.pct === null
      ? "—"
      : esc(soc.pct.toFixed(0)) + '<span class="pct">%</span>' +
        (soc.estimated ? '<span class="est">EST</span>' : "");
    return '<div class="meter s-' + band + '" data-sys="' + esc(id) +
      '" title="' + esc(tip) + '">' +
      '<div class="meter-top"><span class="meter-name">' +
      esc(SHORT[id] || id) + "</span></div>" +
      '<div class="meter-soc">' + value + "</div>" +
      '<div class="meter-bar"><div class="meter-fill" style="width:' +
      width + '%"></div></div>' +
      '<div class="meter-sub">' + subLine(sys) + "</div></div>";
  }

  function renderMeters(snap) {
    var systems = obj(obj(snap).systems);
    var html = "";
    for (var i = 0; i < ORDER.length; i++) {
      html += meterHTML(ORDER[i], systems[ORDER[i]]);
    }
    metersEl.innerHTML = html;
  }

  // ---- detail dialog ------------------------------------------------------

  function kv(label, value, unit) {
    if (value === "—") return "";
    return "<div><span>" + esc(label) + "</span> <b>" + esc(value) +
      (unit ? " " + esc(unit) : "") + "</b></div>";
  }

  function detailFor(id, sys) {
    if (!sys) {
      return '<div class="sys"><h3>' + esc(SHORT[id] || id) +
        '</h3><div class="sub">not in the status feed</div></div>';
    }
    var html = '<div class="sys"><h3>' + esc(sys.title || SHORT[id] || id) +
      "</h3>" + '<div class="sub">' + esc(sys.subtitle || "") + " · " +
      esc(sys.status_text || "") + " · " + esc(sys.port || "") +
      "</div>";

    html += '<div class="kvgrid">';
    arr(sys.summary).forEach(function (s) {
      if (s) html += kv(s.label, String(s.value), s.unit);
    });
    html += "</div>";

    var pack = obj(sys.pack);
    if (id === "72v") {
      html += '<div class="kvgrid" style="margin-top:8px">' +
        kv("DOD", fmt(pack.dod, 0), "%") +
        kv("2nd SOC est", fmt(pack.soc_alt, 1), "%") +
        kv("DCL", fmt(pack.dcl_a, 0), "A") +
        kv("CCL", fmt(pack.ccl_a, 0), "A") +
        kv("Relays", fmt(pack.relay_state, 0), "") + "</div>";
      arr(sys.units).forEach(function (u) {
        u = obj(u);
        html += '<div class="kvgrid" style="margin-top:6px">' +
          kv(String(u.name || "unit"), fmt(u.temp_low_c, 0) + "–" +
             fmt(u.temp_high_c, 0), "°C") +
          kv("DCL", fmt(u.dcl_a, 0), "A") +
          kv("CCL", fmt(u.ccl_a, 0), "A") +
          kv("frames", fmt(u.frames, 0), "") + "</div>";
      });
    } else if (id === "24v") {
      html += '<div class="kvgrid" style="margin-top:8px">' +
        kv("Avg cell", fmt(pack.avg_cell, 3), "V") +
        kv("Cell min", fmt(pack.cell_min, 3), "V") +
        kv("Cell max", fmt(pack.cell_max, 3), "V") +
        kv("Modules", fmt(pack.modules, 0), "") + "</div>";
      arr(sys.modules).forEach(function (m) {
        m = obj(m);
        html += '<div class="kvgrid" style="margin-top:6px">' +
          kv("Module " + fmt(m.addr, 0), fmt(m.voltage, 3), "V") +
          kv("SOC est", fmt(m.soc_estimate, 0), "%") +
          kv("spread", fmt(m.cell_delta_mv, 1), "mV") +
          kv("temps", fmt(arr(m.temps)[0], 1) + " / " +
             fmt(arr(m.temps)[1], 1), "°C") + "</div>";
      });
    } else {
      arr(sys.packs).forEach(function (p) {
        p = obj(p);
        if (!p.online) {
          html += '<div class="kvgrid" style="margin-top:6px">' +
            kv("Pack " + fmt(p.addr, 0), "not responding", "") + "</div>";
          return;
        }
        html += '<div class="kvgrid" style="margin-top:6px">' +
          kv("Pack " + fmt(p.addr, 0), fmt(p.voltage, 2), "V") +
          kv("current", fmt(p.current, 1), "A") +
          kv("SOC", fmt(p.soc, 0), "%") +
          kv("remaining", fmt(p.capacity_ah, 0), "Ah") +
          kv("cycles", fmt(p.cycles, 0), "") +
          kv("spread", fmt(p.cell_delta_mv, 1), "mV") + "</div>";
      });
    }

    var notes = arr(sys.notes).filter(function (n) {
      return n !== null && n !== undefined && String(n).trim() !== "";
    });
    if (notes.length) {
      html += '<ul class="notes">';
      notes.forEach(function (n) { html += "<li>" + esc(n) + "</li>"; });
      html += "</ul>";
    }
    return html + "</div>";
  }

  function renderDetail() {
    var systems = obj(obj(latest).systems);
    var html = "";
    for (var i = 0; i < ORDER.length; i++) {
      html += detailFor(ORDER[i], systems[ORDER[i]]);
    }
    bodyEl.innerHTML = html || "<p>No battery data yet.</p>";
  }

  function openDialog() {
    renderDetail();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog() {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  // ---- wiring -------------------------------------------------------------

  function apply(snap) {
    latest = snap;
    renderMeters(snap);
    if (dialog.open) renderDetail();
  }

  metersEl.addEventListener("click", function (e) {
    var card = e.target.closest ? e.target.closest(".meter") : null;
    if (card) openDialog();
  });
  if (openBtn) openBtn.addEventListener("click", openDialog);
  if (closeBtn) closeBtn.addEventListener("click", closeDialog);

  renderMeters(null);

  fetch("api/status")
    .then(function (r) { return r.json(); })
    .then(apply)
    .catch(function () { /* the stream below retries on its own */ });

  var stream = new EventSource("api/stream");
  stream.onmessage = function (ev) {
    try { apply(JSON.parse(ev.data)); } catch (err) { /* ignore a bad frame */ }
  };
  stream.onerror = function () { /* EventSource reconnects by itself */ };
})();
