const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

for (const file of ['app.js', 'app.js.src']) {
  const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', file), 'utf8');
  test(`favorites startup is one bootstrap request with legacy fallback (${file})`, () => {
    assert.match(source, /function loadFavoritesBootstrap\(\)/);
    assert.match(source, /\/api\/favorites\/bootstrap\?device_id=/);
    assert.match(source, /Promise\.all\(\[loadUserFavorites\(\),\s*loadFavoriteCounts\(\)\]\)/);
    const startup = source.indexOf("runOptionalStartupTask('favorites'");
    assert.ok(startup >= 0);
    assert.match(source.slice(startup, startup + 180), /loadFavoritesBootstrap\(\)/);
    assert.doesNotMatch(source.slice(startup, startup + 180), /Promise\.all\(\[loadUserFavorites/);
  });

  test(`favorites filter constrains the virtual list before rendering or scrolling (${file})`, () => {
    const toggleStart = source.indexOf('function toggleFavoritesFilter()');
    const helperStart = source.indexOf('function _renderFavoritesView()');
    const renderStart = source.indexOf('function renderMatches(data)');
    const mobileStart = source.indexOf('function renderMobileMatchCards(data)');
    assert.ok(toggleStart >= 0 && helperStart > toggleStart && renderStart >= 0 && mobileStart >= 0);
    const toggle = source.slice(toggleStart, source.indexOf('function _applyFavoritesFilter()', toggleStart));
    const helper = source.slice(helperStart, renderStart);
    assert.ok(toggle.indexOf('_renderFavoritesView()') < toggle.indexOf('_loadAndApplyFavoritesFilter('),
      'filter the current list before the async favorites lookup');
    assert.match(helper, /applySorting\\(matches/);
    assert.match(helper, /renderMatches\\(filteredMatches/);
    for (const start of [renderStart, mobileStart]) {
      assert.match(source.slice(start, start + 260),
        /if\\s*\\(_favFilterActive\\)\\s*data\\s*=\\s*data\\.filter/);
    }
    assert.match(toggle, /_favoritesFilterRequestId/);
  });
}
