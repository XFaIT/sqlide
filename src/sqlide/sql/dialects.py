"""Per-dialect lexing and block rules. Dialect ids match DriverDef.dialect."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockRules:
    """Procedural blocks (BEGIN..END). Only active inside DECLARE/BEGIN/CREATE ROUTINE."""

    openers: frozenset[str] = frozenset()  # statement-level words that open an END-closed block
    inline_openers: frozenset[str] = frozenset()  # same, but valid anywhere (FOR..LOOP)
    routines: frozenset[str] = frozenset()  # CREATE <kind> that enters block context
    expect_begin_for: frozenset[str] = frozenset()  # ';' does not end these until their BEGIN
    slash_only_for: frozenset[str] = frozenset()  # only '/' ends these (oracle packages)
    declare_starts_block: bool = False
    top_begin_block: bool = False  # statement-initial BEGIN is a block, not a transaction
    tx_words: frozenset[str] = frozenset()  # BEGIN <word> is a transaction start
    # CREATE <kind> whose body runs to the end of the batch (GO) unless it is a BEGIN..END block
    batch_scoped: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Rules:
    backslash_escapes: bool = False
    dollar_quotes: bool = False
    nested_comments: bool = False
    backtick: bool = False
    brackets: bool = False  # [ident]
    hash_comment: bool = False
    q_quote: bool = False  # oracle q'[...]'
    e_strings: bool = False  # postgres E'..\n..'
    slash_lines: bool = False  # '/' alone on a line ends a statement
    delimiter_command: bool = False  # mysql client 'DELIMITER x' lines
    go_batches: bool = False  # 'GO' alone on a line ends a batch
    block: BlockRules | None = None


_F = frozenset

RULES: dict[str, Rules] = {
    "generic": Rules(dollar_quotes=True, e_strings=True),
    "postgres": Rules(dollar_quotes=True, nested_comments=True, e_strings=True),
    "clickhouse": Rules(backslash_escapes=True, backtick=True, hash_comment=True),
    "mysql": Rules(
        backslash_escapes=True,
        backtick=True,
        hash_comment=True,
        delimiter_command=True,
        block=BlockRules(
            openers=_F({"IF", "WHILE", "REPEAT"}),
            inline_openers=_F({"LOOP"}),
            routines=_F({"PROCEDURE", "FUNCTION", "TRIGGER", "EVENT"}),
            tx_words=_F({"WORK"}),
        ),
    ),
    "oracle": Rules(
        q_quote=True,
        slash_lines=True,
        block=BlockRules(
            openers=_F({"IF"}),
            inline_openers=_F({"LOOP"}),
            routines=_F({"PROCEDURE", "FUNCTION", "TRIGGER", "PACKAGE", "TYPE"}),
            expect_begin_for=_F({"PROCEDURE", "FUNCTION", "TRIGGER"}),
            slash_only_for=_F({"PACKAGE", "TYPE"}),  # TYPE only when followed by BODY
            declare_starts_block=True,
            top_begin_block=True,
        ),
    ),
    "mssql": Rules(
        brackets=True,
        go_batches=True,
        block=BlockRules(
            routines=_F({"PROCEDURE", "PROC", "FUNCTION", "TRIGGER"}),
            top_begin_block=True,
            tx_words=_F({"TRAN", "TRANSACTION", "DISTRIBUTED"}),
            batch_scoped=_F({"PROCEDURE", "PROC", "FUNCTION", "TRIGGER"}),
        ),
    ),
    "sqlite": Rules(
        backtick=True,
        brackets=True,
        block=BlockRules(
            routines=_F({"TRIGGER"}),
            tx_words=_F({"TRANSACTION", "DEFERRED", "IMMEDIATE", "EXCLUSIVE"}),
        ),
    ),
}


def rules_for(dialect: str) -> Rules:
    return RULES.get(dialect, RULES["generic"])
