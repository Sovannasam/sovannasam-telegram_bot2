#!/usr/bin/env python3
import logging
from datetime import time
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

# Import from our new folder
from bot_modules import config, database, db_access, jobs, logic, admin_commands

# Setup Logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot")

async def post_initialization(application: Application):
    """Runs once when the bot starts."""
    await database.setup_database()
    await db_access.load_state()
    await db_access.load_owner_directory()
    await db_access.load_whatsapp_bans()
    await db_access.load_user_country_bans()
    await db_access.load_admins()
    await db_access.load_whitelisted_users()
    # Start the listener for DB changes
    application.create_task(logic.listen_for_owner_changes(application))

async def post_shutdown(application: Application):
    """Runs once when the bot stops."""
    await database.close_db_pool()

async def on_message(update: Update, context):
    """Main message router."""
    await logic.process_message(update, context)

if __name__ == "__main__":
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_initialization)
        .post_shutdown(post_shutdown)
        .build()
    )

    if app.job_queue:
        # Check reminders every minute
        app.job_queue.run_repeating(jobs.check_reminders, interval=60, first=60)
        # Clear expired App IDs every hour
        app.job_queue.run_repeating(jobs.clear_expired_app_ids, interval=3600, first=3600)
        # Daily reset at 5:31 AM local time
        reset_time = time(hour=5, minute=31, tzinfo=config.TIMEZONE)
        app.job_queue.run_daily(jobs.daily_reset, time=reset_time)
        # Reset WA 45min counter
        app.job_queue.run_repeating(jobs.reset_45min_wa_counter, interval=2700, first=2700)

    # Handle all text messages
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, on_message))

    log.info("Bot is starting...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
