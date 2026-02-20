import asyncio
import sys
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import math
import os

# --- Настройки логирования (чтобы сразу видеть в консоли) ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("🚀 Бот запускается...", flush=True)

# --- Настройки из переменных окружения ---
API_TOKEN = os.getenv('BOT_TOKEN')  # Берем из переменных окружения
MANAGER_CHAT_ID = int(os.getenv('MANAGER_CHAT_ID', '5915357483'))  # ID менеджера

# --- Инициализация ---
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Константы ---
INACTIVITY_TIMEOUT = 300  # 5 минут в секундах
FREE_WALLS_LIMIT = 4  # Бесплатно можно рассчитать 4 стены

# --- Класс состояний (FSM) ---
class CalcStates(StatesGroup):
    choosing_apparatus = State()    # Выбор аппарата
    entering_distance = State()      # Ввод расстояния r
    choosing_room = State()          # Выбор помещения
    choosing_material = State()      # Выбор материала стены
    entering_length = State()        # Ввод длины стены
    entering_height = State()        # Ввод высоты стены
    choosing_door = State()          # Есть ли дверь (да/нет)
    choosing_next_wall = State()     # Выбор: следующая стена или завершить
    choosing_service = State()       # Выбор дополнительной услуги
    entering_phone = State()         # Ввод номера телефона
    waiting_continue = State()        # Ожидание выбора после бездействия

# --- Константы для дентального аппарата ---
DENTAL = {
    'name': '🦷 Дентальный аппарат',
    'U': 70,      # Напряжение на трубке, кВ
    'R': 5.6,     # Постоянная аппарата, мА·мин⁻¹·м²
    'W': 40,      # Рабочая нагрузка, мА·мин/нед
    'N': 1        # Коэффициент занятости
}

# --- Константы для ортопантомографа ---
OPTG = {
    'name': '🦴 Ортопантомограф',
    'U': 90,      # Напряжение на трубке, кВ
    'R': 7.92,    # Постоянная аппарата, мА·мин⁻¹·м²
    'W': 200,     # Рабочая нагрузка, мА·мин/нед
    'N': 0.1      # Коэффициент занятости
}

# --- Справочник помещений с коэффициентами D ---
ROOMS = {
    "🚪 Комната управления": 13,
    "🚶 Коридор, раздевалка, стерилизационная": 2,
    "🩺 Кабинет врача": 2.5,
    "🏙️ Улица": 2.8,
    "🏢 Сторонняя организация": 0.5,
    "⬇️ Подвал": 40,
    "🛏️ Палата": 1.3,
    "🏠 Квартира": 0.3
}

# --- Таблица материалов стен для ДЕНТАЛЬНОГО аппарата ---
DENTAL_WALL_MATERIALS = {
    "🧱 Кирпич 120 мм": 0.96,
    "🧱 Кирпич 250 мм": 2.19,
    "🏗️ Бетон 100 мм": 1.08,
    "🏗️ Бетон 200 мм": 2.15,
    "🧱 Пеноблок 100 мм": 0.3,
    "🧱 Пеноблок 200 мм": 0.63,
    "🪵 ГКЛ 25 мм": 0.08
}

# --- Таблица материалов стен для ОРТОПАНТОМОГРАФА ---
OPTG_WALL_MATERIALS = {
    "🧱 Кирпич 120 мм": 1.19,
    "🧱 Кирпич 250 мм": 2.82,
    "🏗️ Бетон 100 мм": 1.31,
    "🏗️ Бетон 200 мм": 2.66,
    "🧱 Пеноблок 100 мм": 0.3,
    "🧱 Пеноблок 200 мм": 0.63,
    "🪵 ГКЛ 25 мм": 0.08
}

# --- Таблица кратности ослабления (K) и защиты (X) для ДЕНТАЛЬНОГО ---
DENTAL_PROTECTION_TABLE = [
    (3, 0.046), (5, 0.082), (10, 0.136), (30, 0.26), (50, 0.328),
    (100, 0.426), (200, 0.515), (300, 0.6), (400, 0.65), (500, 0.688),
    (600, 0.71), (700, 0.74), (800, 0.765), (900, 0.79), (1000, 0.81),
    (1100, 0.82), (1200, 0.83), (1300, 0.84), (1400, 0.85), (1500, 0.86),
    (1600, 0.87), (1700, 0.88), (1800, 0.89), (1900, 0.9), (2000, 0.91),
    (2100, 0.92), (2200, 0.93), (2300, 0.94), (2400, 0.95), (2500, 0.96),
    (2600, 0.97), (2700, 0.98), (2800, 0.99), (2900, 1), (3000, 1.014),
    (4000, 1.06), (5000, 1.11), (6000, 1.136), (7000, 1.162), (8000, 1.188),
    (9000, 1.214), (10000, 1.236), (15000, 1.2925), (20000, 1.345), (25000, 1.3975),
    (30000, 1.448), (50000, 1.546), (100000, 1.68), (300000, 1.888), (500000, 1.986),
    (1000000, 2.122), (3000000, 2.33), (5000000, 2.428), (10000000, 2.564)
]

