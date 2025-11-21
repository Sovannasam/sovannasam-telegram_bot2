import re
import unicodedata
from datetime import datetime, timedelta, date
from .config import TIMEZONE, PHONE_LIKE_RX, ALLOWED_COUNTRIES
from . import globals

def _norm_handle(h: str) -> str: return re.sub(r"^@", "", (h or "").strip().lower())
def _norm_phone(p: str) -> str: return re.sub(r"\D+", "", (p or ""))

def _normalize_app_id(app_id: str) -> str:
    if not app_id: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', unicodedata.normalize('NFKC', app_id)).lower()

def _norm_owner_name(s: str) -> str:
    s = (s or "").strip()
    return s[1:].lower() if s.startswith("@") else s.lower()

def _looks_like_phone(s: str) -> bool:
    return bool(PHONE_LIKE_RX.fullmatch((s or "").strip()))

def _logical_day_today() -> date:
    return (datetime.now(TIMEZONE) - timedelta(hours=3, minutes=30)).date()

def mention_user_html(user_id: int) -> str:
    info = globals.state.get("user_names", {}).get(str(user_id), {})
    name = info.get("first_name") or info.get("username") or str(user_id)
    return f'<a href="tg://user?id={user_id}">{name}</a>'

def _find_age_in_text(text: str) -> int | None:
    match = re.search(r'\b(?:age|old)\s*:?\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:yrs|yr|years|year old)\b', text.lower())
    if match:
        age_str = match.group(1) or match.group(2)
        return int(age_str) if age_str else None
    return None

def _find_country_in_text(text: str):
    match = re.search(r'\b(?:from|country)\s*:?\s*(.*)', text, re.IGNORECASE)
    if not match: return None, None
    line = match.group(1).split('\n')[0].strip().lower()
    for country in ALLOWED_COUNTRIES:
        if re.search(r'\b' + re.escape(country) + r'\b', line):
            return (country, 'india') if country in ['indian', 'india'] else (country, country)
    return line.split(',')[0].strip(), 'not_allowed'

def _find_closest_app_id(typed_id: str):
    def levenshtein(s1, s2):
        if len(s1) < len(s2): return levenshtein(s2, s1)
        if not s2: return len(s1)
        prev = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
            prev = curr
        return prev[-1]

    all_ids = [i['value'] for k, v in globals.state.get("issued", {}).get("app_id", {}).items() for i in v if i.get("value")]
    if not all_ids: return None
    
    norm_typed = _normalize_app_id(typed_id)
    closest, min_dist = None, 3
    for pid in all_ids:
        dist = levenshtein(norm_typed, _normalize_app_id(pid))
        if dist < min_dist:
            min_dist = dist
            closest = pid
    return closest
