from datetime import datetime, timedelta
from telegram.constants import ParseMode
from .config import TIMEZONE, REMINDER_DELAY_MINUTES, log
from . import globals, db_access
from .utils import mention_user_html, _logical_day_today

async def check_reminders(context):
    """Sends reminders and applies bans for overdue items."""
    reminders_to_send = []
    state_changed = False

    async with globals.db_lock:
        now = datetime.now(TIMEZONE)
        pool = await db_access.get_db_pool()

        # 1. Username Reminders
        username_bucket = globals.state["issued"].setdefault("username", {})
        for user_id_str, items in list(username_bucket.items()):
            for item in list(items):
                try:
                    last_ts_str = item.get("last_reminder_ts") or item["ts"]
                    base_ts = datetime.fromisoformat(last_ts_str)
                    if (now - base_ts) > timedelta(minutes=REMINDER_DELAY_MINUTES):
                        user_id = int(user_id_str)
                        text = f"សូមរំលឹក: {mention_user_html(user_id)}, អ្នកនៅមិនទាន់បានផ្តល់ព័ត៌មានសម្រាប់ username {item.get('value')}។"
                        reminders_to_send.append({'chat_id': item.get("chat_id"), 'text': text})
                        item["last_reminder_ts"] = now.isoformat()
                        state_changed = True
                except Exception as e:
                    log.error(f"Username reminder error: {e}")

        # 2. WhatsApp Reminders & Bans
        wa_bucket = globals.state["issued"].setdefault("whatsapp", {})
        for user_id_str, items in list(wa_bucket.items()):
            user_id = int(user_id_str)
            for item in items:
                try:
                    item_ts = datetime.fromisoformat(item["ts"])
                    if (now - item_ts) > timedelta(minutes=REMINDER_DELAY_MINUTES) and not item.get("punished"):
                        offense_count = globals.state.setdefault("whatsapp_offense_count", {}).get(user_id_str, 0) + 1
                        globals.state["whatsapp_offense_count"][user_id_str] = offense_count
                        
                        ban_msg = ""
                        if offense_count == 1:
                            ban_until = now + timedelta(minutes=30)
                            globals.state.setdefault("whatsapp_temp_bans", {})[user_id_str] = ban_until.isoformat()
                            ban_msg = f"សូមរំលឹក: {mention_user_html(user_id)}, អ្នកត្រូវបានហាមឃាត់ 30 នាទី។"
                        elif offense_count == 2:
                            ban_until = now + timedelta(minutes=120)
                            globals.state.setdefault("whatsapp_temp_bans", {})[user_id_str] = ban_until.isoformat()
                            ban_msg = f"{mention_user_html(user_id)}, អ្នកត្រូវបានហាមឃាត់ 2 ម៉ោង។"
                        else:
                            globals.WHATSAPP_BANNED_USERS.add(user_id)
                            async with pool.acquire() as conn:
                                await conn.execute("INSERT INTO whatsapp_bans (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
                            ban_msg = f"{mention_user_html(user_id)}, អ្នកត្រូវបានហាមឃាត់ជាអចិន្ត្រៃយ៍។"
                        
                        if ban_msg:
                            reminders_to_send.append({'chat_id': item.get("chat_id"), 'text': ban_msg})
                        item["punished"] = True
                        state_changed = True
                except Exception as e:
                    log.error(f"WA reminder error: {e}")

        if state_changed:
            await db_access.save_state()

    for r in reminders_to_send:
        try: await context.bot.send_message(chat_id=r['chat_id'], text=r['text'], parse_mode=ParseMode.HTML)
        except: pass

async def daily_reset(context):
    log.info("Running daily reset...")
    async with globals.db_lock:
        globals.state['whatsapp_offense_count'] = {}
        globals.state['username_round_count'] = 0
        globals.state['whatsapp_round_count'] = 0
        pool = await db_access.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM wa_daily_usage")
            await conn.execute("DELETE FROM user_daily_activity")
            await conn.execute("DELETE FROM user_daily_country_counts")
            await conn.execute("DELETE FROM user_daily_confirmations")
            await conn.execute("DELETE FROM owner_daily_performance")
        await db_access.save_state()

async def clear_expired_app_ids(context):
    log.info("Clearing expired App IDs...")
    async with globals.db_lock:
        now = datetime.now(TIMEZONE)
        cutoff = timedelta(hours=48)
        changed = False
        bucket = globals.state.setdefault("issued", {}).get("app_id", {})
        
        for uid, items in list(bucket.items()):
            new_items = []
            for item in items:
                try:
                    if (now - datetime.fromisoformat(item["ts"])) <= cutoff:
                        new_items.append(item)
                    else:
                        changed = True
                except: new_items.append(item)
            
            if not new_items: 
                del bucket[uid]; changed = True
            else: 
                bucket[uid] = new_items
        
        if changed: await db_access.save_state()

async def reset_45min_wa_counter(context):
    async with globals.db_lock:
        globals.state['wa_45min_counter'] = 0
        await db_access.save_state()

async def send_all_pending_reminders(context):
    """Manual trigger for reminders."""
    reminders = []
    for kind in ("username", "whatsapp"):
        for uid_str, items in globals.state.get("issued", {}).get(kind, {}).items():
            for item in items:
                text = f"Reminder: {mention_user_html(int(uid_str))}, pending {kind}: {item.get('value')}"
                reminders.append({'chat_id': item.get("chat_id"), 'text': text})
    
    count = 0
    for r in reminders:
        try:
            await context.bot.send_message(chat_id=r['chat_id'], text=r['text'], parse_mode=ParseMode.HTML)
            count += 1
        except: pass
    return f"Sent {count} manual reminders."
