"""Package dependency rules (architecture.md): every import in a package's source must stay
inside what that package is allowed to use. Adapters and the lab reach the server over HTTP,
never by import."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    # directory: (its namespace portion, the precheck portions it may import)
    "core": ("precheck.core", set()),
    "translator": ("precheck.translator", {"precheck.core"}),
    "server": ("precheck.server", {"precheck.core", "precheck.translator"}),
    "mcp-proxy": ("precheck.mcp_proxy", {"precheck.core"}),
    "lab": ("precheck.lab", {"precheck.core"}),
}


def imported_modules(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def violations(package_dir: Path, own: str, allowed: set[str]) -> list[str]:
    out = []
    for path in sorted(package_dir.rglob("*.py")):
        for name in imported_modules(path):
            if name == "precheck" or name.startswith("precheck."):
                portion = ".".join(name.split(".")[:2])
                if portion != own and portion not in allowed:
                    out.append(f"{path.relative_to(package_dir)}: imports {name}")
    return out


@pytest.mark.parametrize("pkg", PACKAGES)
def test_package_imports_follow_the_dependency_rules(pkg: str) -> None:
    own, allowed = PACKAGES[pkg]
    assert violations(ROOT / "packages" / pkg / "src", own, allowed) == []


def test_every_package_is_covered() -> None:
    assert {p.name for p in (ROOT / "packages").iterdir() if p.is_dir()} == set(PACKAGES)


def test_detects_a_forbidden_import(tmp_path: Path) -> None:
    bad = tmp_path / "precheck" / "core" / "leak.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("from precheck.server.db import models\n")
    assert violations(tmp_path, "precheck.core", set()) == [
        "precheck/core/leak.py: imports precheck.server.db"
    ]
