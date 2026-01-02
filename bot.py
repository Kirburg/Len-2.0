import os
import asyncio
import logging
from time import time

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from aiohttp import web

# ==========================
# CONFIG
# ==========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") + WEBHOOK_PATH

MENU_TTL = 60          # жизнь меню
CLICK_COOLDOWN = 1.5   # антиспам кликов (сек)

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================
# FSM
# ==========================

class MenuFSM(StatesGroup):
    choosing_shift = State()
    choosing_type = State()

# ==========================
# UTILS
# ==========================

async def auto_delete(chat_id: int, msg_id: int, ttl: int):
    await asyncio.sleep(ttl)
    try:
        await bot.delete_message(chat_id, msg_id)
    except:
        pass


async def drop_old_menu(state: FSMContext):
    data = await state.get_data()
    old_id = data.get("menu_msg_id")
    chat_id = data.get("chat_id")

    if old_id and chat_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except:
            pass


def now():
    return time()

# ==========================
# KEYBOARDS
# ==========================

def shift_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Смена 11", callback_data="shift_11")],
        [InlineKeyboardButton(text="Смена 20", callback_data="shift_20")],
    ])


def type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Jira", callback_data="type_jira")],
        [InlineKeyboardButton(text="CI", callback_data="type_ci")],
    ])

# ==========================
# START
# ==========================

@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await drop_old_menu(state)
    await state.clear()

    menu = await bot.send_message(
        msg.chat.id,
        "Напиши, на кого обратить внимание:",
        reply_markup=shift_kb()
    )

    await state.set_state(MenuFSM.choosing_shift)
    await state.update_data(
        menu_msg_id=menu.message_id,
        chat_id=menu.chat.id,
        last_click=0
    )

    asyncio.create_task(auto_delete(menu.chat.id, menu.message_id, MENU_TTL))

# ==========================
# SHIFT
# ==========================

@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb: CallbackQuery, state: FSMContext):
    await cb.answer()  # ВАЖНО

    data = await state.get_data()

    # антиспам
    if now() - data.get("last_click", 0) < CLICK_COOLDOWN:
        return

    shift = cb.data.split("_")[1]

    # Jira только для 11 и 20
    if shift not in ("11", "20"):
        await cb.answer("Недоступно", show_alert=True)
        return

    await drop_old_menu(state)

    msg = await bot.send_message(
        cb.message.chat.id,
        f"Смена {shift}. Выбери тип:",
        reply_markup=type_kb()
    )

    await state.set_state(MenuFSM.choosing_type)
    await state.update_data(
        menu_msg_id=msg.message_id,
        chat_id=msg.chat.id,
        shift=shift,
        last_click=now()
    )

    asyncio.create_task(auto_delete(msg.chat.id, msg.message_id, MENU_TTL))

# ==========================
# TYPE
# ==========================

@dp.callback_query(F.data.startswith("type_"))
async def choose_type(cb: CallbackQuery, state: FSMContext):
    await cb.answer()

    data = await state.get_data()

    if now() - data.get("last_click", 0) < CLICK_COOLDOWN:
        return

    t = cb.data.split("_")[1]
    shift = data.get("shift")

    await drop_old_menu(state)
    await state.clear()

    await bot.send_message(
        cb.message.chat.id,
        f"✅ Принято:\nСмена: {shift}\nТип: {t.upper()}"
    )

# ==========================
# RESTART
# ==========================

@dp.message(Command("restart"))
@dp.message(F.text.regexp(r"^/restart@"))
async def restart(msg: Message):
    try:
        await msg.delete()
    except:
        pass

    await msg.answer("♻️ Перезапуск…", delete_after=3)
    await asyncio.sleep(0.5)

    os._exit(1)  # Railway рестарт

# ==========================
# WEBHOOK
# ==========================

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("Webhook set")


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


async def handle_webhook(request):
    data = await request.json()
    update = dp.feed_raw_update(bot, data)
    await update
    return web.Response(text="OK")


def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))


if __name__ == "__main__":
    main()
