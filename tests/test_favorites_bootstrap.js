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
}
