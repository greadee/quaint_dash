from pathlib import Path

from tools.check_architecture_boundaries import BoundaryRule, collect_violations


def test_current_architecture_boundaries_are_clean() -> None:
    violations = collect_violations(Path.cwd())
    assert violations == []


def test_python_boundary_rule_detects_forbidden_import(tmp_path: Path) -> None:
    root = tmp_path
    module_dir = root / "src" / "dashboard" / "analytics"
    module_dir.mkdir(parents=True)
    (module_dir / "bad.py").write_text("from fastapi import APIRouter\n", encoding="utf-8")

    violations = collect_violations(root)

    assert len(violations) == 1
    assert violations[0].rule == "python-core-no-web-framework"
    assert violations[0].imported == "fastapi"


def test_web_boundary_rule_detects_backend_import(tmp_path: Path) -> None:
    root = tmp_path
    route_dir = root / "web" / "src" / "routes"
    route_dir.mkdir(parents=True)
    (route_dir / "bad.ts").write_text(
        'import { value } from "dashboard.db";\n',
        encoding="utf-8",
    )

    violations = collect_violations(root)

    assert len(violations) == 1
    assert violations[0].rule == "web-no-python-internals"
    assert violations[0].imported == "dashboard.db"


def test_rule_dataclass_documents_reason() -> None:
    rule = BoundaryRule(
        name="example",
        paths=("src",),
        extensions=(".py",),
        forbidden_imports=("fastapi",),
        reason="domain must not know HTTP",
    )

    assert rule.reason == "domain must not know HTTP"

