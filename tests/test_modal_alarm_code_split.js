const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const bundles = [
  ['runtime', fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8')],
];
const deferredRuntime = fs.readFileSync(path.join(root, 'static/js/modal-alarms.js'), 'utf8');
const deferredSource = fs.readFileSync(path.join(root, 'static/js/modal-alarms.js.src'), 'utf8');
const template = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');

function extractFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} should exist`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  let inTemplate = false;
  let inLineComment = false;
  let inBlockComment = false;
  let escaped = false;
  for (let i = bodyStart; i < source.length; i += 1) {
    const c = source[i];
    const n = source[i + 1] || '';
    if (inLineComment) {
      if (c === '\n') inLineComment = false;
      continue;
    }
    if (inBlockComment) {
      if (c === '*' && n === '/') { inBlockComment = false; i += 1; }
      continue;
    }
    if (inSingle) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === "'") inSingle = false;
      continue;
    }
    if (inDouble) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '"') inDouble = false;
      continue;
    }
    if (inTemplate) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '`') inTemplate = false;
      continue;
    }
    if (c === '/' && n === '/') { inLineComment = true; i += 1; continue; }
    if (c === '/' && n === '*') { inBlockComment = true; i += 1; continue; }
    if (c === "'") { inSingle = true; continue; }
    if (c === '"') { inDouble = true; continue; }
    if (c === '`') { inTemplate = true; continue; }
    if (c === '{') depth += 1;
    if (c === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  assert.fail(`${signature} should have a closing brace`);
}

for (const [name, source] of bundles) {
  test(`main bundle keeps only lazy match-alarm stub (${name})`, () => {
    const fn = extractFunction(source, 'async function renderMatchAlarmsSection(');
    assert.match(fn, /loadModalAlarmsRuntime\(\)/);
    assert.match(fn, /window\.__sxfRenderMatchAlarmsSectionImpl/);
    assert.doesNotMatch(fn, /groupBySelection/);
    assert.match(source, /function loadModalAlarmsRuntime\(\)/);
  });
}

test('modal alarm implementation is deferred and not eager in template', () => {
  assert.doesNotMatch(template, /modal-alarms\.js/);
  assert.match(deferredRuntime, /window\.__sxfRenderMatchAlarmsSectionImpl\s*=\s*async function renderMatchAlarmsSection/);
  assert.match(deferredSource, /window\.__sxfRenderMatchAlarmsSectionImpl\s*=\s*async function renderMatchAlarmsSection/);
  assert.match(deferredRuntime, /groupBySelection/);
});

test('modal alarm loader deduplicates concurrent requests and inherits app version', async () => {
  const source = bundles[1][1];
  const urlFn = extractFunction(source, 'function _getModalAlarmsRuntimeUrl(');
  const loaderFn = extractFunction(source, 'function loadModalAlarmsRuntime(');
  const stubFn = extractFunction(source, 'async function renderMatchAlarmsSection(');
  const appended = [];
  const windowObj = {};
  const context = vm.createContext({
    window: windowObj,
    document: {
      getElementsByTagName(name) {
        assert.equal(name, 'script');
        return [{ src: 'https://preview.example/static/js/app.js?v=alarm123' }];
      },
      createElement(name) {
        assert.equal(name, 'script');
        return {};
      },
      head: {
        appendChild(script) {
          appended.push(script);
          setImmediate(() => {
            windowObj.__sxfRenderMatchAlarmsSectionImpl = async (...args) => args.join('|');
            script.onload();
          });
        }
      }
    },
    Promise,
    Error,
    setImmediate,
  });
  vm.runInContext(`${urlFn}\n${loaderFn}\n${stubFn}\nwindow.__testRender = renderMatchAlarmsSection;`, context);
  const [a, b] = await Promise.all([
    windowObj.__testRender('A', 'B'),
    windowObj.__testRender('C', 'D'),
  ]);
  assert.equal(appended.length, 1);
  assert.equal(appended[0].src, '/static/js/modal-alarms.js?v=alarm123');
  assert.equal(a, 'A|B');
  assert.equal(b, 'C|D');
});
