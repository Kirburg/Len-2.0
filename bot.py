import os
import asyncio
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties

# ====== ENV ======
TOKEN = os.getenv("BOT_TOKEN")
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ====== INIT ======
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

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

async def allow_click(state: FSMContext, cooldown=1.5):
    data = await state.get_data()
    now = time.time()
    if now - data.get("last_click", 0) < cooldown:
        return False
    await state.update_data(last_click=now)
    return True

async def delete_later(chat_id: int, message_id: int, delay=60):
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
    await state.clear()

# ====== SHIFT ======
@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if not await allow_click(state):
        return

    shift = cb.data.split("_", 1)[1]
    await state.update_data(shift=shift)

    msg = await cb.message.edit_text(
        f"Смена {shift}. Что дальше?",
        reply_markup=type_kb()
    )
    asyncio.create_task(delete_later(msg.chat.id, msg.message_id))

# ====== TYPE ======
@dp.callback_query(F.data == "type_dop")
async def type_dop(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if not await allow_click(state):
        return

    msg = await cb.message.edit_text("ДОП статус:", reply_markup=dop_kb())
    asyncio.create_task(delete_later(msg.chat.id, msg.message_id))

@dp.callback_query(F.data == "type_vi")
async def type_vi(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if not await allow_click(state):
        return

    await state.update_data(type="vi")
    await state.set_state(ReportFSM.text)
    await cb.message.delete()

# ====== ДОП OK ======
@dp.callback_query(F.data == "dop_ok")
async def dop_ok(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if not await allow_click(state):
        return

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
    if not await allow_click(state):
        return

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

# ====== RESTART ======
@dp.message(F.text.regexp(r"^/restart(@\w+)?$"))
async def restart(msg: Message):
    try:
        await msg.delete()
    except:
        pass

    await msg.answer("♻️ Перезапуск…", delete_after=2)
    await asyncio.sleep(0.3)
    os._exit(1)

# ====== RUN ======
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
