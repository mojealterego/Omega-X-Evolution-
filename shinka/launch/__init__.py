"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'JobScheduler': ('.scheduler', 'JobScheduler'), 'JobConfig': ('.scheduler', 'JobConfig'), 'LocalJobConfig': ('.scheduler', 'LocalJobConfig'), 'SlurmDockerJobConfig': ('.scheduler', 'SlurmDockerJobConfig'), 'SlurmCondaJobConfig': ('.scheduler', 'SlurmCondaJobConfig'), 'SlurmEnvJobConfig': ('.scheduler', 'SlurmEnvJobConfig'), 'ProcessWithLogging': ('.local', 'ProcessWithLogging')}
__all__ = ['JobScheduler', 'JobConfig', 'LocalJobConfig', 'SlurmDockerJobConfig', 'SlurmCondaJobConfig', 'SlurmEnvJobConfig', 'ProcessWithLogging']

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
