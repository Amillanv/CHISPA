"""Tests of the rule that the live paths of the growth forecast and of the growth risk do not
import the evaluation."""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "chispa"
LIVE = ("fronts", "front_inputs", "forecast_model", "forecast_live", "forecast_files", "record")
LIVE += ("config_hash", "risk", "risk_files", "risk_weather", "risk_live")


def imports_of(path: Path) -> set[str]:
    """Return each module and each name that a file imports, as dotted names."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found |= {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def test_the_live_paths_import_no_module_of_the_evaluation():
    for name in LIVE:
        used = {module for module in imports_of(SRC / f"{name}.py") if "evaluation" in module}
        assert not used, (name, sorted(used))


def test_the_live_paths_and_the_record_load_with_the_evaluation_blocked():
    # A module that the live path imports can import the evaluation. Only a real import of the
    # live path, in a new process that cannot import the evaluation, shows that.
    code = "import sys; sys.modules['chispa.evaluation'] = None; "
    code += "import chispa.forecast_live, chispa.record, chispa.risk_live"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-500:]
