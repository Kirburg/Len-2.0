import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ====== ENV ======
TOKEN = os.getenv("BOT_TOKEN")
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_BASE = os.getenv("WEBHOOK_URL")  # https://your-project.up.railway.app
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ====== INIT ======
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# ====== FSM ======
class ReportFSM(StatesGroup):
    shift = State()
    type = State()
    text = State()

# ====== KEYBOARDS ======
def shift_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"shift_{s}")]
        for s in ["8-20", "11-23", "14-02", "20-08"]
    ])

def type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[ 
        InlineKeyboardButton(text="➕ ДОП", callback_data="type_dop"),
        InlineKeyboardButton(text="👀 ВИ", callback_data="type_vi"),
    ]])

def dop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[ 
        InlineKeyboardButton(text="✅ Всё ок", callback_data="dop_ok"),
        InlineKeyboardButton(text="⚠️ Внимание", callback_data="dop_warn"),
    ]])

# ====== HELPERS ======
def mention_user(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

def mention_admin():
    return f'<a href="tg://user?id={ADMIN_ID}">руководитель</a>'

# ====== START ======
@dp.message(F.text.startswith("/start"))
async def start(msg: Message, state: FSMContext):
    try:
        await msg.delete()
    except:
        pass
    await msg.answer("Выбирай смену:", reply_markup=shift_kb())
    await state.clear()

# ====== SHIFT ======
@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb, state: FSMContext):
    shift = cb.data.split("_", 1)[1]
    await state.update_data(shift=shift)
    await cb.message.edit_text(
        f"Смена {shift}. Что дальше?",
        reply_markup=type_kb()
    )

# ====== TYPE ======
@dp.callback_query(F.data == "type_dop")
async def type_dop(cb, state: FSMContext):
    await cb.message.edit_text("ДОП статус:", reply_markup=dop_kb())

@dp.callback_query(F.data == "type_vi")
async def type_vi(cb, state: FSMContext):
    await cb.message.edit_text("Напиши саммари ВИ:")
    await state.update_data(type="vi")
    await state.set_state(ReportFSM.text)
    await cb.message.delete()

# ====== ДОП OK ======
@dp.callback_query(F.data == "dop_ok")
async def dop_ok(cb, state: FSMContext):
    data = await state.get_data()
    shift = data["shift"]
    date = datetime.now().strftime("%d.%m.%Y")
    user = mention_user(cb.from_user)

    header = "Эпизоды\\Jira" if shift in ("11-23", "20-08") else "Эпизоды"

    text = (
        "✅\n"
        f"{header} [{date}]\n"
        f"{header} обработаны.\n\n"
        f"Ответственный: {user}, смена {shift}"
    )

    await bot.send_message(REPORT_CHAT_ID, text)
    await cb.message.delete()
    await state.clear()

# ====== ДОП WARN ======
@dp.callback_query(F.data == "dop_warn")
async def dop_warn(cb, state: FSMContext):
    await cb.message.edit_text("Напиши, на кого обратить внимание:")
    await state.update_data(type="dop_warn")
    await state.set_state(ReportFSM.text)
    await cb.message.delete()

# ====== TEXT INPUT ======
@dp.message(ReportFSM.text)
async def input_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    shift = data["shift"]
    date = datetime.now().strftime("%d.%m.%Y")
    user = mention_user(msg.from_user)

    if data["type"] == "dop_warn":
        header = "Эпизоды\\Jira" if shift in ("11-23", "20-08") else "Эпизоды"
        text = (
            "⚠️\n"
            f"{header} [{date}]\n"
            f"{header} обработаны.\n"
            f"На кого стоит обратить внимание:\n{msg.text}\n\n"
            f"Ответственный: {user}, смена {shift}"
        )
    else:
        text = (
            "👀\n"
            f"ВИ [{date}]\n\n"
            f"Саммари:\n{msg.text}\n\n"
            f"Ответственный: {user}\n"
            f"Статус: требует внимания {mention_admin()}"
        )

    await bot.send_message(REPORT_CHAT_ID, text)
    await msg.delete()
    await state.clear()

# ====== STARTUP / SHUTDOWN ======
async def on_startup(bot: Bot):
    print("=== BOT COLD START ===")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    await bot.session.close()

# ====== MAIN ======
async def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return app

if __name__ == "__main__":
    web.run_app(main(), port=int(os.getenv("PORT", 8080)))
