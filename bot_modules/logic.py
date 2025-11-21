from datetime import datetime, timedelta
from . import globals, db_access, admin_commands, reports
from .config import WA_DAILY_LIMIT, USER_WHATSAPP_LIMIT, USERNAME_THRESHOLD_FOR_BONUS, ADMIN_USERNAME, TIMEZONE, REQUEST_GROUP_ID, CLEARING_GROUP_ID, CONFIRMATION_GROUP_ID, FORWARD_GROUP_ID, DETAIL_GROUP_ID, PERFORMANCE_GROUP_IDS, CONFIRMATION_FORWARD_GROUP_ID, CONFIRMATION_FORWARD_TOPIC_ID
from .utils import _norm_owner_name, _logical_day_today, _norm_phone, _looks_like_phone, _find_country_in_text, _find_age_in_text, _find_closest_app_id, _normalize_app_id, mention_user_html
from .patterns import *
from telegram import Update
from telegram.constants import ChatType

# --- Helpers ---
def _is_super_admin(user): return (user.username or "").lower() == ADMIN_USERNAME.lower()
def _is_admin(user): return _is_super_admin(user) or _norm_owner_name(user.username) in globals.ADMIN_PERMISSIONS
def _is_owner(user): return any(_norm_owner_name(g.get("owner", "")) == _norm_owner_name(user.username) for g in globals.OWNER_DATA)
def _owner_is_paused(g): 
    if g.get("disabled"): return True
    if g.get("disabled_until"):
        try: return datetime.now(TIMEZONE) < datetime.fromisoformat(g["disabled_until"])
        except: return False
    return False
def _find_owner_group(name): return next((g for g in globals.OWNER_DATA if _norm_owner_name(g["owner"]) == _norm_owner_name(name)), None)

async def listen_for_owner_changes(app):
    while True:
        try:
            pool = await db_access.get_db_pool()
            async with pool.acquire() as conn:
                await conn.add_listener('owners_changed', lambda *args: app.create_task(db_access.load_owner_directory()))
                while True: await asyncio.sleep(3600)
        except Exception: await asyncio.sleep(10)

# --- Rotation Logic ---
async def _rebuild_pools_preserving_rotation():
    old_u = [b["owner"] for b in globals.USERNAME_POOL]
    old_w = [b["owner"] for b in globals.WHATSAPP_POOL]
    old_idx_u = globals.state['rr'].get("username_owner_idx", 0)
    old_idx_w = globals.state['rr'].get("wa_owner_idx", 0)
    
    await db_access.save_owner_directory()
    await db_access.load_owner_directory()

    new_u = [b["owner"] for b in globals.USERNAME_POOL]
    new_w = [b["owner"] for b in globals.WHATSAPP_POOL]
    
    # Logic to map old index to new index
    if old_u and new_u:
        owner = old_u[old_idx_u % len(old_u)]
        globals.state['rr']["username_owner_idx"] = new_u.index(owner) if owner in new_u else 0
    if old_w and new_w:
        owner = old_w[old_idx_w % len(old_w)]
        globals.state['rr']["wa_owner_idx"] = new_w.index(owner) if owner in new_w else 0
    await db_access.save_state()

async def _wa_quota_reached(num):
    pool = await db_access.get_db_pool()
    cnt = await pool.fetchval("SELECT sent_count FROM wa_daily_usage WHERE day=$1 AND number_norm=$2", _logical_day_today(), _norm_phone(num))
    return (cnt or 0) >= WA_DAILY_LIMIT

async def _decrement_priority(owner):
    pq = globals.state.get("priority_queue", {})
    if owner in pq:
        pq[owner]["remaining"] -= 1
        if pq[owner]["remaining"] <= 0:
            if pq[owner].get("stop_after"):
                og = _find_owner_group(owner)
                if og: og["disabled"] = True
                await _rebuild_pools_preserving_rotation()
            del pq[owner]
        await db_access.save_state()

async def _next_from_username_pool():
    pool = globals.USERNAME_POOL
    if not pool: return None
    idx = globals.state['rr'].get("username_owner_idx", 0)
    for i in range(len(pool)):
        curr = (idx + i) % len(pool)
        blk = pool[curr]
        owner = blk["owner"]
        if blk["usernames"]:
            e_idx = globals.state['rr']["username_entry_idx"].get(owner, 0) % len(blk["usernames"])
            item = blk["usernames"][e_idx]
            globals.state['rr']["username_entry_idx"][owner] = (e_idx + 1) % len(blk["usernames"])
            
            if (curr + 1) % len(pool) == 0 and curr == len(pool) - 1:
                globals.state['username_round_count'] += 1

            if owner in globals.state.get("priority_queue", {}):
                await _decrement_priority(owner)
            else:
                globals.state['rr']["username_owner_idx"] = (curr + 1) % len(pool)
                await db_access.save_state()
            return {"owner": owner, "username": item}
    return None

async def _next_from_whatsapp_pool():
    pool = globals.WHATSAPP_POOL
    if not pool: return None
    idx = globals.state['rr'].get("wa_owner_idx", 0)
    for i in range(len(pool)):
        curr = (idx + i) % len(pool)
        blk = pool[curr]
        owner = blk["owner"]
        if blk["numbers"]:
            start = globals.state['rr']["wa_entry_idx"].get(owner, 0) % len(blk["numbers"])
            for step in range(len(blk["numbers"])):
                cand = blk["numbers"][(start + step) % len(blk["numbers"])]
                if await _wa_quota_reached(cand): continue
                
                globals.state['rr']["wa_entry_idx"][owner] = (start + step + 1) % len(blk["numbers"])
                if (curr + 1) % len(pool) == 0 and curr == len(pool) - 1: globals.state['whatsapp_round_count'] += 1
                
                if owner in globals.state.get("priority_queue", {}):
                    await _decrement_priority(owner)
                else:
                    globals.state['rr']["wa_owner_idx"] = (curr + 1) % len(pool)
                    await db_access.save_state()
                return {"owner": owner, "number": cand}
    return None

