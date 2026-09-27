"""Dify 「仿真」workflow translated to LangChain / LangGraph.

Public API::

    from jwave_flow import Settings, SimulationWorkflow, run_workflow
"""
from __future__ import annotations

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "Settings",
    "SimulationWorkflow",
    "run_workflow",
    "ExecutionResult",
    "get_executor",
    "build_retriever",
]


def __getattr__(name):  # lazy: keep `import jwave_flow` cheap
    if name == "Settings":
        from .config import Settings

        return Settings
    if name in ("SimulationWorkflow", "run_workflow"):
        from .graph import SimulationWorkflow, run_workflow

        return {"SimulationWorkflow": SimulationWorkflow, "run_workflow": run_workflow}[name]
    if name in ("ExecutionResult", "get_executor"):
        from .executor import ExecutionResult, get_executor

        return {"ExecutionResult": ExecutionResult, "get_executor": get_executor}[name]
    if name == "build_retriever":
        from .knowledge import build_retriever

        return build_retriever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
