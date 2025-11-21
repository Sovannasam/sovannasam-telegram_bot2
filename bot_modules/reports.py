from . import globals, db_access, utils
from datetime import timedelta, time, datetime
from .config import TIMEZONE

async def get_user_detail_text(user_id):
    pool = await db_access.get_db_pool()
    # Activity
    row = await pool.fetchrow("SELECT username_requests, whatsapp_requests FROM user_daily_activity WHERE day=$1 AND user_id=$2", utils._logical_day_today(), user_id)
    reqs_u = row['username_requests'] if row else 0
    reqs_w = row['whatsapp_requests'] if row else 0
    
    # Countries
    rows = await pool.fetch("SELECT country, count FROM user_daily_country_counts WHERE day=$1 AND user_id=$2", utils._logical_day_today(), user_id)
    countries = "\n".join([f"  - {r['country'].title()}: {r['count']}" for r in rows])

    # Confirmations
    conf = await pool.fetchval("SELECT confirm_count FROM user_daily_confirmations WHERE day=$1 AND user_id=$2", utils._logical_day_today(), user_id) or 0

    # Pending
    pending_u = [i['value'] for i in globals.state.get("issued", {}).get("username", {}).get(str(user_id), [])]
    pending_w = [i['value'] for i in globals.state.get("issued", {}).get("whatsapp", {}).get(str(user_id), [])]

    lines = [f"<b>📊 Detail for {utils.mention_user_html(user_id)}</b>"]
    lines.append(f"Usernames: {reqs_u} | WhatsApp: {reqs_w} | Customers: {conf}")
    if countries: lines.append(f"<b>🌍 Submissions:</b>\n{countries}")
    
    if pending_u: lines.append(f"<b>⏳ Pending Usernames:</b>\n" + "\n".join([f"<code>{x}</code>" for x in pending_u]))
    else: lines.append("✅ No Pending Usernames")
    
    if pending_w: lines.append(f"<b>⏳ Pending WhatsApp:</b>\n" + "\n".join([f"<code>{x}</code>" for x in pending_w]))
    else: lines.append("✅ No Pending WhatsApp")
    
    return "\n".join(lines)

async def get_owner_performance_text(owner_name, day):
    pool = await db_access.get_db_pool()
    
    # Performance DB
    row = await pool.fetchrow("SELECT telegram_count, whatsapp_count FROM owner_daily_performance WHERE day=$1 AND owner_name=$2", day, owner_name)
    tg = row['telegram_count'] if row else 0
    wa = row['whatsapp_count'] if row else 0
    
    # Distribution (Audit Log)
    start = datetime.combine(day, time(3, 30)).replace(tzinfo=TIMEZONE)
    end = start + timedelta(days=1)
    dist_rows = await pool.fetch("SELECT kind, COUNT(*) as c FROM audit_log WHERE owner=$1 AND action='issued' AND ts_local >= $2 AND ts_local < $3 GROUP BY kind", owner_name, start, end)
    dist_map = {r['kind']: r['c'] for r in dist_rows}

    # Inventory
    og = next((g for g in globals.OWNER_DATA if g["owner"] == owner_name), None)
    inv_tg = len(og["entries"]) if og else 0
    inv_wa = len(og["whatsapp"]) if og else 0

    return (f"<b>📊 Performance @{owner_name} ({day})</b>\n"
            f"Customers (TG): {tg}\nCustomers (WA): {wa}\nTotal: {tg+wa}\n\n"
            f"<b>Sent by Bot:</b>\nTG: {dist_map.get('username', 0)}\nWA: {dist_map.get('whatsapp', 0)}\n\n"
            f"<b>Inventory:</b>\nTG: {inv_tg}\nWA: {inv_wa}")

async def get_daily_data_summary_text():
    pool = await db_access.get_db_pool()
    day = utils._logical_day_today()
    rows = await pool.fetch("SELECT owner_name, telegram_count + whatsapp_count as total FROM owner_daily_performance WHERE day=$1 ORDER BY total DESC", day)
    if not rows: return "No data today."
    return "<b>📊 Today's Summary</b>\n" + "\n".join([f"- @{r['owner_name']}: {r['total']}" for r in rows])

async def get_user_performance_text(day):
    pool = await db_access.get_db_pool()
    rows = await pool.fetch("SELECT user_id, confirm_count FROM user_daily_confirmations WHERE day=$1 ORDER BY confirm_count DESC", day)
    if not rows: return f"No performance data for {day}."
    
    lines = [f"<b>🏆 User Rankings ({day})</b>"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {utils.mention_user_html(r['user_id'])}: {r['confirm_count']}")
    return "\n".join(lines)

async def get_user_stats_text(day):
    pool = await db_access.get_db_pool()
    # Fetch confirm counts
    confirms = {r['user_id']: r['confirm_count'] for r in await pool.fetch("SELECT user_id, confirm_count FROM user_daily_confirmations WHERE day=$1", day)}
    # Fetch requests
    reqs = {r['user_id']: (r['username_requests'] + r['whatsapp_requests']) for r in await pool.fetch("SELECT user_id, username_requests, whatsapp_requests FROM user_daily_activity WHERE day=$1", day)}
    
    all_ids = set(confirms.keys()) | set(reqs.keys())
    stats = []
    for uid in all_ids:
        c = confirms.get(uid, 0)
        r = reqs.get(uid, 0)
        rate = (c / r * 100) if r > 0 else 0
        stats.append((uid, rate, c, r))
    
    stats.sort(key=lambda x: x[1], reverse=True)
    lines = [f"<b>📊 Success Rates ({day})</b>"]
    for i, (uid, rate, c, r) in enumerate(stats, 1):
        lines.append(f"{i}. {utils.mention_user_html(uid)}: {rate:.1f}% ({c}/{r})")
    return "\n".join(lines)

def get_inventory_text():
    u_act = sum(1 for g in globals.OWNER_DATA for e in g.get("entries", []) if not e.get("disabled"))
    u_tot = sum(len(g.get("entries", [])) for g in globals.OWNER_DATA)
    w_act = sum(1 for g in globals.OWNER_DATA for w in g.get("whatsapp", []) if not w.get("disabled"))
    w_tot = sum(len(g.get("whatsapp", [])) for g in globals.OWNER_DATA)
    return f"<b>📋 Inventory</b>\nUsernames: {u_act} active / {u_tot} total\nWhatsApp: {w_act} active / {w_tot} total"

def get_commands_text():
    return """<b>Commands</b>
/i need username - Request username
/i need whatsapp - Request number
/my detail - Check stats
/who is using @item - Find owner
Admin: /add owner, /stop @owner, /take 5 customer..."""
