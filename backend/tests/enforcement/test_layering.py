"""Data plane must not depend on the control plane (architecture.md)."""

import ast
from pathlib import Path

ENFORCEMENT = Path(__file__).resolve().parents[2] / "src" / "precheck" / "enforcement"
FORBIDDEN = ("precheck.authoring", "precheck.api", "precheck.db", "precheck.translator")


def test_enforcement_never_imports_control_plane() -> None:
    offenders = []
    for path in ENFORCEMENT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            offenders += [f"{path.name}: {n}" for n in names if n.startswith(FORBIDDEN)]
    assert offenders == []
