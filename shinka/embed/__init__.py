"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'EmbeddingClient': ('.embedding', 'EmbeddingClient'), 'AsyncEmbeddingClient': ('.embedding', 'AsyncEmbeddingClient'), 'count_tokens': ('.embedding', 'count_tokens'), 'estimate_tokens': ('.embedding', 'estimate_tokens'), 'get_client_embed': ('.client', 'get_client_embed'), 'get_async_client_embed': ('.client', 'get_async_client_embed')}
__all__ = ['EmbeddingClient', 'AsyncEmbeddingClient', 'get_client_embed', 'get_async_client_embed', 'count_tokens', 'estimate_tokens']

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
