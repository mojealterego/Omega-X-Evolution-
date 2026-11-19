"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'ProgramDatabase': ('.dbase', 'ProgramDatabase'), 'Program': ('.dbase', 'Program'), 'DatabaseConfig': ('.dbase', 'DatabaseConfig'), 'AsyncProgramDatabase': ('.async_dbase', 'AsyncProgramDatabase'), 'SystemPromptDatabase': ('.prompt_dbase', 'SystemPromptDatabase'), 'SystemPrompt': ('.prompt_dbase', 'SystemPrompt'), 'SystemPromptConfig': ('.prompt_dbase', 'SystemPromptConfig'), 'create_system_prompt': ('.prompt_dbase', 'create_system_prompt')}
__all__ = ['ProgramDatabase', 'Program', 'DatabaseConfig', 'AsyncProgramDatabase', 'SystemPromptDatabase', 'SystemPrompt', 'SystemPromptConfig', 'create_system_prompt']

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