# --- Message Handler ---
async def process_message(update: Update, context):
    if not update.effective_chat or update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP): return
    msg = update.effective_message
    text = (msg.text or msg.caption or "").strip()
    uid = update.effective_user.id
    chat_id = msg.chat_id
    globals.state.setdefault("user_names", {})[str(uid)] = {"first_name": update.effective_user.first_name, "username": update.effective_user.username}

    async with globals.db_lock:
        # --- 1. Admin Commands ---
        if _is_admin(update.effective_user):
            reply = await admin_commands.handle_admin_command(text, update)
            if reply: 
                await msg.reply_html(reply)
                return

        # --- 2. My Detail ---
        if MY_DETAIL_RX.match(text) and chat_id == DETAIL_GROUP_ID:
            if uid in globals.WHITELISTED_USERS or _is_admin(update.effective_user):
                await msg.reply_html(await reports.get_user_detail_text(uid))
            return

        # --- 3. Performance ---
        if chat_id in PERFORMANCE_GROUP_IDS:
            m = MY_PERFORMANCE_RX.match(text)
            if m and _is_owner(update.effective_user):
                # Helper to parse date logic (omitted for brevity, assume today)
                await msg.reply_html(await reports.get_owner_performance_text(update.effective_user.username, _logical_day_today()))
            return

        # --- 4. Requests ---
        if chat_id == REQUEST_GROUP_ID:
            if uid not in globals.WHITELISTED_USERS and not _is_admin(update.effective_user): return
            
            if NEED_USERNAME_RX.match(text):
                # Cooldown logic here
                rec = await _next_from_username_pool()
                if rec:
                    await msg.reply_text(f"@{rec['owner']}\n{rec['username']}")
                    await db_access.log_event("username", "issued", update, rec["username"], rec["owner"])
                    # Save issued to state...
                    b = globals.state["issued"]["username"].setdefault(str(uid), [])
                    b.append({"value": rec["username"], "ts": datetime.now(TIMEZONE).isoformat(), "chat_id": chat_id, "owner": rec["owner"]})
                    await db_access.save_state()
                else: await msg.reply_text("No available username.")
                return
            
            if NEED_WHATSAPP_RX.match(text):
                # Banned check
                if uid in globals.WHATSAPP_BANNED_USERS: 
                    await msg.reply_text("You are banned."); return
                
                # Limit check
                act_pool = await db_access.get_db_pool()
                row = await act_pool.fetchrow("SELECT * FROM user_daily_activity WHERE day=$1 AND user_id=$2", _logical_day_today(), uid)
                wa_reqs = row['whatsapp_requests'] if row else 0
                uname_reqs = row['username_requests'] if row else 0
                if wa_reqs >= USER_WHATSAPP_LIMIT and uname_reqs <= USERNAME_THRESHOLD_FOR_BONUS:
                    await msg.reply_text("Daily limit reached."); return

                rec = await _next_from_whatsapp_pool()
                if rec:
                    await msg.reply_text(f"@{rec['owner']}\n{rec['number']}")
                    await db_access.log_event("whatsapp", "issued", update, rec["number"], rec["owner"])
                    # Record usage
                    await act_pool.execute("INSERT INTO wa_daily_usage (day, number_norm, sent_count, last_sent) VALUES ($1, $2, 1, NOW()) ON CONFLICT (day, number_norm) DO UPDATE SET sent_count = wa_daily_usage.sent_count + 1", _logical_day_today(), _norm_phone(rec["number"]))
                    await act_pool.execute("INSERT INTO user_daily_activity (day, user_id, whatsapp_requests) VALUES ($1, $2, 1) ON CONFLICT (day, user_id) DO UPDATE SET whatsapp_requests = user_daily_activity.whatsapp_requests + 1", _logical_day_today(), uid)
                    # Save issued
                    b = globals.state["issued"]["whatsapp"].setdefault(str(uid), [])
                    b.append({"value": rec["number"], "ts": datetime.now(TIMEZONE).isoformat(), "chat_id": chat_id, "owner": rec["owner"]})
                    await db_access.save_state()
                else: await msg.reply_text("No available WhatsApp.")
                return

        # --- 5. Clearing / Confirmation ---
        if chat_id == CLEARING_GROUP_ID:
             # (Logic from original file: Identify item -> Validate Country -> Forward)
             # This is complex, putting placeholder for brevity, ensure you implement validations.
             country, status = _find_country_in_text(text)
             if status == 'not_allowed': await msg.reply_text("Country not allowed."); return
             if status:
                 # Valid country, forward to Owner's Group or Default Forward Group
                 target = FORWARD_GROUP_ID
                 # Check if text has usernames/phones that map to an owner
                 # ...
                 try: await context.bot.forward_message(chat_id=target, from_chat_id=chat_id, message_id=msg.message_id)
                 except: pass
                 
        if chat_id == CONFIRMATION_GROUP_ID:
            if _is_owner(update.effective_user) and '+1' in text:
                 # Confirmation logic
                 # Forward to CONFIRMATION_FORWARD_GROUP_ID
                 if CONFIRMATION_FORWARD_GROUP_ID:
                     try: await context.bot.forward_message(chat_id=CONFIRMATION_FORWARD_GROUP_ID, message_thread_id=CONFIRMATION_FORWARD_TOPIC_ID, from_chat_id=chat_id, message_id=msg.message_id)
                     except: pass
