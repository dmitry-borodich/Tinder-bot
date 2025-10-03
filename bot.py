import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command
from geopy.distance import geodesic
import aiosqlite
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
import os

load_dotenv()

bot = Bot(token=os.getenv('MAIN_TOKEN'))
dp = Dispatcher()


async def init_db():
    async with aiosqlite.connect('petdating.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS UserProfiles (
                UserId INT PRIMARY KEY,
                PetName TEXT,
                Age INT,
                Breed TEXT,
                About TEXT,
                Photo TEXT,
                LinkOnUserName TEXT,
                Latitude REAL,
                Longitude REAL,
                ChatId INT
            )
        ''')
        # await db.execute('''
        #     INSERT INTO UserProfiles(UserId, PetName, Age, Breed, About, Photo, LinkOnUserName, Latitude, Longitude, ChatId)
        #     VALUES
        #     (123123, 'fwe', 12, 'fewdw', 'wcecwc', NULL, 'dkwekcow', 53.775228, 27.580525, NULL),
        #     (1231234243, 'fwwcdwcwcde', 1332, 'fewdcwcww', 'wcewevcwc', NULL, 'dkwekccwcow', 53.557762, 27.431647, NULL),
        #     (123, 'e', 12, 'w', 'c', NULL, 'w', 53.917259, 27.568753, NULL)
        # ''')
        await db.execute('''
           CREATE TABLE IF NOT EXISTS Likes (
               UserId INT REFERENCES UserProfiles (UserId),
               ViewedId INT REFERENCES UserProfiles (UserId),
               State TEXT,
               ViewedByUser BOOLEAN DEFAULT 0
           )
       ''')
        await db.execute('''
                   CREATE TABLE IF NOT EXISTS Reports (
                       UserId INT REFERENCES UserProfiles (UserId),
                       ReportedId INT REFERENCES UserProfiles (UserId),
                       ReportDescription TEXT
                   )
               ''')
        await db.execute('''
                     CREATE TABLE IF NOT EXISTS Events (
                         EventName TEXT,
                         Description TEXT,
                         EventDate DATE,
                         Address TEXT,
                         Photo TEXT
                     )
                 ''')
        await db.commit()
        await db.execute('''
                     CREATE TABLE IF NOT EXISTS Admins (
                         AdminUserId TEXT,
                         AdminChatId TEXT DEFAULT NULL
                     )
                 ''')
        await db.commit()

async def reset_db():
    async with aiosqlite.connect('petdating.db') as db:
        # await db.execute('DROP TABLE IF EXISTS UserProfiles')
        await db.execute('DROP TABLE IF EXISTS Likes')
        await db.execute('DROP TABLE IF EXISTS Events')
        # await db.execute('DROP TABLE IF EXISTS Reports')
        await db.commit()


