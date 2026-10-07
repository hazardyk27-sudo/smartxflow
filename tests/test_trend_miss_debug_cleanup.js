const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');

function extractFunction(text, name) {
  const re = new RegExp(`function\\s+${name}\\s*\\(`);
  const match = re.exec(text);
  assert.ok(match, `${name} must exist`);
  const start = match.index;
  const brace = text.indexOf('{', match.index + match[0].length);
  assert.ok(brace >= 0, `${name} opening brace missing`);
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let i = brace; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1] || '';
    if (lineComment) {
      if (ch === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (ch === '*' && next === '/') { blockComment = false; i++; }
      continue;
    }
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '/' && next === '/') { lineComment = true; i++; continue; }
    if (ch === '/' && next === '*') { blockComment = true; i++; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}') {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  assert.fail(`${name} closing brace missing`);
}

for (const file of ['static/js/app.js', 'static/js/app.js.src']) {
  test(`${file} getOddsTrendData miss path has no debug work`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    const fn = extractFunction(text, 'getOddsTrendData');
    assert.ok(!fn.includes('_trendDebugCount'), 'trend miss counter must be removed');
    assert.ok(!fn.includes('Object.keys(oddsTrendCache)'), 'trend miss must not enumerate cache keys');
    assert.ok(!fn.includes('cacheKeys'), 'debug cache sample must be removed');
  });

  test(`${file} getOddsTrendData keeps lookup/result semantics`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    const fn = extractFunction(text, 'getOddsTrendData').replace(/\s+/g, '');
    assert.ok(fn.includes('constkey=`${home}|${away}`;'));
    assert.ok(fn.includes('constmatchData=oddsTrendCache[key];'));
    assert.ok(fn.includes('if(!matchData||!matchData.values){returnnull;}'));
    assert.ok(fn.includes('returnmatchData.values[selection]||null;'));
  });
}
