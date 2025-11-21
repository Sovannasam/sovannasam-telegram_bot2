import asyncio

# Database Pool
DB_POOL = None

# Thread Lock
db_lock = asyncio.Lock()

# Default State Structure
BASE_STATE = {
    "user_names": {},
    "rr": {
        "username_owner_idx": 0, "username_entry_idx": {},
        "wa_owner_idx": 0, "wa_entry_idx": {},
    },
    "issued": {"username": {}, "whatsapp": {}, "app_id": {}},
    "priority_queue": {},
    "whatsapp_temp_bans": {},
    "whatsapp_last_request_ts": {},
    "username_last_request_ts": {},
    "whatsapp_offense_count": {},
    "username_round_count": 0,
    "whatsapp_round_count": 0,
    "wa_45min_counter": 0
}

# Current State (Loaded from DB)
state = {k: (v.copy() if isinstance(v, dict) else v) for k, v in BASE_STATE.items()}

# Caches
OWNER_DATA = []
HANDLE_INDEX = {}
PHONE_INDEX = {}
USERNAME_POOL = []
WHATSAPP_POOL = []

# Permissions
WHATSAPP_BANNED_USERS = set()
WHITELISTED_USERS = set()
ADMIN_PERMISSIONS = {}
USER_COUNTRY_BANS = {}

COMMAND_PERMISSIONS = {
    'add owner', 'delete owner', 'add username', 'delete username', 'add whatsapp', 'delete whatsapp',
    'stop open', 'take customer', 'ban whatsapp', 'unban whatsapp','performance', 'remind user', 'clear pending', 
    'list disabled', 'detail user', 'list banned', 'list admins', 'data today', 'list enabled', 'add user', 
    'delete user', 'ban country', 'unban country', 'list country bans', 'user performance', 'user stats',
    'inventory', 'list priority', 'round count', 'cancel priority', 'list owner'
}
