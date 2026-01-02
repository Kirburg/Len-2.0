import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.filters import Command
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
    default=DefaultBotProperties(parse_mode="HTML"),
)

dp = Dispatcher(storage=MemoryStorage())

# ====== FSM ======
class ReportFSM(StatesGroup):
    shift = State()
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

def header_by_shift(shift: str) -> str:
    return "Эпизоды\\Jira" if shift in ("11-23", "20-08") else "Эпизоды"

async def auto_delete(chat_id: int, msg_id: int, delay: int = 60):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, msg_id)
    except:
        pass

async def delete_old_menu(state: FSMContext, chat_id: int):
    data = await state.get_data()
    old_id = data.get("menu_msg_id")
    if old_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except:
            pass

# ====== START ======
@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    try:
        await msg.delete()
    except:
        pass

    await delete_old_menu(state, msg.chat.id)
    await state.clear()

    menu = await msg.answer("Выбирай смену:", reply_markup=shift_kb())
    await state.update_data(menu_msg_id=menu.message_id)

    asyncio.create_task(
        auto_delete(menu.chat.id, menu.message_id, 60)
    )

# ====== SHIFT ======
@dp.callback_query(F.data.startswith("shift_"))
async def choose_shift(cb, state: FSMContext):
    await cb.answer()

    if await state.get_state() is not None:
        return

    shift = cb.data.split("_", 1)[1]
    await state.update_data(shift=shift)

    await delete_old_menu(state, cb.message.chat.id)

    msg = await cb.message.edit_text(
        f"Смена {shift}. Что дальше?",
        reply_markup=type_kb()
    )

    await state.update_data(menu_msg_id=msg.message_id)
    asyncio.create_task(
        auto_delete(msg.chat.id, msg.message_id, 60)
    )

# ====== TYPE ======
@dp.callback_query(F.data == "type_dop")
async def type_dop(cb, state: FSMContext):
    await cb.answer()
    await delete_old_menu(state, cb.message.chat.id)

    msg = await cb.message.edit_text(
        "ДОП статус:",
        reply_markup=dop_kb()
    )

    await state.update_data(menu_msg_id=msg.message_id)
    asyncio.create_task(
        auto_delete(msg.chat.id, msg.message_id, 60)
    )

@dp.callback_query(F.data == "type_vi")
async def type_vi(cb, state: FSMContext):
    await cb.answer()
    await delete_old_menu(state, cb.message.chat.id)

    await cb.message.edit_text("Напиши саммари ВИ:")
    await state.update_data(type="vi")
    await state.set_state(ReportFSM.text)

# ====== ДОП OK ======
@dp.callback_query(F.data == "dop_ok")
async def dop_ok(cb, state: FSMContext):
    await cb.answer()
    data = await state.get_data()

    shift = data["shift"]
    header = header_by_shift(shift)
    date = datetime.now().strftime("%d.%m.%Y")
    user = mention_user(cb.from_user)

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
    await cb.answer()
    await delete_old_menu(state, cb.message.chat.id)

    await cb.message.edit_text("Напиши, на кого обратить внимание:")
    await state.update_data(type="dop_warn")
    await state.set_state(ReportFSM.text)

# ====== TEXT INPUT ======
@dp.message(ReportFSM.text)
async def input_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    shift = data["shift"]
    header = header_by_shift(shift)
    date = datetime.now().strftime("%d.%m.%Y")
    user = mention_user(msg.from_user)

    if data["type"] == "dop_warn":
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

    try:
        await msg.delete()
    except:
        pass

    await state.clear()

# ====== RESTART ======
@dp.message(Command("restart"))
async def restart_bot(msg: Message):
    try:
        await msg.delete()
    except:
        pass

    await msg.answer("♻️ Перезапуск бота…")
    await asyncio.sleep(1)
    os._exit(0)

# ====== RUN (polling для локала / теста) ======
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
