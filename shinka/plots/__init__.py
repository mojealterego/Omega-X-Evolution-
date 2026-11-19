"""Public package exports, loaded on first access."""
from importlib import import_module

_EXPORTS = {'plot_lineage_tree': ('.plot_lineage_tree', 'plot_lineage_tree'), 'plot_evals_performance': ('.plot_evals', 'plot_evals_performance'), 'plot_evals_performance_compare': ('.plot_evals', 'plot_evals_performance_compare'), 'plot_pareto_curve': ('.plot_pareto', 'plot_pareto_curve'), 'plot_pareto_compare': ('.plot_pareto', 'plot_pareto_compare'), 'plot_embed_similarity': ('.plot_similarity', 'plot_embed_similarity'), 'plot_costs': ('.plot_costs', 'plot_costs'), 'plot_cost_performance': ('.plot_costs', 'plot_cost_performance'), 'plot_cost_performance_compare': ('.plot_costs', 'plot_cost_performance_compare'), 'plot_time_performance': ('.plot_time', 'plot_time_performance'), 'plot_time_performance_compare': ('.plot_time', 'plot_time_performance_compare'), 'plot_time_throughput_compare': ('.plot_time', 'plot_time_throughput_compare'), 'plot_cumulative_llm_calls': ('.plot_llm', 'plot_cumulative_llm_calls'), 'plot_generation_runtime_timeline': ('.plot_throughput', 'plot_generation_runtime_timeline'), 'plot_normalized_occupancy_over_time': ('.plot_throughput', 'plot_normalized_occupancy_over_time')}
__all__ = ['plot_lineage_tree', 'plot_evals_performance', 'plot_evals_performance_compare', 'plot_pareto_curve', 'plot_pareto_compare', 'plot_embed_similarity', 'plot_costs', 'plot_cost_performance', 'plot_cost_performance_compare', 'plot_time_performance', 'plot_time_performance_compare', 'plot_time_throughput_compare', 'plot_cumulative_llm_calls', 'plot_generation_runtime_timeline', 'plot_normalized_occupancy_over_time']

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
