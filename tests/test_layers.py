"""A test of the rule that the live path of the growth forecast does not import the evaluation."""

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "chispa"
LIVE = ("fronts", "front_inputs", "forecast_model", "forecast_live", "forecast_files", "record")
# `evaluation/report.py` gives the hash of the configuration. It reads no answer.
PERMITTED = {"chispa.evaluation.report", "chispa.evaluation.report.config_hash"}


def imports_of(path: Path) -> set[str]:
    """Return each module and each name that a file imports, as dotted names."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found |= {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def test_the_live_forecast_imports_no_module_of_the_evaluation():
    for name in LIVE:
        used = {module for module in imports_of(SRC / f"{name}.py") if "evaluation" in module}
        assert used <= PERMITTED, (name, sorted(used - PERMITTED))
