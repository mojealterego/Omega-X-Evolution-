"""Backward-compatible import of the canonical OMEGA-X workers module."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("omega_x_evolution.workers")
