import asyncpg
import logging
from .config import DATABASE_URL
from . import globals

log = logging.getLogger("bot")

async def get_db_pool() -> asyncpg.Pool:
    if globals.DB_POOL is None or globals.DB_POOL.is_closing():
        globals.DB_POOL = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            max_inactive_connection_lifetime=60,
            min_size=1,
            max_size=10
        )
        log.info("DB pool connected.")
    return globals.DB_POOL

async def close_db_pool():
    if globals.DB_POOL:
        await globals.DB_POOL.close()
        globals.DB_POOL = None

async def setup_database():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_storage (key TEXT PRIMARY KEY, data JSONB NOT NULL, updated_at TIMESTAMPTZ DEFAULT NOW());
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (id SERIAL PRIMARY KEY, ts_local TIMESTAMPTZ NOT NULL, chat_id BIGINT, message_id BIGINT, user_id BIGINT, user_first TEXT, user_username TEXT, kind TEXT, action TEXT, value TEXT, owner TEXT);
        """)
        await conn.execute("CREATE TABLE IF NOT EXISTS wa_daily_usage (day DATE NOT NULL, number_norm TEXT NOT NULL, sent_count INTEGER NOT NULL DEFAULT 0, last_sent TIMESTAMPTZ, PRIMARY KEY (day, number_norm));")
        await conn.execute("CREATE TABLE IF NOT EXISTS user_daily_activity (day DATE NOT NULL, user_id BIGINT NOT NULL, username_requests INTEGER DEFAULT 0, whatsapp_requests INTEGER DEFAULT 0, PRIMARY KEY (day, user_id));")
        await conn.execute("CREATE TABLE IF NOT EXISTS whatsapp_bans (user_id BIGINT PRIMARY KEY);")
        await conn.execute("CREATE TABLE IF NOT EXISTS whitelisted_users (user_id BIGINT PRIMARY KEY);")
        await conn.execute("CREATE TABLE IF NOT EXISTS user_daily_country_counts (day DATE NOT NULL, user_id BIGINT NOT NULL, country TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, user_id, country));")
        await conn.execute("CREATE TABLE IF NOT EXISTS user_daily_confirmations (day DATE NOT NULL, user_id BIGINT NOT NULL, confirm_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, user_id));")
        await conn.execute("CREATE TABLE IF NOT EXISTS owner_daily_performance (day DATE NOT NULL, owner_name TEXT NOT NULL, telegram_count INTEGER NOT NULL DEFAULT 0, whatsapp_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, owner_name));")
        await conn.execute("CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, permissions JSONB NOT NULL);")
        await conn.execute("CREATE TABLE IF NOT EXISTS user_country_bans (user_id BIGINT NOT NULL, country TEXT NOT NULL, PRIMARY KEY (user_id, country));")
