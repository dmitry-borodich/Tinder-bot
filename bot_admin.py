
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
import aiosqlite
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import BotCommand
from dotenv import load_dotenv
import os

load_dotenv()

bot_admin = Bot(token=os.getenv('ADMIN_TOKEN'))
dp_admin = Dispatcher()
other_bot = Bot(token=os.getenv('BOT_TOKEN'))


async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="complaints", description="Работа с жалобами"),
        BotCommand(command="add_event", description="Добавить событие")
    ]
    await bot_admin.set_my_commands(commands)


class AdminStates(StatesGroup):
    event_name = State()
    event_date = State()
    event_description = State()
    event_photo = State()
    event_address = State()

complaint_states = {}

async def is_admin(user_id):
    async with aiosqlite.connect('petdating.db') as db:
        async with db.execute("SELECT AdminUserId FROM Admins") as cursor:
            admins = await cursor.fetchall()
    admin_ids = [int(admin[0]) for admin in admins]
    return int(user_id) in admin_ids

# Команда старта для бота-администратора
@dp_admin.message(Command("start"))
async def send_welcome(message: Message):
    if await is_admin(message.from_user.id):
        await message.answer("Привет, администратор! Ознакомиться с командами можно в меню")
    else:
        await message.answer("У вас нет доступа")

# Команда для просмотра жалоб
@dp_admin.message(Command("complaints"))
async def show_complaints(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    async with (aiosqlite.connect('petdating.db') as db):
        async with db.execute('''
            SELECT r.ReportDescription, u.UserId, u.PetName, u.Age, u.Breed, u.About FROM Reports r
            JOIN UserProfiles u ON r.ReportedId = u.UserId''') as cursor:
            complaints = await cursor.fetchall()

    if not complaints:
        await message.answer("Жалоб пока нет", reply_markup=types.ReplyKeyboardRemove())
        return

    complaint_states[message.from_user.id] = {"complaints": complaints, "index": 0}
    await send_next_complaint(message)

async def send_next_complaint(message: Message):
    state = complaint_states.get(message.from_user.id)
    if not state or state["index"] >= len(state["complaints"]):
        await message.answer("Все жалобы просмотрены", reply_markup=types.ReplyKeyboardRemove())
        complaint_states.pop(message.from_user.id, None)
        return

    complaint = state["complaints"][state["index"]]
    complaint_id, user_id, pet_name, age, breed, about = complaint

    caption = f"Жалоба:\nИмя: {pet_name}\nВозраст: {age} лет\nПорода: {breed}\nОписание: {about}\nПричина жалобы: {complaint_id}"

    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Удалить анкету"), KeyboardButton(text="✅ Оставить анкету")],
        [KeyboardButton(text="💤 Остановить")]
    ], resize_keyboard=True)

    await message.answer(caption, reply_markup=keyboard)

    state["index"] += 1

    @dp_admin.message(F.text.in_({"❌ Удалить анкету", "✅ Оставить анкету", "💤 Остановить"}))
    async def handle_complaint_action(message: Message):
        user_id = message.from_user.id
        state = complaint_states.get(user_id)

        if not state:
            await message.answer("Просмотр жалоб не активен")
            return

        if message.text == "💤 Остановить":
            complaint_states.pop(user_id, None)
            await message.answer("Вы остановили просмотр жалоб")
            return

        complaint = state["complaints"][state["index"] - 1]
        complaint_id, target_user_id, *_ = complaint

        async with aiosqlite.connect('petdating.db') as db:
            if message.text == "❌ Удалить анкету":
                await db.execute('DELETE FROM UserProfiles WHERE UserId = ?', (target_user_id,))
                await db.execute('DELETE FROM Reports WHERE ReportedId = ?', (target_user_id,))
                await message.answer("Анкета удалена")
                try:
                    await other_bot.send_message(
                        chat_id=target_user_id,
                        text="Ваша анкета была удалена администратором, вы можете заполнить новую в соответствии с требованиями"
                    )
                except Exception as e:
                    await message.answer(f"Не удалось уведомить пользователя: {e}")
            elif message.text == "✅ Оставить анкету":
                await db.execute('DELETE FROM Complaints WHERE ComplaintId = ?', (complaint_id,))
                await message.answer("Анкета оставлена.")
            await db.commit()

        await send_next_complaint(message)

# Команда для добавления события
@dp_admin.message(Command("add_event"))
async def add_event(message: types.Message, state = FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        return
    await message.answer("Введите название события:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Прекратить создание события")]
        ],
        resize_keyboard=True,
    ))
    await state.set_state(AdminStates.event_name)

@dp_admin.message(AdminStates.event_name)
async def get_pet_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        await state.clear()
        return
    if message.text == "Прекратить создание события":
        await state.clear()
        await message.reply("Создание события прекращено", reply_markup=types.ReplyKeyboardRemove())
        return
    event_name = message.text
    await state.update_data(event_name=event_name)
    await message.reply(f"Введите адрес события")
    await state.set_state(AdminStates.event_address)

# ввод возраста
@dp_admin.message(AdminStates.event_address)
async def get_age(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        await state.clear()
        return
    if message.text == "Прекратить создание события":
        await state.clear()
        await message.reply("Создание события прекращено", reply_markup=types.ReplyKeyboardRemove())
        return
    event_address = message.text
    await state.update_data(event_address=event_address)
    await message.reply(f"Введите дату обытия в формате YYYY-MM-DD")
    await state.set_state(AdminStates.event_date)

# ввод породы
@dp_admin.message(AdminStates.event_date)
async def get_breed(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        await state.clear()
        return
    if message.text == "Прекратить создание события":
        await state.clear()
        await message.reply("Создание события прекращено", reply_markup=types.ReplyKeyboardRemove())
        return
    event_date = message.text
    await state.update_data(event_date=event_date)
    await message.reply(f"Введите описание события")
    await state.set_state(AdminStates.event_description)

# ввод описания
@dp_admin.message(AdminStates.event_description)
async def get_about(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа")
        await state.clear()
        return
    if message.text == "Прекратить создание события":
        await state.clear()
        await message.reply("Создание события прекращено", reply_markup=types.ReplyKeyboardRemove())
        return
    event_description = message.text
    await state.update_data(event_description = event_description)
    data = await state.get_data()
    event_name = data['event_name']
    event_address = data['event_address']
    event_description = data['event_description']
    event_date = data['event_date']

    await state.clear()

    await save_event(event_name, event_description, event_date, event_address)

    await message.answer("Так выглядит добавленное событие:", reply_markup=types.ReplyKeyboardRemove())

    caption = f"Название: {event_name}\nДата проведения: {event_date}\nАдрес проведения: {event_address}\nОписание: {event_description}"

    await message.answer(caption)

async def save_event(event_name, event_description, event_date, event_address):
    async with aiosqlite.connect('petdating.db') as db:
        await db.execute('''
            INSERT OR REPLACE INTO Events (EventName, Description, EventDate, Address)
            VALUES (?, ?, ?, ?)
        ''', (event_name, event_description, event_date, event_address))
        await db.commit()

async def main():
    await set_bot_commands()
    await dp_admin.start_polling(bot_admin)

if __name__ == "__main__":
    asyncio.run(main())