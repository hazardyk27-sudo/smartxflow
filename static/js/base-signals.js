/* SmartXFlow Base Signals — replacement Analizler UI. No legacy analyst cards. */
(function () {
  'use strict';

  var DAY_MS = 86400000;
  var overlay, rail, engineRail, content, summary, toolbarMessage;
  var current = { start: '', day: '', engine: '*', search: '', payload: null, loading: false, seq: 0 };
  var ENGINE_NAMES = {
    EARLY_MONEY_CORE: 'Early Money Core',
    EARLY_MONEY_T12: 'Early Money T-12',
    '1X2_CONCENTRATION_V1': '1X2 Concentration V1',
    '1X2_CONCENTRATION_V2': '1X2 Concentration V2',
    HEAVY_1X2_CONCENTRATION: 'Heavy Concentration',
    SURPRISE_TEAM: 'Surprise Team',
    STABLE_OVER_2_5: 'Stable Over 2.5',
    PREMIUM_OVER_2_5: 'Premium Over 2.5',
    BTTS_YES: 'BTTS Yes'
  };
  var DAYS = ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'];
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[ch];
    });
  }
  function localDayNow() {
    var parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Istanbul', day: '2-digit', month: '2-digit', year: 'numeric'
    }).formatToParts(new Date());
    var o = {};
    parts.forEach(function (p) { o[p.type] = p.value; });
    return o.year + '-' + o.month + '-' + o.day;
  }
  function offsetDay(day, n) {
    return new Date(Date.parse(day + 'T12:00:00Z') + n * DAY_MS).toISOString().slice(0, 10);
  }
  function trTime(value) {
    if (!value) return '—';
    var d = new Date(value);
    if (isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('tr-TR', {
      timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit'
    }).format(d);
  }
  function labelEngine(name) { return ENGINE_NAMES[name] || String(name).replace(/_/g, ' '); }
  function pick(item) {
    var v = item.selection;
    if (item.market === '1X2') {
      if (v === '1') return item.home + ' kazanır';
      if (v === '2') return item.away + ' kazanır';
      if (v === 'X') return 'Beraberlik';
    }
    if (item.market === 'OU25') return v === 'O' ? '2.5 Üst' : v === 'U' ? '2.5 Alt' : v;
    if (item.market === 'BTTS') return v === 'Y' ? 'Karşılıklı Gol Var' : v === 'N' ? 'Karşılıklı Gol Yok' : v;
    return v;
  }
  function marketName(v) { return v === 'OU25' ? 'Alt / Üst 2.5' : v === 'BTTS' ? 'Karşılıklı Gol' : 'Maç Sonucu'; }
  function signalStage(item) {
    if (item.kind === 'CORRECTED') return 'Uzlaştırma kaydı';
    if (item.kind === 'FINAL_SIGNAL') return 'T-6 değerlendirmesi';
    if (item.kind === 'PRELIMINARY_SIGNAL') return 'T-8 ön sinyal';
    return 'Erken sinyal';
  }
  function ensureElements() {
    overlay = document.getElementById('sxfBaseSignalOverlay');
    rail = document.getElementById('sxfSignalDateRail');
    engineRail = document.getElementById('sxfSignalEngineRail');
    content = document.getElementById('sxfSignalContent');
    summary = document.getElementById('sxfSignalSummary');
    toolbarMessage = document.getElementById('sxfSignalNotice');
    return !!(overlay && rail && engineRail && content && summary && toolbarMessage);
  }
  function matches(item) {
    return item && item.day === current.day &&
      (current.engine === '*' || item.engine === current.engine) &&
      (!current.search || [item.home, item.away, item.league, labelEngine(item.engine)]
        .join(' ').toLocaleLowerCase('tr-TR').includes(current.search));
  }
  function allItems() { return current.payload && Array.isArray(current.payload.items) ? current.payload.items : []; }
  function getEngines() {
    var arr = (current.payload && current.payload.engines || []).slice();
    allItems().forEach(function (x) { if (arr.indexOf(x.engine) < 0) arr.push(x.engine); });
    return arr;
  }
  function renderDates() {
    if (!rail) return;
    var today = localDayNow();
    var items = allItems();
    var html = '';
    for (var i = 0; i < 21; i++) {
      var day = offsetDay(current.start, i);
      var date = new Date(day + 'T12:00:00Z');
      var count = items.filter(function (x) {
        return x.day === day && (current.engine === '*' || x.engine === current.engine);
      }).length;
      var selected = day === current.day, isToday = day === today;
      html += '<button type="button" class="sxf-day' + (selected ? ' is-active' : '') +
        (isToday ? ' is-today' : '') + '" data-day="' + day + '" role="tab" aria-selected="' +
        (selected ? 'true' : 'false') + '" aria-label="' + esc(day + ' - ' + count + ' sinyal') + '">' +
        '<span class="sxf-day-week">' + DAYS[date.getUTCDay()] + '</span>' +
        '<span class="sxf-day-date">' + date.getUTCDate().toString().padStart(2, '0') +
        '.' + String(date.getUTCMonth() + 1).padStart(2, '0') + '</span>' +
        '<span class="sxf-day-indicator' + (count ? ' has-signals' : '') + '"></span>' +
        (isToday ? '<span class="sxf-day-now">Bugün</span>' : '') + '</button>';
    }
    rail.innerHTML = html;
    rail.querySelectorAll('[data-day]').forEach(function (b) {
      b.addEventListener('click', function () { current.day = b.dataset.day; render(); });
    });
    var active = rail.querySelector('.is-active');
    if (active) active.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }
  function renderEngines() {
    var all = allItems(), engines = getEngines();
    var html = '<button class="sxf-engine' + (current.engine === '*' ? ' selected' : '') +
      '" data-engine="*">Tüm motorlar <span>' + all.filter(function (x) { return x.day === current.day; }).length + '</span></button>';
    engines.forEach(function (name) {
      var count = all.filter(function (x) { return x.day === current.day && x.engine === name; }).length;
      html += '<button class="sxf-engine' + (current.engine === name ? ' selected' : '') +
        '" data-engine="' + esc(name) + '">' + esc(labelEngine(name)) +
        (count ? '<span>' + count + '</span>' : '') + '</button>';
    });
    engineRail.innerHTML = html;
    engineRail.querySelectorAll('[data-engine]').forEach(function (b) {
      b.addEventListener('click', function () {
        current.engine = b.dataset.engine;
        render();
      });
    });
  }
  function card(item) {
    var odds = typeof item.odds === 'number' && isFinite(item.odds) ?
      '<div class="sxf-signal-odds"><span>Sinyal oranı</span><strong>' +
        item.odds.toFixed(2) + '</strong></div>' :
      '<div class="sxf-signal-odds is-unavailable">Oran kaydı yok</div>';
    var checkpoint = typeof item.checkpoint === 'number' ? 'T-' + item.checkpoint : 'SXF';
    var source = typeof item.source_checkpoint === 'number' ? 'Kaynak T-' + item.source_checkpoint : '';
    return '<article class="sxf-signal-card">' +
      '<div class="sxf-signal-card-head"><div class="sxf-signal-league">' +
      '<span class="sxf-league-mark"></span>' + esc(item.league || 'Lig belirtilmemiş') +
      '</div><time>' + esc(trTime(item.kickoff_utc)) + ' TR</time></div>' +
      '<h3 class="sxf-signal-fixture">' + esc(item.home || 'Ev sahibi') +
      '<span>vs</span>' + esc(item.away || 'Deplasman') + '</h3>' +
      '<div class="sxf-signal-choice"><div><small>' + esc(marketName(item.market)) +
      ' · ' + esc(item.market) + '</small><strong>' + esc(pick(item)) +
      '</strong></div>' + odds + '</div>' +
      '<div class="sxf-signal-card-foot"><span class="sxf-stage">' +
      esc(signalStage(item)) + '</span><span class="sxf-checkpoint">' +
      esc(checkpoint) + (source ? ' · ' + esc(source) : '') + '</span>' +
      '<span class="sxf-signal-moment">Veri ' + esc(trTime(item.observed_at)) +
      '</span></div>' +
      (item.strength_tag ? '<div class="sxf-strength-note">Güç etiketi · ayrı doğrulama değildir</div>' : '') +
      '</article>';
  }
  function renderContent() {
    var list = allItems().filter(matches);
    var engines = Array.from(new Set(list.map(function (x) { return x.engine; })));
    var fixtures = new Set(list.map(function (x) { return x.uid; }));
    summary.textContent = list.length + ' sinyal · ' + fixtures.size + ' maç · ' + engines.length + ' motor';
    if (!list.length) {
      content.innerHTML = '<div class="sxf-zero"><span class="sxf-zero-icon">◇</span>' +
        '<h3>Bu gün için sinyal bulunmuyor</h3>' +
        '<p>Seçili motor ve tarihte tamamlanmış Base kaydı yok. Shadow süresince oluşan yeni kayıtlar yenilemeyle görünür.</p>' +
        '</div>';
      return;
    }
    var groups = {};
    list.forEach(function (x) { (groups[x.engine] = groups[x.engine] || []).push(x); });
    var html = '';
    Object.keys(groups).sort().forEach(function (name) {
      var rows = groups[name].slice().sort(function (a,b) {
        return a.kickoff_utc.localeCompare(b.kickoff_utc) || b.id-a.id;
      });
      var matchCount = new Set(rows.map(function (x) { return x.uid; })).size;
      html += '<section class="sxf-motor-group"><div class="sxf-motor-head">' +
        '<div><span class="sxf-motor-overline">SİNYAL MOTORU</span><h3>' +
        esc(labelEngine(name)) + '</h3></div><div class="sxf-motor-count">' +
        rows.length + ' sinyal <span>·</span> ' + matchCount + ' maç</div></div>' +
        '<div class="sxf-signal-grid">' + rows.map(card).join('') + '</div></section>';
    });
    content.innerHTML = html;
  }
  function render() {
    if (!ensureElements()) return;
    renderDates();
    renderEngines();
    renderContent();
  }
  function setMessage(text, mode) {
    toolbarMessage.textContent = text;
    toolbarMessage.dataset.mode = mode || 'info';
  }
  function load() {
    if (!ensureElements()) return Promise.resolve();
    var seq = ++current.seq;
    current.loading = true;
    setMessage('Base sinyalleri yükleniyor…', 'loading');
    content.innerHTML = '<div class="sxf-zero"><div class="sxf-spinner"></div><p>Motor kayıtları getiriliyor…</p></div>';
    var headers = {};
    if (window.userLicenseKey) headers['X-License-Key'] = window.userLicenseKey;
    return fetch('/api/base-signals/feed?start=' + encodeURIComponent(current.start) + '&days=21', {
      credentials: 'same-origin', headers: headers
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || data.status !== 'ok') {
          var error = new Error(data.error || 'SIGNAL_DATA_UNAVAILABLE');
          error.code = data.error; throw error;
        }
        return data;
      });
    }).then(function (data) {
      if (seq !== current.seq || overlay.hidden) return;
      current.payload = data;
      current.loading = false;
      setMessage('SHADOW · Test sinyalleri, onaylanmış bahis önerisi değildir', 'shadow');
      render();
    }).catch(function (error) {
      if (seq !== current.seq || overlay.hidden) return;
      current.loading = false;
      current.payload = null;
      var code = error.code || '';
      var msg = code === 'PRO_REQUIRED' ? 'Bu bölüm PRO üyelik gerektirir.' :
        code === 'LOGIN_REQUIRED' || code === 'SESSION_EXPIRED' ? 'Oturum açmanız gerekiyor.' :
        'Sinyal verileri şu anda yüklenemiyor.';
      setMessage(msg, 'error');
      content.innerHTML = '<div class="sxf-zero"><span class="sxf-zero-icon">!</span>' +
        '<h3>' + esc(msg) + '</h3><p>Veri bulunamadığında eski analiz kartları veya örnek sinyaller gösterilmez.</p>' +
        '<button class="sxf-retry" type="button" id="sxfSignalRetry">Yeniden dene</button></div>';
      document.getElementById('sxfSignalRetry').addEventListener('click', load);
      renderDates(); renderEngines();
    });
  }
  function switchWindow(direction) {
    current.start = offsetDay(current.start, 10 * direction);
    current.day = offsetDay(current.day, 10 * direction);
    if (current.day < current.start || current.day >= offsetDay(current.start, 21)) {
      current.day = offsetDay(current.start, 10);
    }
    load();
  }
  function open() {
    if (!ensureElements()) return;
    var today = localDayNow();
    current.day = today; current.start = offsetDay(today, -10);
    current.engine = '*'; current.search = ''; current.payload = null;
    var input = document.getElementById('sxfSignalSearch');
    if (input) input.value = '';
    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('sxf-signals-open');
    var close = document.getElementById('sxfSignalClose');
    if (close) close.focus();
    load();
  }
  function close() {
    if (!ensureElements()) return;
    overlay.hidden = true;
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('sxf-signals-open');
    current.seq++; // Cancel any prior asynchronous UI response.
  }
  function attach() {
    if (!ensureElements()) return;
    var closeBtn = document.getElementById('sxfSignalClose');
    if (closeBtn) closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !overlay.hidden) close();
    });
    document.getElementById('sxfSignalPrevious').addEventListener('click', function () { switchWindow(-1); });
    document.getElementById('sxfSignalNext').addEventListener('click', function () { switchWindow(1); });
    document.getElementById('sxfSignalToday').addEventListener('click', function () {
      var today = localDayNow(); current.day = today; current.start = offsetDay(today, -10); load();
    });
    document.getElementById('sxfSignalRefresh').addEventListener('click', load);
    document.getElementById('sxfSignalSearch').addEventListener('input', function (e) {
      current.search = String(e.target.value || '').toLocaleLowerCase('tr-TR').trim();
      renderContent();
    });
  }
  window.openBaseSignalsPanel = open;
  window.closeBaseSignalsPanel = close;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach, { once: true });
  } else attach();
})();
