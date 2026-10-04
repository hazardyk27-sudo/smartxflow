"""SmartXFlow Services.

Bind the legacy Supabase client's fixture identity methods to the repository
canonical helpers so all API fixture consumers use one normalization contract.
"""

from core.hash_utils import make_fixture_identity_key, make_match_id_hash, normalize_field


def _bind_supabase_fixture_identity() -> None:
    from . import supabase_client as _supabase_client

    def _fixture_norm(value):
        return normalize_field(value)

    def _fixture_canonical_hash(cls, fixture):
        return make_match_id_hash(
            fixture.get("home_team", ""),
            fixture.get("away_team", ""),
            fixture.get("league", ""),
            fixture.get("kickoff_utc", ""),
        )

    def _fixture_identity_key(cls, fixture):
        return make_fixture_identity_key(
            fixture.get("home_team", ""),
            fixture.get("away_team", ""),
            fixture.get("league", ""),
            fixture.get("kickoff_utc", ""),
        )

    _supabase_client.SupabaseClient._fixture_norm = staticmethod(_fixture_norm)
    _supabase_client.SupabaseClient._fixture_canonical_hash = classmethod(_fixture_canonical_hash)
    _supabase_client.SupabaseClient._fixture_identity_key = classmethod(_fixture_identity_key)


_bind_supabase_fixture_identity()