# --- Таблица кратности ослабления (K) и защиты (X) для ОРТОПАНТОМОГРАФА ---
OPTG_PROTECTION_TABLE = [
    (3, 0.074), (5, 0.09), (10, 0.14), (30, 0.35), (50, 0.55),
    (100, 0.726), (200, 0.883), (300, 1.04), (400, 1.12), (500, 1.2),
    (600, 1.242), (700, 1.2848), (800, 1.327), (900, 1.3696), (1000, 1.412),
    (1100, 1.44667), (1200, 1.46533), (1300, 1.48333), (1400, 1.50067), (1500, 1.518),
    (1600, 1.536), (1700, 1.55333), (1800, 1.57133), (1900, 1.58933), (2000, 1.60667),
    (2100, 1.624), (2200, 1.642), (2300, 1.65933), (2400, 1.67733), (2500, 1.69667),
    (2600, 1.71267), (2700, 1.73033), (2800, 1.748), (2900, 1.76567), (3000, 1.78467),
    (4000, 1.865), (5000, 1.95), (6000, 1.996), (7000, 2.042), (8000, 2.088),
    (9000, 2.134), (10000, 2.17867), (15000, 2.27083), (20000, 2.36167), (25000, 2.4525),
    (30000, 2.54267), (50000, 2.70867), (100000, 2.94), (300000, 3.32267), (500000, 3.46867),
    (1000000, 3.70067), (3000000, 4.06333), (5000000, 4.22933), (10000000, 4.46133)
]

# Сортируем таблицы
DENTAL_PROTECTION_TABLE.sort(key=lambda x: x[0])
OPTG_PROTECTION_TABLE.sort(key=lambda x: x[0])

# --- Таблица пересчета Z в баритовую штукатурку ---
BARYTE_TABLE = [
    (0.2, 3.8), (0.3, 5.0), (0.4, 6.3), (0.5, 7.6), (0.6, 8.76),
    (0.7, 9.92), (0.8, 11.08), (0.9, 12.24), (1.0, 13.4), (1.1, 14.58),
    (1.2, 15.76), (1.3, 16.94), (1.4, 18.12), (1.5, 19.3), (1.6, 20.48),
    (1.7, 21.66), (1.8, 22.84), (1.9, 24.02), (2.0, 25.2)
]
BARYTE_TABLE.sort(key=lambda x: x[0])

# --- Константа для расчета цены штукатурки ---
PLASTER_PRICE_CONST = 76.8

# --- Функции поиска ---
def find_protection(calculated_k, apparatus_type):
    """Находит толщину защиты X по K (ближайшее большее)"""
    if apparatus_type == "dental":
        table = DENTAL_PROTECTION_TABLE
    else:
        table = OPTG_PROTECTION_TABLE
    
    for k_value, protection in table:
        if k_value >= calculated_k:
            return protection, k_value
    return table[-1]

def find_baryte_thickness(z_value):
    """Находит толщину баритовой штукатурки по Z (ближайшее большее)"""
    for z_table, thickness in BARYTE_TABLE:
        if z_table >= z_value:
            return thickness, z_table
    return BARYTE_TABLE[-1]

def calculate_plaster_price(length, height, baryte_thickness):
    """Расчет стоимости баритовой штукатурки"""
    price = length * height * baryte_thickness * PLASTER_PRICE_CONST
    return round(price, 2)

def get_door_price(protection_needed):
    """Определяет цену двери в зависимости от требуемой защиты X"""
    if protection_needed < 1:
        return 42300
    elif 1 <= protection_needed < 1.5:
        return 47800
    elif 1.5 <= protection_needed <= 2:
        return 52000
    else:
        return 52000

# --- Клавиатуры ---
apparatus_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🦷 Дентальный аппарат")],
        [KeyboardButton(text="🦴 Ортопантомограф")]
    ],
    resize_keyboard=True
)

