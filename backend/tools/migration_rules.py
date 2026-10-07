"""Checks migrations against ADR-0013's rules (OPS-4), from their source.

`python -m tools.migration_rules migrations/versions` prints each problem and exits 1 if any.
"""

import ast
import re
import sys
from pathlib import Path

_DESTRUCTIVE = frozenset({"drop_table", "drop_column", "rename_table"})
_DESTRUCTIVE_SQL = re.compile(
    r"\bDROP\s+TABLE\b"
    r"|\bALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?\S+\s+"
    r"(?:DROP\s+(?!CONSTRAINT\b)|RENAME\s+(?!CONSTRAINT\b))",
    re.IGNORECASE,
)


def problems(source: str) -> list[str]:
    """What breaks the rules in one migration's source.

    Expand, then contract: a migration may drop or rename a table or column only as the contract
    step, which sets `contract` to what the previous release had already stopped using."""
    module = ast.parse(source)
    upgrade = _function(module, "upgrade")
    found = [] if _contract(module) else _removals(upgrade)
    found += _not_null_additions(upgrade)
    downgrade = _function(module, "downgrade")
    if not _does_nothing(downgrade):
        found.append(
            f"line {downgrade.lineno}: downgrade() must do nothing; a rollback restores the backup"
        )
    return found


def _does_nothing(function: ast.FunctionDef) -> bool:
    """Only a docstring and `pass`."""
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return all(isinstance(statement, ast.Pass) for statement in body)


def _removals(upgrade: ast.FunctionDef) -> list[str]:
    found = []
    for node in ast.walk(upgrade):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        if name in _DESTRUCTIVE or (
            name == "alter_column" and any(k.arg == "new_column_name" for k in node.keywords)
        ):
            found.append(f"line {node.lineno}: {name} removes what the previous release uses")
        elif name == "execute" and any(_DESTRUCTIVE_SQL.search(s) for s in _strings(node)):
            found.append(f"line {node.lineno}: SQL that drops or renames a table or column")
    return found


def _not_null_additions(upgrade: ast.FunctionDef) -> list[str]:
    """Columns added to an existing table as NOT NULL without a server default: the previous
    release's inserts leave them out, and fail."""
    found = []
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_column"
        ):
            continue
        for column in ast.walk(node):
            if _is_column(column) and _not_null(column) and not _keyword(column, "server_default"):
                found.append(
                    f"line {node.lineno}: a NOT NULL column needs a server_default, or the"
                    " previous release's inserts fail"
                )
    return found


def _is_column(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "Column") or (
        isinstance(func, ast.Name) and func.id == "Column"
    )


def _not_null(column: ast.AST) -> bool:
    nullable = _keyword(column, "nullable")
    return isinstance(nullable, ast.Constant) and nullable.value is False


def _keyword(call: ast.AST, name: str) -> ast.expr | None:
    if isinstance(call, ast.Call):
        for keyword in call.keywords:
            if keyword.arg == name:
                return keyword.value
    return None


def _contract(module: ast.Module) -> bool:
    """The module sets `contract` to a reason that is not empty."""
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "contract" for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return bool(node.value.value.strip())
    return False


def _strings(node: ast.AST) -> list[str]:
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"no {name}() function")


def check_directory(directory: Path) -> list[str]:
    """Every migration's problems, each prefixed with its file's name."""
    found = []
    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            found += [f"{path.name}: {problem}" for problem in problems(path.read_text())]
        except (SyntaxError, ValueError) as error:
            found.append(f"{path.name}: {error}")
    return found


def main(arguments: list[str]) -> int:
    found = check_directory(Path(arguments[0]))
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
