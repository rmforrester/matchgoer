"""Non-secret database target fingerprint for mutation-capable tools."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, text


class DatabaseTargetError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpectedDatabaseTarget:
    database: str
    schema: str
    environment: str
    required_tables: tuple[str, ...]
    required_columns: tuple[tuple[str, str], ...] = ()


def verify_database_target(connection, expected: ExpectedDatabaseTarget | None, actual_environment: str | None) -> dict:
    if expected is None:
        raise DatabaseTargetError("expected database target fingerprint is required")
    if not actual_environment or actual_environment != expected.environment:
        raise DatabaseTargetError("database target environment label mismatch")
    identity = connection.execute(text("SELECT current_database(), current_schema()" )).one()
    if identity[0] != expected.database:
        raise DatabaseTargetError("database target name mismatch")
    if identity[1] != expected.schema:
        raise DatabaseTargetError("database target schema mismatch")
    tables_query = text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema=:schema AND table_name IN :tables
    """).bindparams(bindparam("tables", expanding=True))
    present = set(connection.execute(
        tables_query, {"schema": expected.schema, "tables": list(expected.required_tables)}
    ).scalars())
    missing = set(expected.required_tables) - present
    if missing:
        raise DatabaseTargetError(f"database target required table mismatch: {sorted(missing)}")
    if expected.required_columns:
        columns = connection.execute(text("""
            SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema=:schema
        """), {"schema": expected.schema}).all()
        available = {(row[0], row[1]) for row in columns}
        missing_columns = set(expected.required_columns) - available
        if missing_columns:
            raise DatabaseTargetError(f"database target schema signature mismatch: {sorted(missing_columns)}")
    return {
        "database": identity[0],
        "schema": identity[1],
        "environment": actual_environment,
        "required_tables_present": True,
        "schema_signature_present": True,
    }
