/* Glorb power monitor — vanilla JS, no build step, no external requests. */
(function () {
  'use strict';

  /* ------------------------------------------------------------------ *
   * constants + state
   * ------------------------------------------------------------------ */

  var SYS_ORDER = ['12v', '24v', '72v'];
  var SYS_LABEL = { '12v': '12 V', '24v': '24 V', '72v': '72 V' };
  var TABS = [
    { id: 'overview', label: 'Overview' },
    { id: '12v', label: '12 V' },
    { id: '24v', label: '24 V' },
    { id: '72v', label: '72 V' },
    { id: 'raw', label: 'Raw' }
  ];
  var STATE_RANK = { ok: 0, warn: 1, stale: 2, down: 3, fault: 4 };
  var HIST_CAP = 300;
  var DELTA_HILITE_MV = 30;
  var LS_KEY = 'glorbmon.tab';

  var snapshot = null;      // last good status object
  var lastRecv = 0;         // Date.now() when snapshot was applied
  var history = {};         // sysId -> array of numbers (first summary value)
  var rawData = null;       // last /api/raw payload
  var rawError = null;
  var rawLoading = false;
  var rawScroll = {};       // key -> scrollTop, so refresh keeps position
  var connected = false;
  var sawFirstMessage = false;
  var sawError = false;     // stream has failed at least once
  var activeTab = 'overview';

  var elTabs = document.getElementById('tabs');
  var elContent = document.getElementById('content');
  var elBanner = document.getElementById('banner');
  var elPill = document.getElementById('overallPill');

  /* ------------------------------------------------------------------ *
   * tiny helpers
   * ------------------------------------------------------------------ */

  var ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v).replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  /** Coerce to a finite number, or null. */
  function num(v) {
    var n;
    if (typeof v === 'number') n = v;
    else if (typeof v === 'string' && v.trim() !== '') n = Number(v);
    else return null;
    return isFinite(n) ? n : null;
  }

  /** Format a number for display; never yields undefined/null/NaN. */
  function fmt(value, digits, fallback) {
    if (fallback === undefined) fallback = '—';
    var n = num(value);
    if (n === null) return fallback;
    var d = (typeof digits === 'number' && digits >= 0 && digits <= 20) ? digits : 0;
    return n.toFixed(d);
  }

  /** Display a pre-formatted summary value (backend sends strings). */
  function showValue(v) {
    if (typeof v === 'number') return isFinite(v) ? String(v) : '—';
    if (typeof v === 'string') {
      var s = v.trim();
      if (!s) return '—';
      var low = s.toLowerCase();
      if (low === 'nan' || low === 'null' || low === 'undefined') return '—';
      return s;
    }
    return '—';
  }

  function arr(v) { return Array.isArray(v) ? v : []; }
  function obj(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }

  function lsGet(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* private mode / quota */ } }

  function stateOf(v) {
    var s = (typeof v === 'string') ? v.trim().toLowerCase() : '';
    return Object.prototype.hasOwnProperty.call(STATE_RANK, s) ? s : 'unknown';
  }

  function rankOf(s) {
    return Object.prototype.hasOwnProperty.call(STATE_RANK, s) ? STATE_RANK[s] : 2;
  }

  function systems() { return obj(obj(snapshot).systems); }

  function sysAt(id) {
    var s = systems()[id];
    return (s && typeof s === 'object' && !Array.isArray(s)) ? s : null;
  }

  /** "3.4 s ago" — base age plus time elapsed since we received the snapshot. */
  function ageText(baseAge) {
    var b = num(baseAge);
    if (b === null) return 'age unknown';
    var a = b + (lastRecv ? (Date.now() - lastRecv) / 1000 : 0);
    if (!(a > 0)) a = 0;
    if (a < 10) return a.toFixed(1) + ' s ago';
    if (a < 600) return Math.round(a) + ' s ago';
    return Math.round(a / 60) + ' min ago';
  }

  function ageHTML(ageS) {
    var b = num(ageS);
    return '<span class="age" data-age="' + (b === null ? '' : esc(String(b))) + '">' + esc(ageText(b)) + '</span>';
  }

  function updateAges() {
    var nodes = elContent.querySelectorAll('.age');
    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i].getAttribute('data-age');
      nodes[i].textContent = ageText(a === '' ? null : a);
    }
  }

  /* ------------------------------------------------------------------ *
   * shared HTML fragments
   * ------------------------------------------------------------------ */

  function statHTML(label, value, unit, cls) {
    return '<div class="' + (cls || 'stat-item') + '">' +
      '<div class="stat-label">' + esc(label) + '</div>' +
      '<div class="stat-value">' + esc(value) +
      (unit ? '<span class="unit">' + esc(unit) + '</span>' : '') +
      '</div></div>';
  }

  function chipsHTML(items, cls) {
    var list = arr(items).filter(function (x) {
      return x !== null && x !== undefined && String(x).trim() !== '';
    });
    if (!list.length) return '';
    var html = '<div class="chips">';
    for (var i = 0; i < list.length; i++) {
      html += '<span class="chip' + (cls ? ' ' + cls : '') + '">' + esc(String(list[i])) + '</span>';
    }
    return html + '</div>';
  }

  function tempChipsHTML(temps) {
    var list = arr(temps);
    if (!list.length) return '';
    var html = '<div class="chips">';
    for (var i = 0; i < list.length; i++) {
      html += '<span class="chip">' + esc(fmt(list[i], 1)) + ' °C</span>';
    }
    return html + '</div>';
  }

  function summaryHTML(entries) {
    var list = arr(entries);
    if (!list.length) return '<div class="empty">no readings</div>';
    var html = '<div class="summary">';
    for (var i = 0; i < list.length; i++) {
      var e = obj(list[i]);
      html += statHTML(e.label === null || e.label === undefined ? '' : e.label,
                       showValue(e.value), e.unit);
    }
    return html + '</div>';
  }

  /* ------------------------------------------------------------------ *
   * cell bars
   * ------------------------------------------------------------------ */

  function cellStats(src) {
    var o = obj(src);
    var raw = arr(o.cells);
    var nums = [];
    for (var i = 0; i < raw.length; i++) {
      var v = num(raw[i]);
      if (v !== null) nums.push(v);
    }
    var mn = num(o.cell_min);
    var mx = num(o.cell_max);
    if (mn === null && nums.length) mn = Math.min.apply(null, nums);
    if (mx === null && nums.length) mx = Math.max.apply(null, nums);
    var d = num(o.cell_delta_mv);
    if (d === null && mn !== null && mx !== null) d = (mx - mn) * 1000;
    return { raw: raw, min: mn, max: mx, delta: d };
  }

  /**
   * Bars scale across the observed min->max of this pack/module so that small
   * imbalances are visible. A floor of 8% keeps the lowest cell from vanishing.
   */
  function cellBarsHTML(src, opts) {
    opts = obj(opts);
    var st = cellStats(src);
    if (!st.raw.length) return '<div class="empty">no cell data</div>';
    var span = (st.min !== null && st.max !== null) ? (st.max - st.min) : 0;
    var scaled = span > 1e-9;
    var hilite = st.delta !== null && st.delta > DELTA_HILITE_MV;
    var html = '<div class="cells' + (opts.small ? ' cells-sm' : '') + '">';
    for (var i = 0; i < st.raw.length; i++) {
      var v = num(st.raw[i]);
      var pct = 100;
      var cls = '';
      if (v === null) {
        pct = 0;
      } else if (scaled) {
        pct = 8 + 92 * ((v - st.min) / span);
        if (!(pct >= 0)) pct = 0;
        if (pct > 100) pct = 100;
        if (hilite) {
          if (v >= st.max - 1e-9) cls = ' hi';
          else if (v <= st.min + 1e-9) cls = ' lo';
        }
      }
      html += '<div class="cell' + cls + '">' +
        (opts.index ? '<span class="cidx">' + esc(String(i + 1)) + '</span>' : '') +
        '<span class="cbar"><i style="width:' + pct.toFixed(1) + '%"></i></span>' +
        '<span class="clabel">' + esc(fmt(v, 3)) + '</span>' +
        '</div>';
    }
    return html + '</div>';
  }

  function cellRangeHTML(src) {
    var st = cellStats(src);
    return '<div class="muted small tabular">min ' + esc(fmt(st.min, 3)) +
      ' V · max ' + esc(fmt(st.max, 3)) +
      ' V · Δ ' + esc(fmt(st.delta, 1)) + ' mV</div>';
  }

  function legendHTML() {
    return '<div class="panel legend">Cell bars scale across each pack’s own ' +
      'min→max, so a full bar just means “highest cell here” — not a full cell. ' +
      'When Δ exceeds ' + DELTA_HILITE_MV + ' mV the <b class="hi">highest</b> cell turns blue and the ' +
      '<b class="lo">lowest</b> turns amber; below that everything stays neutral.</div>';
  }

  /* ------------------------------------------------------------------ *
   * system card
   * ------------------------------------------------------------------ */

  function systemCardHTML(id, sys, clickable) {
    var s = obj(sys);
    var st = stateOf(s.state);
    var title = (s.title === null || s.title === undefined || String(s.title).trim() === '')
      ? (SYS_LABEL[id] || id) : s.title;
    var html = '<div class="panel card s-' + st + (clickable ? ' clickable' : '') + '"' +
      (clickable ? ' data-goto="' + esc(id) + '" role="button" tabindex="0"' : '') + '>';
    html += '<div class="card-head"><div>' +
      '<div class="card-title">' + esc(title) + '</div>' +
      (s.subtitle ? '<div class="card-sub">' + esc(s.subtitle) + '</div>' : '') +
      '</div><span class="pill s-' + st + '">' + esc(st === 'unknown' ? 'no state' : st) + '</span></div>';
    html += '<div class="status-row"><span class="dot"></span><span>' +
      esc(s.status_text || 'no status reported') + '</span></div>';
    html += summaryHTML(s.summary);
    if (clickable) {
      html += '<canvas class="spark" data-spark="' + esc(id) + '" width="320" height="38" aria-hidden="true"></canvas>';
    }
    html += '<div class="foot">' + ageHTML(s.age_s) +
      (s.port ? '<span>·</span><span>' + esc(s.port) + '</span>' : '') + '</div>';
    return html + '</div>';
  }

  function missingCardHTML(id, clickable) {
    return '<div class="panel card s-down' + (clickable ? ' clickable' : '') + '"' +
      (clickable ? ' data-goto="' + esc(id) + '" role="button" tabindex="0"' : '') + '>' +
      '<div class="card-head"><div><div class="card-title">' + esc(SYS_LABEL[id] || id) + '</div>' +
      '<div class="card-sub">not in the status feed</div></div>' +
      '<span class="pill s-down">absent</span></div>' +
      '<div class="status-row"><span class="dot"></span><span>' +
      (snapshot ? 'backend is not reporting this system' : 'waiting for first status…') +
      '</span></div></div>';
  }

  /* ------------------------------------------------------------------ *
   * tab renderers
   * ------------------------------------------------------------------ */

  function renderOverview() {
    var html = '';
    var alerts = arr(obj(snapshot).alerts);
    if (alerts.length) {
      html += '<div class="panel"><div class="panel-title">Alerts</div>';
      for (var i = 0; i < alerts.length; i++) {
        var a = obj(alerts[i]);
        var lvl = stateOf(a.level);
        html += '<div class="alert ' + esc(lvl) + '">' +
          '<span class="who">' + esc(a.system || '—') + '</span>' +
          '<span class="what">' + esc(a.text || '') + '</span></div>';
      }
      html += '</div>';
    }

    html += '<div class="grid">';
    for (var j = 0; j < SYS_ORDER.length; j++) {
      var id = SYS_ORDER[j];
      var sys = sysAt(id);
      html += sys ? systemCardHTML(id, sys, true) : missingCardHTML(id, true);
    }
    html += '</div>';

    if (!snapshot) {
      html += '<div class="panel empty">Waiting for the first status snapshot from the backend…</div>';
    }
    return html;
  }

  function render12v(sys) {
    var packs = arr(sys.packs);
    if (!packs.length) {
      return '<div class="panel empty">No packs reported. ' + esc(sys.status_text || '') + '</div>';
    }
    var html = legendHTML();
    for (var i = 0; i < packs.length; i++) {
      var p = obj(packs[i]);
      var online = p.online !== false;
      var addr = num(p.addr);
      html += '<div class="panel' + (online ? '' : ' offline') + '">';
      html += '<div class="panel-title">Pack ' + esc(addr === null ? (i + 1) : fmt(addr, 0)) +
        (online ? '' : ' <span class="tag bad">not responding</span>') + '</div>';

      if (!online) {
        html += '</div>';
        continue;
      }

      html += '<div class="stats">' +
        statHTML('Voltage', fmt(p.voltage, 2), 'V') +
        statHTML('Current', fmt(p.current, 1), 'A') +
        statHTML('SOC', fmt(p.soc, 0), '%') +
        statHTML('Cycles', fmt(p.cycles, 0), '') +
        statHTML('Capacity', fmt(p.capacity_ah, 0), 'Ah') +
        '</div>';

      html += cellBarsHTML(p, { index: true });
      html += cellRangeHTML(p);

      var temps = tempChipsHTML(p.temps);
      if (temps) html += '<div class="kv" style="margin-bottom:2px">Temperatures</div>' + temps;

      var alarms = chipsHTML(p.alarms, 'bad');
      if (alarms) html += '<div class="kv" style="margin-bottom:2px">Alarms</div>' + alarms;

      html += '</div>';
    }
    return html;
  }

  function render24v(sys) {
    var pack = obj(sys.pack);
    var html = '<div class="panel"><div class="panel-title">Pack totals' +
      (pack.faulted === true ? ' <span class="tag bad">faulted</span>' : '') + '</div>' +
      '<div class="stats">' +
      statHTML('Bank', fmt(pack.voltage, 2), 'V') +
      statHTML('SOC (est)', fmt(pack.soc_estimate, 0), '%') +
      statHTML('Avg cell', fmt(pack.avg_cell, 3), 'V') +
      statHTML('Avg temp', fmt(pack.avg_temp, 1), '°C') +
      statHTML('Cell min', fmt(pack.cell_min, 3), 'V') +
      statHTML('Cell max', fmt(pack.cell_max, 3), 'V') +
      statHTML('Delta', fmt(pack.cell_delta_mv, 2), 'mV') +
      statHTML('Module spread', fmt(num(pack.module_spread_v) === null ? null : num(pack.module_spread_v) * 1000, 0), 'mV') +
      statHTML('Modules', fmt(pack.modules, 0), '') +
      '</div></div>';

    var mods = arr(sys.modules);
    if (!mods.length) {
      return html + '<div class="panel empty">No modules reported. ' + esc(sys.status_text || '') + '</div>';
    }

    html += legendHTML();
    html += '<div class="panel"><div class="panel-title">Modules</div><div class="rows">';
    for (var i = 0; i < mods.length; i++) {
      var m = obj(mods[i]);
      var addr = num(m.addr);
      var st = cellStats(m);
      html += '<div class="row-item">';
      html += '<div class="row-head">' +
        '<span class="row-name">Module ' + esc(addr === null ? (i + 1) : fmt(addr, 0)) + '</span>' +
        '<span class="big">' + esc(fmt(m.voltage, 2)) + '<span class="unit">V</span>' +
        (num(m.soc_estimate) === null ? '' :
          ' <span class="unit">· ' + esc(fmt(m.soc_estimate, 0)) + '% est</span>') +
        '</span>' +
        '</div>';
      html += cellBarsHTML(m, { small: true });
      html += '<div class="kv">' +
        '<span>Δ <b>' + esc(fmt(st.delta, 2)) + ' mV</b></span>' +
        '<span>min <b>' + esc(fmt(st.min, 3)) + ' V</b></span>' +
        '<span>max <b>' + esc(fmt(st.max, 3)) + ' V</b></span>' +
        '<span>temps <b>' + esc(fmt(arr(m.temps)[0], 1)) + ' / ' +
        esc(fmt(arr(m.temps)[1], 1)) + ' °C</b></span>' +
        '</div>';
      var flags = chipsHTML(m.flags, 'bad');
      if (flags) html += '<div style="margin-top:8px">' + flags + '</div>';
      html += '</div>';
    }
    html += '</div></div>';
    return html + notesHTML(sys.notes);
  }

  function render72v(sys) {
    var pack = obj(sys.pack);
    var html = '<div class="panel"><div class="panel-title">Pack</div><div class="stats">' +
      statHTML('Bus', fmt(pack.bus_voltage, 1), 'V') +
      statHTML('Current', fmt(pack.avg_current, 1), 'A') +
      statHTML('SOC', fmt(pack.soc, 0), '%') +
      statHTML('Relay', fmt(pack.relay_state, 0), '') +
      statHTML('DCL', fmt(pack.dcl_a, 0), 'A') +
      statHTML('CCL', fmt(pack.ccl_a, 0), 'A') +
      statHTML('Temp low', fmt(pack.temp_low_c, 0), '°C') +
      statHTML('Temp high', fmt(pack.temp_high_c, 0), '°C') +
      '</div></div>';

    var units = arr(sys.units);
    if (!units.length) {
      html += '<div class="panel empty">No BMS units on the bus. ' + esc(sys.status_text || '') + '</div>';
    } else {
      html += '<div class="grid">';
      for (var i = 0; i < units.length; i++) {
        var u = obj(units[i]);
        html += '<div class="panel">' +
          '<div class="panel-title">' + esc(u.name || ('Unit ' + (i + 1))) + '</div>' +
          '<div class="stats">' +
          statHTML('DCL', fmt(u.dcl_a, 0), 'A') +
          statHTML('CCL', fmt(u.ccl_a, 0), 'A') +
          statHTML('Temp low', fmt(u.temp_low_c, 0), '°C') +
          statHTML('Temp high', fmt(u.temp_high_c, 0), '°C') +
          '</div>' +
          '<div class="kv"><span>frames <b>' + esc(fmt(u.frames, 0)) + '</b></span>' +
          '<span>' + ageHTML(u.age_s) + '</span></div>' +
          '</div>';
      }
      html += '</div>';
    }

    return html + notesHTML(sys.notes);
  }

  function notesHTML(value) {
    var notes = arr(value).filter(function (n) {
      return n !== null && n !== undefined && String(n).trim() !== '';
    });
    if (!notes.length) return '';
    var html = '<ul class="notes">';
    for (var j = 0; j < notes.length; j++) {
      html += '<li>' + esc(String(notes[j])) + '</li>';
    }
    return html + '</ul>';
  }

  function renderSystemTab(id) {
    var sys = sysAt(id);
    if (!sys) return missingCardHTML(id, false);
    var html = systemCardHTML(id, sys, false);
    if (id === '12v') html += render12v(sys);
    else if (id === '24v') html += render24v(sys);
    else if (id === '72v') html += render72v(sys);
    return html;
  }

  function renderRaw() {
    var html = '<div class="panel"><div class="rawhead">' +
      '<div class="panel-title" style="margin:0">Recent protocol lines</div>' +
      '<button class="btn" type="button" data-action="refresh-raw"' +
      (rawLoading ? ' disabled' : '') + '>' + (rawLoading ? 'Loading…' : 'Refresh') + '</button>' +
      '</div>';
    html += '<div class="muted small">Debug view — fetched on demand from ' +
      '<span class="tabular">/api/raw</span>, not from the live stream.</div></div>';

    if (rawError) {
      html += '<div class="panel"><span class="chip bad">' + esc(rawError) + '</span></div>';
    }

    var data = obj(rawData);
    var keys = SYS_ORDER.slice();
    // include any unexpected extra keys the backend may add
    Object.keys(data).forEach(function (k) {
      if (keys.indexOf(k) === -1) keys.push(k);
    });

    var any = false;
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (!Object.prototype.hasOwnProperty.call(data, k)) continue;
      any = true;
      var lines = arr(data[k]).map(function (l) {
        return (l === null || l === undefined) ? '' : String(l);
      });
      html += '<div class="panel"><div class="panel-title">' + esc(SYS_LABEL[k] || k) +
        ' <span class="tag">' + esc(String(lines.length)) + ' lines</span></div>';
      html += lines.length
        ? '<pre class="raw" data-rawkey="' + esc(k) + '">' + esc(lines.join('\n')) + '</pre>'
        : '<div class="empty">no lines captured</div>';
      html += '</div>';
    }

    if (!any && !rawError) {
      html += '<div class="panel empty">' +
        (rawLoading ? 'Fetching…' : 'No raw capture available.') + '</div>';
    }
    return html;
  }

  /* ------------------------------------------------------------------ *
   * sparklines
   * ------------------------------------------------------------------ */

  function drawSpark(cv, pts) {
    if (!cv || typeof cv.getContext !== 'function') return;
    var rect = cv.getBoundingClientRect ? cv.getBoundingClientRect() : null;
    var w = Math.floor((rect && rect.width) || cv.clientWidth || 0);
    var h = Math.floor((rect && rect.height) || cv.clientHeight || 0);
    if (!isFinite(w) || !isFinite(h) || w < 2 || h < 2) return false;

    var dpr = window.devicePixelRatio;
    if (!isFinite(dpr) || dpr <= 0) dpr = 1;
    dpr = Math.min(dpr, 3);

    cv.width = Math.max(2, Math.round(w * dpr));
    cv.height = Math.max(2, Math.round(h * dpr));

    var ctx = cv.getContext('2d');
    if (!ctx) return true;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    var data = arr(pts);
    if (data.length < 2) return true;

    var mn = Infinity, mx = -Infinity, i;
    for (i = 0; i < data.length; i++) {
      if (data[i] < mn) mn = data[i];
      if (data[i] > mx) mx = data[i];
    }
    if (!isFinite(mn) || !isFinite(mx)) return true;
    var span = mx - mn;
    if (!(span > 1e-9)) { mn -= 0.5; mx += 0.5; span = mx - mn; }

    var pad = 3;
    var usable = h - pad * 2;
    if (!(usable > 0)) usable = h;
    var stepX = (data.length > 1) ? (w - 2) / (data.length - 1) : 0;

    ctx.beginPath();
    for (i = 0; i < data.length; i++) {
      var x = 1 + i * stepX;
      var y = pad + usable * (1 - (data[i] - mn) / span);
      if (!isFinite(x) || !isFinite(y)) continue;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = '#34c3ff';
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.stroke();
    return true;
  }

  function drawAllSparks(retry) {
    var nodes = elContent.querySelectorAll('canvas[data-spark]');
    var deferred = false;
    for (var i = 0; i < nodes.length; i++) {
      var id = nodes[i].getAttribute('data-spark');
      if (drawSpark(nodes[i], history[id]) === false) deferred = true;
    }
    // canvas can be 0-wide before first layout; try once more on the next frame
    if (deferred && retry !== false && window.requestAnimationFrame) {
      window.requestAnimationFrame(function () { drawAllSparks(false); });
    }
  }

  /* ------------------------------------------------------------------ *
   * painting
   * ------------------------------------------------------------------ */

  function overallState() {
    var ss = systems();
    var keys = Object.keys(ss);
    if (!keys.length) return null;
    var worst = 'ok';
    for (var i = 0; i < keys.length; i++) {
      var st = stateOf(obj(ss[keys[i]]).state);
      if (rankOf(st) > rankOf(worst)) worst = st;
    }
    return worst;
  }

  function paintChrome() {
    var st = overallState();
    var label;
    if (!snapshot) {
      st = 'unknown';
      label = connected ? 'waiting for data' : (sawError ? 'offline' : 'connecting…');
    } else if (st === null) {
      st = 'unknown';
      label = 'no systems';
    } else {
      label = st === 'unknown' ? 'unknown' : st;
    }
    elPill.className = 'pill s-' + st;
    elPill.textContent = label;

    if (!connected && (sawError || sawFirstMessage)) {
      elBanner.textContent = snapshot
        ? 'Disconnected from the monitor — retrying… (showing the last values received)'
        : 'Cannot reach the monitor backend — retrying…';
      elBanner.classList.remove('hidden');
    } else {
      elBanner.classList.add('hidden');
      elBanner.textContent = '';
    }
  }

  function tabHTML() {
    if (activeTab === 'overview') return renderOverview();
    if (activeTab === 'raw') return renderRaw();
    if (SYS_ORDER.indexOf(activeTab) !== -1) return renderSystemTab(activeTab);
    return renderOverview();
  }

  function saveRawScroll() {
    var pres = elContent.querySelectorAll('pre.raw[data-rawkey]');
    for (var i = 0; i < pres.length; i++) {
      rawScroll[pres[i].getAttribute('data-rawkey')] = pres[i].scrollTop;
    }
  }

  function restoreRawScroll() {
    var pres = elContent.querySelectorAll('pre.raw[data-rawkey]');
    for (var i = 0; i < pres.length; i++) {
      var k = pres[i].getAttribute('data-rawkey');
      if (typeof rawScroll[k] === 'number') pres[i].scrollTop = rawScroll[k];
      else pres[i].scrollTop = pres[i].scrollHeight;   // newest lines first view
    }
  }

  function renderContent() {
    if (activeTab === 'raw') saveRawScroll();
    elContent.innerHTML = tabHTML();
    if (activeTab === 'raw') restoreRawScroll();
    drawAllSparks();
  }

  /** Full repaint; the Raw pane is left alone so its scroll never jumps. */
  function paint() {
    paintChrome();
    if (activeTab === 'raw') { updateAges(); return; }
    renderContent();
  }

  function paintTabs() {
    var btns = elTabs.querySelectorAll('button[data-tab]');
    for (var i = 0; i < btns.length; i++) {
      var on = btns[i].getAttribute('data-tab') === activeTab;
      btns[i].className = on ? 'active' : '';
      btns[i].setAttribute('aria-current', on ? 'page' : 'false');
    }
  }

  function selectTab(id, remember) {
    var valid = false;
    for (var i = 0; i < TABS.length; i++) if (TABS[i].id === id) valid = true;
    if (!valid) id = 'overview';
    activeTab = id;
    if (remember !== false) lsSet(LS_KEY, id);
    paintTabs();
    paintChrome();
    renderContent();
    if (id === 'raw' && rawData === null && !rawLoading) fetchRaw();
  }

  /* ------------------------------------------------------------------ *
   * data
   * ------------------------------------------------------------------ */

  function pushHistory(data) {
    var ss = obj(obj(data).systems);
    var keys = Object.keys(ss);
    for (var i = 0; i < keys.length; i++) {
      var id = keys[i];
      var first = obj(arr(obj(ss[id]).summary)[0]);
      var v = num(first.value);
      if (v === null) continue;
      if (!history[id]) history[id] = [];
      history[id].push(v);
      if (history[id].length > HIST_CAP) {
        history[id].splice(0, history[id].length - HIST_CAP);
      }
    }
  }

  function applySnapshot(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return;
    snapshot = data;
    lastRecv = Date.now();
    pushHistory(data);
    paint();
  }

  function fetchStatus() {
    if (!window.fetch) return;
    window.fetch('/api/status', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        // don't clobber a newer snapshot that already arrived on the stream
        if (d && !snapshot) applySnapshot(d);
      })
      .catch(function () { /* the stream is the real source; ignore */ });
  }

  function fetchRaw() {
    if (!window.fetch) {
      rawError = 'This browser cannot fetch the raw log.';
      if (activeTab === 'raw') renderContent();
      return;
    }
    rawLoading = true;
    rawError = null;
    if (activeTab === 'raw') renderContent();
    window.fetch('/api/raw', { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        rawData = (d && typeof d === 'object' && !Array.isArray(d)) ? d : {};
        rawError = null;
      })
      .catch(function (e) {
        rawData = rawData || {};
        rawError = 'Could not load /api/raw (' + (e && e.message ? e.message : 'error') + ')';
      })
      .then(function () {
        rawLoading = false;
        if (activeTab === 'raw') renderContent();
      });
  }

  function connect() {
    if (!window.EventSource) {
      // very old browser: fall back to polling the one-shot endpoint
      connected = true;
      sawFirstMessage = true;
      window.setInterval(function () {
        if (!window.fetch) return;
        window.fetch('/api/status', { cache: 'no-store' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (d) { if (d) applySnapshot(d); })
          .catch(function () { });
      }, 2000);
      return;
    }

    var es;
    try {
      es = new window.EventSource('/api/stream');
    } catch (e) {
      connected = false;
      sawError = true;
      paintChrome();
      return;
    }

    es.onopen = function () {
      connected = true;
      paintChrome();
    };
    es.onmessage = function (ev) {
      connected = true;
      sawFirstMessage = true;
      var d = null;
      try { d = JSON.parse(ev.data); } catch (err) { return; }
      applySnapshot(d);
    };
    es.onerror = function () {
      // EventSource retries on its own; just reflect the state
      connected = false;
      sawError = true;
      paintChrome();
    };
  }

  /* ------------------------------------------------------------------ *
   * init
   * ------------------------------------------------------------------ */

  function buildTabs() {
    var html = '';
    for (var i = 0; i < TABS.length; i++) {
      html += '<button type="button" data-tab="' + esc(TABS[i].id) + '">' +
        esc(TABS[i].label) + '</button>';
    }
    elTabs.innerHTML = html;
    elTabs.addEventListener('click', function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest('button[data-tab]') : null;
      if (b) selectTab(b.getAttribute('data-tab'));
    });
  }

  function wireContent() {
    elContent.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var btn = t.closest('[data-action="refresh-raw"]');
      if (btn) { fetchRaw(); return; }
      var card = t.closest('[data-goto]');
      if (card) selectTab(card.getAttribute('data-goto'));
    });
    elContent.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var t = ev.target;
      if (!t || !t.closest) return;
      var card = t.closest('[data-goto]');
      if (card) { ev.preventDefault(); selectTab(card.getAttribute('data-goto')); }
    });
  }

  function init() {
    buildTabs();
    wireContent();

    var saved = lsGet(LS_KEY);
    activeTab = 'overview';
    if (saved) {
      for (var i = 0; i < TABS.length; i++) if (TABS[i].id === saved) activeTab = saved;
    }

    paintTabs();
    paintChrome();
    renderContent();
    if (activeTab === 'raw') fetchRaw();

    fetchStatus();
    connect();

    window.setInterval(updateAges, 1000);
    window.addEventListener('resize', function () { drawAllSparks(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
