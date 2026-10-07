#!/usr/bin/env node
import fs from 'node:fs';
import { parse } from 'acorn';

const sourcePath = 'static/js/app.js.src';
const runtimeSourcePath = 'static/js/admin-panel.js.src';
const minifyPath = 'minify.py';
let source = fs.readFileSync(sourcePath, 'utf8');

if (source.includes('function loadAdminPanelRuntime(') && fs.existsSync(runtimeSourcePath)) {
  console.log('P2.21 already staged');
  process.exit(0);
}

const moveNames = [
  'openAdminPanel',
  'closeAdminPanel',
  'switchAdminTab',
  'loadAdminVolumeLeaderData',
  'saveVolumeLeaderConfig',
  'calculateVolumeLeaderAlarms',
  'deleteVolumeLeaderAlarms',
  'loadAdminDroppingData',
  'saveDroppingConfig',
  'calculateDroppingAlarms',
  'deleteDroppingAlarms',
  'loadAdminMimData',
  'saveMimConfig',
  'deleteMimAlarms',
];

const ast = parse(source, { ecmaVersion: 'latest', sourceType: 'script' });
const nodes = [];
const foundFunctions = new Set();
let foundAdminState = false;

for (const node of ast.body) {
  if (node.type === 'FunctionDeclaration' && node.id && moveNames.includes(node.id.name)) {
    nodes.push({ name: node.id.name, node });
    foundFunctions.add(node.id.name);
    continue;
  }
  if (node.type === 'VariableDeclaration') {
    const ownsAdminState = node.declarations.some(d => d.id && d.id.type === 'Identifier' && d.id.name === 'currentAdminTab');
    if (ownsAdminState) {
      nodes.push({ name: 'currentAdminTab', node });
      foundAdminState = true;
    }
  }
}

const missing = moveNames.filter(name => !foundFunctions.has(name));
if (!foundAdminState) missing.push('currentAdminTab');
if (missing.length) throw new Error('Missing P2.21 node(s): ' + missing.join(', '));

nodes.sort((a, b) => a.node.start - b.node.start);
const insertionPoint = nodes[0].node.start;
const runtimeParts = nodes.map(({ node }) => source.slice(node.start, node.end));

for (const { node } of [...nodes].sort((a, b) => b.node.start - a.node.start)) {
  source = source.slice(0, node.start) + source.slice(node.end);
}

const wrappers = `window._sxfAdminPanelRuntimePromise = window._sxfAdminPanelRuntimePromise || null;
function _getAdminPanelRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/admin-panel.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/admin-panel.js';
}

function loadAdminPanelRuntime() {
    if (typeof window.__sxfOpenAdminPanelImpl === 'function') return Promise.resolve();
    if (window._sxfAdminPanelRuntimePromise) return window._sxfAdminPanelRuntimePromise;

    window._sxfAdminPanelRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getAdminPanelRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfOpenAdminPanelImpl === 'function') {
                resolve();
                return;
            }
            window._sxfAdminPanelRuntimePromise = null;
            reject(new Error('Admin panel runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfAdminPanelRuntimePromise = null;
            reject(new Error('Admin panel runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfAdminPanelRuntimePromise;
}

async function openAdminPanel(...args) {
    await loadAdminPanelRuntime();
    return window.__sxfOpenAdminPanelImpl(...args);
}

async function closeAdminPanel(...args) {
    await loadAdminPanelRuntime();
    return window.__sxfCloseAdminPanelImpl(...args);
}

async function switchAdminTab(...args) {
    await loadAdminPanelRuntime();
    return window.__sxfSwitchAdminTabImpl(...args);
}

`;

source = source.slice(0, insertionPoint) + wrappers + source.slice(insertionPoint);
fs.writeFileSync(sourcePath, source);

const inlineCallbacks = [
  'saveVolumeLeaderConfig', 'calculateVolumeLeaderAlarms', 'deleteVolumeLeaderAlarms',
  'saveDroppingConfig', 'calculateDroppingAlarms', 'deleteDroppingAlarms',
  'saveMimConfig', 'deleteMimAlarms',
];
const exports = [
  'window.__sxfOpenAdminPanelImpl = openAdminPanel;',
  'window.__sxfCloseAdminPanelImpl = closeAdminPanel;',
  'window.__sxfSwitchAdminTabImpl = switchAdminTab;',
  ...inlineCallbacks.map(name => `window.${name} = ${name};`),
].join('\n');
const runtimeSource = `(function() {\n${runtimeParts.join('\n\n')}\n\n${exports}\n})();\n`;
fs.writeFileSync(runtimeSourcePath, runtimeSource);

let minify = fs.readFileSync(minifyPath, 'utf8');
const appPair = "    ('static/js/app.js.src', 'static/js/app.js'),";
const adminPair = "    ('static/js/admin-panel.js.src', 'static/js/admin-panel.js'),";
if (!minify.includes(adminPair)) {
  if (!minify.includes(appPair)) throw new Error('minify.py app pair marker not found');
  minify = minify.replace(appPair, appPair + '\n' + adminPair);
  fs.writeFileSync(minifyPath, minify);
}

console.log('P2.21 staged:', moveNames.length, 'functions + admin state moved');
