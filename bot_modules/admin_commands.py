import json
import re
from .patterns import *
from .utils import _norm_owner_name, _find_owner_group, _owner_is_paused, _ensure_owner_shape, _norm_handle, _norm_phone, _parse_stop_open_target, _find_age_in_text, _find_closest_app_id
from . import globals, db_access, reports, jobs
from datetime import datetime, date, timedelta
from telegram import Update

def _find_user_id_by_name(name):
    norm = name.lower().lstrip('@')
    for uid, d in globals.state.get("user_names", {}).items():
        if d.get("username", "").lower() == norm or d.get("first_name", "").lower() == norm:
            return int(uid)
    return None

def _parse_report_day(arg):
    if not arg or arg == "today": return date.today() # Simplified, should use timezone logic
    if arg == "yesterday": return date.today() - timedelta(days=1)
    try: return datetime.strptime(arg, "%Y-%m-%d").date()
    except: return date.today()

async def handle_admin_command(text, update: Update):
    user = update.effective_user
    uname = _norm_owner_name(user.username)
    
    # --- Super Admin ---
    if uname == globals.ADMIN_USERNAME:
        m = SET_FORWARD_GROUP_RX.match(text)
        if m:
            name, gid = m.groups()
            og = _find_owner_group(name)
            if og:
                og["forward_group_id"] = int(gid)
                await db_access.rebuild_pools_preserving_rotation()
                return f"Forward group for {name} set to {gid}"
        
        m = ADD_ADMIN_RX.match(text)
        if m:
            pool = await db_access.get_db_pool()
            await pool.execute("INSERT INTO admins (username, permissions) VALUES ($1, '[]') ON CONFLICT DO NOTHING", _norm_owner_name(m.group(1)))
            await db_access.load_admins()
            return f"Added admin {m.group(1)}"

        m = ADD_USER_RX.match(text)
        if m:
            uid = _find_user_id_by_name(m.group(1))
            if uid:
                pool = await db_access.get_db_pool()
                await pool.execute("INSERT INTO whitelisted_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", uid)
                await db_access.load_whitelisted_users()
                return f"Whitelisted {m.group(1)}"
            return "User not found."

    # --- Regular Admin ---
    
    # Take Customer
    m = TAKE_CUSTOMER_RX.match(text)
    if m:
        cnt, owners_str, stop = m.groups()
        owners = [_norm_owner_name(x) for x in re.split(r'[\s,]+', owners_str) if x]
        for o in owners:
            if _find_owner_group(o):
                globals.state["priority_queue"][o] = {"remaining": int(cnt), "stop_after": bool(stop)}
        await db_access.save_state()
        return f"Priority queue updated for {', '.join(owners)}."

    # Stop/Open
    m = STOP_OPEN_RX.match(text)
    if m:
        action, target = m.groups()
        is_stop = action.lower() == "stop"
        
        if target == "all owners":
            for o in globals.OWNER_DATA: o["disabled"] = is_stop
        elif target == "all whatsapp":
            for o in globals.OWNER_DATA:
                for w in o["whatsapp"]: w["disabled"] = is_stop
        elif _norm_owner_name(target) in [o["owner"] for o in globals.OWNER_DATA]:
            og = _find_owner_group(target)
            if og: og["disabled"] = is_stop
        else:
            # Assume phone/username
            kind, val = _parse_stop_open_target(target)
            found = False
            if kind == "username":
                norm = _norm_handle(val)
                for o in globals.OWNER_DATA:
                    for e in o["entries"]:
                        if _norm_handle(e["telegram"]) == norm: e["disabled"] = is_stop; found=True
            else:
                norm = _norm_phone(val)
                for o in globals.OWNER_DATA:
                    for w in o["whatsapp"]:
                        if _norm_phone(w["number"]) == norm: w["disabled"] = is_stop; found=True
            if not found: return "Target not found."

        await db_access.rebuild_pools_preserving_rotation()
        return f"{'Stopped' if is_stop else 'Opened'} {target}."

    # Add Owner
    m = ADD_OWNER_RX.match(text)
    if m:
        name = _norm_owner_name(m.group(1))
        if _find_owner_group(name): return "Exists."
        globals.OWNER_DATA.append(_ensure_owner_shape({"owner": name}))
        await db_access.rebuild_pools_preserving_rotation()
        return f"Added {name}."

    # Add Username
    m = ADD_USERNAME_RX.match(text)
    if m:
        handle, owner = m.groups()
        og = _find_owner_group(owner)
        if og:
            og["entries"].append({"telegram": handle, "disabled": False})
            await db_access.rebuild_pools_preserving_rotation()
            return f"Added @{handle} to {owner}."
    
    # Add WhatsApp
    m = ADD_WHATSAPP_RX.match(text)
    if m:
        num, owner = m.groups()
        og = _find_owner_group(owner)
        if og:
            og["whatsapp"].append({"number": num, "disabled": False})
            await db_access.rebuild_pools_preserving_rotation()
            return f"Added {num} to {owner}."

    # Delete Owner
    m = DEL_OWNER_RX.match(text)
    if m:
        name = _norm_owner_name(m.group(1))
        globals.OWNER_DATA = [g for g in globals.OWNER_DATA if g["owner"] != name]
        await db_access.rebuild_pools_preserving_rotation()
        return f"Deleted {name}."
    
    # List commands
    if LIST_DISABLED_RX.match(text):
        return "Disabled: " + ", ".join([o["owner"] for o in globals.OWNER_DATA if _owner_is_paused(o)])
    if LIST_ENABLED_RX.match(text):
        return "Enabled: " + ", ".join([o["owner"] for o in globals.OWNER_DATA if not _owner_is_paused(o)])
    if LIST_PRIORITY_RX.match(text):
        return str(globals.state.get("priority_queue", "None"))
    if COMMANDS_RX.match(text):
        return reports.get_commands_text()
    if INVENTORY_RX.match(text):
        return reports.get_inventory_text()
    
    # Bans
    m = BAN_WHATSAPP_RX.match(text)
    if m:
        uid = _find_user_id_by_name(m.group(1))
        if uid:
            pool = await db_access.get_db_pool()
            await pool.execute("INSERT INTO whatsapp_bans (user_id) VALUES ($1) ON CONFLICT DO NOTHING", uid)
            await db_access.load_whatsapp_bans()
            return f"Banned {m.group(1)}"
    
    m = BAN_COUNTRY_RX.match(text)
    if m:
        country, user_name = m.groups()
        uid = _find_user_id_by_name(user_name)
        if uid:
            pool = await db_access.get_db_pool()
            await pool.execute("INSERT INTO user_country_bans (user_id, country) VALUES ($1, $2) ON CONFLICT DO NOTHING", uid, country.lower())
            await db_access.load_user_country_bans()
            return f"Banned {user_name} from {country}"

    # Reports
    m = USER_PERFORMANCE_RX.match(text)
    if m: return await reports.get_user_performance_text(_parse_report_day(m.group(1)))
    
    m = USER_STATS_RX.match(text)
    if m: return await reports.get_user_stats_text(_parse_report_day(m.group(1)))

    m = DETAIL_USER_RX.match(text)
    if m:
        uid = _find_user_id_by_name(m.group(1))
        if uid: return await reports.get_user_detail_text(uid)

    if DATA_TODAY_RX.match(text):
        return await reports.get_daily_data_summary_text()

    if REMIND_ALL_RX.match(text):
        return await jobs.send_all_pending_reminders(None) # Needs context usually

    return None
