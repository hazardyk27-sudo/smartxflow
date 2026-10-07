#!/usr/bin/env node

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('static/js/app.js.src', 'utf8');

function extractFunctionDeclaration(sourceText, signature) {
    const start = sourceText.indexOf(signature);
    assert(start >= 0, `${signature} should exist`);
    const bodyStart = sourceText.indexOf('{', start);
    assert(bodyStart > start, `${signature} should have a body`);

    let depth = 0;
    for (let index = bodyStart; index < sourceText.length; index += 1) {
        if (sourceText[index] === '{') depth += 1;
        if (sourceText[index] === '}') {
            depth -= 1;
            if (depth === 0) return sourceText.slice(start, index + 1);
        }
    }

    assert.fail(`${signature} should have a closing brace`);
}

const groupSource = extractFunctionDeclaration(source, 'function groupAlarmsByMatch(');
const identitySource = extractFunctionDeclaration(source, 'function _matchContextHash(');

const sandbox = {
    console,
    toTurkeyTime(value) {
        const date = new Date(value);
        return { isValid: () => !Number.isNaN(date.valueOf()), valueOf: () => date.valueOf() };
    }
};
vm.createContext(sandbox);
vm.runInContext(groupSource + '\n' + identitySource, sandbox);

const base = {
    home: 'Barcelona',
    away: 'Feyenoord',
    league: 'UEFA Youth League',
    market: 'ou25',
    selection: 'U',
    kickoff_utc: '2026-09-09T16:00:00Z',
    _type: 'sharp'
};

assert.strictEqual(
    sandbox._alarmBelongsToMatch(
        { ...base },
        'Barcelona',
        'Feyenoord',
        base.league,
        base.kickoff_utc,
        'senior-hash'
    ),
    false,
    'hash-bearing modal must reject hashless legacy alarms'
);
assert.strictEqual(
    sandbox._alarmBelongsToMatch(
        { ...base, match_id_hash: 'u19-hash' },
        'Barcelona',
        'Feyenoord',
        base.league,
        base.kickoff_utc,
        'senior-hash'
    ),
    false,
    'modal must reject a different match hash'
);
assert.strictEqual(
    sandbox._alarmBelongsToMatch(
        { ...base, match_id_hash: 'senior-hash', home: 'FC Barcelona', away: 'Feyenoord U19' },
        'Barcelona',
        'Feyenoord',
        base.league,
        base.kickoff_utc,
        'senior-hash'
    ),
    true,
    'modal must accept the matching match hash'
);

const grouped = sandbox.groupAlarmsByMatch([
    { ...base, kickoff_utc: '2026-09-09T16:00:00Z' },
    { ...base, kickoff_utc: '2026-09-05T16:00:00Z' }
]);
assert.strictEqual(grouped.length, 2, 'different kickoff dates must stay separate groups');

const sameHashGrouped = sandbox.groupAlarmsByMatch([
    { ...base, match_id_hash: 'same-hash' },
    { ...base, match_id_hash: 'same-hash', trigger_at: '2026-09-09T15:30:00Z' }
]);
assert.strictEqual(sameHashGrouped.length, 1, 'alarms for one hash must remain one group');

console.log('alarm identity regression tests passed');
