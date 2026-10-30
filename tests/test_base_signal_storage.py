"""Phase 4 durable queue contract without network / database writes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from base_signal_engine.storage import (
    SupabaseCheckpointStore, ClaimedCheckpoint, DurableStoreError,
)
from base_signal_engine.durable_runtime import (
    cycle, execute_claims, retry_delay_seconds,
)
from base_signal_engine.scheduler import (
    CHECKPOINT_TASKS, RULESET_VERSION, CheckpointJob, FixtureRef,
)
from base_signal_engine.rules import Fixture

KO = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)
UID = 'ef5c99bf-e002-451b-b401-af9174ad53f0'
REF = FixtureRef(UID, KO)
JOB = CheckpointJob(REF, 6, 'BASE')


class Response:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.payload = payload
    def json(self):
        return self.payload


class FakeRpc:
    def __init__(self, *, result_by_rpc=None, statuses=None):
        self.results = result_by_rpc or {}
        self.statuses = statuses or {}
        self.calls = []

    def post(self, url, *, json, headers, timeout):
        name = url.rsplit('/', 1)[-1]
        self.calls.append((name, json, url, headers, timeout))
        result = self.results.get(name, 0)
        if isinstance(result, list) and name != 'sxf_base_claim_due_jobs':
            result = result.pop(0)
        return Response(result, self.statuses.get(name, 200))


def store(fake):
    return SupabaseCheckpointStore('https://example.supabase.co', 'very-secret-token', session=fake)


def fake_claim(job=JOB, *, attempt=1, **overrides):
    row = {
        'job_id': str(uuid4()), 'lease_token': str(uuid4()),
        'job_key': job.key, 'ruleset_version': RULESET_VERSION,
        'fixture_uid': job.fixture.fixture_uid,
        'kickoff_utc': job.fixture.kickoff_utc.isoformat(),
        'checkpoint_hours': job.hours, 'family': job.family,
        'checkpoint_at': job.timestamp.isoformat(),
        'attempt_count': attempt,
    }
    row.update(overrides)
    return row


def test_all_motor_jobs_enqueued_once_and_with_identity():
    fake = FakeRpc(result_by_rpc={'sxf_base_enqueue_jobs': len(CHECKPOINT_TASKS)})
    s = store(fake)
    assert s.enqueue([REF, REF]) == len(CHECKPOINT_TASKS)
    requests = [arg for op, arg, *_ in fake.calls if op == 'sxf_base_enqueue_jobs']
    assert len(requests) == 1
    data = requests[0]['p_jobs']
    assert len(data) == len(CHECKPOINT_TASKS)
    assert {(x['checkpoint_hours'], x['family']) for x in data} == set(CHECKPOINT_TASKS)
    assert all(x['fixture_uid'] == UID and x['ruleset_version'] == RULESET_VERSION for x in data)
    assert all(x['job_key'].startswith(RULESET_VERSION + ':') for x in data)


def test_enqueue_chunking_and_empty_universe():
    twin = FixtureRef(str(uuid4()), KO)
    fake = FakeRpc(result_by_rpc={'sxf_base_enqueue_jobs': [3, 3, 3, 3, 3, 3, 2]})
    s = store(fake)
    assert s.enqueue([REF, twin], batch_size=3) == 20
    assert len(fake.calls) == 7
    assert s.enqueue([]) == 0
    assert len(fake.calls) == 8


def test_claim_confirms_identities_and_rejects_unknown_ruleset():
    row = fake_claim()
    fake = FakeRpc(result_by_rpc={'sxf_base_claim_due_jobs': [row]})
    items = store(fake).claim('worker-1')
    assert len(items) == 1 and items[0].job.key == JOB.key
    assert items[0].attempt_count == 1
    fake.results['sxf_base_claim_due_jobs'] = [fake_claim(ruleset_version='unknown')]
    with pytest.raises(DurableStoreError, match='mismatched'):
        store(fake).claim('worker-1')


def test_claim_rejects_identity_or_checkpoint_tampering():
    for corrupt in [{'job_key': 'wrong'}, {'checkpoint_hours': 5},
                    {'checkpoint_at': (JOB.timestamp + timedelta(seconds=1)).isoformat()},
                    {'fixture_uid': 'not-a-uid'}]:
        fake = FakeRpc(result_by_rpc={'sxf_base_claim_due_jobs': [fake_claim(**corrupt)]})
        with pytest.raises(DurableStoreError):
            store(fake).claim('worker-1')


def test_complete_requires_same_key_and_ack_and_never_logs_secret():
    item = ClaimedCheckpoint(str(uuid4()), str(uuid4()), JOB, 1)
    fake = FakeRpc(result_by_rpc={'sxf_base_complete_job': True})
    s = store(fake)
    s.complete(item, {'key': JOB.key, 'signals': []})
    assert fake.calls[-1][0] == 'sxf_base_complete_job'
    assert fake.calls[-1][1]['p_lease_token'] == item.lease_token
    with pytest.raises(ValueError):
        s.complete(item, {'key': 'other'})
    fake.statuses['sxf_base_complete_job'] = 503
    with pytest.raises(DurableStoreError) as exc:
        s.complete(item, {'key': JOB.key})
    assert 'very-secret-token' not in str(exc.value)


def test_fail_and_renew_lease_are_token_guarded():
    item = ClaimedCheckpoint(str(uuid4()), str(uuid4()), JOB, 2)
    fake = FakeRpc(result_by_rpc={'sxf_base_fail_job': True, 'sxf_base_renew_lease': True})
    s = store(fake)
    s.renew(item, lease_seconds=300)
    s.fail(item, 'SNAPSHOTREADERROR', delay_seconds=60)
    assert [x[0] for x in fake.calls] == ['sxf_base_renew_lease', 'sxf_base_fail_job']
    with pytest.raises(ValueError):
        s.fail(item, 'SECRET credential leaked in error')
    fake.results['sxf_base_renew_lease'] = False
    with pytest.raises(DurableStoreError):
        s.renew(item)


def test_rpc_disallows_arbitrary_tables_and_no_secret_error_detail():
    fake = FakeRpc(statuses={'sxf_base_claim_due_jobs': 401})
    s = store(fake)
    with pytest.raises(ValueError):
        s._rpc('delete_all_moneyway_snapshots', {})
    with pytest.raises(DurableStoreError) as err:
        s.claim('worker')
    assert 'very-secret-token' not in str(err.value)
    assert all('/rpc/' in x[2] for x in fake.calls)
    assert all(x[0] != 'delete_all_moneyway_snapshots' for x in fake.calls)


def test_retry_backoff_never_exceeds_one_hour():
    assert [retry_delay_seconds(x) for x in (1,2,3,4,10,100)] == [30,60,120,240,3600,3600]


def test_execute_claims_missing_data_waits_without_false_completion():
    row = fake_claim()
    fake = FakeRpc(result_by_rpc={
        'sxf_base_claim_due_jobs': [row], 'sxf_base_skip_missing_source': True})
    s = store(fake)

    class Reader:
        def load_fixture(self, fixture_uid):
            return Fixture(UID, KO), 'legacy'
        def load_checkpoints(self, fixture, *, hours, as_of_utc, include_v2_history, expected_legacy_hash):
            return SimpleNamespace(snapshots=(),fetched_rows=0,discarded_groups=0,hash_drift_rows=0)

    report = execute_claims(Reader(), s, worker_id='test-worker')
    assert report == {'claimed':1, 'completed':0, 'waiting_data':0,
                      'skipped_data':1, 'retry':0, 'lease_lost':0, 'commit_uncertain':0}
    assert [x[0] for x in fake.calls] == ['sxf_base_claim_due_jobs','sxf_base_skip_missing_source']
    assert fake.calls[1][1]['p_reason'] == 'SOURCE_INCOMPLETE'


def test_execute_claims_eval_failure_retries_not_completes():
    fake = FakeRpc(result_by_rpc={
        'sxf_base_claim_due_jobs': [fake_claim(attempt=3)],
        'sxf_base_fail_job': True,
    })
    class Reader:
        def load_fixture(self, fixture_uid):
            raise ConnectionError('SECRET token unreachable')
    report = execute_claims(Reader(),store(fake),worker_id='worker')
    assert report['retry'] == 1 and report['completed'] == 0
    assert fake.calls[-1][1]['p_retry_seconds'] == 120
    assert fake.calls[-1][1]['p_error_code'] == 'CONNECTIONERROR'
    assert 'SECRET' not in str(fake.calls[-1][1])


def test_execute_claims_lost_lease_records_failure_without_second_write():
    fake = FakeRpc(result_by_rpc={'sxf_base_claim_due_jobs':[fake_claim()], 'sxf_base_fail_job': False})
    class Reader:
        def load_fixture(self, uid):
            raise RuntimeError('disconnected')
    stats = execute_claims(Reader(),store(fake),worker_id='worker')
    assert stats['lease_lost'] == 1 and stats['completed'] == 0


def test_discovery_outage_does_not_block_existing_queue():
    fake = FakeRpc(result_by_rpc={'sxf_base_claim_due_jobs': []})
    s = store(fake)
    class Catalog:
        def list_between(self, start, end):
            raise RuntimeError('network down')
    results = cycle(object(),s,worker_id='worker',catalog=Catalog(),now=KO)
    assert results['catalog_error'] and results['claimed'] == 0
    assert [c[0] for c in fake.calls] == ['sxf_base_claim_due_jobs']


def test_discovery_enqueues_checkpoint_plan_then_claims():
    fake = FakeRpc(result_by_rpc={
        'sxf_base_enqueue_jobs': len(CHECKPOINT_TASKS),
        'sxf_base_claim_due_jobs': []})
    class Catalog:
        def list_between(self, start, end): return [REF]
    report = cycle(object(),store(fake),worker_id='worker',catalog=Catalog(),now=KO)
    assert report['fixtures'] == 1 and report['enqueued'] == len(CHECKPOINT_TASKS)
    assert [r[0] for r in fake.calls] == ['sxf_base_enqueue_jobs','sxf_base_claim_due_jobs']


def test_db_schema_has_rpc_locking_audit_and_no_legacy_table_writes():
    from pathlib import Path
    script = Path(__file__).resolve().parents[1] / 'migrations/2026_10_18_sxf_base_durable_queue.sql'
    content = script.read_text()
    assert 'FOR UPDATE SKIP LOCKED' in content
    assert 'lease_token=gen_random_uuid()' in content
    assert 'CREATE TABLE IF NOT EXISTS public.sxf_base_checkpoint_evaluations' in content
    assert 'CREATE TABLE IF NOT EXISTS public.sxf_base_signal_events' in content
    assert 'sxf_base_signal_events_immutable' in content
    assert "'MARKET_DECISION'" in content
    assert 'GRANT EXECUTE ON FUNCTION public.sxf_base_enqueue_jobs' in content
    assert 'UPDATE public.moneyway_snapshots' not in content
    assert 'DELETE FROM public.' not in content