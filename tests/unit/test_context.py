from sqlide.sql.context import TableRef, analyze


def ctx(sql: str, dialect: str = "generic"):
    """`|` marks the cursor."""
    offset = sql.index("|")
    return analyze(sql.replace("|", ""), offset, dialect)


def test_after_from_wants_tables():
    c = ctx("select * from us|")
    assert (c.kind, c.prefix) == ("table", "us")


def test_after_join_and_comma_in_from_list():
    assert ctx("select * from a join |").kind == "table"
    assert ctx("select * from a, |").kind == "table"


def test_select_list_wants_columns_and_sees_tables_later_in_statement():
    c = ctx("select | from users u join orders o on o.uid = u.id")
    assert c.kind == "column"
    assert c.tables == [TableRef(("users",), "u"), TableRef(("orders",), "o")]


def test_where_is_column_context():
    assert ctx("select 1 from t where |").kind == "column"
    assert ctx("select 1 from t where a = 1 and b|").prefix == "b"


def test_qualifier_after_dot():
    c = ctx("select u.| from users u")
    assert (c.kind, c.qualifier, c.prefix) == ("qualified", ("u",), "")
    c = ctx("select * from public.us|")
    assert (c.kind, c.qualifier, c.prefix) == ("qualified", ("public",), "us")


def test_two_part_qualifier_and_quoted_parts():
    assert ctx("select a.b.| from a.b").qualifier == ("a", "b")
    assert ctx('select "My T".| from "My T"').qualifier == ("My T",)
    assert ctx("select [x y].| from [x y]", "mssql").qualifier == ("x y",)


def test_aliases_with_and_without_as_and_schema():
    c = ctx("select | from s.users as u, orders o where 1=1")
    assert c.tables == [TableRef(("s", "users"), "u"), TableRef(("orders",), "o")]


def test_keyword_after_table_is_not_alias():
    c = ctx("select | from users where id = 1 order by id")
    assert c.tables == [TableRef(("users",), "")]


def test_update_and_insert_targets():
    assert ctx("update | set a = 1").kind == "table"
    c = ctx("insert into t(a) values (1); select | from other")
    assert c.tables == [TableRef(("other",), "")]  # only the current statement


def test_no_completion_in_strings_and_comments():
    assert ctx("select 'ab|c'") is None
    assert ctx("select 1 -- note |") is None
    assert ctx("select /* x| */ 1") is None


def test_subselect_clause_is_scoped():
    c = ctx("select * from (select 1 from t) x where |")
    assert c.kind == "column"
    c = ctx("select * from t where id in (select | from u)")
    assert c.kind == "column"


def test_at_statement_start():
    c = ctx("sel|")
    assert (c.kind, c.prefix) == ("column", "sel")


def test_unterminated_string_and_comment_at_end_of_text():
    assert ctx("select 'ab|") is None
    assert ctx("select /* ab|") is None
    assert ctx("select 'ab'|").kind == "column"  # right after a closed string is outside it


def test_open_backtick_makes_the_name_so_far_the_prefix():
    c = ctx("select * from `dbt-an|", "databricks")
    assert (c.kind, c.prefix, c.lead, c.replace_len) == ("table", "dbt-an", 1, 7)


def test_open_double_quote_after_a_dot_keeps_the_qualifier():
    c = ctx('select * from main."dbt-an|')
    assert (c.kind, c.qualifier, c.prefix, c.replace_len) == ("qualified", ("main",), "dbt-an", 7)


def test_closed_quote_is_not_an_open_one():
    c = ctx("select * from `dbt-analytics` wh|", "databricks")
    assert (c.prefix, c.lead) == ("wh", 0)


def test_qualifier_with_a_hyphen_even_without_quotes():
    c = ctx("select * from dbt-analytics.|", "databricks")
    assert (c.kind, c.qualifier, c.prefix) == ("qualified", ("dbt-analytics",), "")
    c = ctx("select * from `dbt-analytics`.or|", "databricks")
    assert (c.qualifier, c.prefix) == (("dbt-analytics",), "or")


def test_backtick_table_reference_is_recognised_in_databricks():
    c = ctx("select | from `dbt-analytics`.orders o", "databricks")
    assert c.tables == [TableRef(("dbt-analytics", "orders"), "o")]


def test_doubled_quote_in_a_quoted_name_is_unescaped():
    c = ctx('select | from "we""ird" t')
    assert c.tables == [TableRef(('we"ird',), "t")]