# сохранение профиля
async def save_profile(user_id, pet_name, age, breed, about, photo, link, latitude, longitude, chat_id):
    async with aiosqlite.connect('petdating.db') as db:
        await db.execute('''
            INSERT OR REPLACE INTO UserProfiles (UserId, PetName, Age, Breed, About, Photo, LinkOnUserName, Latitude, Longitude, ChatId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, pet_name, age, breed, about, photo, link, latitude, longitude, chat_id))
        await db.commit()


async def get_profile_by_id(user_id):
    async with aiosqlite.connect('petdating.db') as db:
        async with db.execute('SELECT * FROM UserProfiles WHERE UserId = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def delete_profile(user_id):
    async with aiosqlite.connect('petdating.db') as db:
        await db.execute('DELETE FROM UserProfiles WHERE UserId = ?', (user_id,))
        await db.commit()

# профили для поиска
async def get_all_profiles(user_id):
    try:
        async with aiosqlite.connect('petdating.db') as db:
            async with db.execute('SELECT * FROM UserProfiles WHERE UserId != ?', (user_id,)) as cursor:
                return await cursor.fetchall()
    except Exception as e:
        print(f"Ошибка при получении профилей: {e}")
        return []

# стандарт клавиатура
def default_keyboard():
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Анкета \ud83d\udd8d")],[KeyboardButton(text="Посмотреть лайки 💌")],[KeyboardButton(text="Поиск \ud83d\udd0e")], [KeyboardButton(text="События \ud83c\udf89")]
        ],
        resize_keyboard=True,
    )
    return markup

# cостояния
class ProfileForm(StatesGroup):
    pet_name = State()
    age = State()
    breed = State()
    about = State()
    photo = State()
    location = State()
    edit_pet_name = State()
    edit_age = State()
    edit_breed = State()
    edit_about = State()
    edit_photo = State()
    edit_location = State()
    search_all_profiles = State()
    search_nearby_profiles = State()
    waiting_for_reason = State()

user_states = {}  # {user_id: {"profiles": list, "index": int, "stop": bool}}

async def print_profile(message: Message, user_id: int, state: FSMContext):
    await message.answer("Так выглядит ваша анкета:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Изменить анкету")], [KeyboardButton(text="Удалить анкету")],
            [KeyboardButton(text="Главное меню")]
        ],
        resize_keyboard=True,
    ))
    profile = await get_profile_by_id(user_id)
    pet_name, age, breed, about, photo = profile[1], profile[2], profile[3], profile[4], profile[5]
    caption = f"Имя: {pet_name}\nВозраст: {age} лет\nПорода: {breed}\nОписание: {about}"

    if photo:
        await message.answer_photo(photo, caption=caption)
    else:
        await message.answer(caption)

# /start
@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.reply("Привет, здесь ты можешь найти своему питомцу пару!", reply_markup=default_keyboard())

# создание профиля
@dp.message(F.text == "Анкета 🖍")
async def start_profile_creation(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время", reply_markup=default_keyboard())
        return
    if await get_profile_by_id(message.from_user.id):
        await print_profile(message=message, user_id=message.from_user.id, state=state)
    else:
        await message.reply("У вас еще нет анкеты, давайте ее создадим", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Прекратить заполнение анкеты")]
        ],
        resize_keyboard=True,
        ))
        await message.answer("Как зовут вашего питомца?")
        await state.set_state(ProfileForm.pet_name)

# ввод имени питомца
@dp.message(ProfileForm.pet_name)
async def get_pet_name(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время", reply_markup=default_keyboard())
        return
    pet_name = message.text
    await state.update_data(pet_name=pet_name)
    await message.reply(f"Сколько лет вашему питомцу?")
    await state.set_state(ProfileForm.age)

# ввод возраста
@dp.message(ProfileForm.age)
async def get_age(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время", reply_markup=default_keyboard())
        return
    age = message.text
    if age is not None and age.isdigit() and int(age) > 0:
        await state.update_data(age=age)
        await message.reply(f"Какая порода у вашего питомца?")
        await state.set_state(ProfileForm.breed)
    else:
        await message.reply(f"Возраст должен быть целым числом больше 0, попробуйте еще раз")

# ввод породы
@dp.message(ProfileForm.breed)
async def get_breed(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время", reply_markup=default_keyboard())
        return
    breed = message.text
    await state.update_data(breed=breed)
    await message.reply(f"Напишите описание питомца?")
    await state.set_state(ProfileForm.about)

# ввод описания
@dp.message(ProfileForm.about)
async def get_about(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время", reply_markup=default_keyboard())
        return
    about = message.text
    await state.update_data(about=about)
    await message.reply("Пожалуйста, отправьте фотографию питомца.")
    await state.set_state(ProfileForm.photo)

# ввод фото
@dp.message(ProfileForm.photo, F.content_type == 'photo')
async def get_photo(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время",breply_markup=default_keyboard())
        return
    file_id = message.photo[-1].file_id
    await state.update_data(photo = file_id)
    await message.reply("Теперь отправьте вашу локацию")
    await state.set_state(ProfileForm.location)

# ввод локации
@dp.message(ProfileForm.location, F.content_type == 'location')
async def get_location(message: Message, state: FSMContext):
    if message.text == "Прекратить заполнение анкеты":
        await state.clear()
        await message.reply("Заполнение анкеты прекращено, вы можеете заполнить ее заново в любое время", reply_markup=default_keyboard())
        return
    latitude = message.location.latitude if message.location else None
    longitude = message.location.longitude if message.location else None
    link_on_username = message.from_user.username
    chat_id = message.chat.id

    data = await state.get_data()
    pet_name = data['pet_name']
    age = data['age']
    breed = data['breed']
    about = data['about']
    photo = data['photo']

    await save_profile(message.from_user.id, pet_name, age, breed, about, photo, link_on_username, latitude, longitude, chat_id)

    await print_profile(message=message, user_id=message.from_user.id, state=state)
    await state.clear()

# "Главное меню"
@dp.message(F.text == "Главное меню")
async def return_to_main_menu(message: Message):
    await message.reply("Вы вернулись в главное меню", reply_markup=default_keyboard())

# "Удалить анкету"
@dp.message(F.text == "Удалить анкету")
async def delete_user_profile(message: Message):
    user_id = message.from_user.id
    await delete_profile(user_id)
    await message.reply("Ваша анкета удалена, вы можете заполнить ее заново в любое время", reply_markup=default_keyboard())

# "Изменить анкету"
@dp.message(F.text == "Изменить анкету")
async def edit_user_profile(message: Message, state: FSMContext):
    if not await get_profile_by_id(message.from_user.id):
        await message.reply("У вас еще нет анкеты, давайте ее создадим", reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Прекратить заполнение анкеты")]
            ],
            resize_keyboard=True,
        ))
        await message.answer("Как зовут вашего питомца?")
        await state.set_state(ProfileForm.pet_name)
        return

    button1 = types.InlineKeyboardButton(text="Имя", callback_data='edit_pet_name')
    button2 = types.InlineKeyboardButton(text="Возраст", callback_data='edit_age')
    button3 = types.InlineKeyboardButton(text="Порода", callback_data='edit_breed')
    button4 = types.InlineKeyboardButton(text="Описание", callback_data='edit_about')
    button5 = types.InlineKeyboardButton(text="Фото", callback_data='edit_photo')
    button6 = types.InlineKeyboardButton(text="Локация", callback_data='edit_location')
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [button1, button2], [button3, button4], [button5, button6]
        ],
        row_width=2
    )

    await message.reply("Что хотели бы изменить?", reply_markup=keyboard)

# инлайн кнопки изменения профиля
@dp.callback_query()
async def process_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)

    if not await get_profile_by_id(callback_query.from_user.id):
        await bot.send_message(callback_query.from_user.id,"У вас еще нет анкеты, давайте ее создадим", reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Прекратить заполнение анкеты")]
            ],
            resize_keyboard=True,
        ))
        await bot.send_message(callback_query.from_user.id,"Как зовут вашего питомца?")
        await state.set_state(ProfileForm.pet_name)
        return

    if callback_query.data == 'edit_pet_name':
        await state.set_state(ProfileForm.edit_pet_name)
        await bot.send_message(callback_query.from_user.id, "Введите новое имя:")
    elif callback_query.data == 'edit_age':
        await state.set_state(ProfileForm.edit_age)
        await bot.send_message(callback_query.from_user.id, "Введите новый возраст:")
    elif callback_query.data == 'edit_breed':
        await state.set_state(ProfileForm.edit_breed)
        await bot.send_message(callback_query.from_user.id, "Введите новую породу:")
    elif callback_query.data == 'edit_about':
        await state.set_state(ProfileForm.edit_about)
        await bot.send_message(callback_query.from_user.id, "Введите новое описание:")
    elif callback_query.data == 'edit_photo':
        await state.set_state(ProfileForm.edit_photo)
        await bot.send_message(callback_query.from_user.id, "Отправьте новое фото:")
    elif callback_query.data == 'edit_location':
        await state.set_state(ProfileForm.edit_location)
        await bot.send_message(callback_query.from_user.id, "Отправьте вашу новую локацию:")
    if callback_query.data == 'nearby_profiles':
        await start_profile_sending(callback_query.from_user.id, callback_query.message, True)
    elif callback_query.data == 'all_profiles':
        await start_profile_sending(callback_query.from_user.id, callback_query.message, False)

    await callback_query.answer()

async def update_profile(user_id, field, value):
    async with aiosqlite.connect('petdating.db') as db:
        query = f"UPDATE UserProfiles SET {field} = ? WHERE UserId = ?"
        await db.execute(query, (value, user_id))
        await db.commit()

# обновление профиля
@dp.message(ProfileForm.edit_pet_name)
async def update_pet_name(message: Message, state: FSMContext):
    new_name = message.text
    await update_profile(user_id=message.from_user.id, field="PetName", value=new_name)
    await print_profile(message=message, user_id=message.from_user.id, state=state)
    await state.clear()

@dp.message(ProfileForm.edit_age)
async def update_age(message: Message, state: FSMContext):
    new_age = message.text
    if new_age is not None and new_age.isdigit() and int(new_age) > 0:
        await update_profile(user_id=message.from_user.id, field="Age", value=new_age)
        await print_profile(message=message, user_id=message.from_user.id, state=state)
        await state.clear()
    else:
        await message.reply(f"Возраст должен быть целым числом больше 0, попробуйте еще раз")

@dp.message(ProfileForm.edit_breed)
async def update_breed(message: Message, state: FSMContext):
    new_breed = message.text
    await update_profile(user_id=message.from_user.id, field="Breed", value=new_breed)
    await print_profile(message=message, user_id=message.from_user.id, state=state)
    await state.clear()

@dp.message(ProfileForm.edit_about)
async def update_about(message: Message, state: FSMContext):
    new_about = message.text
    await update_profile(user_id=message.from_user.id, field="About", value=new_about)
    await print_profile(message=message, user_id=message.from_user.id, state=state)
    await state.clear()

@dp.message(ProfileForm.edit_photo, F.content_type == 'photo')
async def update_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await update_profile(user_id=message.from_user.id, field="Photo", value=file_id)
    await print_profile(message=message, user_id=message.from_user.id, state=state)
    await state.clear()

@dp.message(ProfileForm.edit_location, F.content_type == 'location')
async def update_location(message: Message, state: FSMContext):
    latitude = message.location.latitude if message.location else None
    longitude = message.location.longitude if message.location else None
    async with aiosqlite.connect('petdating.db') as db:
        await db.execute(
            "UPDATE UserProfiles SET Latitude = ?, Longitude = ? WHERE UserId = ?",
            (latitude, longitude, message.from_user.id),
        )
        await db.commit()
    await message.reply("Локация обновлена!")
    await print_profile(message=message, user_id=message.from_user.id, state=state)
    await state.clear()

# "Поиск"
@dp.message(F.text == "Поиск 🔎")
async def search_profiles(message: Message, state: FSMContext):
    if not await get_profile_by_id(message.from_user.id):
        await message.reply("У вас еще нет анкеты, давайте ее создадим", reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Прекратить заполнение анкеты")]
            ],
            resize_keyboard=True,
        ))
        await message.answer("Как зовут вашего питомца?")
        await state.set_state(ProfileForm.pet_name)
        return

    button1 = types.InlineKeyboardButton(text="Поблизости", callback_data='nearby_profiles')
    button2 = types.InlineKeyboardButton(text="Все анкеты", callback_data='all_profiles')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[ [button1, button2] ])

    await message.reply("Выберите критерии поиска", reply_markup=keyboard)

@dp.message(F.text.in_({"❤️", "👎", "💤"}))
async def handle_reaction(message: Message):
    text = message.text
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state:
        await message.answer("Поиск анкет не активен", reply_markup=default_keyboard())
        return

    if message.text == "💤":
        state["stop"] = True
        await message.answer("Вы остановили просмотр анкет", reply_markup=default_keyboard())
        user_states.pop(user_id, None)
        return

    if state["index"] > 0:
        previous_profile = state["profiles"][state["index"] - 1][0]
        profile_id = previous_profile[0]
        reaction = {
            "❤️": "like",
            "👎": "dislike",
        }[message.text]

        async with aiosqlite.connect('petdating.db') as db:
            await db.execute(
                '''INSERT OR REPLACE INTO Likes (UserId, ViewedId, State) VALUES (?, ?, ?)''',
                (user_id, profile_id, reaction)
            )
            await db.commit()

        if text == "❤️":
            async with aiosqlite.connect('petdating.db') as db:
                async with db.execute("SELECT ChatId FROM UserProfiles WHERE UserId = ?", (profile_id,)) as cursor:
                    user_info = await cursor.fetchone()
                    if user_info:
                        chat_id = user_info[0]
            await bot.send_message(chat_id, "Ваша анкета понравилась пользователю!")

    await send_next_profile(message, user_id)

async def start_profile_sending(user_id, message: Message, show_distance: bool):
    if show_distance:
        profiles = await get_nearby_profiles(user_id)
    else:
        profiles = await get_all_profiles(user_id)
    if not profiles:
        await message.answer("К сожалению, доступных анкет нет")
        return

    user_states[user_id] = {"profiles": profiles, "index": 0, "stop": False}
    await send_next_profile(message, user_id)

async def send_next_profile(message: Message, user_id: int):
    state = user_states.get(user_id)
    if not state or state["stop"]:
        await message.answer("Вы остановили просмотр анкет", reply_markup=default_keyboard())
        user_states.pop(user_id, None)
        return
    if not state or state["index"] >= len(state["profiles"]):
        await message.answer("Анкеты закончились", reply_markup=default_keyboard())
        user_states.pop(user_id, None)
        return

    profile, distance = state["profiles"][state["index"]]
    pet_name, age, breed, about, photo, profile_id = profile[1], profile[2], profile[3], profile[4], profile[5], profile[0]
    caption = f"Имя: {pet_name}\nВозраст: {age} лет\nПорода: {breed}\nОписание: {about}\n📍 Расстояние: {distance:.2f} км"

    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text = "❤️"), KeyboardButton(text = "👎")],
        [KeyboardButton(text = "Пожаловаться 🔞"), KeyboardButton(text = "💤")]
    ], resize_keyboard=True)
    if photo:
        await bot.send_photo(message.chat.id, photo, caption=caption, reply_markup=keyboard)
    else:
        await message.answer(caption, reply_markup=keyboard)

    state["index"] += 1


# Обработка нажатия на кнопку "пожаловаться"
@dp.message(F.text == "Пожаловаться 🔞")
async def handle_complaint(message: types.Message, state: FSMContext):
    userstate = user_states.get(message.from_user.id)
    if not userstate:
        await message.answer("Вы не в поиске анкет", reply_markup = default_keyboard())
        return
    await message.reply("Напишите причину жалобы:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(ProfileForm.waiting_for_reason)

# Обработка ввода причины жалобы
@dp.message(ProfileForm.waiting_for_reason)
async def process_complaint(message: types.Message, state: FSMContext):
    complaint_reason = message.text
    user_id = message.from_user.id
    userstate = user_states.get(user_id)
    previous_profile = userstate["profiles"][userstate["index"] - 1][0]
    profile_id = previous_profile[0]

    async with aiosqlite.connect('petdating.db') as db:
        await db.execute(
            '''INSERT OR REPLACE INTO Reports (UserId, ReportedId, ReportDescription) VALUES (?, ?, ?)''',
            (user_id, profile_id, complaint_reason)
        )
        await db.execute(
            '''INSERT OR REPLACE INTO Likes (UserId, ViewedId, State) VALUES (?, ?, ?)''',
            (user_id, profile_id, "dislike")
        )
        await db.commit()
    await message.reply("Спасибо за ваше сообщение, мы рассмотрим вашу жалобу, продолжаем поиск анкет")

    await state.clear()
    await send_next_profile(message, user_id)

async def get_nearby_profiles(user_id, max_distance_km=100):
    async with aiosqlite.connect('petdating.db') as db:
        user = await get_profile_by_id(user_id)
        if user and user[-3] and user[-2]:
            user_location = (user[-3], user[-2])

            async with db.execute('''
                SELECT ViewedId FROM Likes WHERE UserId = ?
                UNION
                SELECT UserId FROM Likes WHERE ViewedId = ?
            ''', (user_id, user_id)) as cursor:
                excluded_ids = {row[0] for row in await cursor.fetchall()}

            async with db.execute('SELECT * FROM UserProfiles WHERE UserId != ?', (user_id,)) as cursor:
                profiles = await cursor.fetchall()
                nearby_profiles = []
                for profile in profiles:
                    if profile[0] not in excluded_ids and profile[-3] and profile[-2]:
                        profile_location = (profile[-3], profile[-2])
                        distance = geodesic(user_location, profile_location).kilometers
                        if distance <= max_distance_km:
                            nearby_profiles.append((profile, distance))
                return sorted(nearby_profiles, key=lambda x: x[1])
        return []


async def get_all_profiles(user_id):
    async with aiosqlite.connect('petdating.db') as db:
        user = await get_profile_by_id(user_id)
        if user and user[-3] and user[-2]:
            user_location = (user[-3], user[-2])

            async with db.execute('''
                       SELECT ViewedId FROM Likes WHERE UserId = ?
                       UNION
                       SELECT UserId FROM Likes WHERE ViewedId = ?
                   ''', (user_id, user_id)) as cursor:
                excluded_ids = {row[0] for row in await cursor.fetchall()}

            async with db.execute('SELECT * FROM UserProfiles WHERE UserId != ?', (user_id,)) as cursor:
                profiles = await cursor.fetchall()
                all_profiles = []
                for profile in profiles:
                    if profile[0] not in excluded_ids and profile[-3] and profile[-2]:
                        profile_location = (profile[-3], profile[-2])
                        distance = geodesic(user_location, profile_location).kilometers
                        all_profiles.append((profile, distance))
                return all_profiles
        return []

@dp.message(F.text == "Посмотреть лайки 💌")
async def show_likes(message: Message):
    async with aiosqlite.connect('petdating.db') as db:
        user_id = message.from_user.id
        async with db.execute('''
                   SELECT u.LinkOnUserName, u.UserId, u.PetName, u.Age, u.Breed, u.About, u.Photo FROM Likes l
                   JOIN UserProfiles u ON l.UserId = u.UserId WHERE l.ViewedId = ? AND l.State = 'mutual_like' AND l.ViewedByUser == 0 ''',
                              (user_id,)) as cursor:
            not_viewed_mutual_likes = await cursor.fetchall()
            if not_viewed_mutual_likes:
                for like in not_viewed_mutual_likes:
                    link_on_user_name, liked_user_id, pet_name, age, breed, about, photo = like

                    caption = f"Имя: {pet_name}\nВозраст: {age} лет\nПорода: {breed}\nОписание: {about}\nСсылка на профиль: @{link_on_user_name}"

                    if photo:
                        await bot.send_photo(message.chat.id, photo, caption=caption)
                    else:
                        await bot.send_message(message.chat.id, caption)

                    async with aiosqlite.connect('petdating.db') as db:
                        await db.execute('''UPDATE Likes SET ViewedByUser = 1 WHERE UserId = ? AND ViewedId = ?''',(liked_user_id, user_id))
                        await db.commit()

        async with aiosqlite.connect('petdating.db') as db:
            async with db.execute('''
                SELECT u.UserId, u.PetName, u.Age, u.Breed, u.About, u.Photo FROM Likes l
                JOIN UserProfiles u ON l.UserId = u.UserId WHERE l.ViewedId = ? AND l.State = 'like' ''', (user_id,)) as cursor:
                likes = await cursor.fetchall()
                await db.commit()

    if not likes and not not_viewed_mutual_likes:
        await message.answer("У вас пока нет лайков", reply_markup=default_keyboard())
        return
    elif not likes:
        await message.answer("Это все лайки", reply_markup=default_keyboard())
        return

    user_states[user_id] = {"likes": likes, "index": 0}
    await send_next_like(message, user_id)


async def send_next_like(message: Message, user_id: int):
    state = user_states.get(user_id)
    if not state or state["index"] >= len(state["likes"]):
        await message.answer("Все лайки просмотрены", reply_markup=default_keyboard())
        user_states.pop(user_id, None)
        return

    like = state["likes"][state["index"]]
    liked_user_id, pet_name, age, breed, about, photo = like

    caption = f"Имя: {pet_name}\nВозраст: {age} лет\nПорода: {breed}\nОписание: {about}"

    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❤️ Ответить взаимностью"), KeyboardButton(text="👎 Пропустить")],
        [KeyboardButton(text="💤 Остановить")]
    ], resize_keyboard=True)

    if photo:
        await bot.send_photo(message.chat.id, photo, caption=caption, reply_markup=keyboard)
    else:
        await message.answer(caption, reply_markup=keyboard)

    state["index"] += 1


@dp.message(F.text.in_({"❤️ Ответить взаимностью", "👎 Пропустить", "💤 Остановить"}))
async def handle_like_reaction(message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state:
        await message.answer("Просмотр лайков не активен", reply_markup=default_keyboard())
        return

    if message.text == "💤 Остановить":
        user_states.pop(user_id, None)
        await message.answer("Вы остановили просмотр лайков", reply_markup=default_keyboard())
        return

    # Получаем текущий лайк
    like = state["likes"][state["index"] - 1]
    liked_user_id = like[0]

    if message.text == "❤️ Ответить взаимностью":
        async with aiosqlite.connect('petdating.db') as db:
            async with db.execute('SELECT ChatId, LinkOnUserName FROM UserProfiles WHERE UserId = ?', (liked_user_id,)) as cursor:
                liked_user_info = await cursor.fetchone()
                if liked_user_info:
                    liked_user_chat_id = liked_user_info[0]
                    liked_user_username = liked_user_info[1]
                    await bot.send_message(liked_user_chat_id,
                        "🎉 У вас взаимный лайк!")
            await message.answer(f"Ссылка на профиль: @{liked_user_username}")

            await db.execute('''INSERT INTO Likes (UserId, ViewedId, State) VALUES (?, ?, 'mutual_like')''',
                             (user_id, liked_user_id))
            await db.commit()

            await db.execute('''DELETE FROM Likes WHERE UserId = ? AND ViewedId = ? AND State = 'like' ''',
                             (liked_user_id, user_id))

            await db.commit()

    await send_next_like(message, user_id)

@dp.message(F.text == "События 🎉")
async def show_likes(message: Message):
    async with aiosqlite.connect('petdating.db') as db:
        user_id = message.from_user.id
        async with db.execute('''SELECT EventName, Description, EventDate, Address FROM Events WHERE EventDate >= CURRENT_DATE''') as cursor:
            events = await cursor.fetchall()
            if not events:
                await message.answer("Нет доступных событий")
                return
            await message.answer("Запланированные события:")
            for e in events:
                event_name, event_description, event_date, event_address = e
                caption = f"Название: {event_name}\nДата проведения: {event_date}\nАдрес проведения: {event_address}\nОписание: {event_description}"
                await message.answer(caption)


async def main():
    await reset_db()
    await init_db()
    async with aiosqlite.connect('petdating.db') as db:
        await db.execute('''
               INSERT INTO Admins(AdminUserId, AdminChatId)
               VALUES
               (929270527, 929270527)
           ''')
        await db.commit()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())