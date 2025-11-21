import json
from datetime import datetime
from .database import get_db_pool
from . import globals
from .config import TIMEZONE
from .utils import _ensure_owner_shape if hasattr(globals, '_ensure_owner_shape') else lambda x: x 
# Note: Helper to fix shape logic below

def _ensure_owner_shape(g: dict) -> dict:
    g.setdefault("owner", ""); g.setdefault("disabled", False); g.setdefault("managed_by", None)
    g.setdefault("entries", []); g.setdefault("whatsapp", []); g.setdefault("forward_group_id", None)
    return g

async def save_state():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO kv_storage (key, data) VALUES ('state', $1) ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW();", json.dumps(globals.state))

async def load_state():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        res = await conn.fetchval("SELECT data FROM kv_storage WHERE key = 'state'")
        if res:
            loaded = json.loads(res)
            for k, v in loaded.items():
                if k in globals.state and isinstance(v, dict): globals.state[k].update(v)
                else: globals.state[k] = v
        else: await save_state()

async def save_owner_directory():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO kv_storage (key, data) VALUES ('owners', $1) ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data;", json.dumps(globals.OWNER_DATA))

async def load_owner_directory():
    pool = await get_db_pool()
    from .utils import _norm_owner_name, _norm_handle, _norm_phone, _looks_like_phone # local import
    globals.OWNER_DATA = []
    globals.HANDLE_INDEX = {}
    globals.PHONE_INDEX = {}
    globals.USERNAME_POOL = []
    globals.WHATSAPP_POOL = []

    async with pool.acquire() as conn:
        res = await conn.fetchval("SELECT data FROM kv_storage WHERE key = 'owners'")
        if res: globals.OWNER_DATA = [_ensure_owner_shape(g) for g in json.loads(res)]

    for group in globals.OWNER_DATA:
        owner = _norm_owner_name(group.get("owner"))
        if not owner or group.get("disabled"): continue
        
        # Usernames
        usernames = []
        for e in group.get("entries", []):
            if e.get("disabled"): continue
            tel = e.get("telegram", "").strip()
            ph = e.get("phone", "").strip()
            if tel:
                handle = tel if tel.startswith("@") else f"@{tel}"
                usernames.append(handle)
                globals.HANDLE_INDEX.setdefault(_norm_handle(tel), []).append({"owner": owner, "phone": ph, "telegram": tel, "channel": "telegram"})
            if ph: globals.PHONE_INDEX[_norm_phone(ph)] = {"owner": owner, "phone": ph, "telegram": tel, "channel": "telegram"}
        if usernames: globals.USERNAME_POOL.append({"owner": owner, "usernames": usernames})

        # WhatsApp
        numbers = []
        for w in group.get("whatsapp", []):
            if w.get("disabled"): continue
            num = w.get("number", "").strip()
            if num:
                numbers.append(num)
                globals.PHONE_INDEX[_norm_phone(num)] = {"owner": owner, "phone": num, "telegram": None, "channel": "whatsapp"}
        if numbers: globals.WHATSAPP_POOL.append({"owner": owner, "numbers": numbers})

async def load_admins():
    globals.ADMIN_PERMISSIONS = {}
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        for row in await conn.fetch("SELECT username, permissions FROM admins"):
            globals.ADMIN_PERMISSIONS[row['username']] = json.loads(row['permissions'])

async def load_whatsapp_bans():
    globals.WHATSAPP_BANNED_USERS = {r['user_id'] for r in await (await get_db_pool()).fetch("SELECT user_id FROM whatsapp_bans")}

async def load_user_country_bans():
    globals.USER_COUNTRY_BANS = {}
    for r in await (await get_db_pool()).fetch("SELECT user_id, country FROM user_country_bans"):
        globals.USER_COUNTRY_BANS.setdefault(r['user_id'], set()).add(r['country'].lower())

async def load_whitelisted_users():
    globals.WHITELISTED_USERS = {r['user_id'] for r in await (await get_db_pool()).fetch("SELECT user_id FROM whitelisted_users")}

async def log_event(kind, action, update, value, owner=""):
    pool = await get_db_pool()
    u, m, c = update.effective_user, update.effective_message, update.effective_chat
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO audit_log (ts_local, chat_id, message_id, user_id, user_first, user_username, kind, action, value, owner) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)", datetime.now(TIMEZONE), c.id if c else None, m.message_id if m else None, u.id if u else None, u.first_name, u.username, kind, action, value, owner)
