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

# Identity V2 reader layer must bind before display fallback captures the client
# methods. New/current rows prefer fixture_uid; old history remains readable via
# the legacy hash/physical fallback when UID proof does not exist.
from .fixture_uid_reader_patch import bind_fixture_uid_reader_patch

bind_fixture_uid_reader_patch()

# Current market tables are intentionally prematch-current only. Keep the UI
# useful after kickoff by showing the final prematch history snapshot when a
# visible started/finished fixture no longer has a current-table row.
from .display_history_fallback import bind_display_history_fallback

bind_display_history_fallback()

# Polymarket bettor profiles must never hide a qualifying canonical bet because
# sport classification is missing, uncertain, or non-football. Classification
# remains metadata; visibility is controlled only by the tracked-wallet stake
# contract and canonical lifecycle accounting.
from .polymarket_visibility_patch import bind_polymarket_visibility_patch

bind_polymarket_visibility_patch()

# Large tracked bettors use the durable normalized lifecycle as the canonical
# profile/stats source. Raw fills are revisited only for assets touched since the
# previous successful sync; CLOB resolution repairs stale unknown/open results.
from .polymarket_lifecycle_v4_patch import bind_polymarket_lifecycle_v4_patch

bind_polymarket_lifecycle_v4_patch()

# Interactive bettor profiles must not transfer/render the full durable ledger
# on every click. Keep aggregate stats canonical, fetch open bets separately,
# and bound the visible recent-history window so large profiles stay responsive.
from .polymarket_profile_v41_patch import bind_polymarket_profile_v41_patch

bind_polymarket_profile_v41_patch()

# Gamma Soccer event payloads are large. Bound live match discovery to the
# scraper's actual date window and compact each keyset page before fetching the
# next one so production memory does not scale with all active events.
from .polymarket_match_discovery_patch import bind_polymarket_match_discovery_patch

bind_polymarket_match_discovery_patch()
