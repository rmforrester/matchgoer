import unittest

from database_target import DatabaseTargetError, ExpectedDatabaseTarget, verify_database_target


class Result:
    def __init__(self, rows): self.rows = rows
    def one(self): return self.rows[0]
    def scalars(self): return self
    def all(self): return self.rows
    def __iter__(self): return iter(self.rows)


class Connection:
    def __init__(self, database="matchgoer_test", schema="public", tables=None, columns=None):
        self.database=database; self.schema=schema
        self.tables=tables or ["teams", "venues"]
        self.columns=columns or [("teams", "team_id"), ("venues", "venue_id")]
    def execute(self, statement, params=None):
        sql=" ".join(str(statement).split())
        if "current_database()" in sql: return Result([(self.database,self.schema)])
        if "information_schema.tables" in sql: return Result(self.tables)
        if "information_schema.columns" in sql: return Result(self.columns)
        raise AssertionError(sql)


def expected(**changes):
    values={"database":"matchgoer_test","schema":"public","environment":"disposable-test","required_tables":("teams","venues"),"required_columns":(("teams","team_id"),("venues","venue_id"))}
    values.update(changes); return ExpectedDatabaseTarget(**values)


class DatabaseTargetTests(unittest.TestCase):
    def test_correct_target_passes_without_secrets(self):
        result=verify_database_target(Connection(),expected(),"disposable-test")
        self.assertEqual(result["database"],"matchgoer_test"); self.assertNotIn("url",str(result).lower()); self.assertNotIn("password",str(result).lower())
    def test_wrong_database_fails(self):
        with self.assertRaises(DatabaseTargetError): verify_database_target(Connection(database="wrong"),expected(),"disposable-test")
    def test_wrong_schema_fails(self):
        with self.assertRaises(DatabaseTargetError): verify_database_target(Connection(schema="other"),expected(),"disposable-test")
    def test_missing_table_fails(self):
        with self.assertRaises(DatabaseTargetError): verify_database_target(Connection(tables=["teams"]),expected(),"disposable-test")
    def test_schema_signature_fails(self):
        with self.assertRaises(DatabaseTargetError): verify_database_target(Connection(columns=[("teams","team_id")]),expected(),"disposable-test")
    def test_wrong_or_missing_environment_fails(self):
        for value in (None,"production"):
            with self.assertRaises(DatabaseTargetError): verify_database_target(Connection(),expected(),value)
    def test_missing_expected_target_fails(self):
        with self.assertRaises(DatabaseTargetError): verify_database_target(Connection(),None,"disposable-test")


if __name__ == "__main__": unittest.main()
