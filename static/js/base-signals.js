/* SmartXFlow Analizler V4: graphite motor directory -> day-scoped fixture detail.
   Displays only authenticated Base feed records. No synthetic results or picks. */
(function () {
  'use strict';
  var DAY_MS = 86400000;
  var overlay, rail, content, summary, notice, searchWrap;
  var priorFocus = null;
  var current = { start: '', day: '', engine: null, search: '', payload: null, seq: 0 };
  var ENGINES = {
    EARLY_MONEY_CORE: { name: 'Early Money Core', description: 'Erken para hareketleri', market: 'PARA AKIŞI', code: 'EM' },
    EARLY_MONEY_T12: { name: 'Early Money T-12', description: 'T-12 erken hareketleri', market: 'PARA AKIŞI', code: 'T12' },
    '1X2_CONCENTRATION_V1': { name: '1X2 Concentration V1', description: '1X2 para yoğunlaşması · V1', market: 'MAÇ SONUCU', code: 'V1' },
    '1X2_CONCENTRATION_V2': { name: '1X2 Concentration V2', description: '1X2 para yoğunlaşması · V2', market: 'MAÇ SONUCU', code: 'V2' },
    HEAVY_1X2_CONCENTRATION: { name: 'Heavy Concentration', description: 'Güçlü 1X2 yoğunlaşması', market: 'MAÇ SONUCU', code: 'HC' },
    SURPRISE_TEAM: { name: 'Surprise Team', description: 'Sürpriz takım sinyalleri', market: 'MAÇ SONUCU', code: 'ST' },
    STABLE_OVER_2_5: { name: 'Stable Over 2.5', description: '2.5 üst istikrarı', market: 'ALT / ÜST', code: 'O2' },
    PREMIUM_OVER_2_5: { name: 'Premium Over 2.5', description: '2.5 üst premium hareketleri', market: 'ALT / ÜST', code: 'PO' },
    PREMIUM_OVER_MIN1_70: { name: 'Premium Over · Min 1.70', description: '1.70+ premium üst · güç etiketi', market: 'ALT / ÜST', code: 'P70' },
    BTTS_YES: { name: 'BTTS Yes', description: 'Karşılıklı gol var sinyalleri', market: 'KG VAR / YOK', code: 'KG' }
  };
  var WEEK = ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'];
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[ch];
    });
  }
  function todayTR() {
    var parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(new Date());
    var obj = {};
    parts.forEach(function (part) { obj[part.type] = part.value; });
    return obj.year + '-' + obj.month + '-' + obj.day;
  }
  function dayShift(day, offset) {
    return new Date(Date.parse(day + 'T12:00:00Z') + offset * DAY_MS).toISOString().slice(0, 10);
  }
  function dateTitle(day) {
    var d = new Date(day + 'T12:00:00Z');
    return d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  }
  function timeTR(value) {
    if (!value) return '—';
    var d = new Date(value);
    if (!isFinite(d.getTime())) return '—';
    return new Intl.DateTimeFormat('tr-TR', {
      timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit'
    }).format(d);
  }
  function labelEngine(id) { return (ENGINES[id] && ENGINES[id].name) || String(id).replace(/_/g, ' '); }
  function marketLabel(m) {
    return m === 'OU25' ? 'Alt / Üst 2.5' : m === 'BTTS' ? 'Karşılıklı Gol' : 'Maç Sonucu';
  }
  function choice(item) {
    var s = item.selection;
    if (item.market === '1X2') {
      if (s === '1') return (item.home || 'Ev sahibi') + ' kazanır';
      if (s === '2') return (item.away || 'Deplasman') + ' kazanır';
      if (s === 'X') return 'Beraberlik';
    }
    if (item.market === 'OU25') return s === 'O' ? '2.5 Üst' : s === 'U' ? '2.5 Alt' : s;
    if (item.market === 'BTTS') return s === 'Y' ? 'KG Var' : s === 'N' ? 'KG Yok' : s;
    return s;
  }
  function stage(item) {
    if (item.stage_status === 'T8_HISTORICAL') return 'Geçmiş T-8';
    if (item.kind === 'CORRECTED') return 'Uzlaştırma';
    if (item.kind === 'FINAL_SIGNAL') return 'T-6';
    if (item.kind === 'PRELIMINARY_SIGNAL') return 'Ön sinyal · T-8';
    return 'Erken sinyal';
  }
  function getEls() {
    overlay = document.getElementById('sxfBaseSignalOverlay');
    rail = document.getElementById('sxfSignalDateRail');
    content = document.getElementById('sxfSignalContent');
    summary = document.getElementById('sxfSignalSummary');
    notice = document.getElementById('sxfSignalNotice');
    searchWrap = document.getElementById('sxfSearchWrap');
    return !!(overlay && rail && content && summary && notice && searchWrap);
  }
  function items() { return current.payload && Array.isArray(current.payload.items) ? current.payload.items : []; }
  function engineIds() {
    var known = Object.keys(ENGINES);
    if (current.payload && Array.isArray(current.payload.engines)) {
      current.payload.engines.forEach(function (id) { if (known.indexOf(id) === -1) known.push(id); });
    }
    items().forEach(function (x) { if (known.indexOf(x.engine) === -1) known.push(x.engine); });
    return known;
  }
  function dayItems() {
    return items().filter(function (x) {
      return x.day === current.day && (current.engine === null || x.engine === current.engine);
    });
  }
  function fixturesCount(rows) {
    return new Set(rows.map(function (x) { return x.uid + '/' + x.kickoff_utc; })).size;
  }
  function renderDates() {
    var today = todayTR(), html = '';
    for (var i = 0; i < 21; i++) {
      var day = dayShift(current.start, i), d = new Date(day + 'T12:00:00Z');
      var count = items().filter(function (x) {
        return x.day === day && (current.engine === null || x.engine === current.engine);
      }).length;
      var selected = day === current.day, isToday = day === today;
      html += '<button type="button" class="sxf-day' + (selected ? ' is-active' : '') +
        '" data-day="' + day + '" role="tab" aria-selected="' + (selected ? 'true' : 'false') +
        '" aria-label="' + esc(day + ', ' + count + ' sinyal') + '">' +
        '<span class="sxf-day-week">' + WEEK[d.getUTCDay()] + '</span>' +
        '<span class="sxf-day-date">' + String(d.getUTCDate()).padStart(2, '0') + '.' +
        String(d.getUTCMonth() + 1).padStart(2, '0') + '</span>' +
        '<span class="sxf-day-indicator' + (count ? ' has-signals' : '') + '"></span>' +
        (isToday ? '<span class="sxf-day-now">Bugün</span>' : '') + '</button>';
    }
    rail.innerHTML = html;
    rail.querySelectorAll('[data-day]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        current.day = btn.dataset.day;
        render();
      });
    });
    var active = rail.querySelector('.is-active');
    if (active && typeof active.scrollIntoView === 'function')
      active.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'instant' });
  }
  function engineCard(name) {
    var descriptor = ENGINES[name] || { name: labelEngine(name), description: 'SmartXFlow Base sinyal motoru', market: 'SİNYAL', code: 'SX' };
    var all = items().filter(function (x) { return x.engine === name; });
    var today = all.filter(function (x) { return x.day === current.day; });
    var fixtures = fixturesCount(today);
    return '<button type="button" class="sxf-engine-tile" data-motor="' + esc(name) +
      '" aria-label="' + esc(descriptor.name + ' motorunu aç, ' + fixtures + ' maç') + '">' +
      '<span class="sxf-engine-tile-top"><span class="sxf-engine-mark" aria-hidden="true">' +
      esc(descriptor.code) + '</span><span class="sxf-engine-category">' + esc(descriptor.market) +
      '</span></span><strong class="sxf-engine-name">' + esc(descriptor.name) + '</strong>' +
      '<span class="sxf-engine-description">' + esc(descriptor.description) + '</span>' +
      '<span class="sxf-engine-tile-bottom"><span><b>' + fixtures +
      '</b> maç <span class="sxf-secondary-count">· ' + today.length +
      ' sinyal</span></span><span class="sxf-tile-open" aria-hidden="true">↗</span></span>' +
      '</button>';
  }
  function signalRow(item) {
    var isHistory = item.stage_status === 'T8_HISTORICAL';
    var odds = typeof item.odds === 'number' && isFinite(item.odds)
      ? '<span class="sxf-row-odds">Oran <b>' + item.odds.toFixed(2) + '</b></span>'
      : '<span class="sxf-row-no-odds">Oran kayıtlı değil</span>';
    return '<div class="sxf-signal-row' + (isHistory ? ' is-archived' : '') + '">' +
      '<div class="sxf-signal-pick"><span class="sxf-signal-market">' +
      esc(marketLabel(item.market)) + '</span><strong>' + esc(choice(item)) +
      '</strong></div>' + odds +
      '<div class="sxf-signal-meta"><span class="sxf-stage">' + esc(stage(item)) +
      '</span>' + (typeof item.checkpoint === 'number' ? '<span>T-' + item.checkpoint + '</span>' : '') +
      (typeof item.source_checkpoint === 'number' && item.source_checkpoint !== item.checkpoint
        ? '<span>Kaynak T-' + item.source_checkpoint + '</span>' : '') +
      '<span>Veri ' + esc(timeTR(item.observed_at)) + '</span></div>' +
      (isHistory ? '<div class="sxf-row-warning">T-6 kararı sonrası geçmiş ön sinyal</div>' : '') +
      '</div>';
  }
  function fixtureCard(rows) {
    var item = rows[0];
    return '<article class="sxf-signal-card"><header class="sxf-match-top">' +
      '<span class="sxf-match-league">' + esc(item.league || 'Lig belirtilmemiş') + '</span>' +
      '<time class="sxf-match-time">' + esc(timeTR(item.kickoff_utc)) + ' TR</time></header>' +
      '<h3 class="sxf-match-name">' + esc(item.home || 'Ev sahibi') +
      '<span>–</span>' + esc(item.away || 'Deplasman') + '</h3>' +
      '<div class="sxf-match-signals">' + rows.map(signalRow).join('') + '</div></article>';
  }
  function renderHome() {
    var entries = engineIds();
    var cards = entries.map(engineCard).join('');
    var rows = dayItems();
    summary.textContent = dateTitle(current.day) + '  ·  ' + fixturesCount(rows) + ' maç / ' + rows.length + ' sinyal';
    searchWrap.hidden = true;
    content.innerHTML = '<div class="sxf-directory-header"><div><span class="sxf-eyebrow">' +
      'SİNYAL MOTORLARI</span><h3>Bir motor seç</h3><p>Seçtiğin günün maçlarını motor bazında görüntüle.</p>' +
      '</div><span class="sxf-directory-total">' + entries.length + ' motor</span></div>' +
      '<div class="sxf-engine-grid">' + cards + '</div>';
    content.querySelectorAll('[data-motor]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        current.engine = btn.dataset.motor;
        current.search = '';
        var search = document.getElementById('sxfSignalSearch');
        if (search) search.value = '';
        render();
        content.scrollTop = 0;
      });
    });
  }
  function renderDetail() {
    var descriptor = ENGINES[current.engine];
    var source = dayItems();
    var needle = current.search;
    var filtered = source.filter(function (x) {
      return !needle || [x.home, x.away, x.league, choice(x)].join(' ')
        .toLocaleLowerCase('tr-TR').includes(needle);
    });
    var groups = new Map();
    filtered.slice().sort(function (a, b) {
      return a.kickoff_utc.localeCompare(b.kickoff_utc) || a.id - b.id;
    }).forEach(function (x) {
      var key = x.uid + '/' + x.kickoff_utc;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(x);
    });
    summary.textContent = labelEngine(current.engine) + ' · ' + fixturesCount(source) +
      ' maç / ' + source.length + ' sinyal';
    searchWrap.hidden = false;
    var html = '<div class="sxf-detail-head"><button class="sxf-back" type="button" ' +
      'id="sxfSignalBack">← Tüm motorlar</button><div class="sxf-detail-caption">' +
      '<span class="sxf-eyebrow">' + esc(descriptor ? descriptor.market : 'SİNYAL MOTORU') +
      '</span><h3>' + esc(labelEngine(current.engine)) + '</h3><p>' +
      esc(dateTitle(current.day)) + ' · ' + groups.size + ' maç</p></div></div>';
    if (!filtered.length) {
      html += '<div class="sxf-zero"><span class="sxf-zero-icon">◇</span>' +
        '<h4>Bu gün için maç bulunmuyor</h4><p>Seçili motor için bu tarihte tamamlanmış bir sinyal kaydı yok.</p></div>';
    } else {
      html += '<div class="sxf-signal-grid">' +
        Array.from(groups.values()).map(fixtureCard).join('') + '</div>';
    }
    content.innerHTML = html;
    document.getElementById('sxfSignalBack').addEventListener('click', function () {
      var returningFrom = current.engine;
      current.engine = null;
      current.search = '';
      var search = document.getElementById('sxfSignalSearch');
      if (search) search.value = '';
      render();
      var chosen = Array.from(content.querySelectorAll('[data-motor]')).find(function (node) {
        return node.dataset.motor === returningFrom;
      });
      if (chosen) chosen.focus();
      else content.scrollTop = 0;
    });
  }
  function render() {
    if (!getEls()) return;
    renderDates();
    if (current.engine === null) renderHome();
    else renderDetail();
  }
  function message(text, state) {
    notice.textContent = text;
    notice.dataset.mode = state || 'shadow';
  }
  function load() {
    if (!getEls()) return Promise.resolve();
    var seq = ++current.seq;
    message('Sinyaller yükleniyor…', 'loading');
    summary.textContent = 'Yükleniyor…';
    content.innerHTML = '<div class="sxf-zero"><span class="sxf-spinner"></span><p>Motor kayıtları yükleniyor…</p></div>';
    var headers = {};
    if (window.userLicenseKey) headers['X-License-Key'] = window.userLicenseKey;
    return fetch('/api/base-signals/feed?start=' + encodeURIComponent(current.start) + '&days=21', {
      credentials: 'same-origin', headers: headers
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || data.status !== 'ok') {
          var err = new Error(data.error || 'SIGNAL_DATA_UNAVAILABLE');
          err.code = data.error;
          throw err;
        }
        return data;
      });
    }).then(function (data) {
      if (seq !== current.seq || overlay.hidden) return;
      current.payload = data;
      message('SHADOW / TEST · Onaylanmış bahis önerisi değildir', 'shadow');
      render();
    }).catch(function (err) {
      if (seq !== current.seq || overlay.hidden) return;
      current.payload = null;
      var error = err.code === 'PRO_REQUIRED' ? 'Bu bölüm PRO üyelik gerektirir.' :
        err.code === 'LOGIN_REQUIRED' || err.code === 'SESSION_EXPIRED' ? 'Oturum açman gerekiyor.' :
        'Sinyal verileri yüklenemedi.';
      message(error, 'error');
      summary.textContent = 'Veri alınamadı';
      searchWrap.hidden = true;
      content.innerHTML = '<div class="sxf-zero"><span class="sxf-zero-icon">!</span>' +
        '<h4>' + esc(error) + '</h4><p>Motor verisi olmadığında örnek veya eski sinyal gösterilmez.</p>' +
        '<button type="button" class="sxf-retry" id="sxfSignalRetry">Tekrar dene</button></div>';
      document.getElementById('sxfSignalRetry').addEventListener('click', load);
    });
  }
  function switchWindow(delta) {
    var nextStart = dayShift(current.start, delta * 10);
    var today = todayTR();
    // The private API bounds kickoff windows: 45 days back, 21 days ahead.
    // Never replace an otherwise healthy screen with a predictable 400.
    if (nextStart < dayShift(today, -45) || nextStart > dayShift(today, 21)) {
      message('Bu tarih aralığı için kayıt görüntülenemiyor.', 'shadow');
      return;
    }
    current.start = nextStart;
    current.day = dayShift(current.day, delta * 10);
    load();
  }
  function open() {
    if (!getEls()) return;
    var today = todayTR();
    current.start = dayShift(today, -10);
    current.day = today;
    current.engine = null;
    current.search = '';
    current.payload = null;
    var search = document.getElementById('sxfSignalSearch');
    if (search) search.value = '';
    priorFocus = document.activeElement;
    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('sxf-signals-open');
    document.getElementById('sxfSignalClose').focus();
    load();
  }
  function close() {
    if (!getEls()) return;
    overlay.hidden = true;
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('sxf-signals-open');
    current.seq++;
    if (priorFocus && typeof priorFocus.focus === 'function') priorFocus.focus();
    priorFocus = null;
  }
  function attach() {
    if (!getEls()) return;
    document.getElementById('sxfSignalClose').addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.addEventListener('keydown', function (e) {
      if (overlay.hidden) return;
      if (e.key === 'Escape') { close(); return; }
      if (e.key !== 'Tab') return;
      var nodes = overlay.querySelectorAll('button:not([disabled]), input:not([disabled])');
      var visible = Array.from(nodes).filter(function (n) { return !n.closest('[hidden]'); });
      if (!visible.length) return;
      var first = visible[0], last = visible[visible.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    document.getElementById('sxfSignalPrevious').addEventListener('click', function () { switchWindow(-1); });
    document.getElementById('sxfSignalNext').addEventListener('click', function () { switchWindow(1); });
    document.getElementById('sxfSignalToday').addEventListener('click', function () {
      var today = todayTR();
      current.start = dayShift(today, -10);
      current.day = today;
      load();
    });
    document.getElementById('sxfSignalRefresh').addEventListener('click', load);
    document.getElementById('sxfSignalSearch').addEventListener('input', function (e) {
      current.search = String(e.target.value || '').toLocaleLowerCase('tr-TR').trim();
      if (current.engine !== null) renderDetail();
    });
  }
  window.openBaseSignalsPanel = open;
  window.closeBaseSignalsPanel = close;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach, { once: true });
  } else attach();
})();
