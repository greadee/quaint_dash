"""Check lightweight architecture import boundaries.

This is intentionally narrow. It enforces only rules that are already true or
intended to be true during Phase 1.5, so the check can run in CI without forcing
a broad refactor.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BoundaryRule:
    name: str
    paths: tuple[str, ...]
    extensions: tuple[str, ...]
    forbidden_imports: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Violation:
    rule: str
    path: Path
    line: int
    imported: str
    reason: str

    def format(self, root: Path) -> str:
        rel_path = self.path.relative_to(root)
        return f"{self.rule}: {rel_path}:{self.line} imports {self.imported} ({self.reason})"


RULES: tuple[BoundaryRule, ...] = (
    BoundaryRule(
        name="python-core-no-web-framework",
        paths=(
            "src/dashboard/analytics",
            "src/dashboard/brokers",
            "src/dashboard/ingestion",
            "src/dashboard/ingestion_sentiment",
            "src/dashboard/news",
            "src/dashboard/services/business_strength",
        ),
        extensions=(".py",),
        forbidden_imports=("fastapi", "starlette", "uvicorn", "react", "web"),
        reason="core/domain/service code must not depend on UI or HTTP framework packages",
    ),
    BoundaryRule(
        name="python-application-no-framework-or-driver",
        paths=("src/dashboard/application",),
        extensions=(".py",),
        forbidden_imports=("fastapi", "starlette", "uvicorn", "react", "web", "duckdb"),
        reason="application use cases must depend on interfaces and domain contracts, not adapters",
    ),
    BoundaryRule(
        name="api-no-web-ui",
        paths=("src/dashboard/api",),
        extensions=(".py",),
        forbidden_imports=("react", "web", "web.src"),
        reason="API adapters must not import browser UI modules",
    ),
    BoundaryRule(
        name="web-no-python-internals",
        paths=("web/src",),
        extensions=(".ts", ".tsx", ".js", ".jsx"),
        forbidden_imports=("dashboard", "src/dashboard", "duckdb", "fastapi"),
        reason="web UI must consume backend capabilities through HTTP/API client contracts",
    ),
)


TS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:type\s+)?(?:[^'"]+\s+from\s+)?|export\s+[^'"]+\s+from\s+|import\()\s*['"]([^'"]+)['"]"""
)


def _iter_rule_files(root: Path, rule: BoundaryRule) -> Iterable[Path]:
    for rel_dir in rule.paths:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in rule.extensions:
                yield path


def _python_imports(path: Path) -> Iterable[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        yield exc.lineno or 1, "<syntax-error>"
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.lineno, node.module


def _typescript_imports(path: Path) -> Iterable[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    line_offsets = [0]
    for match in re.finditer(r"\n", text):
        line_offsets.append(match.end())
    for match in TS_IMPORT_RE.finditer(text):
        line = 1
        for offset in line_offsets:
            if offset > match.start():
                break
            line += 1
        yield max(1, line - 1), match.group(1)


def _imports_for(path: Path) -> Iterable[tuple[int, str]]:
    if path.suffix == ".py":
        return _python_imports(path)
    return _typescript_imports(path)


def _matches_forbidden(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(f"{forbidden}.")


def collect_violations(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    for rule in RULES:
        for path in _iter_rule_files(root, rule):
            for line, imported in _imports_for(path):
                for forbidden in rule.forbidden_imports:
                    if _matches_forbidden(imported, forbidden):
                        violations.append(
                            Violation(
                                rule=rule.name,
                                path=path,
                                line=line,
                                imported=imported,
                                reason=rule.reason,
                            )
                        )
    return violations


def main() -> int:
    violations = collect_violations(ROOT)
    if violations:
        print("Architecture boundary violations found:")
        for violation in violations:
            print(f"- {violation.format(ROOT)}")
        return 1
    print("Architecture boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
