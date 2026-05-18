"""SQL tool — parameterized queries against a SQLite placeholder database.

The database is seeded in-memory with fake fintech data:
  funds, positions, trades, nav_history, limit_rules

Only SELECT statements are permitted. In a real deployment swap
get_db() for a connection to your actual data warehouse.
"""
import json
import aiosqlite
from typing import Any
from langchain_core.tools import tool

from src.gateway.sanitizer import InputSanitizer
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton — kept alive for the process lifetime
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Return (and lazily create) the singleton SQLite connection."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(":memory:")
        _db.row_factory = aiosqlite.Row
        await _seed(_db)
        logger.info("placeholder_db_ready")
    return _db


async def _seed(conn: aiosqlite.Connection) -> None:
    """Create tables and populate with realistic fake fintech data."""
    await conn.executescript("""
        CREATE TABLE funds (
            fund_id     TEXT PRIMARY KEY,
            fund_name   TEXT,
            fund_type   TEXT,
            aum_usd     REAL,
            currency    TEXT,
            manager     TEXT
        );
        INSERT INTO funds VALUES
            ('F001', 'Alpha Growth Fund',   'Equity',       250000000.0, 'USD', 'Jane Smith'),
            ('F002', 'Beta Income Fund',    'Fixed Income', 180000000.0, 'USD', 'John Chen'),
            ('F003', 'Gamma Balanced Fund', 'Multi-Asset',  320000000.0, 'USD', 'Sarah Lee');

        CREATE TABLE positions (
            position_id     TEXT PRIMARY KEY,
            fund_id         TEXT,
            asset_name      TEXT,
            asset_type      TEXT,
            quantity        REAL,
            price_usd       REAL,
            market_value_usd REAL,
            weight_pct      REAL,
            as_of_date      TEXT
        );
        INSERT INTO positions VALUES
            ('P001','F001','Apple Inc',                 'Equity',    10000, 185.50, 1855000.0,  7.42, '2025-05-17'),
            ('P002','F001','Microsoft Corp',            'Equity',     8000, 415.20, 3321600.0, 13.29, '2025-05-17'),
            ('P003','F001','Amazon.com Inc',            'Equity',     5000, 185.90,  929500.0,  3.72, '2025-05-17'),
            ('P004','F001','Nvidia Corp',               'Equity',     3000, 950.00, 2850000.0, 11.40, '2025-05-17'),
            ('P005','F002','US Treasury 4.5pct 2027',  'Bond',    500000,  98.50,  492500.0,  2.74, '2025-05-17'),
            ('P006','F002','Corp Bond AAA 5pct 2026',  'Bond',    300000, 101.20,  303600.0,  1.69, '2025-05-17'),
            ('P007','F003','Gold ETF',                  'Commodity', 20000, 185.00, 3700000.0, 11.56, '2025-05-17'),
            ('P008','F003','S&P 500 ETF',               'Equity',   15000, 520.00, 7800000.0, 24.38, '2025-05-17'),
            ('P009','F003','Emerging Mkt Bond ETF',    'Bond',     10000,  95.00,  950000.0,  2.97, '2025-05-17');

        CREATE TABLE trades (
            trade_id    TEXT PRIMARY KEY,
            fund_id     TEXT,
            asset_name  TEXT,
            trade_type  TEXT,
            quantity    REAL,
            price_usd   REAL,
            trade_date  TEXT,
            status      TEXT
        );
        INSERT INTO trades VALUES
            ('T001','F001','Apple Inc',               'BUY',  1000, 183.20,'2025-05-15','SETTLED'),
            ('T002','F001','Tesla Inc',               'SELL',  500, 175.40,'2025-05-16','SETTLED'),
            ('T003','F002','US Treasury 4.5pct 2027','BUY', 100000, 98.30,'2025-05-14','SETTLED'),
            ('T004','F003','Gold ETF',                'BUY',  2000, 184.50,'2025-05-17','PENDING'),
            ('T005','F001','Nvidia Corp',             'BUY',  3000, 945.00,'2025-05-17','SETTLED');

        CREATE TABLE nav_history (
            nav_id       TEXT PRIMARY KEY,
            fund_id      TEXT,
            nav_per_unit REAL,
            total_nav_usd REAL,
            as_of_date   TEXT
        );
        INSERT INTO nav_history VALUES
            ('N001','F001', 125.40, 250800000.0,'2025-05-17'),
            ('N002','F001', 124.80, 249600000.0,'2025-05-16'),
            ('N003','F001', 123.90, 247800000.0,'2025-05-15'),
            ('N004','F002', 102.30, 180054000.0,'2025-05-17'),
            ('N005','F002', 102.10, 179694000.0,'2025-05-16'),
            ('N006','F003', 145.20, 319440000.0,'2025-05-17'),
            ('N007','F003', 144.80, 318560000.0,'2025-05-16');

        CREATE TABLE limit_rules (
            rule_id       TEXT PRIMARY KEY,
            fund_id       TEXT,
            rule_name     TEXT,
            rule_type     TEXT,
            limit_value   REAL,
            current_value REAL,
            breached      INTEGER,
            as_of_date    TEXT
        );
        INSERT INTO limit_rules VALUES
            ('R001','F001','Single Stock Concentration','MAX_WEIGHT_PCT', 15.0, 13.29, 0,'2025-05-17'),
            ('R002','F001','Cash Minimum',              'MIN_CASH_PCT',   2.0,   1.50, 1,'2025-05-17'),
            ('R003','F002','Duration Limit',            'MAX_DURATION',   5.0,   4.20, 0,'2025-05-17'),
            ('R004','F003','Equity Exposure',           'MAX_EQUITY_PCT',60.0,  65.50, 1,'2025-05-17'),
            ('R005','F003','Commodity Exposure',        'MAX_COMMODITY_PCT',15.0,11.56,0,'2025-05-17');
    """)
    await conn.commit()


