"""Flags destructive operations in Alembic migrations before they ship.

    python scripts/check_migrations.py alembic/versions/0033_*.py ...
    python scripts/check_migrations.py --since origin/main   # files changed vs a git ref

A deploy runs migrations while the previous release is still serving, and
a rollback (deploy/deploy.sh) only swaps the app images back - it never
downgrades the database. So upgrade() must stay compatible with the code
before it: add, don't drop or rename. Dropping a column/table, renaming,
changing a type, making a column NOT NULL, or raw DELETE/DROP/TRUNCATE is
flagged; do it in a later release once nothing reads it, and mark the line
(or the file) with a reviewed reason:

    op.drop_column("users", "legacy_flag")  # migration-safe: unused since 0029

Also checks there is exactly one head. Exit status 1 when anything is flagged.
"""

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
MARK = "migration-safe:"
CALLS = {
    "drop_table": "drops a table",
    "drop_column": "drops a column",
    "rename_table": "renames a table",
    "drop_index": None,  # harmless for old code
    "drop_constraint": None,
}
RAW_SQL = re.compile(r"\b(DROP\s+(TABLE|COLUMN)|TRUNCATE|DELETE\s+FROM|ALTER\s+TABLE\s+\w+\s+RENAME)\b", re.I)


def _problems(path: Path) -> list[str]:
    source = path.read_text()
    if MARK in "".join(source.splitlines()[:15]):  # whole file reviewed (in the docstring/header)
        return []
    lines = source.splitlines()
    tree = ast.parse(source)
    upgrade = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None)
    if upgrade is None:
        return []
    found = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name, line = node.func.attr, node.lineno
        text = " ".join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
        if MARK in text:
            continue
        reason = CALLS.get(name)
        if name == "alter_column":
            kw = {k.arg: k.value for k in node.keywords}
            if "new_column_name" in kw:
                reason = "renames a column"
            elif "type_" in kw:
                reason = "changes a column type"
            elif isinstance(kw.get("nullable"), ast.Constant) and kw["nullable"].value is False:
                reason = "makes a column NOT NULL (old code may still insert without it)"
        elif name == "execute" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            if RAW_SQL.search(node.args[0].value):
                reason = "runs destructive SQL"
        if reason:
            found.append(f"{path.name}:{line}: {reason} - `{text.strip()[:100]}`")
    return found


def _changed_since(ref: str) -> list[Path]:
    out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", ref, "--", str(VERSIONS)],
                         capture_output=True, text=True, check=True).stdout
    root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
    return [root / p for p in out.split() if p.endswith(".py")]


def _heads() -> set[str]:
    revisions, downs = set(), set()
    for f in VERSIONS.glob("*.py"):
        s = f.read_text()
        if m := re.search(r'^revision(?:: str)? = "([^"]+)"', s, re.M):
            revisions.add(m.group(1))
        if m := re.search(r'^down_revision(?:: [^=]+)? = "([^"]+)"', s, re.M):
            downs.add(m.group(1))
    return revisions - downs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--since", help="check migrations added or changed since this git ref")
    args = parser.parse_args()
    files = args.files or (_changed_since(args.since) if args.since else sorted(VERSIONS.glob("*.py")))
    problems = [p for f in files for p in _problems(f)]
    heads = _heads()
    if len(heads) != 1:
        problems.append(f"expected one migration head, found {sorted(heads)} - merge them")
    for p in problems:
        print(f"::error::{p}" if "GITHUB_ACTIONS" in __import__("os").environ else p)
    print(f"checked {len(files)} migration file(s): {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
