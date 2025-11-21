from . import globals, db_access, utils

async def get_user_detail_text(user_id):
    pool = await db_access.get_db_pool()
    row = await pool.fetchrow("SELECT * FROM user_daily_activity WHERE day=$1 AND user_id=$2", utils._logical_day_today(), user_id)
    u = row['username_requests'] if row else 0
    w = row['whatsapp_requests'] if row else 0
    return f"<b>User Detail:</b>\nUsername Reqs: {u}\nWhatsApp Reqs: {w}"

async def get_owner_performance_text(owner, day):
    return f"Performance for {owner}: (Check DB)"
