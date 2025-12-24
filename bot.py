from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from datetime import datetime
import os

# ====== ПЕРЕМЕННЫЕ ======
TOKEN = os.getenv("BOT_TOKEN")
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_BASE = os.getenv("WEBHOOK_URL")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== FSM ======
class ReportFSM(StatesGroup):
    shift = State()
    type = State()
    dop_status = State()
    text = State()

# ====== Кнопки ======
def shift_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"shift_{s}")]
        for s in ["8-20", "11-23", "14-02", "20-08"]
    ])

def type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ ДОП", callback_data="type_dop"),
            InlineKeyboardButton(text="👀 ВИ", callback_data="type_vi"),
        ]
    ])

def dop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Всё ок", callback_data="dop_ok"),
            InlineKeyboardButton(text="⚠️ Внимание", callback_data="dop_warn"),
        ]
    ])

# ====== Упоминания ======
def mention_user(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

def mention_admin():
    return f'<a href="tg://user?id={ADMIN_ID}">Руководитель</a>'

# ====== Хендлеры ======
@dp.message()
async def start(msg: Message, state: FSMContext):
    # сразу показываем кнопки выбора смены
    await msg.answer("Выбирай смену:", reply_markup=shift_kb())
    await state.set_state(ReportFSM.shift)

@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb, state: FSMContext):
    shift = cb.data.split("_")[1]
    await state.update_data(shift=shift)
    await cb.message.edit_text(f"Смена {shift}. Что дальше?", reply_markup=type_kb())
    await state.set_state(ReportFSM.type)

@dp.callback_query(F.data == "type_dop")
async def dop(cb, state: FSMContext):
    await cb.message.edit_text("ДОП статус:", reply_markup=dop_kb())
    await state.set_state(ReportFSM.dop_status)

@dp.callback_query(F.data == "dop_ok")
async def dop_ok(cb, state: FSMContext):
    data = await state.get_data()
    date = datetime.now().strftime("%d.%m.%Y")
    user_mention = mention_user(cb.from_user)
    text = (
        "✅\n"
        f"Эпизоды\\Jira [{date}]\n"
        "Эпизоды\\Jira обработаны.\n\n"
        f"Ответственный: {user_mention}, смена {data['shift']}"
    )
    await bot.send_message(REPORT_CHAT_ID, text)
    await state.clear()
    await cb.message.delete()  # удаляем сообщение с кнопками

@dp.callback_query(F.data == "dop_warn")
async def dop_warn(cb, state: FSMContext):
    await cb.message.edit_text("Напиши, на кого обратить внимание:")
    await state.set_state(ReportFSM.text)
    await state.update_data(dop_warn=True)

@dp.callback_query(F.data == "type_vi")
async def vi(cb, state: FSMContext):
    await cb.message.edit_text("Напиши саммари ВИ:")
    await state.set_state(ReportFSM.text)
    await state.update_data(dop_vi=True)

@dp.message(ReportFSM.text)
async def input_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    date = datetime.now().strftime("%d.%m.%Y")
    user_mention = mention_user(msg.from_user)

    if data.get("dop_warn"):
        text = (
            "⚠️\n"
            f"Эпизоды [{date}]\n"
            "Эпизоды обработаны.\n"
            f"На кого стоит обратить внимание:\n{msg.text}\n\n"
            f"Ответственный: {user_mention}, смена {data['shift']}"
        )
    elif data.get("dop_vi") or data.get("type_vi"):
        text = (
            "👀\n"
            f"[ВИ] [{date}]\n\n"
            f"Саммари:\n{msg.text}\n\n"
            f"Ответственный: {user_mention}\n"
            f"Статус: требует внимания {mention_admin()}"
        )
    else:
        text = "Неопределённый сценарий"

    await bot.send_message(REPORT_CHAT_ID, text)
    await state.clear()
    await msg.delete()  # удаляем сообщение пользователя с текстом

# ===== Startup / Shutdown =====
async def on_startup(bot: Bot):
    print("=== BOT COLD START ===")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    await bot.session.close()

# ===== Main =====
async def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return app

if __name__ == "__main__":
    web.run_app(main(), port=int(os.getenv("PORT", 8080)))
