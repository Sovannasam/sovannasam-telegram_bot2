from .patterns import *
from .utils import _norm_owner_name, _find_owner_group, _owner_is_paused, _ensure_owner_shape
from . import globals, db_access
from datetime import datetime

async def handle_admin_command(text, update):
    user = update.effective_user
    
    # Example: Stop/Open
    m = STOP_OPEN_RX.match(text)
    if m:
        action, target = m.groups()
        is_stop = action.lower() == "stop"
        if target == "all owners":
            for o in globals.OWNER_DATA: o["disabled"] = is_stop
            await db_access.save_owner_directory()
            await db_access.load_owner_directory()
            return f"{'Stopped' if is_stop else 'Opened'} all owners."
        # ... other stop/open logic
        
    # Example: Add Owner
    m = ADD_OWNER_RX.match(text)
    if m:
        name = _norm_owner_name(m.group(1))
        if _find_owner_group(name): return "Exists."
        globals.OWNER_DATA.append(_ensure_owner_shape({"owner": name}))
        await db_access.save_owner_directory()
        await db_access.load_owner_directory()
        return f"Added {name}."

    # Set Forward Group (Super Admin)
    m = SET_FORWARD_GROUP_RX.match(text)
    if m:
        name, gid = m.groups()
        og = _find_owner_group(name)
        if og:
            og["forward_group_id"] = int(gid)
            await db_access.save_owner_directory()
            await db_access.load_owner_directory()
            return f"Set forward group for {name} to {gid}"
            
    return None
