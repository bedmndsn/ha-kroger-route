"""Shared test helpers.

Component modules live in a Home Assistant package whose __init__
imports Home Assistant, so modules under test are loaded here under a
stub package name instead of importing custom_components directly.
Only pure logic is exercised; no network or HA calls are made.
"""

import importlib.util
import sys
import types
from pathlib import Path

COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "kroger_route"


def load_component_module(name):
    """Load a component module (e.g. 'api', 'const') under a stub package."""
    pkg_name = "kroger_route_stub"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(COMPONENT_DIR)]
        sys.modules[pkg_name] = pkg
    full_name = f"{pkg_name}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, COMPONENT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module