room_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=room)] for room in ROOMS.keys()],
    resize_keyboard=True
)

# Функция для получения клавиатуры материалов в зависимости от аппарата
def get_material_kb(apparatus_type):
    if apparatus_type == "dental":
        materials = DENTAL_WALL_MATERIALS
    else:
        materials = OPTG_WALL_MATERIALS
    
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=material)] for material in materials.keys()],
        resize_keyboard=True
    )

yes_no_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Да")],
        [KeyboardButton(text="❌ Нет")]
    ],
    resize_keyboard=True
)

next_wall_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Рассчитать следующую стену")],
        [KeyboardButton(text="✅ Завершить расчет")]
    ],
    resize_keyboard=True
)

continue_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="▶️ Продолжить расчет")],
        [KeyboardButton(text="🔄 Начать заново")]
    ],
    resize_keyboard=True
)

final_options_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Подтвердить расчет инженером")],
        [KeyboardButton(text="📄 Получить коммерческое предложение на проект")],
        [KeyboardButton(text="🧱 Получить коммерческое предложение на материалы")]
    ],
    resize_keyboard=True
)

new_calc_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔄 Новый расчет")]],
    resize_keyboard=True
)

# --- Middleware для отслеживания бездействия ---
@dp.update.outer_middleware()
async def activity_middleware(handler, event, data):
    state: FSMContext = data.get('state')
    if state:
        current_state = await state.get_state()
        if current_state and current_state != CalcStates.waiting_continue.state:
            # Обновляем время последней активности
            await state.update_data(last_activity=datetime.now())
    return await handler(event, data)

# --- Фоновая задача для проверки бездействия ---
async def check_inactivity():
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту
        for chat_id in await get_active_chats():
            try:
                state = dp.fsm.storage.get_state(chat=chat_id, user=chat_id)
                if state and state != CalcStates.waiting_continue.state:
                    data = await dp.fsm.storage.get_data(chat=chat_id, user=chat_id)
                    last_activity = data.get('last_activity')
                    if last_activity and datetime.now() - last_activity > timedelta(seconds=INACTIVITY_TIMEOUT):
                        # Отправляем предложение продолжить
                        await bot.send_message(
                            chat_id=chat_id,
                            text="⏰ Вы не активны более 5 минут. Хотите продолжить расчет или начать заново?",
                            reply_markup=continue_kb
                        )
                        await dp.fsm.storage.set_state(chat=chat_id, user=chat_id, state=CalcStates.waiting_continue)
            except Exception as e:
                logger.error(f"Ошибка проверки бездействия: {e}")

async def get_active_chats():
    """Получает список активных чатов (упрощенно)"""
    # В реальном проекте нужно хранить список активных пользователей
    return []

# --- Обработчики ---
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    # Сохраняем информацию о пользователе
    await state.update_data(
        walls=[], 
        current_wall=1,
        user_id=message.from_user.id,
        username=message.from_user.username or "нет username",
        last_activity=datetime.now()
    )
    
    await message.answer(
        "🦷🦴 Калькулятор радиационной защиты\n\n"
        f"Бесплатно вы можете рассчитать до {FREE_WALLS_LIMIT} стен.\n\n"
        "Выберите тип аппарата:",
        reply_markup=apparatus_kb
    )
    await state.set_state(CalcStates.choosing_apparatus)

@dp.message(F.text == "🔄 Новый расчет")
async def new_calculation(message: Message, state: FSMContext):
    await cmd_start(message, state)

