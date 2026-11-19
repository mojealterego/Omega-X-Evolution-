"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'LLMClient': ('.llm', 'LLMClient'), 'AsyncLLMClient': ('.llm', 'AsyncLLMClient'), 'extract_between': ('.text', 'extract_between'), 'QueryResult': ('.providers', 'QueryResult'), 'BanditBase': ('.prioritization', 'BanditBase'), 'AsymmetricUCB': ('.prioritization', 'AsymmetricUCB'), 'FixedSampler': ('.prioritization', 'FixedSampler'), 'ThompsonSampler': ('.prioritization', 'ThompsonSampler'), 'EmbeddingClient': ('shinka.embed', 'EmbeddingClient'), 'AsyncEmbeddingClient': ('shinka.embed', 'AsyncEmbeddingClient')}
__all__ = ['LLMClient', 'AsyncLLMClient', 'extract_between', 'QueryResult', 'EmbeddingClient', 'AsyncEmbeddingClient', 'BanditBase', 'AsymmetricUCB', 'FixedSampler', 'ThompsonSampler']

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
