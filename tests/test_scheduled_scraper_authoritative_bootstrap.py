from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_scraper_forces_authoritative_identity_before_runtime_import():
    source = (ROOT / "scheduled_scraper.py").read_text(encoding="utf-8")
    flag = 'os.environ["SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE"] = "true"'
    runtime_import = "from scheduled_scraper_legacy import *"

    assert flag in source
    assert runtime_import in source
    assert source.index(flag) < source.index(runtime_import)
    assert "SUPABASE_SERVICE_ROLE_KEY" in source
    assert "raise SystemExit" in source


def test_preserved_runtime_still_uses_betwatch_prematch_and_loop():
    source = (ROOT / "scheduled_scraper_legacy.py").read_text(encoding="utf-8")

    assert "from betwatch_prematch import run_scrape_betwatch as run_scrape" in source
    assert "def run_loop():" in source
    assert "def main():" in source
