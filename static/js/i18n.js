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

  function detectLang() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (e) {}
    return DEFAULT_LANG;
  }

  function get(key) {
    if (!key) return '';
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
    return fetch(BASE_PATH + lang + '.json?v=1', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('i18n load failed: ' + lang);
        return r.json();
      })
      .then(function (data) {
        dict = data;
        currentLang = lang;
        try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
        applyDOM();
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
    if (init !== DEFAULT_LANG) load(DEFAULT_LANG).catch(function () {});
  });
  scheduleInteractionWarmup();
})();
