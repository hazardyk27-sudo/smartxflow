#!/usr/bin/env node
import fs from 'node:fs';
import { parse } from 'acorn';

const sourcePath = 'static/js/app.js.src';
const runtimeSourcePath = 'static/js/live-tab.js.src';
const minifyPath = 'minify.py';
let source = fs.readFileSync(sourcePath, 'utf8');

if (source.includes('function loadLiveTabRuntime(') && fs.existsSync(runtimeSourcePath)) {
  console.log('P2.20 already staged');
  process.exit(0);
}

const moveNames = [
  '_liveProBanner',
  '_renderLiveProLock',
  'switchToLive',
  'setLiveMarket',
  'toggleLiveMarketDropdown',
  'setLiveMarketFromDropdown',
  'loadLiveMatches',
  '_liveDonut',
  '_liveGetOu',
  '_liveCalcVol1x2',
  '_liveCalcVolOU',
  'renderLiveMatches',
  '_startGoalTakeover',
  '_calcLiveMatchMin',
  '_liveMwBlock',
  '_liveMobileCard',
  '_liveMobileBlock',
  'openLiveDetail',
  '_openLiveInMainModal',
  '_buildDetailTabs',
  'setLiveDetailMarket',
  'closeLiveDetail',
  'renderLiveDetail',
];

const publicImpls = new Map([
  ['switchToLive', '__sxfSwitchToLiveImpl'],
  ['setLiveMarket', '__sxfSetLiveMarketImpl'],
  ['toggleLiveMarketDropdown', '__sxfToggleLiveMarketDropdownImpl'],
  ['setLiveMarketFromDropdown', '__sxfSetLiveMarketFromDropdownImpl'],
  ['openLiveDetail', '__sxfOpenLiveDetailImpl'],
  ['setLiveDetailMarket', '__sxfSetLiveDetailMarketImpl'],
  ['closeLiveDetail', '__sxfCloseLiveDetailImpl'],
]);

const ast = parse(source, { ecmaVersion: 'latest', sourceType: 'script' });
const nodes = new Map();
for (const node of ast.body) {
  if (node.type === 'FunctionDeclaration' && node.id && moveNames.includes(node.id.name)) {
    nodes.set(node.id.name, node);
  }
}

const missing = moveNames.filter(name => !nodes.has(name));
if (missing.length) {
  throw new Error('Missing P2.20 function(s): ' + missing.join(', '));
}

const ordered = [...nodes.entries()].sort((a, b) => a[1].start - b[1].start);
const runtimeParts = ordered.map(([name, node]) => source.slice(node.start, node.end));

const removals = ordered.map(([, node]) => ({ start: node.start, end: node.end })).sort((a, b) => b.start - a.start);
for (const { start, end } of removals) {
  source = source.slice(0, start) + source.slice(end);
}

const marker = 'function switchFromLive() {';
if (!source.includes(marker)) throw new Error('P2.20 insertion marker not found');

const wrappers = `
window._sxfLiveTabRuntimePromise = window._sxfLiveTabRuntimePromise || null;
function _getLiveTabRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/live-tab.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/live-tab.js';
}

function loadLiveTabRuntime() {
    if (typeof window.__sxfSwitchToLiveImpl === 'function') return Promise.resolve();
    if (window._sxfLiveTabRuntimePromise) return window._sxfLiveTabRuntimePromise;

    window._sxfLiveTabRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getLiveTabRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfSwitchToLiveImpl === 'function') {
                resolve();
                return;
            }
            window._sxfLiveTabRuntimePromise = null;
            reject(new Error('Live tab runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfLiveTabRuntimePromise = null;
            reject(new Error('Live tab runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfLiveTabRuntimePromise;
}

async function switchToLive(...args) {
    await loadLiveTabRuntime();
    return window.__sxfSwitchToLiveImpl(...args);
}

async function setLiveMarket(...args) {
    await loadLiveTabRuntime();
    return window.__sxfSetLiveMarketImpl(...args);
}

async function toggleLiveMarketDropdown(...args) {
    await loadLiveTabRuntime();
    return window.__sxfToggleLiveMarketDropdownImpl(...args);
}

async function setLiveMarketFromDropdown(...args) {
    await loadLiveTabRuntime();
    return window.__sxfSetLiveMarketFromDropdownImpl(...args);
}

async function openLiveDetail(...args) {
    await loadLiveTabRuntime();
    return window.__sxfOpenLiveDetailImpl(...args);
}

async function setLiveDetailMarket(...args) {
    await loadLiveTabRuntime();
    return window.__sxfSetLiveDetailMarketImpl(...args);
}

async function closeLiveDetail(...args) {
    await loadLiveTabRuntime();
    return window.__sxfCloseLiveDetailImpl(...args);
}

`;

source = source.replace(marker, wrappers + marker);
fs.writeFileSync(sourcePath, source);

const assignments = [...publicImpls.entries()]
  .map(([name, impl]) => `window.${impl} = ${name};`)
  .join('\n');
const runtimeSource = `(function() {\n${runtimeParts.join('\n\n')}\n\n${assignments}\n})();\n`;
fs.writeFileSync(runtimeSourcePath, runtimeSource);

let minify = fs.readFileSync(minifyPath, 'utf8');
const appPair = "    ('static/js/app.js.src', 'static/js/app.js'),";
const livePair = "    ('static/js/live-tab.js.src', 'static/js/live-tab.js'),";
if (!minify.includes(livePair)) {
  if (!minify.includes(appPair)) throw new Error('minify.py app pair marker not found');
  minify = minify.replace(appPair, appPair + '\n' + livePair);
  fs.writeFileSync(minifyPath, minify);
}

console.log('P2.20 staged:', moveNames.length, 'functions moved');
