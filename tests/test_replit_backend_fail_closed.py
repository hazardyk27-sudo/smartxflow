from pathlib import Path

import sitecustomize


def test_replit_marker_blocks_production_workers():
    env = {"REPL_ID": "example-repl"}
    workers = [
        "scheduled_scraper.py",
        "scheduled_scraper_legacy.py",
        "prematch_authoritative_runtime.py",
        "alarm_engine.py",
        "live_scraper.py",
        "sinyal_engine.py",
        "sinyal_engine_runtime.py",
        "polymarket_scraper.py",
    ]
    for worker in workers:
        assert sitecustomize.should_refuse_replit_backend(worker, env)


def test_replit_does_not_block_web_app():
    env = {"REPL_ID": "example-repl"}
    assert not sitecustomize.should_refuse_replit_backend("app.py", env)


def test_legacy_repl_deployment_does_not_misclassify_hetzner():
    env = {"REPL_DEPLOYMENT": "1"}
    assert not sitecustomize.is_replit_runtime(env)
    assert not sitecustomize.should_refuse_replit_backend("live_scraper.py", env)


def test_hetzner_worker_is_allowed_without_replit_markers():
    env = {"SMARTXFLOW_MODE": "server"}
    assert not sitecustomize.should_refuse_replit_backend("alarm_engine.py", env)


def test_path_basename_is_used():
    env = {"REPLIT_DEV_DOMAIN": "preview.example"}
    worker_path = str(Path("/home/runner/workspace/live_scraper.py"))
    assert sitecustomize.should_refuse_replit_backend(worker_path, env)
