#!/usr/bin/env node
import fs from 'node:fs';
import { parse } from 'acorn';

const sourcePath = 'static/js/app.js.src';
const runtimeSourcePath = 'static/js/alarm-sidebar.js.src';
let source = fs.readFileSync(sourcePath, 'utf8');

if (source.includes('function loadAlarmSidebarRuntime(') && fs.existsSync(runtimeSourcePath)) {
  console.log('P2.19 already staged');
  process.exit(0);
}

const publicImpls = new Map([
  ['loadAllAlarms', '__sxfLoadAllAlarmsImpl'],
  ['selectDateFilter', '__sxfSelectDateFilterImpl'],
  ['filterAlarms', '__sxfFilterAlarmsImpl'],
  ['searchAlarms', '__sxfSearchAlarmsImpl'],
  ['toggleAlarmDetail', '__sxfToggleAlarmDetailImpl'],
  ['loadMoreAlarms', '__sxfLoadMoreAlarmsImpl']
]);

const targetNames = [
  'loadAllAlarms',
  'updateAlarmCounts',
  'selectDateFilter',
  'filterAlarmsByMatchDate',
  'updateDateFilterCounts',
  'filterAlarms',
  'searchAlarms',
  'getFilteredAlarms',
  'renderAlarmsList',
  'toggleAlarmDetail',
  'formatMarketChip',
  'loadMoreAlarms'
];

const ast = parse(source, {
  ecmaVersion: 'latest',
  sourceType: 'script',
  ranges: true,
  allowHashBang: true
});

const functions = new Map();
for (const node of ast.body) {
  if (node.type === 'FunctionDeclaration' && node.id && targetNames.includes(node.id.name)) {
    functions.set(node.id.name, node);
  }
}

for (const name of targetNames) {
  if (!functions.has(name)) {
    throw new Error(`P2.19 target function missing: ${name}`);
  }
}

const extracted = new Map();
for (const name of targetNames) {
  const node = functions.get(name);
  extracted.set(name, source.slice(node.start, node.end));
}

const implNames = [...publicImpls.values()];
const readyCheck = implNames
  .map((name) => `typeof window.${name} === 'function'`)
  .join(' &&\n        ');

const loader = `window._sxfAlarmSidebarRuntimePromise = window._sxfAlarmSidebarRuntimePromise || null;
function _getAlarmSidebarRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryAt = src.indexOf('?');
                return '/static/js/alarm-sidebar.js' + (queryAt >= 0 ? src.slice(queryAt) : '');
            }
        }
    } catch (e) {}
    return '/static/js/alarm-sidebar.js';
}

function loadAlarmSidebarRuntime() {
    const ready = ${readyCheck};
    if (ready) return Promise.resolve();
    if (window._sxfAlarmSidebarRuntimePromise) return window._sxfAlarmSidebarRuntimePromise;

    window._sxfAlarmSidebarRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getAlarmSidebarRuntimeUrl();
        script.async = true;
        script.onload = () => {
            const loaded = ${readyCheck};
            if (!loaded) {
                window._sxfAlarmSidebarRuntimePromise = null;
                reject(new Error('Alarm sidebar runtime loaded without required implementations'));
                return;
            }
            resolve();
        };
        script.onerror = () => {
            window._sxfAlarmSidebarRuntimePromise = null;
            reject(new Error('Alarm sidebar runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfAlarmSidebarRuntimePromise;
}

function _callAlarmSidebarRuntime(implName, args) {
    const impl = window[implName];
    if (typeof impl === 'function') return impl(...args);
    return loadAlarmSidebarRuntime().then(() => {
        const loadedImpl = window[implName];
        if (typeof loadedImpl !== 'function') {
            throw new Error('Alarm sidebar runtime missing ' + implName);
        }
        return loadedImpl(...args);
    });
}
`;

const stubFor = (name, implName) => `function ${name}(...args) {
    return _callAlarmSidebarRuntime('${implName}', args);
}`;

const edits = [];
for (const name of targetNames) {
  const node = functions.get(name);
  let replacement = '';
  if (publicImpls.has(name)) {
    replacement = stubFor(name, publicImpls.get(name));
    if (name === 'loadAllAlarms') replacement = `${loader}\n${replacement}`;
  }
  edits.push({ start: node.start, end: node.end, replacement });
}

edits.sort((a, b) => b.start - a.start);
for (const edit of edits) {
  source = source.slice(0, edit.start) + edit.replacement + source.slice(edit.end);
}

const runtimeBody = targetNames.map((name) => extracted.get(name)).join('\n\n');
const exports = [...publicImpls.entries()]
  .map(([name, implName]) => `window.${implName} = ${name};`)
  .join('\n');
const runtimeSource = `(function() {\n${runtimeBody}\n\n${exports}\n})();\n`;

fs.writeFileSync(sourcePath, source);
fs.writeFileSync(runtimeSourcePath, runtimeSource);

console.log('P2.19 staged');
console.log('app.js.src', Buffer.byteLength(source));
console.log('alarm-sidebar.js.src', Buffer.byteLength(runtimeSource));