# ---------------------------------------------------------------------------
# LangChain tool
# ---------------------------------------------------------------------------

@tool
async def sql_query(query: str) -> str:
    """Run a SELECT query against the fintech database and return results as JSON.

    Available tables:
      - funds(fund_id, fund_name, fund_type, aum_usd, currency, manager)
      - positions(position_id, fund_id, asset_name, asset_type, quantity,
                  price_usd, market_value_usd, weight_pct, as_of_date)
      - trades(trade_id, fund_id, asset_name, trade_type, quantity,
               price_usd, trade_date, status)
      - nav_history(nav_id, fund_id, nav_per_unit, total_nav_usd, as_of_date)
      - limit_rules(rule_id, fund_id, rule_name, rule_type,
                    limit_value, current_value, breached, as_of_date)

    Only SELECT statements are allowed. Use fund_id values F001, F002, F003.
    """
    return await execute_query(query)


async def execute_query(query: str) -> str:
    """Execute a query and return JSON-encoded results. Callable directly in tests."""
    query = query.strip()

    # Block anything that isn't a SELECT
    if not query.upper().startswith("SELECT"):
        logger.warning("non_select_query_blocked", query_preview=query[:80])
        return json.dumps({"error": "Only SELECT queries are permitted."})

    # Block the most dangerous SQL constructs even inside a SELECT
    is_safe, threats = InputSanitizer.validate_sql_param(query)
    if not is_safe:
        logger.warning("sql_injection_attempt_blocked", threats=threats)
        return json.dumps({"error": f"Query blocked: {', '.join(threats)}"})

    try:
        db = await get_db()
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            columns = [d[0] for d in cursor.description] if cursor.description else []

        results = [dict(zip(columns, row)) for row in rows]
        logger.info("sql_query_executed", row_count=len(results))
        return json.dumps(results, default=str)

    except Exception as exc:
        logger.error("sql_query_failed", error=str(exc))
        return json.dumps({"error": str(exc)})
