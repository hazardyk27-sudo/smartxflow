#!/usr/bin/env python3
"""Apply the fixture identity de-duplication patch to SupabaseClient once."""

from pathlib import Path


PATH = Path("services/supabase_client.py")
text = PATH.read_text(encoding="utf-8")

if "def _dedupe_fixtures(" in text:
    print("fixture dedupe patch already applied")
    raise SystemExit(0)


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, got {count}")
    text = text.replace(old, new, 1)


one(
    "import json\n\n\nclass SupabaseClient:",
    "import json\nimport hashlib\nimport re\n\n\nclass SupabaseClient:",
    "imports",
)

one(
    '''    def _rest_url(self, table: str) -> str:\n        return f"{self.url}/rest/v1/{table}"\n    \n    def get_or_create_match''',
    '''    def _rest_url(self, table: str) -> str:\n        return f"{self.url}/rest/v1/{table}"\n\n    @staticmethod\n    def _fixture_norm(value: Any) -> str:\n        return re.sub(r"\\s+", " ", str(value or "").strip().lower())\n\n    @classmethod\n    def _fixture_canonical_hash(cls, fixture: Dict[str, Any]) -> str:\n        canonical = "|".join((\n            cls._fixture_norm(fixture.get("league")),\n            cls._fixture_norm(fixture.get("home_team")),\n            cls._fixture_norm(fixture.get("away_team")),\n        ))\n        return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:12]\n\n    @classmethod\n    def _fixture_identity_key(cls, fixture: Dict[str, Any]):\n        home = cls._fixture_norm(fixture.get("home_team"))\n        away = cls._fixture_norm(fixture.get("away_team"))\n        raw_kickoff = str(fixture.get("kickoff_utc") or "").strip()\n        if not home or not away or not raw_kickoff:\n            return None\n        try:\n            kickoff = datetime.fromisoformat(raw_kickoff.replace("Z", "+00:00"))\n            kickoff_key = kickoff.replace(second=0, microsecond=0).isoformat()\n        except Exception:\n            kickoff_key = raw_kickoff[:16]\n        return home, away, kickoff_key\n\n    @classmethod\n    def _dedupe_fixtures(cls, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:\n        \"\"\"Collapse legacy fixture hashes for the same teams/kickoff.\n\n        Prefer the hash produced by the current Betwatch algorithm.  If neither\n        row matches it, keep the lexicographically smaller hash so selection is\n        deterministic without mutating stored history.\n        \"\"\"\n        selected: List[Dict[str, Any]] = []\n        positions = {}\n        removed = 0\n        for fixture in fixtures or []:\n            key = cls._fixture_identity_key(fixture)\n            if key is None:\n                selected.append(fixture)\n                continue\n            existing_pos = positions.get(key)\n            if existing_pos is None:\n                positions[key] = len(selected)\n                selected.append(fixture)\n                continue\n\n            existing = selected[existing_pos]\n            existing_hash = str(existing.get("match_id_hash") or "")\n            incoming_hash = str(fixture.get("match_id_hash") or "")\n            existing_is_current = bool(existing_hash) and existing_hash == cls._fixture_canonical_hash(existing)\n            incoming_is_current = bool(incoming_hash) and incoming_hash == cls._fixture_canonical_hash(fixture)\n\n            replace = False\n            if incoming_is_current and not existing_is_current:\n                replace = True\n            elif incoming_is_current == existing_is_current:\n                if incoming_hash and (not existing_hash or incoming_hash < existing_hash):\n                    replace = True\n            if replace:\n                selected[existing_pos] = fixture\n            removed += 1\n\n        if removed:\n            print(f"[Supabase] Fixture identity dedupe: {len(fixtures)} -> {len(selected)} ({removed} legacy duplicate hidden)")\n        return selected\n    \n    def get_or_create_match''',
    "fixture helper methods",
)

# All date-scoped fixture reads should collapse stale legacy hashes before use.
count = text.count("                fixtures = fix_resp.json()\n")
if count != 3:
    raise SystemExit(f"date-scoped fixtures: expected 3 occurrences, got {count}")
text = text.replace(
    "                fixtures = fix_resp.json()\n",
    "                fixtures = self._dedupe_fixtures(fix_resp.json())\n",
)

one(
    "                fixtures_list = fix_resp.json() if fix_resp.status_code == 200 else []\n",
    "                fixtures_list = self._dedupe_fixtures(fix_resp.json()) if fix_resp.status_code == 200 else []\n",
    "all-mode fixtures",
)

one(
    '''            if fix_resp.status_code == 200:\n                fixtures_list = fix_resp.json()\n                for fix in fixtures_list:\n''',
    '''            if fix_resp.status_code == 200:\n                fixtures_list = self._dedupe_fixtures(fix_resp.json())\n                for fix in fixtures_list:\n''',
    "paginated fixtures",
)

PATH.write_text(text, encoding="utf-8")
print("fixture integrity patch applied")
