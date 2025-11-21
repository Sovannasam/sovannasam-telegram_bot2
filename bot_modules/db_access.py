import json
from datetime import datetime
from .database import get_db_pool
from . import globals
from .config import TIMEZONE
from .utils import _norm_owner_name, _norm_handle, _norm_phone, _owner_is_paused

# --- Helper Functions ---
def _ensure_owner_shape(g: dict) -> dict:
    g.setdefault("owner", "")
    g.setdefault("disabled", False)
    g.setdefault("managed_by", None)
    g.setdefault("entries", [])
    g.setdefault("whatsapp", [])
    g.setdefault("forward_group_id", None)
    
    # Normalize entries
    norm_entries = []
    for e in g.get("entries", []):
        if isinstance(e, dict):
            e_copy = e.copy()
            e_copy.setdefault("telegram", "")
            e_copy.setdefault("phone", "")
            e_copy.setdefault("disabled", False)
            e_copy.setdefault("managed_by", None)
            norm_entries.append(e_copy)
    g["entries"] = norm_entries

    # Normalize WhatsApp
    norm_wa = []
    for w in g.get("whatsapp", []):
        entry = {}
        if isinstance(w, dict):
            entry = w.copy()
            entry.setdefault("number", w.get("number") or w.get("phone") or "")
        elif isinstance(w, str) and w.strip():
            entry["number"] = w

        if (entry.get("number") or "").strip():
            entry.setdefault("disabled", False)
            entry.setdefault("managed_by", None)
            norm_wa.append(entry)
    g["whatsapp"] = norm_wa
    return g

# --- Core DB Functions ---
async def save_state():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO kv_storage (key, data) VALUES ('state', $1)
                ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW();
            """, json.dumps(globals.state))
    except Exception as e:
        print(f"Failed to save state: {e}")

async def load_state():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            res = await conn.fetchval("SELECT data FROM kv_storage WHERE key = 'state'")
            if res:
                loaded = json.loads(res)
                # Deep merge to preserve structure
                for k, v in loaded.items():
                    if k in globals.state and isinstance(v, dict):
                        globals.state[k].update(v)
                    else:
                        globals.state[k] = v
            else:
                await save_state()
    except Exception as e:
        print(f"Failed to load state: {e}")

async def save_owner_directory():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO kv_storage (key, data) VALUES ('owners', $1)
                ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW();
            """, json.dumps(globals.OWNER_DATA))
    except Exception as e:
        print(f"Failed to save owners: {e}")

async def load_owner_directory():
    pool = await get_db_pool()
    globals.OWNER_DATA = []
    globals.HANDLE_INDEX = {}
    globals.PHONE_INDEX = {}
    globals.USERNAME_POOL = []
    globals.WHATSAPP_POOL = []

    try:
        async with pool.acquire() as conn:
            res = await conn.fetchval("SELECT data FROM kv_storage WHERE key = 'owners'")
            if res:
                globals.OWNER_DATA = [_ensure_owner_shape(g) for g in json.loads(res)]
    except Exception as e:
        print(f"Failed to load owners: {e}")

    for group in globals.OWNER_DATA:
        owner = _norm_owner_name(group.get("owner"))
        if not owner or _owner_is_paused(group): continue
        
        # Usernames
        usernames = []
        for e in group.get("entries", []):
            if e.get("disabled"): continue
            tel = e.get("telegram", "").strip()
            ph = e.get("phone", "").strip()
            if tel:
                handle = tel if tel.startswith("@") else f"@{tel}"
                usernames.append(handle)
                globals.HANDLE_INDEX.setdefault(_norm_handle(tel), []).append(
                    {"owner": owner, "phone": ph, "telegram": tel, "channel": "telegram"}
                )
            if ph:
                globals.PHONE_INDEX[_norm_phone(ph)] = {"owner": owner, "phone": ph, "telegram": tel, "channel": "telegram"}
        if usernames:
            globals.USERNAME_POOL.append({"owner": owner, "usernames": usernames})

        # WhatsApp
        numbers = []
        for w in group.get("whatsapp", []):
            if w.get("disabled"): continue
            num = w.get("number", "").strip()
            if num:
                numbers.append(num)
                globals.PHONE_INDEX[_norm_phone(num)] = {"owner": owner, "phone": num, "telegram": None, "channel": "whatsapp"}
        if numbers:
            globals.WHATSAPP_POOL.append({"owner": owner, "numbers": numbers})

