import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from aiohttp import web

# ====== ENV ======
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

# ====== BOT ======
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
@dp.message(F.text.startswith("/start"))
async def start(msg: Message, state: FSMContext):
    try:
        await msg.delete()
    except:
        pass
    sent = await msg.answer("Выбирай смену:", reply_markup=shift_kb())
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id))

# ====== SHIFT ======
@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if await state.get_state() is not None:
        return

    shift = cb.data.split("_", 1)[1]
    await state.set_state(ReportFSM.shift)
    await state.update_data(shift=shift)

    sent = await cb.message.answer(f"Смена {shift}. Что дальше?", reply_markup=type_kb())
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id))
    asyncio.create_task(delete_later(cb.message.chat.id, cb.message.message_id, delay=1))

# ====== TYPE ======
@dp.callback_query(F.data == "type_dop")
async def type_dop(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(ReportFSM.type)
    sent = await cb.message.answer("ДОП статус:", reply_markup=dop_kb())
    asyncio.create_task(delete_later(sent.chat.id, sent.message_id))
    await cb.message.delete()

@dp.callback_query(F.data == "type_vi")
async def type_vi(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(type="vi")
    await state.set_state(ReportFSM.text)
    await cb.message.edit_text("Напиши саммари ВИ:")
    asyncio.create_task(delete_later(cb.message.chat.id, cb.message.message_id))

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
    asyncio.create_task(delete_later(cb.message.chat.id, cb.message.message_id))

# ====== TEXT ======
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
    await msg.answer("♻️ Перезапуск бота…", delete_after=1)
    raise RuntimeError("Manual restart")

# ====== WEBHOOK ======
async def handle_webhook(request: web.Request):
    data = await request.json()
    await dp.feed_raw_update(bot, data)
    return web.Response()

# ====== RUN ======
async def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    return app

if __name__ == "__main__":
    web.run_app(main(), port=int(os.getenv("PORT", 8080)))
