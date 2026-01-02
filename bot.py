import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ====== ENV ======
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID"))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# ====== BOT & DISPATCHER ======
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
        InlineKeyboardButton(text="👀 ВИ", callback_data="type_vi")
    ]])

def dop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Всё ок", callback_data="dop_ok"),
        InlineKeyboardButton(text="⚠️ Внимание", callback_data="dop_warn")
    ]])

# ====== HELPERS ======
def mention_user(user):
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

def mention_admin():
    return f'<a href="tg://user?id={ADMIN_ID}">руководитель</a>'

async def delete_later(chat_id: int, message_id: int, delay: int = 60):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

# ====== START ======
@dp.message(F.text.regexp(r"^/start(@\w+)?$"))
async def start(msg: Message, state: FSMContext):
    try:
        await msg.delete()
    except:
        pass
    await state.clear()
    sent = await msg.answer("Выбирай смену:", reply_markup=shift_kb())
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id, delay=60))

# ====== SHIFT ======
@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    shift = cb.data.split("_", 1)[1]
    await state.set_state(ReportFSM.shift)
    await state.update_data(shift=shift)
    sent = await cb.message.answer(f"Смена {shift}. Что дальше?", reply_markup=type_kb())
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id, delay=60))
    await cb.message.delete()

# ====== TYPE ======
@dp.callback_query(F.data == "type_dop")
async def type_dop(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(ReportFSM.type)
    sent = await cb.message.answer("ДОП статус:", reply_markup=dop_kb())
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id, delay=60))
    await cb.message.delete()

@dp.callback_query(F.data == "type_vi")
async def type_vi(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(type="vi")
    await state.set_state(ReportFSM.text)
    await cb.message.edit_text("Напиши саммари ВИ:")
    asyncio.create_task(delete_later(cb.message.chat.id, cb.message.message_id, delay=60))

# ====== ДОП OK ======
@dp.callback_query(F.data == "dop_ok")
async def dop_ok(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
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
async def dop_warn(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(type="dop_warn")
    await state.set_state(ReportFSM.text)
    await cb.message.edit_text("Напиши, на кого обратить внимание:")
    asyncio.create_task(delete_later(cb.message.chat.id, cb.message.message_id, delay=60))

# ====== TEXT INPUT ======
@dp.message(ReportFSM.text)
async def input_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    shift = data["shift"]
    date = datetime.now().strftime("%d.%m.%Y")
    user = mention_user(msg.from_user)
    header = "Эпизоды\\Jira" if shift in ("11-23", "20-08") else "Эпизоды"
    if data.get("type") == "dop_warn":
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

# ====== RESTART ======
@dp.message(F.text.regexp(r"^/restart(@\w+)?$"))
async def restart(msg: Message):
    try:
        await msg.delete()
    except:
        pass
    sent = await msg.answer("♻️ Перезапуск бота")  # Убрали delete_after
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id, delay=1))  # Отложенное удаление через 1 сек
    os._exit(1)  # Форсированный рестарт

# ====== STARTUP для webhook ======
async def on_startup(bot: Bot) -> None:
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)

dp.startup.register(on_startup)

# ====== RUN WEBHOOK ======
if __name__ == "__main__":
    app = web.Application()
    
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
