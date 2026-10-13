import pytest

from tool_worker.sqlcheck import SqlRejected, validate_select

ALLOWED = {"items", "t", "u"}


@pytest.mark.parametrize(
    "sql,dialect,expected",
    [
        ("select * from items", "postgresql", "SELECT * FROM items LIMIT 50"),
        ("select a from t limit 5", "mysql", "SELECT a FROM t LIMIT 5"),
        ("select a from t limit 5000", "postgresql", "SELECT a FROM t LIMIT 50"),
        ("select top 3 a from t", "mssql", "SELECT TOP 3 a FROM t"),
        ("with x as (select a from t) select a from x", "postgresql", "WITH x AS (SELECT a FROM t) SELECT a FROM x LIMIT 50"),
        ("select a from t union select a from u", "sqlite", "SELECT a FROM t UNION SELECT a FROM u"),
        ("SELECT count(*) FROM t WHERE a LIKE '%x%'", "postgresql", "SELECT COUNT(*) FROM t WHERE a LIKE '%x%' LIMIT 50"),
    ],
)
def test_plain_selects_pass_and_get_a_row_limit(sql, dialect, expected):
    assert validate_select(sql, dialect, ALLOWED) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "insert into t values (1)",
        "update t set a = 1",
        "delete from t",
        "drop table t",
        "select 1; select 2",
        "select a from t; drop table t",
        "select * into x from t",
        "select a from t for update",
        "with d as (delete from t returning *) select * from d",
        "copy t to '/tmp/x'",
        "pragma table_info(t)",
        "set role x",
        "select pg_read_file('/etc/passwd')",
        "select load_extension('x')",
        "select xp_cmdshell('dir')",
        "select current_setting('x')",
        "select * from generate_series(1,10)",
        "select * from secret",
        "select * from pg_catalog.pg_tables",
        "",
        "   ",
        "select (",
    ],
)
def test_dangerous_or_unlisted_sql_is_rejected(sql):
    with pytest.raises(SqlRejected):
        validate_select(sql, "postgresql", ALLOWED)


BLOCKED = {"items": {"salary"}}


@pytest.mark.parametrize(
    "sql",
    [
        "select salary from items",
        "select i.salary from items i",
        "select name from items where salary > 1",
        "select * from items",
        "select name from items order by salary",
        "select (select max(salary) from items) as m",
    ],
)
def test_blocked_columns_cannot_be_read_in_any_form(sql):
    with pytest.raises(SqlRejected):
        validate_select(sql, "postgresql", {"items"}, BLOCKED)


def test_other_columns_of_the_same_table_are_fine():
    assert validate_select("select name, email from items", "postgresql", {"items"}, BLOCKED) == (
        "SELECT name, email FROM items LIMIT 50"
    )


def test_all_tables_allowed_when_no_list_is_given():
    assert validate_select("select a from anything", "sqlite") == "SELECT a FROM anything LIMIT 50"


def test_unknown_dialect_is_rejected():
    with pytest.raises(SqlRejected):
        validate_select("select 1", "oracle")


def test_cte_names_are_not_treated_as_unlisted_tables():
    sql = "with recent as (select a from t) select a from recent"
    assert "recent" in validate_select(sql, "postgresql", {"t"})