async def load_admins():
    globals.ADMIN_PERMISSIONS = {}
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT username, permissions FROM admins")
            for row in rows:
                globals.ADMIN_PERMISSIONS[row['username']] = json.loads(row['permissions'])
    except Exception as e: print(f"Load admins error: {e}")

async def load_whatsapp_bans():
    globals.WHATSAPP_BANNED_USERS = set()
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id FROM whatsapp_bans")
            for row in rows: globals.WHATSAPP_BANNED_USERS.add(row['user_id'])
    except Exception as e: print(f"Load WA bans error: {e}")

async def load_user_country_bans():
    globals.USER_COUNTRY_BANS = {}
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, country FROM user_country_bans")
            for row in rows:
                globals.USER_COUNTRY_BANS.setdefault(row['user_id'], set()).add(row['country'].lower())
    except Exception as e: print(f"Load country bans error: {e}")

async def load_whitelisted_users():
    globals.WHITELISTED_USERS = set()
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id FROM whitelisted_users")
            for row in rows: globals.WHITELISTED_USERS.add(row['user_id'])
    except Exception as e: print(f"Load whitelist error: {e}")

async def log_event(kind, action, update, value, owner=""):
    try:
        pool = await get_db_pool()
        u, m, c = update.effective_user, update.effective_message, update.effective_chat
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO audit_log (
                    ts_local, chat_id, message_id, user_id, user_first,
                    user_username, kind, action, value, owner
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, datetime.now(TIMEZONE), c.id if c else None, m.message_id if m else None,
                u.id if u else None, u.first_name if u else None, u.username if u else None,
                kind, action, value, owner or "")
    except Exception as e: print(f"Log error: {e}")

# --- Pool Rebuild Logic (Moved here to avoid circular imports) ---
def _owner_list_from_pool(pool): return [blk["owner"] for blk in pool]

def _preserve_owner_pointer(old_list, new_list, old_idx):
    if not new_list: return 0
    old_list = list(old_list or [])
    if not old_list: return 0
    if old_idx >= len(old_list): old_idx = 0
    start_owner = old_list[old_idx]
    if start_owner in new_list: return new_list.index(start_owner)
    n = len(old_list)
    for step in range(1, n + 1):
        cand = old_list[(old_idx + step) % n]
        if cand in new_list: return new_list.index(cand)
    return 0

def _preserve_entry_indices(rr_map, new_pool, list_key):
    valid_owners = {blk["owner"]: len(blk.get(list_key, []) or []) for blk in new_pool}
    for owner in list(rr_map.keys()):
        if owner not in valid_owners: rr_map.pop(owner, None)
    for owner, sz in valid_owners.items():
        if sz <= 0: rr_map.pop(owner, None)
        else: rr_map[owner] = rr_map.get(owner, 0) % sz

async def rebuild_pools_preserving_rotation():
    old_user_owner_list = _owner_list_from_pool(globals.USERNAME_POOL)
    old_wa_owner_list   = _owner_list_from_pool(globals.WHATSAPP_POOL)

    rr = globals.state.setdefault("rr", {})
    old_user_owner_idx = rr.get("username_owner_idx", 0)
    old_wa_owner_idx   = rr.get("wa_owner_idx", 0)
    old_user_entry_idx = dict(rr.get("username_entry_idx", {}))
    old_wa_entry_idx   = dict(rr.get("wa_entry_idx", {}))

    await save_owner_directory()
    await load_owner_directory()

    new_user_owner_list = _owner_list_from_pool(globals.USERNAME_POOL)
    new_wa_owner_list   = _owner_list_from_pool(globals.WHATSAPP_POOL)

    rr["username_owner_idx"] = _preserve_owner_pointer(old_user_owner_list, new_user_owner_list, old_user_owner_idx)
    rr["wa_owner_idx"] = _preserve_owner_pointer(old_wa_owner_list, new_wa_owner_list, old_wa_owner_idx)

    rr.setdefault("username_entry_idx", old_user_entry_idx)
    rr.setdefault("wa_entry_idx", old_wa_entry_idx)
    _preserve_entry_indices(rr["username_entry_idx"], globals.USERNAME_POOL, "usernames")
    _preserve_entry_indices(rr["wa_entry_idx"], globals.WHATSAPP_POOL, "numbers")

    await save_state()
