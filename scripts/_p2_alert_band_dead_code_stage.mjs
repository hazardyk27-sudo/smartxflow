#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'acorn';

const appPath = 'static/js/app.js.src';
let source = fs.readFileSync(appPath, 'utf8');

if (!source.includes('function showAlertBandDetail(') && !source.includes('function formatAlertValue(')) {
  console.log('P2.22 already staged');
  process.exit(0);
}

function collectFiles(dir, predicate, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectFiles(full, predicate, out);
    else if (predicate(full)) out.push(full);
  }
  return out;
}

const sourceFiles = [
  ...collectFiles('static/js', f => f.endsWith('.src')),
  ...collectFiles('templates', f => f.endsWith('.html')),
];

function occurrences(text, needle) {
  let count = 0;
  let pos = 0;
  while ((pos = text.indexOf(needle, pos)) !== -1) {
    count += 1;
    pos += needle.length;
  }
  return count;
}

function refsFor(symbol) {
  const refs = [];
  for (const file of sourceFiles) {
    const text = fs.readFileSync(file, 'utf8');
    const count = occurrences(text, symbol);
    if (count) refs.push({ file: file.replaceAll('\\', '/'), count });
  }
  return refs;
}

const detailRefs = refsFor('showAlertBandDetail');
const valueRefs = refsFor('formatAlertValue');

const detailTotal = detailRefs.reduce((sum, r) => sum + r.count, 0);
const valueTotal = valueRefs.reduce((sum, r) => sum + r.count, 0);

console.log('showAlertBandDetail refs:', JSON.stringify(detailRefs));
console.log('formatAlertValue refs:', JSON.stringify(valueRefs));

if (detailTotal !== 1 || detailRefs.length !== 1 || detailRefs[0].file !== appPath) {
  throw new Error(`P2.22 fail-closed: showAlertBandDetail expected exactly one declaration-only source reference, got ${JSON.stringify(detailRefs)}`);
}
if (valueTotal !== 2 || valueRefs.length !== 1 || valueRefs[0].file !== appPath) {
  throw new Error(`P2.22 fail-closed: formatAlertValue expected declaration + dead-renderer call only, got ${JSON.stringify(valueRefs)}`);
}

const ast = parse(source, { ecmaVersion: 'latest', sourceType: 'script' });
const targetNames = new Set(['showAlertBandDetail', 'formatAlertValue']);
const targets = ast.body.filter(node =>
  node.type === 'FunctionDeclaration' && node.id && targetNames.has(node.id.name)
);

if (targets.length !== 2 || new Set(targets.map(n => n.id.name)).size !== 2) {
  throw new Error('P2.22 fail-closed: expected exactly two target FunctionDeclaration nodes');
}

for (const node of [...targets].sort((a, b) => b.start - a.start)) {
  source = source.slice(0, node.start) + source.slice(node.end);
}

for (const required of [
  'function loadAlertBand(',
  'function renderAlertBand(',
  'function getAlertType(',
  'goToMatchFromAlarm('
]) {
  if (!source.includes(required)) {
    throw new Error(`P2.22 invariant missing after cleanup: ${required}`);
  }
}
if (source.includes('showAlertBandDetail') || source.includes('formatAlertValue')) {
  throw new Error('P2.22 target symbol remained after AST cleanup');
}

fs.writeFileSync(appPath, source);
console.log('P2.22 staged: removed legacy Alert Band detail renderer and its private formatter');
