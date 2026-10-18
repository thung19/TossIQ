"""Idempotent applier for the tracked DDL in this directory.

Oracle has no CREATE TABLE IF NOT EXISTS, so re-running raw DDL raises rather
than no-op'ing. This applier executes each statement and swallows exactly the
"it already exists" errors, which makes a second run a clean no-op and lets the
same script serve both first-time creation and later re-verification.

Only those specific error codes are tolerated; anything else is re-raised, so a
genuine DDL mistake still fails loudly rather than being silently skipped.

Every schema/*.sql file is discovered and applied in lexical filename order,
rather than one hardcoded file, so a new migration lands by adding a file here
with the next numeric prefix and needs no applier of its own.

Statements in the .sql files are separated by a line containing only "/" --
PL/SQL-style delimiter, since a plain ";" split would break on any future
trigger or block body.

Run from the repository root:
    python schema/apply.py
"""

import os
import sys

import oracledb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402  -- path must be set before this import

SCHEMA_DIR = os.path.dirname(os.path.abspath(__file__))

# ORA-00955: name is already used by an existing object (table, index, constraint)
# ORA-01430: column being added already exists in table
# ORA-02275: such a referential constraint already exists in the table
ALREADY_APPLIED_CODES = {955, 1430, 2275}


def iter_statements(sql_text: str):
    """Yields each statement in a .sql file, split on lines containing only '/'."""
    buffer: list[str] = []
    for line in sql_text.splitlines():
        if line.strip() == "/":
            statement = "\n".join(buffer).strip()
            if statement:
                yield statement
            buffer = []
        else:
            buffer.append(line)
    tail = "\n".join(buffer).strip()
    if tail:
        yield tail


def _first_line(statement: str) -> str:
    """A short label for log output -- the first non-comment line of a statement."""
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return stripped
    return statement.strip().splitlines()[0]


def apply_file(path: str) -> tuple[int, int]:
    """Applies one .sql file. Returns (applied, already_present) statement counts."""
    with open(path) as handle:
        sql_text = handle.read()

    applied = 0
    skipped = 0
    with db.get_connection() as conn, conn.cursor() as cursor:
        for statement in iter_statements(sql_text):
            label = _first_line(statement)
            try:
                cursor.execute(statement)
            except oracledb.DatabaseError as exc:
                (error,) = exc.args
                if error.code in ALREADY_APPLIED_CODES:
                    skipped += 1
                    print(f"  already present: {label}")
                    continue
                print(f"  FAILED: {label}", file=sys.stderr)
                raise
            applied += 1
            print(f"  applied: {label}")
        conn.commit()
    return applied, skipped


def main() -> None:
    files = sorted(f for f in os.listdir(SCHEMA_DIR) if f.endswith(".sql"))
    if not files:
        print(f"No .sql files found in {SCHEMA_DIR}")
        return

    total_applied = 0
    total_skipped = 0
    for name in files:
        print(f"{name}:")
        applied, skipped = apply_file(os.path.join(SCHEMA_DIR, name))
        total_applied += applied
        total_skipped += skipped

    print(f"\n{total_applied} statement(s) applied, {total_skipped} already present.")


if __name__ == "__main__":
    main()
