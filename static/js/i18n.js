(function () {
  'use strict';

  // Inject flag-icon styles once (works on Windows where emoji flags don't render)
  try {
    if (!document.getElementById('sxf-flag-icon-style')) {
      var st = document.createElement('style');
      st.id = 'sxf-flag-icon-style';
      st.textContent = '.flag-icon{display:inline-block;width:18px;height:13px;vertical-align:middle;border-radius:2px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,0.12);}.lang-picker-code{font-size:11px;font-weight:600;letter-spacing:0.5px;margin-left:4px;vertical-align:middle;}';
      (document.head || document.documentElement).appendChild(st);
    }
  } catch (e) {}

  var SUPPORTED = ['tr', 'en', 'de', 'fr', 'nl', 'it', 'es'];
  var DEFAULT_LANG = 'en';
  var STORAGE_KEY = 'sxf_lang';
  var BASE_PATH = '/static/i18n/';
  var FLAGS = { tr: '<img class="flag-icon" src="/static/flags/tr.svg" alt="">', en: '<img class="flag-icon" src="/static/flags/gb.svg" alt="">', de: '<img class="flag-icon" src="/static/flags/de.svg" alt="">', fr: '<img class="flag-icon" src="/static/flags/fr.svg" alt="">', nl: '<img class="flag-icon" src="/static/flags/nl.svg" alt="">', it: '<img class="flag-icon" src="/static/flags/it.svg" alt="">', es: '<img class="flag-icon" src="/static/flags/es.svg" alt="">' };

  // These descriptions mirror the live constants in sinyal_engine.py. Keeping
  // them here prevents stale locale JSON from showing retired thresholds.
  var RULE_OVERRIDES = {
    tr: {
      'app.j.rv_underdog_desc': 'Oran ≥2.90. Hacim £800–£4.999 ise para yüzdesi ≥%55; hacim ≥£5.000 ise ≥%50. Yalnız 1/2 seçimleri.',
      'app.j.rv_confirmed_desc': 'Hacim ≥£5.000, para yüzdesi >%80 ve son 3 snapshot boyunca >%80; oran 1.35–2.20 ve ilk geçerli orana göre ≥%5 düşüş.',
      'app.j.rv_confirmed_v2_desc': 'Hacim ≥£5.000, para yüzdesi ≥%88 ve son 3 snapshot boyunca ≥%88; oran 1.55–2.20 ve ilk geçerli orana göre ≥%7 düşüş. Yalnız 1/2 seçimleri.',
      'app.j.rv_early_desc': 'Maça ≥24 saat kala, hacim ≥£5.000 ve aynı seçimde son 5 ardışık snapshot boyunca para yüzdesi ≥%85 olduğunda tetiklenir.',
      'app.j.rv_fake_desc': 'Hacim ≥£5.000 ve para yüzdesi >%75 iken son 3 snapshot da >%75; oran 1.35–2.20 ve ilk geçerli orana göre ≥%5 yükseliyorsa tetiklenir. Yalnız 1/2 seçimleri.'
    },
    en: {
      'app.j.rv_underdog_desc': 'Odds ≥2.90. At £800–£4,999 volume, money share must be ≥55%; at ≥£5,000, ≥50%. Home/away selections only.',
      'app.j.rv_confirmed_desc': 'Volume ≥£5,000, money share >80% and >80% for the last 3 snapshots; odds 1.35–2.20 with a ≥5% drop from the first valid odds.',
      'app.j.rv_confirmed_v2_desc': 'Volume ≥£5,000, money share ≥88% for the last 3 snapshots; odds 1.55–2.20 with a ≥7% drop from the first valid odds. Home/away only.',
      'app.j.rv_early_desc': 'Triggers ≥24 hours before kickoff when volume is ≥£5,000 and the same selection holds ≥85% money share for 5 consecutive snapshots.',
      'app.j.rv_fake_desc': 'Volume ≥£5,000 and money share >75% for the last 3 snapshots; odds 1.35–2.20 and ≥5% higher than the first valid odds. Home/away only.'
    },
    de: {
      'app.j.rv_underdog_desc': 'Quote ≥2,90. Bei £800–£4.999 Volumen gilt Geldanteil ≥55 %, ab £5.000 ≥50 %. Nur Heim/Auswärts.',
      'app.j.rv_confirmed_desc': 'Volumen ≥£5.000, Geldanteil >80 % und in den letzten 3 Snapshots >80 %; Quote 1,35–2,20 und ≥5 % Rückgang gegenüber der ersten gültigen Quote.',
      'app.j.rv_confirmed_v2_desc': 'Volumen ≥£5.000, Geldanteil in den letzten 3 Snapshots ≥88 %; Quote 1,55–2,20 und ≥7 % Rückgang gegenüber der ersten gültigen Quote. Nur Heim/Auswärts.',
      'app.j.rv_early_desc': 'Auslösung ≥24 Stunden vor Anpfiff bei Volumen ≥£5.000 und ≥85 % Geldanteil derselben Auswahl in 5 aufeinanderfolgenden Snapshots.',
      'app.j.rv_fake_desc': 'Volumen ≥£5.000 und Geldanteil >75 % in den letzten 3 Snapshots; Quote 1,35–2,20 und ≥5 % über der ersten gültigen Quote. Nur Heim/Auswärts.'
    },
    fr: {
      'app.j.rv_underdog_desc': 'Cote ≥2,90. Pour £800–£4 999 de volume, part d’argent ≥55 % ; à partir de £5 000, ≥50 %. Sélections domicile/extérieur uniquement.',
      'app.j.rv_confirmed_desc': 'Volume ≥£5 000, part d’argent >80 % sur les 3 derniers snapshots ; cote 1,35–2,20 avec baisse ≥5 % depuis la première cote valide.',
      'app.j.rv_confirmed_v2_desc': 'Volume ≥£5 000, part d’argent ≥88 % sur les 3 derniers snapshots ; cote 1,55–2,20 avec baisse ≥7 % depuis la première cote valide. Domicile/extérieur uniquement.',
      'app.j.rv_early_desc': 'Déclenché ≥24 h avant le coup d’envoi avec volume ≥£5 000 et part d’argent ≥85 % sur la même sélection pendant 5 snapshots consécutifs.',
      'app.j.rv_fake_desc': 'Volume ≥£5 000 et part d’argent >75 % sur les 3 derniers snapshots ; cote 1,35–2,20 et hausse ≥5 % depuis la première cote valide. Domicile/extérieur uniquement.'
    },
    nl: {
      'app.j.rv_underdog_desc': 'Odds ≥2,90. Bij £800–£4.999 volume moet het geldpercentage ≥55% zijn; vanaf £5.000 ≥50%. Alleen thuis/uit.',
      'app.j.rv_confirmed_desc': 'Volume ≥£5.000, geldpercentage >80% in de laatste 3 snapshots; odds 1,35–2,20 met ≥5% daling vanaf de eerste geldige odds.',
      'app.j.rv_confirmed_v2_desc': 'Volume ≥£5.000, geldpercentage ≥88% in de laatste 3 snapshots; odds 1,55–2,20 met ≥7% daling vanaf de eerste geldige odds. Alleen thuis/uit.',
      'app.j.rv_early_desc': 'Triggert ≥24 uur voor aftrap bij volume ≥£5.000 en ≥85% geldpercentage op dezelfde selectie gedurende 5 opeenvolgende snapshots.',
      'app.j.rv_fake_desc': 'Volume ≥£5.000 en geldpercentage >75% in de laatste 3 snapshots; odds 1,35–2,20 en ≥5% hoger dan de eerste geldige odds. Alleen thuis/uit.'
    },
    it: {
      'app.j.rv_underdog_desc': 'Quota ≥2,90. Con volume £800–£4.999 la quota denaro deve essere ≥55%; da £5.000, ≥50%. Solo casa/trasferta.',
      'app.j.rv_confirmed_desc': 'Volume ≥£5.000, quota denaro >80% negli ultimi 3 snapshot; quota 1,35–2,20 con calo ≥5% dalla prima quota valida.',
      'app.j.rv_confirmed_v2_desc': 'Volume ≥£5.000, quota denaro ≥88% negli ultimi 3 snapshot; quota 1,55–2,20 con calo ≥7% dalla prima quota valida. Solo casa/trasferta.',
      'app.j.rv_early_desc': 'Si attiva ≥24 ore prima del calcio d’inizio con volume ≥£5.000 e quota denaro ≥85% sulla stessa selezione per 5 snapshot consecutivi.',
      'app.j.rv_fake_desc': 'Volume ≥£5.000 e quota denaro >75% negli ultimi 3 snapshot; quota 1,35–2,20 e aumento ≥5% dalla prima quota valida. Solo casa/trasferta.'
    },
    es: {
      'app.j.rv_underdog_desc': 'Cuota ≥2,90. Con volumen £800–£4.999, el porcentaje de dinero debe ser ≥55%; desde £5.000, ≥50%. Solo local/visitante.',
      'app.j.rv_confirmed_desc': 'Volumen ≥£5.000, porcentaje de dinero >80% en los últimos 3 snapshots; cuota 1,35–2,20 con caída ≥5% desde la primera cuota válida.',
      'app.j.rv_confirmed_v2_desc': 'Volumen ≥£5.000, porcentaje de dinero ≥88% en los últimos 3 snapshots; cuota 1,55–2,20 con caída ≥7% desde la primera cuota válida. Solo local/visitante.',
      'app.j.rv_early_desc': 'Se activa ≥24 h antes del inicio con volumen ≥£5.000 y ≥85% del dinero en la misma selección durante 5 snapshots consecutivos.',
      'app.j.rv_fake_desc': 'Volumen ≥£5.000 y porcentaje de dinero >75% en los últimos 3 snapshots; cuota 1,35–2,20 y subida ≥5% desde la primera cuota válida. Solo local/visitante.'
    }
  };

  var dict = {};
  var currentLang = DEFAULT_LANG;
  var listeners = [];
  var latestLocaleRequest = 0; // reject out-of-order locale fetch completions
  var canonicalTurkish = null;
  var canonicalEnglish = null;
  var authCatalog = null;
  var authCatalogPromise = null;
  var autoIndex = null;
  var autoObserver = null;
  var autoRefreshPending = false;
  var autoDirtyNodes = [];

  function detectLang() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (e) {}
    return DEFAULT_LANG;
  }

  function get(key) {
    if (!key) return '';
    if (key.indexOf('app.auth.') === 0 && authCatalog) {
      var authKey = key.slice('app.auth.'.length);
      return (authCatalog[currentLang] && authCatalog[currentLang][authKey]) ||
        (authCatalog.en && authCatalog.en[authKey]) || null;
    }
    var overrides = RULE_OVERRIDES[currentLang] || RULE_OVERRIDES[DEFAULT_LANG] || {};
    if (Object.prototype.hasOwnProperty.call(overrides, key)) return overrides[key];
    var parts = key.split('.');
    var v = dict;
    for (var i = 0; i < parts.length; i++) {
      if (v && typeof v === 'object' && parts[i] in v) v = v[parts[i]];
      else return null;
    }
    return typeof v === 'string' ? v : null;
  }


  // Safe fallback for legacy pages and dynamically inserted labels.  The
  // canonical Turkish UI already has hundreds of complete hand-translated
  // entries; tag only text-only elements with an *unambiguous exact* match.
  // Never send phrases, API data, user input or DOM text to a translation API.
  function normalizeAutoText(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }
  function isAuthPage() {
    var path = (window.location && window.location.pathname) || '';
    return /^\/(?:login|signup|forgot-password|reset-password|verify-email|auth-callback|membership-required|migrate-account|account|admin-login)(?:\/)?$/.test(path);
  }
  function flattenCatalog(obj, path, into) {
    if (!obj || typeof obj !== 'object') return;
    Object.keys(obj).forEach(function (key) {
      var value = obj[key];
      var full = path ? path + '.' + key : key;
      if (typeof value === 'string') {
        var text = normalizeAutoText(value);
        if (!text || text.length < 3 || text.length > 500 || /<[^>]*>/.test(text)) return;
        var existing = into[text];
        if (existing === undefined) into[text] = full;
        else if (existing !== full) into[text] = null; // ambiguous, never guess
      } else if (value && typeof value === 'object') {
        flattenCatalog(value, full, into);
      }
    });
  }
  function rebuildAutoIndex() {
    if (!canonicalTurkish) return;
    var map = Object.create(null);
    flattenCatalog(canonicalTurkish, '', map);
    // Authentication and admin-login screens were authored in English.
    // Do not let their English labels affect match/team data in /app.
    if (isAuthPage() && authCatalog) {
      var sourceEnglish = Object.create(null);
      var sourceTurkish = Object.create(null);
      flattenCatalog(authCatalog.en, 'app.auth', sourceEnglish);
      flattenCatalog(authCatalog.tr, 'app.auth', sourceTurkish);
      Object.keys(sourceEnglish).forEach(function (key) {
        if (sourceEnglish[key]) map[key] = sourceEnglish[key];
      });
      Object.keys(sourceTurkish).forEach(function (key) {
        if (sourceTurkish[key]) map[key] = sourceTurkish[key];
      });
    }
    autoIndex = map;
  }
  function autoEligible(el) {
    if (!el || el.nodeType !== 1 || !el.tagName) return false;
    var tag = el.tagName.toLowerCase();
    if (/^(script|style|noscript|svg|path|code|pre|textarea|iframe)$/.test(tag)) return false;
    if (tag === 'option' && !el.hasAttribute('value')) return false;
    if (el.closest && el.closest('[data-i18n],[data-i18n-html],[data-no-i18n],[contenteditable],.lang-picker,.flag-icon')) return false;
    // Never automatically rewrite statistics, fixture names or financial data.
    if (el.closest && el.closest('.matches-table,.match-card,.live-period-table,.sxf-signal-card,.chart-container,.wallet-stats-grid')) return false;
    return true;
  }
  function autoKeyFor(value) {
    return autoIndex && autoIndex[normalizeAutoText(value)] || null;
  }
  function autoBindElement(el) {
    if (!autoEligible(el)) return;
    if (!el.children || el.children.length === 0) {
      var key = autoKeyFor(el.textContent);
      if (key && !el.hasAttribute('data-i18n')) {
        el.setAttribute('data-i18n', key);
        var next = get(key);
        if (next !== null && el.textContent !== next) el.textContent = next;
      }
    }
    if (el.getAttribute && !el.hasAttribute('data-i18n-attr')) {
      var pairs = [];
      ['placeholder','title','aria-label'].forEach(function (name) {
        var value = el.getAttribute(name);
        if (!value) return;
        var key = autoKeyFor(value);
        if (key) pairs.push(name + ':' + key);
      });
      if (pairs.length) {
        el.setAttribute('data-i18n-attr', pairs.join(';'));
        applyAttrs(el);
      }
    }
  }
  function autoBindTree(root) {
    if (!autoIndex || !root) return;
    if (root.nodeType === 1) autoBindElement(root);
    var els = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (var i = 0; i < els.length; i++) autoBindElement(els[i]);
  }
  function applyAutoBody() {
    if (!autoIndex || !document.body) return;
    autoBindTree(document.body);
    var title = document.querySelector && document.querySelector('title');
    if (title) autoBindElement(title);
    if (!autoObserver && typeof MutationObserver !== 'undefined') {
      autoObserver = new MutationObserver(function (records) {
        records.forEach(function (record) {
          for (var i = 0; i < record.addedNodes.length; i++) {
            var node = record.addedNodes[i];
            if (node.nodeType === 1) autoDirtyNodes.push(node);
            // textContent assignments commonly add a bare Text node to an
            // existing error/status box; translate that box without touching data.
            else if (node.nodeType === 3 && record.target && record.target.nodeType === 1)
              autoDirtyNodes.push(record.target);
          }
        });
        if (autoRefreshPending || !autoDirtyNodes.length) return;
        autoRefreshPending = true;
        setTimeout(function () {
          autoRefreshPending = false;
          var nodes = autoDirtyNodes.splice(0);
          nodes.forEach(autoBindTree);
        }, 40);
      });
      autoObserver.observe(document.body, { childList:true, subtree:true });
    }
  }
  function ensureCanonicalLocales() {
    if (currentLang === 'tr') canonicalTurkish = dict;
    if (currentLang === 'en') canonicalEnglish = dict;
    var pending = [];
    if (!canonicalTurkish) {
      pending.push(fetch(BASE_PATH + 'tr.json?v=1', {cache:'no-cache'})
        .then(function (r) { if (!r.ok) throw new Error('base locale unavailable'); return r.json(); })
        .then(function (obj) { canonicalTurkish = obj; }).catch(function () {}));
    }
    if (isAuthPage() && !authCatalog) {
      if (!authCatalogPromise) {
        authCatalogPromise = fetch(BASE_PATH + 'auth.json?v=20261020', {cache:'no-cache'})
          .then(function (r) { if (!r.ok) throw new Error('auth catalog unavailable'); return r.json(); })
          .then(function (obj) { authCatalog = obj; })
          .catch(function () {});
      }
      pending.push(authCatalogPromise);
    }
    if (!pending.length) { rebuildAutoIndex(); applyAutoBody(); return; }
    Promise.all(pending).then(function () {
      rebuildAutoIndex();
      applyAutoBody();
    });
  }


  function installStandaloneLanguagePicker() {
    if (!document.body || !isAuthPage() || document.getElementById('sxfStandaloneLanguage')) return;
    var control = document.createElement('select');
    control.id = 'sxfStandaloneLanguage';
    control.className = 'sxf-standalone-language lang-picker';
    control.setAttribute('aria-label', 'Language / Dil');
    control.setAttribute('data-no-i18n', '1');
    var names = {tr:'Türkçe',en:'English',de:'Deutsch',fr:'Français',
                 nl:'Nederlands',it:'Italiano',es:'Español'};
    SUPPORTED.forEach(function (code) {
      var option = document.createElement('option');
      option.value = code;
      option.textContent = names[code];
      control.appendChild(option);
    });
    control.value = currentLang;
    control.addEventListener('change', function () {
      window.SXFI18n.set(control.value).catch(function () {
        control.value = currentLang;
      });
    });
    var css = document.createElement('style');
    css.textContent =
      '.sxf-standalone-language{position:fixed;right:12px;bottom:12px;z-index:1700;'+
      'max-width:150px;background:#171d29;color:#f3f4f6;border:1px solid #394253;'+
      'border-radius:9px;font:12px system-ui,sans-serif;padding:9px 12px;cursor:pointer;}'+
      'body.sxf-auth-body{padding-bottom:60px;}'+
      '.sxf-standalone-language:focus-visible{outline:2px solid #34d399;outline-offset:2px;}';
    (document.head || document.documentElement).appendChild(css);
    document.body.appendChild(control);
  }

  function applyAttrs(el) {
    var spec = el.getAttribute('data-i18n-attr');
    if (!spec) return;
    spec.split(';').forEach(function (pair) {
      var idx = pair.indexOf(':');
      if (idx === -1) return;
      var attr = pair.slice(0, idx).trim();
      var key = pair.slice(idx + 1).trim();
      var val = get(key);
      if (val !== null) el.setAttribute(attr, val);
    });
  }

  function applyDOM() {
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      var val = get(key);
      if (val !== null) el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-html]').forEach(function (el) {
      var key = el.getAttribute('data-i18n-html');
      var val = get(key);
      if (val !== null) el.innerHTML = val;
    });
    document.querySelectorAll('[data-i18n-attr]').forEach(applyAttrs);
    var titleEl = document.querySelector('title[data-i18n]');
    if (titleEl) {
      var tk = titleEl.getAttribute('data-i18n');
      var tv = get(tk);
      if (tv !== null) document.title = tv;
    }
    document.documentElement.setAttribute('lang', currentLang);
    var standaloneSelect = document.getElementById('sxfStandaloneLanguage');
    if (standaloneSelect) standaloneSelect.value = currentLang;
    document.querySelectorAll('.lang-picker-current').forEach(function (el) {
      var flag = FLAGS[currentLang] || '';
      var code = (currentLang === 'en') ? 'EN' : currentLang.toUpperCase();
      el.innerHTML = flag + ' <span class="lang-picker-code">' + code + '</span>';
    });
    var ogLocale = document.querySelector('meta[property="og:locale"]');
    if (ogLocale) {
      var map = { tr: 'tr_TR', en: 'en_US', de: 'de_DE', fr: 'fr_FR', nl: 'nl_NL', it: 'it_IT', es: 'es_ES' };
      ogLocale.setAttribute('content', map[currentLang] || 'tr_TR');
    }
  }

  function load(lang) {
    var request = ++latestLocaleRequest;
    return fetch(BASE_PATH + lang + '.json?v=1', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('i18n load failed: ' + lang);
        return r.json();
      })
      .then(function (data) {
        if (request !== latestLocaleRequest) return; // a newer language selection won
        dict = data;
        currentLang = lang;
        try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
        applyDOM();
        ensureCanonicalLocales();
        installStandaloneLanguagePicker();
        listeners.forEach(function (fn) { try { fn(lang); } catch (e) {} });
        try { window.dispatchEvent(new CustomEvent('i18n:change', { detail: { lang: lang } })); } catch (e) {}
      });
  }

  window.SXFI18n = {
    supported: SUPPORTED.slice(),
    current: function () { return currentLang; },
    set: function (lang) {
      if (SUPPORTED.indexOf(lang) === -1) return Promise.reject(new Error('unsupported'));
      return load(lang);
    },
    t: function (key) { var v = get(key); return v === null ? key : v; },
    onChange: function (fn) { if (typeof fn === 'function') listeners.push(fn); },
    apply: applyDOM
  };

  function addInteractionPreconnect(href) {
    try {
      if (document.querySelector('link[data-sxf-interaction-preconnect="' + href + '"]')) return;
      var link = document.createElement('link');
      link.rel = 'preconnect';
      link.href = href;
      link.crossOrigin = 'anonymous';
      link.setAttribute('data-sxf-interaction-preconnect', href);
      document.head.appendChild(link);
    } catch (e) {}
  }

  function prefetchInteractionScript(url) {
    if (!url) return;
    try {
      var links = document.querySelectorAll('link[rel="prefetch"][as="script"]');
      for (var i = 0; i < links.length; i++) {
        if (links[i].href === new URL(url, window.location.href).href) return;
      }
      var link = document.createElement('link');
      link.rel = 'prefetch';
      link.as = 'script';
      link.href = url;
      link.setAttribute('data-sxf-interaction-prefetch', '1');
      document.head.appendChild(link);
    } catch (e) {}
  }

  function runInteractionWarmup() {
    var runtimeUrlHelpers = [
      '_getModalEntryRuntimeUrl',
      '_getModalInfoRuntimeUrl',
      '_getLiveTabRuntimeUrl',
      '_getAdminPanelRuntimeUrl',
      '_getMobileChartPanelRuntimeUrl'
    ];
    runtimeUrlHelpers.forEach(function (name) {
      try {
        if (typeof window[name] === 'function') prefetchInteractionScript(window[name]());
      } catch (e) {}
    });

    try {
      if (typeof window.loadSxfAnalysisUi === 'function') {
        Promise.resolve(window.loadSxfAnalysisUi()).catch(function () {});
      }
    } catch (e) {}

    try {
      if (typeof window.loadChartLibs === 'function') {
        Promise.resolve(window.loadChartLibs()).catch(function () {});
      }
    } catch (e) {}
  }

  function scheduleInteractionWarmup() {
    addInteractionPreconnect('https://cdn.jsdelivr.net');

    var armed = false;
    var observer = null;
    var fallbackTimer = null;

    function hasRenderedMatch() {
      return !!document.querySelector('#matchesTableBody .fav-heart[data-matchkey], #matchCardList .fav-heart[data-matchkey]');
    }

    function armWarmup() {
      if (armed) return;
      armed = true;
      if (observer) observer.disconnect();
      if (fallbackTimer) clearTimeout(fallbackTimer);
      var run = function () { runInteractionWarmup(); };
      if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(run, { timeout: 1500 });
      } else {
        setTimeout(run, 400);
      }
    }

    function watchMatches() {
      if (hasRenderedMatch()) {
        armWarmup();
        return;
      }
      var tableBody = document.getElementById('matchesTableBody');
      var cardList = document.getElementById('matchCardList');
      var target = tableBody || cardList || document.body;
      if (typeof MutationObserver !== 'undefined' && target) {
        observer = new MutationObserver(function () {
          if (hasRenderedMatch()) armWarmup();
        });
        observer.observe(target, { childList: true, subtree: true });
      }
      fallbackTimer = setTimeout(armWarmup, 6000);
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', watchMatches, { once: true });
    } else {
      watchMatches();
    }
  }

  var init = detectLang();
  load(init).catch(function () {
    // Do not reset a newer, user-selected locale due to a late boot failure.
    if (init !== DEFAULT_LANG && latestLocaleRequest === 1)
      load(DEFAULT_LANG).catch(function () {});
  });
  scheduleInteractionWarmup();
})();
