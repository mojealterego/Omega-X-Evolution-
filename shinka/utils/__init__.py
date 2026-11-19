"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'load_programs_to_df': ('.load_df', 'load_programs_to_df'), 'get_path_to_best_node': ('.load_df', 'get_path_to_best_node'), 'store_best_path': ('.load_df', 'store_best_path'), 'load_prompts_to_df': ('.load_df', 'load_prompts_to_df'), 'parse_time_to_seconds': ('.general', 'parse_time_to_seconds'), 'load_results': ('.general', 'load_results'), 'load_configs_from_yaml': ('.general', 'load_configs_from_yaml'), 'truncate_log_tail': ('.general', 'truncate_log_tail'), 'build_cfgs_from_python': ('.utils_hydra', 'build_cfgs_from_python'), 'add_evolve_markers': ('.utils_hydra', 'add_evolve_markers'), 'chdir_to_function_dir': ('.utils_hydra', 'chdir_to_function_dir'), 'wrap_object': ('.utils_hydra', 'wrap_object'), 'load_hydra_config': ('.utils_hydra', 'load_hydra_config'), 'get_language_extension': ('.languages', 'get_language_extension')}
__all__ = ['load_programs_to_df', 'get_path_to_best_node', 'store_best_path', 'parse_time_to_seconds', 'load_results', 'build_cfgs_from_python', 'add_evolve_markers', 'chdir_to_function_dir', 'wrap_object', 'load_hydra_config', 'load_configs_from_yaml', 'truncate_log_tail', 'get_language_extension', 'load_prompts_to_df']

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
