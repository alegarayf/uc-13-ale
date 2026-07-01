"""Eval store and harness error envelope — spec §5.12.9 / plan §2."""


class EvalError(Exception):
    """Base for eval/retrieval contract violations."""


class StoreError(EvalError):
    """EvalStore contract violation."""


class RunNotFoundError(StoreError):
    """Requested run_id does not exist."""


class RunCompleteError(StoreError):
    """Mutation rejected because run is already complete."""


class IncompleteResultsError(StoreError):
    """finalize_run row count mismatch vs affected_intents."""


class SyncError(StoreError):
    """SQLite → Delta promotion failure."""


class PreconditionError(EvalError):
    """Harness setup precondition failed."""


class BaselineInvalidError(PreconditionError):
    """Baseline reference run is invalid or missing."""


class CoverageError(PreconditionError):
    """Gate-eligible intent coverage check failed."""


class GoldSnapshotMismatchError(PreconditionError):
    """gold_snapshot pin mismatch between runs."""


class RegistryHashMismatchError(PreconditionError):
    """registry_hash pin mismatch between runs."""


class IngestionSnapshotMismatchError(PreconditionError):
    """ingestion_snapshot pin mismatch between runs."""


class ScopeResolutionError(EvalError):
    """IntentScopeResolver could not resolve scope."""


class ScopeMismatchError(ScopeResolutionError):
    """PR scope does not match resolved gate scope."""
