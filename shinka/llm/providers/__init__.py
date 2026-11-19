"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'query_anthropic': ('.anthropic', 'query_anthropic'), 'query_anthropic_async': ('.anthropic', 'query_anthropic_async'), 'query_openai': ('.openai', 'query_openai'), 'query_openai_async': ('.openai', 'query_openai_async'), 'query_deepseek': ('.deepseek', 'query_deepseek'), 'query_deepseek_async': ('.deepseek', 'query_deepseek_async'), 'query_gemini': ('.gemini', 'query_gemini'), 'query_gemini_async': ('.gemini', 'query_gemini_async'), 'query_headless': ('.headless', 'query_headless'), 'query_headless_async': ('.headless', 'query_headless_async'), 'query_local_openai': ('.local_openai', 'query_local_openai'), 'query_local_openai_async': ('.local_openai', 'query_local_openai_async'), 'QueryResult': ('.result', 'QueryResult')}
__all__ = ['query_anthropic', 'query_openai', 'query_deepseek', 'query_gemini', 'query_headless', 'query_local_openai', 'query_anthropic_async', 'query_openai_async', 'query_deepseek_async', 'query_gemini_async', 'query_headless_async', 'query_local_openai_async', 'QueryResult']

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
