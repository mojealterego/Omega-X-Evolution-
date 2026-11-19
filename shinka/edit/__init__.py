"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'apply_diff_patch': ('.apply_diff', 'apply_diff_patch'), 'redact_immutable': ('.apply_diff', 'redact_immutable'), 'apply_full_patch': ('.apply_full', 'apply_full_patch'), 'validate_evolve_markers': ('.marker_validation', 'validate_evolve_markers'), 'summarize_diff': ('.summary', 'summarize_diff')}
__all__ = ['redact_immutable', 'apply_diff_patch', 'apply_full_patch', 'summarize_diff', 'validate_evolve_markers']

def __getattr__(name):
    try:
        module, attr = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module, __name__), attr)
    globals()[name] = value
    return value

def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
