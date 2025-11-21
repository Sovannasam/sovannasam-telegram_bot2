import os
import pytz

def get_env(name, default=None):
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing env var: {name}")
    return val

BOT_TOKEN = get_env("BOT_TOKEN")
DATABASE_URL = get_env("DATABASE_URL")
ADMIN_USERNAME = get_env("ADMIN_USERNAME", "excelmerge")

# Configs
WA_DAILY_LIMIT = int(get_env("WA_DAILY_LIMIT", "2"))
REMINDER_DELAY_MINUTES = int(get_env("REMINDER_DELAY_MINUTES", "30"))
USER_WHATSAPP_LIMIT = int(get_env("USER_WHATSAPP_LIMIT", "10"))
USERNAME_THRESHOLD_FOR_BONUS = int(get_env("USERNAME_THRESHOLD_FOR_BONUS", "25"))
COUNTRY_DAILY_LIMIT = int(get_env("COUNTRY_DAILY_LIMIT", "17"))

# Group IDs
REQUEST_GROUP_ID = int(get_env("REQUEST_GROUP_ID", "-1002438185636"))
CLEARING_GROUP_ID = int(get_env("CLEARING_GROUP_ID", "-1002624324856"))
CONFIRMATION_GROUP_ID = int(get_env("CONFIRMATION_GROUP_ID", "-1002694540582"))
CONFIRMATION_FORWARD_GROUP_ID = int(get_env("CONFIRMATION_FORWARD_GROUP_ID", "-1003109226804"))
CONFIRMATION_FORWARD_TOPIC_ID = int(get_env("CONFIRMATION_FORWARD_TOPIC_ID", "15582"))
DETAIL_GROUP_ID = int(get_env("DETAIL_GROUP_ID", "-1002598927727"))
FORWARD_GROUP_ID = int(get_env("FORWARD_GROUP_ID", "-1003109226804"))

PERFORMANCE_GROUP_IDS = {
    -1002670785417, -1002659012767, -1002790753092, -1002520117752
}

ALLOWED_COUNTRIES = {
    'panama', 'united arab emirates','oman', 'jordan', 'italy', 'germany', 'indonesia',
    'bulgaria', 'brazil', 'spain', 'belgium','portugal', 'netherlands', 'poland', 'qatar', 
    'france', 'switzerland', 'argentina', 'costa rica', 'kuwait', 'bahrain', 'malaysia',
    'canada','mauritania','greece','belarus', 'slovakia', 'hungary', 'romania', 
    'luxembourg', 'czechia', 'india', 'austria', 'tunisia', 'iran', 'mexico', 'russia'
}

TIMEZONE = pytz.timezone("Asia/Phnom_Penh")
