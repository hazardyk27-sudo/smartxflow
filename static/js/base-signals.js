/* SmartXFlow Sinyal Motoru: today-first daily motor directory. 
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
  // All visible text is resolved from the active 7-language app dictionary.
  // Turkish is a temporary compatibility fallback if i18n has not loaded yet.
  function t(key, fallback) {
    var full = 'app.v4.' + key;
    var i18n = window.SXFI18n;
    if (i18n && typeof i18n.t === 'function') {
      var value = i18n.t(full);
      if (value && value !== full) return value;
    }
    return fallback || '';
  }
  function fmt(key, fallback, vars) {
    return t(key, fallback).replace(/\{(\w+)\}/g, function (m, name) {
      return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m;
    });
  }
  function locale() {
    var active = window.SXFI18n && window.SXFI18n.current && window.SXFI18n.current();
    return ({tr:'tr-TR',en:'en-GB',de:'de-DE',fr:'fr-FR',nl:'nl-NL',it:'it-IT',es:'es-ES'})[active] || 'tr-TR';
  }
  var DESC = {
    EARLY_MONEY_CORE:'engine_early_core_desc', EARLY_MONEY_T12:'engine_early_t12_desc',
    '1X2_CONCENTRATION_V1':'engine_v1_desc', '1X2_CONCENTRATION_V2':'engine_v2_desc',
    HEAVY_1X2_CONCENTRATION:'engine_heavy_desc', SURPRISE_TEAM:'engine_surprise_desc',
    STABLE_OVER_2_5:'engine_stable_over_desc', PREMIUM_OVER_2_5:'engine_premium_over_desc',
    PREMIUM_OVER_MIN1_70:'engine_premium_min_desc', BTTS_YES:'engine_btts_desc'
  };
  var CATS = {
    EARLY_MONEY_CORE:'cat_money', EARLY_MONEY_T12:'cat_money',
    '1X2_CONCENTRATION_V1':'cat_1x2', '1X2_CONCENTRATION_V2':'cat_1x2',
    HEAVY_1X2_CONCENTRATION:'cat_1x2', SURPRISE_TEAM:'cat_1x2',
    STABLE_OVER_2_5:'cat_over', PREMIUM_OVER_2_5:'cat_over',
    PREMIUM_OVER_MIN1_70:'cat_over', BTTS_YES:'cat_btts'
  };
  function engineDescription(id, descriptor) {
    return t(DESC[id] || 'engine_unknown_desc', descriptor.description);
  }
  function engineCategory(id, descriptor) {
    return t(CATS[id] || 'cat_signal', descriptor.market);
  }
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
    return d.toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  }
  function timeTR(value) {
    if (!value) return '—';
    var d = new Date(value);
    if (!isFinite(d.getTime())) return '—';
    return new Intl.DateTimeFormat('tr-TR', {
      timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).format(d);
  }
  function labelEngine(id) { return (ENGINES[id] && ENGINES[id].name) || String(id).replace(/_/g, ' '); }
  function marketLabel(m) {
    return m === 'OU25' ? t('market_ou','Alt / Üst 2.5') :
      m === 'BTTS' ? t('market_btts','Karşılıklı Gol') : t('market_1x2','Maç Sonucu (1X2)');
  }
  function choice(item) {
    var s = item.selection;
    if (item.market === '1X2') {
      if (s === '1') return fmt('home_wins','{team} kazanır',
        {team:item.home || t('home_team','Ev sahibi')});
      if (s === '2') return fmt('away_wins','{team} kazanır',
        {team:item.away || t('away_team','Deplasman')});
      if (s === 'X') return t('draw','Beraberlik');
    }
    if (item.market === 'OU25') return s === 'O' ? t('over25','2.5 Üst') :
      s === 'U' ? t('under25','2.5 Alt') : s;
    if (item.market === 'BTTS') return s === 'Y' ? t('btts_yes','KG Var') :
      s === 'N' ? t('btts_no','KG Yok') : s;
    return s;
  }
  function stage(item) {
    if (item.stage_status === 'T8_HISTORICAL') return t('historical_t8','Geçmiş T-8');
    if (item.kind === 'CORRECTED') return t('reconciled','Uzlaştırma');
    if (item.kind === 'FINAL_SIGNAL') return 'T-6';
    if (item.kind === 'PRELIMINARY_SIGNAL') return t('pre_signal','Ön sinyal · T-8');
    return t('early_signal','Erken sinyal');
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
  function items() {
    return current.payload && Array.isArray(current.payload.items)
      ? current.payload.items.filter(function (x) {
          // Defense in depth for cached/stale API responses: only verified
          // eligible picks can create cards, counts or same-side badges.
          // Historical ELIGIBLE picks remain visible as archives.
          return Object.prototype.hasOwnProperty.call(ENGINES, x.engine) &&
            x.selection_status === 'ELIGIBLE' &&
            x.review_state !== 'PRICE_REJECTED' &&
            typeof x.odds === 'number' && isFinite(x.odds) && x.odds >= 1.30;
        })
      : [];
  }
  function engineIds() {
    // Only ten approved Base motor families: legacy signals were removed.
    return Object.keys(ENGINES);
  }
  function dayItems() {
    return items().filter(function (x) {
      return x.day === current.day && (current.engine === null || x.engine === current.engine);
    });
  }
  function fixturesCount(rows) {
    return new Set(rows.map(function (x) { return x.uid + '/' + x.kickoff_utc; })).size;
  }
  // An empty date is not proof that a motor has no stored signals. Only
  // offer dates present in the authenticated, bounded server response.
  function lastRecordedDay(engine, beforeDay) {
    return items().filter(function (x) {
      return x.engine === engine && x.day < beforeDay &&
        x.day >= current.start && x.day < dayShift(current.start, 21);
    }).map(function (x) { return x.day; }).sort().pop() || null;
  }
  function shortDay(day) { return day.slice(8, 10) + '.' + day.slice(5, 7); }
  function renderDates() {
    var today = todayTR(), html = '';
    var weekFmt = new Intl.DateTimeFormat(locale(), {weekday:'short',timeZone:'UTC'});
    for (var i = 0; i < 21; i++) {
      var day = dayShift(current.start, i), d = new Date(day + 'T12:00:00Z');
      var count = items().filter(function (x) {
        return x.day === day && (current.engine === null || x.engine === current.engine);
      }).length;
      var selected = day === current.day, isToday = day === today;
      html += '<button type="button" class="sxf-day' + (selected ? ' is-active' : '') +
        '" data-day="' + day + '" role="tab" aria-selected="' + (selected ? 'true' : 'false') +
        '" aria-label="' + esc(fmt('day_count','{date}, {count} sinyal',
          {date:day,count:count})) + '">' +
        '<span class="sxf-day-week">' + esc(weekFmt.format(d)) + '</span>' +
        '<span class="sxf-day-date">' + String(d.getUTCDate()).padStart(2, '0') + '.' +
        String(d.getUTCMonth() + 1).padStart(2, '0') + '</span>' +
        '<span class="sxf-day-indicator' + (count ? ' has-signals' : '') + '"></span>' +
        (isToday ? '<span class="sxf-day-now">' + esc(t('today','Bugün')) + '</span>' : '') + '</button>';
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
    var descriptor = ENGINES[name] || { name: labelEngine(name),
      description: 'SmartXFlow Base sinyal motoru', market: 'SİNYAL', code: 'SX' };
    var all = items().filter(function (x) { return x.engine === name; });
    var today = all.filter(function (x) { return x.day === current.day; });
    var fixtures = fixturesCount(today);
    var last = today.length ? null : lastRecordedDay(name, current.day);
    var unavailable = false;
    return '<button type="button" class="sxf-engine-tile" data-motor="' + esc(name) +
      '" aria-label="' + esc(fmt('motor_open','{name} motorunu aç, {count} maç',
        {name:descriptor.name,count:fixtures})) + '">' +
      '<span class="sxf-engine-tile-top"><span class="sxf-engine-mark" aria-hidden="true">' +
      esc(descriptor.code) + '</span><span class="sxf-engine-category">' +
      esc(engineCategory(name, descriptor)) +
      '</span></span><strong class="sxf-engine-name">' + esc(descriptor.name) + '</strong>' +
      '<span class="sxf-engine-description">' + esc(engineDescription(name, descriptor)) + '</span>' +
      '<span class="sxf-engine-tile-bottom"><span>' +
      (unavailable ? '<b class="sxf-unknown-count">—</b> ' +
        esc(t('legacy_unavailable_count','Kaynak okunamıyor')) :
        '<b>' + fixtures + '</b> ' +
        esc(t('match_count','{count} maç').replace('{count}','').trim())) +
      (unavailable ? '' : ' <span class="sxf-secondary-count">· ' +
        esc(recordsSummary(today)) +
        '</span>') + (last ? '<span class="sxf-last-day">' +
        esc(fmt('last_seen','Son sinyal: {date}', {date:shortDay(last)})) +
        '</span>' : '') + '</span><span class="sxf-tile-open" aria-hidden="true">↗</span></span>' +
      '</button>';
  }
  function timelySignalCount(rows) {
    return rows.filter(function (item) { return item.valid_on_time === true; }).length;
  }
  function recordsSummary(rows) {
    return fmt('signals_count','{count} sinyal',{count:timelySignalCount(rows)}) +
      ' · ' + fmt('records_count','{count} kayıt',{count:rows.length});
  }
  // Aggregate only real source events. Repeated T checkpoints must not
  // duplicate an engine badge or become independent confirmation votes.
  var SHORT_ENGINE = {
    EARLY_MONEY_CORE:'EARLY CORE', EARLY_MONEY_T12:'EARLY T12',
    '1X2_CONCENTRATION_V1':'V1','1X2_CONCENTRATION_V2':'V2',
    HEAVY_1X2_CONCENTRATION:'HEAVY', SURPRISE_TEAM:'SURPRISE',
    STABLE_OVER_2_5:'STABLE', PREMIUM_OVER_2_5:'PREMIUM',
    PREMIUM_OVER_MIN1_70:'PREMIUM 1.70+', BTTS_YES:'BTTS'
  };
  function recordTime(item) {
    var value = Date.parse(item.observed_at || item.recorded_at || '');
    return isFinite(value) ? value : 0;
  }
  function recordPrice(rows) {
    return rows.filter(function (r) {
      return typeof r.odds === 'number' && isFinite(r.odds);
    }).sort(function (a,b) {
      return recordTime(b)-recordTime(a) || Number(b.id||0)-Number(a.id||0);
    })[0];
  }
  function isHistorical(item) {
    return item.stage_status === 'T8_HISTORICAL' || item.valid_on_time === false ||
      item.review_state === 'LATE_HISTORY' || item.review_state === 'RECONCILED_HISTORY';
  }
  function rowState(item) {
    if (item.review_state === 'PRICE_REJECTED') return t('status_rejected','Uygun değil');
    if (item.review_state === 'HISTORY_INCOMPLETE') return t('history_unverified','Early geçmişi eksik');
    if (isHistorical(item)) return t('status_archive','Arşiv');
    if (item.valid_on_time === true) return t('status_timely','Zamanında');
    return t('status_unverified','Doğrulanmadı');
  }
  function signalRow(item) {
    var price = typeof item.odds === 'number' && isFinite(item.odds) ?
      item.odds.toFixed(2) : '—';
    var decided = item.result_state === 'FT' && (item.outcome === 'WIN' || item.outcome === 'LOSS');
    var outcome = decided ? '<span class="sxf-history-result ' +
      (item.outcome === 'WIN' ? 'is-win' : 'is-loss') + '">' +
      esc(item.outcome === 'WIN' ? t('won','KAZANDI') : t('lost','KAYBETTİ')) + '</span>' : '';
    return '<div class="sxf-signal-row sxf-history-entry">' +
      '<b class="sxf-history-engine">' + esc(SHORT_ENGINE[item.engine] || labelEngine(item.engine)) + '</b>' +
      '<span>' + esc(stage(item)) + (typeof item.checkpoint === 'number' ? ' · T-'+item.checkpoint : '') + '</span>' +
      (typeof item.source_checkpoint === 'number' && item.source_checkpoint !== item.checkpoint ?
        '<span>' + esc(t('source_t','Kaynak')) + ' T-' + item.source_checkpoint + '</span>' : '') +
      '<span>' + esc(t('data_at','Veri')) + ' ' + esc(timeTR(item.observed_at)) + '</span>' +
      '<span class="sxf-history-price">' + esc(t('odds','Oran')) + ' <b>' + esc(price) + '</b></span>' +
      '<span class="sxf-history-status">' + esc(rowState(item)) + '</span>' + outcome +
      '</div>';
  }
  function signalGroupInfo(rows) {
    var item = rows[0], price = recordPrice(rows);
    var engines = Array.from(new Set(rows.map(function (r) { return r.engine; })));
    var timely = rows.some(function (r) {
      return r.valid_on_time === true && !isHistorical(r);
    });
    var archived = rows.some(isHistorical);
    var state = timely && archived ? 'mixed' : timely ? 'timely' :
      archived ? 'archive' : 'unverified';
    var status = state === 'mixed' ? t('status_mixed','Zamanında + arşiv') :
      state === 'timely' ? t('status_timely','Zamanında') :
      state === 'archive' ? t('status_archive','Arşiv') :
      t('status_unverified','Doğrulanmadı');
    var badges = engines.map(function (engine) {
      return '<span class="sxf-direction-badge" title="' + esc(labelEngine(engine)) + '">' +
        esc(SHORT_ENGINE[engine] || labelEngine(engine)) + '</span>';
    }).join('');
    return { item:item, price:price, status:status, state:state, badges:badges };
  }
  function signalHistoryGroup(rows) {
    var info = signalGroupInfo(rows), ordered = rows.slice().sort(function (a,b) {
      return recordTime(b)-recordTime(a) || Number(b.id||0)-Number(a.id||0);
    });
    return '<section class="sxf-list-history-group">' +
      '<div class="sxf-list-history-heading"><div class="sxf-list-history-pick">' +
      '<strong>' + esc(choice(info.item)) + '</strong><span>' +
      esc(marketLabel(info.item.market)) + '</span></div>' +
      '<div class="sxf-list-history-badges">' + info.badges + '</div></div>' +
      '<div class="sxf-history-list">' + ordered.map(signalRow).join('') + '</div>' +
      '</section>';
  }
  // One physical fixture = one full-width list row. The selected engine's
  // pick is prominent, while other markets and all T evidence expand inline.
  function fixtureRow(rows) {
    var item = rows[0], bySelection = new Map();
    rows.forEach(function (r) {
      var key = String(r.market) + '/' + String(r.selection);
      if (!bySelection.has(key)) bySelection.set(key, []);
      bySelection.get(key).push(r);
    });
    var directions = Array.from(bySelection.values()).sort(function (a,b) {
      var aPicked = a.some(function (r) { return r.engine === current.engine; }) ? 1 : 0;
      var bPicked = b.some(function (r) { return r.engine === current.engine; }) ? 1 : 0;
      return bPicked-aPicked || b.length-a.length;
    });
    var primary = signalGroupInfo(directions[0]);
    var actual = item.result_state === 'FT' &&
      /^\d{1,2}-\d{1,2}$/.test(item.final_score || '');
    var score = actual ? '<span class="sxf-list-result" title="' +
      esc(t('final_score_label','MAÇ SONUCU')) + '">MS ' +
      esc(item.final_score) + '</span>' : '';
    var extra = directions.length > 1 ? ' · ' +
      esc(fmt('other_picks_count','+{count} diğer tercih',{count:directions.length-1})) : '';
    var events = rows.length;
    return '<details class="sxf-fixture-line"><summary class="sxf-fixture-summary">' +
      '<span class="sxf-line-time">' + esc(timeTR(item.kickoff_utc)) + '<small>TR</small></span>' +
      '<span class="sxf-line-fixture"><strong>' +
      esc(item.home || t('home_team','Ev sahibi')) + ' – ' +
      esc(item.away || t('away_team','Deplasman')) + '</strong>' +
      '<small>' + esc(item.league || t('unknown_league','Lig belirtilmemiş')) +
      score + '</small></span>' +
      '<span class="sxf-line-selection"><strong>' + esc(choice(primary.item)) +
      '</strong><small>' + esc(marketLabel(primary.item.market)) + extra +
      '</small></span>' +
      '<span class="sxf-line-odds"><small class="sxf-price-key">' +
      esc(t('odds','Oran')) + '</small>' +
      (primary.price ? esc(primary.price.odds.toFixed(2)) : '—') + '</span>' +
      '<span class="sxf-line-engines">' + primary.badges + '</span>' +
      '<span class="sxf-line-state is-' + primary.state + '">' + esc(primary.status) + '</span>' +
      '<span class="sxf-line-open" aria-hidden="true">⌄</span></summary>' +
      '<div class="sxf-fixture-expanded"><div class="sxf-list-expanded-title">' +
      esc(fmt('history_count','{count} checkpoint kaydı',{count:events})) + '</div>' +
      directions.map(signalHistoryGroup).join('') + '</div></details>';
  }
  function renderHome() {
    var entries = engineIds();
    var cards = entries.map(engineCard).join('');
    var rows = dayItems();
    summary.textContent = dateTitle(current.day) + '  ·  ' +
      fmt('match_count','{count} maç',{count:fixturesCount(rows)}) + ' / ' +
      recordsSummary(rows);
    searchWrap.hidden = true;
    content.innerHTML = '<div class="sxf-directory-header"><div><span class="sxf-eyebrow">' +
      esc(t('directory_eyebrow','SİNYAL MOTORLARI')) + '</span><h3>' +
      esc(t('choose_engine','Bir motor seç')) + '</h3><p>' +
      esc(t('choose_engine_desc','Seçtiğin günün maçlarını motor bazında görüntüle.')) +
      '</p></div><span class="sxf-directory-total">' +
      esc(fmt('engines_count','{count} motor',{count:entries.length})) + '</span></div>' +
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
        .toLocaleLowerCase(locale()).includes(needle);
    });
    // The chosen engine selects matches; other real engine records for the
    // same physical match remain visible without an extra network request.
    var selectedKeys = new Set(filtered.map(function (x) {
      return x.uid + '/' + x.kickoff_utc;
    }));
    var groups = new Map();
    items().filter(function (x) {
      return x.day === current.day && selectedKeys.has(x.uid + '/' + x.kickoff_utc);
    }).sort(function (a,b) {
      return a.kickoff_utc.localeCompare(b.kickoff_utc) || a.id-b.id;
    }).forEach(function (x) {
      var key=x.uid+'/'+x.kickoff_utc;
      if (!groups.has(key)) groups.set(key,[]);
      groups.get(key).push(x);
    });
    summary.textContent = labelEngine(current.engine) + ' · ' +
      fmt('match_count','{count} maç',{count:fixturesCount(source)}) + ' / ' +
      recordsSummary(source);
    searchWrap.hidden = false;
    var html = '<div class="sxf-detail-head"><button class="sxf-back" type="button" ' +
      'id="sxfSignalBack">' + esc(t('back_engines','← Tüm motorlar')) +
      '</button><div class="sxf-detail-caption"><span class="sxf-eyebrow">' +
      esc(descriptor ? engineCategory(current.engine, descriptor) : t('cat_signal','SİNYAL')) +
      '</span><h3>' + esc(labelEngine(current.engine)) + '</h3><p>' +
      esc(dateTitle(current.day)) + ' · ' +
      esc(fmt('match_count','{count} maç',{count:groups.size})) + '</p></div></div>';
    if (!filtered.length) {
      // Do not fabricate a match or silently change the user's chosen date.
      // A separate explicit action reveals the last available recorded day.
      var last = source.length ? null : lastRecordedDay(current.engine, current.day);
      html += '<div class="sxf-zero"><span class="sxf-zero-icon">◇</span>' +
        '<h4>' + esc(t('empty_title','Bu gün için maç bulunmuyor')) +
        '</h4><p>' + esc(t('empty_desc','Seçili motor için bu tarihte tamamlanmış bir sinyal kaydı yok.')) +
        '</p>' + (last ? '<button id="sxfSignalShowLast" type="button" class="sxf-retry">' +
          esc(fmt('show_last','{date} sinyallerini göster', {date:dateTitle(last)})) +
          '</button>' : '') + '</div>';
    } else {
      html += '<div class="sxf-fixture-list" role="list" aria-label="' +
        esc(labelEngine(current.engine)) + '">' +
        '<div class="sxf-fixture-list-head" aria-hidden="true">' +
        '<span>' + esc(t('list_col_time','Saat')) + '</span>' +
        '<span>' + esc(t('list_col_match','Maç')) + '</span>' +
        '<span>' + esc(t('list_col_pick','Tercih')) + '</span>' +
        '<span>' + esc(t('odds','Oran')) + '</span>' +
        '<span>' + esc(t('list_col_engines','Sinyaller')) + '</span>' +
        '<span>' + esc(t('list_col_status','Durum')) + '</span>' +
        '<span></span></div>' +
        Array.from(groups.values()).map(fixtureRow).join('') + '</div>';
    }
    content.innerHTML = html;
    var showLast = document.getElementById('sxfSignalShowLast');
    if (last && showLast) showLast.addEventListener('click', function () {
      current.day = last;
      current.search = '';
      var search = document.getElementById('sxfSignalSearch');
      if (search) search.value = '';
      render();
    });
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
  function renderError(code) {
    var error = code === 'PRO_REQUIRED' ? t('pro_required','Bu bölüm PRO üyelik gerektirir.') :
      code === 'EMAIL_NOT_VERIFIED' ? t('email_unverified','E-posta adresini doğrulaman gerekiyor.') :
      code === 'MEMBERSHIP_REQUIRED' ? t('membership_required','Aktif üyelik gerekiyor.') :
      code === 'SESSION_EXPIRED' ? t('session_expired','Oturumun süresi doldu. Yeniden giriş yap.') :
      code === 'LOGIN_REQUIRED' ? t('login_required','Oturum açman gerekiyor.') :
      t('load_failed','Sinyal verileri yüklenemedi.');
    message(error, 'error');
    summary.textContent = t('no_data','Veri alınamadı');
    searchWrap.hidden = true;
    content.innerHTML = '<div class="sxf-zero"><span class="sxf-zero-icon">!</span>' +
      '<h4>' + esc(error) + '</h4><p>' + esc(t('no_mock',
      'Motor verisi olmadığında örnek veya eski sinyal gösterilmez.')) + '</p>' +
      '<button type="button" class="sxf-retry" id="sxfSignalRetry">' +
      esc(t('retry','Tekrar dene')) + '</button></div>';
    document.getElementById('sxfSignalRetry').addEventListener('click', load);
  }
  function refreshLanguage() {
    if (!getEls() || overlay.hidden) return;
    var search = document.getElementById('sxfSignalSearch');
    if (search) current.search = String(search.value || '').toLocaleLowerCase(locale()).trim();
    if (current.payload) {
      render();
      message(current.payload.results_source_state === 'unavailable'
        ? t('score_source_error','SHADOW / TEST · Skor kaynağına erişilemiyor')
        : t('test_notice','SHADOW / TEST · Onaylanmış bahis önerisi değildir'), 'shadow');
    } else if (current.errorCode) {
      renderError(current.errorCode);
    } else {
      message(t('loading_signals','Sinyaller yükleniyor…'), 'loading');
      summary.textContent = t('loading','Yükleniyor…');
      content.innerHTML = '<div class="sxf-zero"><span class="sxf-spinner"></span><p>' +
        esc(t('loading_engines','Motor kayıtları yükleniyor…')) + '</p></div>';
    }
  }
  function load() {
    if (!getEls()) return Promise.resolve();
    var seq = ++current.seq;
    current.errorCode = null;
    message(t('loading_signals','Sinyaller yükleniyor…'), 'loading');
    summary.textContent = t('loading','Yükleniyor…');
    content.innerHTML = '<div class="sxf-zero"><span class="sxf-spinner"></span><p>' +
      esc(t('loading_engines','Motor kayıtları yükleniyor…')) + '</p></div>';
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
      message(data.results_source_state === 'unavailable'
        ? t('score_source_error','SHADOW / TEST · Skor kaynağına erişilemiyor')
        : t('test_notice','SHADOW / TEST · Onaylanmış bahis önerisi değildir'), 'shadow');
      render();
    }).catch(function (err) {
      if (seq !== current.seq || overlay.hidden) return;
      current.payload = null;
      current.errorCode = err.code || 'SIGNAL_DATA_UNAVAILABLE';
      renderError(current.errorCode);
    });
  }
  function switchWindow(delta) {
    var nextStart = dayShift(current.start, delta * 10);
    var today = todayTR();
    // The private API bounds kickoff windows: 45 days back, 21 days ahead.
    // Never replace an otherwise healthy screen with a predictable 400.
    if (nextStart < dayShift(today, -45) || nextStart > dayShift(today, 21)) {
      message(t('range_error','Bu tarih aralığı için kayıt görüntülenemiyor.'), 'shadow');
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
    current.errorCode = null;
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
      current.search = String(e.target.value || '').toLocaleLowerCase(locale()).trim();
      if (current.engine !== null) renderDetail();
    });
    // i18n.js emits this after every locale dictionary load. Keep current
    // engine, day, search and authenticated feed; do not re-fetch on translation.
    if (typeof window.addEventListener === 'function')
      window.addEventListener('i18n:change', refreshLanguage);
  }
  window.openBaseSignalsPanel = open;
  window.closeBaseSignalsPanel = close;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach, { once: true });
  } else attach();
})();
