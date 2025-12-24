import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

TOKEN = os.getenv("TOKEN")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

# ===== ТЕСТОВЫЙ ХЕНДЛЕР =====
@dp.message()
async def echo(msg):
    await msg.answer("Бот жив 🟢")

# ===== STARTUP =====
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

# ===== SHUTDOWN =====
async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

async def main():
    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return app

if __name__ == "__main__":
    web.run_app(main(), port=int(os.getenv("PORT", 8080)))
