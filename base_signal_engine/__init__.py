"""Pure, dependency-free research/base signal rules; no network or database writes.

Checkpoint and runtime integration must live outside this package. All inputs are
frozen, timestamped, provider-verified Moneyway snapshots for one fixture_uid.
"""

from .rules import (
    BASE_CHECKPOINTS,
    EARLY_CORE_CHECKPOINTS,
    EARLY_RETENTION_CHECKPOINTS,
    CheckpointEvaluation,
    EarlyEvaluation,
    Fixture,
    Quote,
    Signal,
    Snapshot,
    choose_base_checkpoint,
    evaluate_base,
    evaluate_early,
    select_snapshot,
)

__all__ = [
    "BASE_CHECKPOINTS", "EARLY_CORE_CHECKPOINTS", "EARLY_RETENTION_CHECKPOINTS",
    "CheckpointEvaluation", "EarlyEvaluation", "Fixture", "Quote", "Signal", "Snapshot",
    "choose_base_checkpoint", "evaluate_base", "evaluate_early", "select_snapshot",
]