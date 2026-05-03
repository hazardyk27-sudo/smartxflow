(function () {
  'use strict';

  // Inject flag-icon styles once (works on Windows where emoji flags don't render)
  try {
    if (!document.getElementById('sxf-flag-icon-style')) {
      var st = document.createElement('style');
      st.id = 'sxf-flag-icon-style';
      st.textContent = '.flag-icon{display:inline-block;width:18px;height:13px;vertical-align:middle;border-radius:2px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,0.12);}';
      (document.head || document.documentElement).appendChild(st);
    }
  } catch (e) {}

  var SUPPORTED = ['tr', 'en', 'de', 'fr', 'nl', 'it', 'es'];
  var DEFAULT_LANG = 'en';
  var STORAGE_KEY = 'sxf_lang';
  var BASE_PATH = '/static/i18n/';
  var FLAGS = { tr: '<img class="flag-icon" src="/static/flags/tr.svg" alt="">', en: '<img class="flag-icon" src="/static/flags/gb.svg" alt="">', de: '<img class="flag-icon" src="/static/flags/de.svg" alt="">', fr: '<img class="flag-icon" src="/static/flags/fr.svg" alt="">', nl: '<img class="flag-icon" src="/static/flags/nl.svg" alt="">', it: '<img class="flag-icon" src="/static/flags/it.svg" alt="">', es: '<img class="flag-icon" src="/static/flags/es.svg" alt="">' };

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
      el.innerHTML = FLAGS[currentLang] || currentLang.toUpperCase();
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

  var init = detectLang();
  load(init).catch(function () {
    if (init !== DEFAULT_LANG) load(DEFAULT_LANG).catch(function () {});
  });
})();
