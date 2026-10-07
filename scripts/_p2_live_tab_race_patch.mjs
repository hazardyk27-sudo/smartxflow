#!/usr/bin/env node
import fs from 'node:fs';

const path = 'static/js/app.js.src';
let source = fs.readFileSync(path, 'utf8');

if (source.includes('window._sxfLiveTabEntryGeneration = window._sxfLiveTabEntryGeneration || 0;')) {
  console.log('P2.20 Live-tab entry guard already applied');
  process.exit(0);
}

const promiseMarker = 'window._sxfLiveTabRuntimePromise = window._sxfLiveTabRuntimePromise || null;';
if (!source.includes(promiseMarker)) throw new Error('Live-tab loader marker not found');
source = source.replace(
  promiseMarker,
  "window._sxfLiveTabEntryGeneration = window._sxfLiveTabEntryGeneration || 0;\n" +
  "window._sxfLiveTabRuntimePromise = window._sxfLiveTabRuntimePromise || null;\n" +
  "function _cancelPendingLiveTabEntry() {\n" +
  "    window._sxfLiveTabEntryGeneration += 1;\n" +
  "}"
);

const oldSwitch = `async function switchToLive(...args) {
    await loadLiveTabRuntime();
    return window.__sxfSwitchToLiveImpl(...args);
}`;
const newSwitch = `async function switchToLive(...args) {
    const entryGeneration = ++window._sxfLiveTabEntryGeneration;
    await loadLiveTabRuntime();
    if (entryGeneration !== window._sxfLiveTabEntryGeneration) return;
    return window.__sxfSwitchToLiveImpl(...args);
}`;
if (!source.includes(oldSwitch)) throw new Error('switchToLive lazy wrapper marker not found');
source = source.replace(oldSwitch, newSwitch);

const oldSetTab = `window.setTab = function(market) {
        if (_liveMode) switchFromLive();
        _realSetTab(market);
    };`;
const newSetTab = `window.setTab = function(market) {
        if (market !== 'live') _cancelPendingLiveTabEntry();
        if (_liveMode) switchFromLive();
        _realSetTab(market);
    };`;
if (!source.includes(oldSetTab)) throw new Error('desktop tab wrapper marker not found');
source = source.replace(oldSetTab, newSetTab);

const oldMobile = `window.setMobileGroup = function(group) {
        if (group === 'live') { switchToLive(); return; }
        if (_liveMode) switchFromLive();
        _realSetMobileGroup(group);
    };`;
const newMobile = `window.setMobileGroup = function(group) {
        if (group === 'live') { switchToLive(); return; }
        _cancelPendingLiveTabEntry();
        if (_liveMode) switchFromLive();
        _realSetMobileGroup(group);
    };`;
if (!source.includes(oldMobile)) throw new Error('mobile tab wrapper marker not found');
source = source.replace(oldMobile, newMobile);

const oldClick = `if (tab && tab.dataset.market !== 'live' && _liveMode) {
        switchFromLive();
    }`;
const newClick = `if (tab && tab.dataset.market !== 'live') {
        _cancelPendingLiveTabEntry();
        if (_liveMode) switchFromLive();
    }`;
if (!source.includes(oldClick)) throw new Error('desktop non-live click guard marker not found');
source = source.replace(oldClick, newClick);

fs.writeFileSync(path, source);
console.log('P2.20 pending Live-tab activation guard applied');