@dp.message(F.text == "▶️ Продолжить расчет", CalcStates.waiting_continue)
async def continue_calculation(message: Message, state: FSMContext):
    user_data = await state.get_data()
    current_wall = user_data.get('current_wall', 1)
    params = user_data.get('apparatus_params', DENTAL)
    
    await message.answer(
        f"🔄 Продолжаем расчет\n"
        f"{params['name']}\n"
        f"Стена {current_wall}\n\n"
        f"Введите расстояние от фокусного пятна до стены (r) в метрах:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CalcStates.entering_distance)
    await state.update_data(last_activity=datetime.now())

@dp.message(F.text == "🔄 Начать заново", CalcStates.waiting_continue)
async def restart_calculation(message: Message, state: FSMContext):
    await cmd_start(message, state)

@dp.message(CalcStates.choosing_apparatus)
async def apparatus_chosen(message: Message, state: FSMContext):
    if message.text == "🦷 Дентальный аппарат":
        await state.update_data(apparatus="dental", apparatus_params=DENTAL)
        apparatus_name = "Дентальный аппарат"
    elif message.text == "🦴 Ортопантомограф":
        await state.update_data(apparatus="optg", apparatus_params=OPTG)
        apparatus_name = "Ортопантомограф"
    else:
        await message.answer("❌ Пожалуйста, выберите тип аппарата из меню.", reply_markup=apparatus_kb)
        return
    
    current_wall = await get_current_wall(state)
    await message.answer(
        f"✅ Выбран {apparatus_name}\n"
        f"Стена {current_wall}\n\n"
        f"Введите расстояние от фокусного пятна до стены (r) в метрах:\n"
        f"(например: 1.5, 2.0, 3.2)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CalcStates.entering_distance)
    await state.update_data(last_activity=datetime.now())

async def get_current_wall(state: FSMContext):
    data = await state.get_data()
    return data.get('current_wall', 1)

@dp.message(CalcStates.entering_distance)
async def distance_entered(message: Message, state: FSMContext):
    try:
        r = float(message.text.replace(",", "."))
        if r <= 0:
            await message.answer("❌ Расстояние должно быть положительным числом. Попробуйте снова:")
            return
        
        await state.update_data(distance=r, last_activity=datetime.now())
        current_wall = await get_current_wall(state)
        await message.answer(
            f"✅ Расстояние {r} м принято.\n"
            f"Стена {current_wall}\n\n"
            f"Теперь выберите тип помещения за стеной:",
            reply_markup=room_kb
        )
        await state.set_state(CalcStates.choosing_room)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например: 1.5 или 2):")

@dp.message(CalcStates.choosing_room)
async def room_chosen(message: Message, state: FSMContext):
    room_name = message.text
    if room_name not in ROOMS:
        await message.answer("❌ Выберите помещение из списка.", reply_markup=room_kb)
        return
    
    D = ROOMS[room_name]
    await state.update_data(room=room_name, D=D, last_activity=datetime.now())
    current_wall = await get_current_wall(state)
    
    user_data = await state.get_data()
    apparatus_type = user_data.get('apparatus', 'dental')
    
    await message.answer(
        f"✅ Выбрано помещение: {room_name} (D={D})\n"
        f"Стена {current_wall}\n\n"
        f"Теперь выберите материал стены:",
        reply_markup=get_material_kb(apparatus_type)
    )
    await state.set_state(CalcStates.choosing_material)

@dp.message(CalcStates.choosing_material)
async def material_chosen(message: Message, state: FSMContext):
    material_name = message.text
    
    user_data = await state.get_data()
    apparatus_type = user_data.get('apparatus', 'dental')
    
    if apparatus_type == "dental":
        materials_dict = DENTAL_WALL_MATERIALS
    else:
        materials_dict = OPTG_WALL_MATERIALS
    
    if material_name not in materials_dict:
        await message.answer("❌ Выберите материал из списка.", 
                           reply_markup=get_material_kb(apparatus_type))
        return
    
    Y = materials_dict[material_name]
    await state.update_data(material=material_name, Y=Y, last_activity=datetime.now())
    current_wall = await get_current_wall(state)
    
    await message.answer(
        f"✅ Выбран материал: {material_name}\n"
        f"Стена {current_wall}\n\n"
        f"Введите длину стены в метрах (например: 5.5):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CalcStates.entering_length)

@dp.message(CalcStates.entering_length)
async def length_entered(message: Message, state: FSMContext):
    try:
        length = float(message.text.replace(",", "."))
        if length <= 0:
            await message.answer("❌ Длина должна быть положительным числом. Попробуйте снова:")
            return
        
        await state.update_data(length=length, last_activity=datetime.now())
        current_wall = await get_current_wall(state)
        await message.answer(
            f"✅ Длина стены {length} м принята.\n"
            f"Стена {current_wall}\n\n"
            f"Введите высоту стены в метрах (например: 3.0):"
        )
        await state.set_state(CalcStates.entering_height)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например: 5.5):")

@dp.message(CalcStates.entering_height)
async def height_entered(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        if height <= 0:
            await message.answer("❌ Высота должна быть положительным числом. Попробуйте снова:")
            return
        
        await state.update_data(height=height, last_activity=datetime.now())
        current_wall = await get_current_wall(state)
        await message.answer(
            f"✅ Высота стены {height} м принята.\n"
            f"Стена {current_wall}\n\n"
            f"Есть ли дверь в этой стене?",
            reply_markup=yes_no_kb
        )
        await state.set_state(CalcStates.choosing_door)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например: 3.0):")

@dp.message(CalcStates.choosing_door)
async def door_chosen(message: Message, state: FSMContext):
    door_answer = message.text
    
    if door_answer not in ["✅ Да", "❌ Нет"]:
        await message.answer("❌ Пожалуйста, выберите Да или Нет.", reply_markup=yes_no_kb)
        return
    
    has_door = (door_answer == "✅ Да")
    
    user_data = await state.get_data()
    r = user_data['distance']
    D = user_data['D']
    Y = user_data['Y']
    length = user_data['length']
    height = user_data['height']
    current_wall = user_data.get('current_wall', 1)
    apparatus_type = user_data.get('apparatus', 'dental')
    
    params = user_data['apparatus_params']
    R = params['R']
    W = params['W']
    N = params['N']
    
    K_calculated = 1000 * R * W * N / D / 30 / (r * r)
    X, k_used = find_protection(K_calculated, apparatus_type)
    
    door_price = 0
    if has_door:
        door_price = get_door_price(X)
    
    apparatus_display = params['name']
    wall_result = f"Стена {current_wall} ({apparatus_display}):\n"
    wall_result += f"  📏 Расстояние: {r} м\n"
    wall_result += f"  🚪 Помещение: {user_data['room']}\n"
    wall_result += f"  🧱 Материал: {user_data['material']}\n"
    
    if Y >= X:
        wall_result += f"  ✅ Защита стены не требуется!\n"
        wall_result += f"     Материал стены {Y} мм ≥ {X:.3f} мм\n"
        plaster_price = 0
        baryte_thickness = 0
        Z = 0
    else:
        Z = X - Y
        baryte_thickness, z_used = find_baryte_thickness(Z)
        lead_thickness = math.ceil(Z * 100) / 100
        
        wall_result += f"  ⚠️ Требуется доп. защита:\n"
        wall_result += f"     Свинцовые листы {lead_thickness:.2f} мм\n"
        wall_result += f"     Баритовая штукатурка: {baryte_thickness} мм\n\n"
        
        plaster_price = calculate_plaster_price(length, height, baryte_thickness)
        wall_result += f"  🪨 Стоимость баритовой штукатурки: {plaster_price:,.2f} руб.\n".replace(",", " ")
    
    if has_door:
        wall_result += f"  🚪 Дверь: {door_price:,.2f} руб.\n".replace(",", " ")
    
    walls = user_data.get('walls', [])
    walls.append({
        'text': wall_result,
        'plaster_price': plaster_price,
        'door_price': door_price,
        'total': plaster_price + door_price
    })
    
    next_wall = current_wall + 1
    
    await state.update_data(walls=walls, current_wall=next_wall, last_activity=datetime.now())
    await message.answer(wall_result, reply_markup=ReplyKeyboardRemove())
    
    if next_wall <= 4:
        await message.answer(
            f"Стена {current_wall} рассчитана. Хотите рассчитать стену {next_wall}?",
            reply_markup=next_wall_kb
        )
        await state.set_state(CalcStates.choosing_next_wall)
    else:
        await message.answer(
            f"✅ Все 4 стены рассчитаны!",
            reply_markup=ReplyKeyboardRemove()
        )
        await show_final_results(message, state)

@dp.message(CalcStates.choosing_next_wall)
async def next_wall_choice(message: Message, state: FSMContext):
    if message.text == "➕ Рассчитать следующую стену":
        user_data = await state.get_data()
        current_wall = user_data.get('current_wall', 1)
        params = user_data['apparatus_params']
        
        await message.answer(
            f"{params['name']}\n"
            f"Стена {current_wall}\n\n"
            f"Введите расстояние от фокусного пятна до стены (r) в метрах:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(CalcStates.entering_distance)
        await state.update_data(last_activity=datetime.now())
    
    elif message.text == "✅ Завершить расчет":
        await show_final_results(message, state)
    
    else:
        await message.answer("Пожалуйста, выберите действие из меню.", reply_markup=next_wall_kb)

async def show_final_results(message: Message, state: FSMContext):
    user_data = await state.get_data()
    walls = user_data.get('walls', [])
    
    if not walls:
        await message.answer("❌ Нет данных для отображения. Начните новый расчет.")
        await cmd_start(message, state)
        return
    
    result = "📊 **ИТОГОВЫЙ РАСЧЕТ ПО КАБИНЕТУ**\n\n"
    
    total_plaster = 0
    total_doors = 0
    
    for i, wall in enumerate(walls, 1):
        result += wall['text']
        if i < len(walls):
            result += "\n"
        total_plaster += wall['plaster_price']
        total_doors += wall['door_price']
    
    total_sum = total_plaster + total_doors
    
    result += f"\n💰 **ОБЩАЯ СТОИМОСТЬ:**\n"
    result += f"🪨 Баритовая штукатурка (все стены): {total_plaster:,.2f} руб.\n".replace(",", " ")
    result += f"🚪 Двери (всего): {total_doors:,.2f} руб.\n".replace(",", " ")
    result += f"💵 **ИТОГО материалы: {total_sum:,.2f} руб.**\n".replace(",", " ")
    
    await message.answer(result, reply_markup=ReplyKeyboardRemove())
    
    await message.answer(
        "Выберите дополнительную услугу:",
        reply_markup=final_options_kb
    )
    await state.set_state(CalcStates.choosing_service)
    await state.update_data(last_activity=datetime.now())

@dp.message(CalcStates.choosing_service)
async def service_chosen(message: Message, state: FSMContext):
    service = message.text
    valid_services = [
        "📋 Подтвердить расчет инженером",
        "📄 Получить коммерческое предложение на проект",
        "🧱 Получить коммерческое предложение на материалы"
    ]
    
    if service not in valid_services:
        await message.answer("❌ Пожалуйста, выберите услугу из меню.", reply_markup=final_options_kb)
        return
    
    await state.update_data(selected_service=service, last_activity=datetime.now())
    
    await message.answer(
        "📞 Введите ваш номер телефона для связи\n"
        "(например: +7 999 123-45-67):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CalcStates.entering_phone)

@dp.message(CalcStates.entering_phone)
async def phone_entered(message: Message, state: FSMContext):
    phone = message.text
    
    if len(phone.strip()) < 5:
        await message.answer("❌ Пожалуйста, введите корректный номер телефона:")
        return
    
    user_data = await state.get_data()
    walls = user_data.get('walls', [])
    selected_service = user_data.get('selected_service', 'Не выбрано')
    username = message.from_user.username or "нет username"
    user_id = message.from_user.id
    
    manager_msg = f"🔔 **НОВАЯ ЗАЯВКА**\n\n"
    manager_msg += f"👤 Пользователь: @{username} (ID: {user_id})\n"
    manager_msg += f"📞 Телефон: {phone}\n"
    manager_msg += f"📋 Услуга: {selected_service}\n\n"
    manager_msg += "📊 **РЕЗУЛЬТАТЫ РАСЧЕТА:**\n\n"
    
    total_plaster = 0
    total_doors = 0
    
    for i, wall in enumerate(walls, 1):
        manager_msg += wall['text']
        if i < len(walls):
            manager_msg += "\n"
        total_plaster += wall['plaster_price']
        total_doors += wall['door_price']
    
    total_sum = total_plaster + total_doors
    
    manager_msg += f"\n💰 **ОБЩАЯ СТОИМОСТЬ:**\n"
    manager_msg += f"Штукатурка: {total_plaster:,.2f} руб.\n".replace(",", " ")
    manager_msg += f"Двери: {total_doors:,.2f} руб.\n".replace(",", " ")
    manager_msg += f"ИТОГО: {total_sum:,.2f} руб.\n".replace(",", " ")
    
    try:
        await bot.send_message(chat_id=MANAGER_CHAT_ID, text=manager_msg)
        logger.info(f"Сообщение отправлено менеджеру {MANAGER_CHAT_ID}")
        await message.answer("✅ Данные отправлены менеджеру. Спасибо!")
    except Exception as e:
        logger.error(f"Ошибка отправки менеджеру: {e}")
        await message.answer("❌ Произошла ошибка при отправке данных. Попробуйте позже.")
    
    await message.answer(
        "✅ Спасибо что воспользовались нашим ботом!\n"
        "В ближайшее время с вами свяжется наш специалист.\n\n"
        "Хотите сделать новый расчет?",
        reply_markup=new_calc_kb
    )
    await state.clear()

# --- Запуск бота ---
async def main():
    print("✅ Бот успешно запущен и готов к работе!", flush=True)
    logger.info(f"Бот запущен с токеном: {API_TOKEN[:10]}...")
    logger.info(f"ID менеджера: {MANAGER_CHAT_ID}")
    
    # Запускаем фоновую задачу для проверки бездействия
    asyncio.create_task(check_inactivity())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
