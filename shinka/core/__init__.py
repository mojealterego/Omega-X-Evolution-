"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'EvolutionConfig': ('.config', 'EvolutionConfig'), 'ShinkaEvolveRunner': ('.async_runner', 'ShinkaEvolveRunner'), 'PromptSampler': ('.sampler', 'PromptSampler'), 'MetaSummarizer': ('.summarizer', 'MetaSummarizer'), 'NoveltyJudge': ('.novelty_judge', 'NoveltyJudge'), 'AsyncNoveltyJudge': ('.async_novelty_judge', 'AsyncNoveltyJudge'), 'run_shinka_eval': ('.wrap_eval', 'run_shinka_eval'), 'SystemPromptEvolver': ('.prompt_evolver', 'SystemPromptEvolver'), 'SystemPromptSampler': ('.prompt_evolver', 'SystemPromptSampler'), 'AsyncSystemPromptEvolver': ('.prompt_evolver', 'AsyncSystemPromptEvolver')}
__all__ = ['PromptSampler', 'MetaSummarizer', 'NoveltyJudge', 'AsyncNoveltyJudge', 'ShinkaEvolveRunner', 'EvolutionConfig', 'run_shinka_eval', 'SystemPromptEvolver', 'SystemPromptSampler', 'AsyncSystemPromptEvolver']

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
