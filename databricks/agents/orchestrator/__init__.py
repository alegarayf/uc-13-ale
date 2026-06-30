from .constants import FILL_STATE_RULES, TLDR_REQUIRED_FIELDS
from .confidence import ConfidenceEngine
from .field_mapping import FIELD_MAPPINGS, apply_field_mappings

__all__ = [
    "BundleBuilder",
    "ConfidenceEngine",
    "FIELD_MAPPINGS",
    "apply_field_mappings",
    "FILL_STATE_RULES",
    "TLDR_REQUIRED_FIELDS",
    "GapAggregator",
    "apply_fill_state",
    "merge_risks_from_flags",
]

_LAZY_EXPORTS = frozenset(
    {
        "BundleBuilder",
        "GapAggregator",
        "apply_fill_state",
        "merge_risks_from_flags",
    }
)


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        from . import bundle_builder as _module

        return getattr(_module, name)
    import importlib

    try:
        return importlib.import_module(f".{name}", __package__)
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
