import logging
import time
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from telegram import Update, Bot, Message, Document, PhotoSize, Video, Animation, Audio
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown
import re # Импортируем модуль re для регулярных выражений
import random # Импортируем модуль random для случайного выбора

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
BOT_TOKEN = "7664851287:AAGZ35zHd0fa66YoqRKegiZ2uv7zvWnH6-4" # !!! ЗАМЕНИТЕ НА ВАШ ТОКЕН БОТА !!!
ADMIN_ID = [1994433796] # Глобальные администраторы. Эти пользователи всегда имеют все права.
# MAIN_GROUP_CHAT_ID может быть использован для дефолта, если не указаны tc/all
MAIN_GROUP_CHAT_ID = -1002670883011 # ID основной группы/канала (может быть использован для дефолта, если не указаны tc/all)

# --- Имена файлов для сохранения данных ---
# ИЗМЕНЕНО: Добавлен префикс "file/" для всех файлов, если они будут находиться в подпапке
BOT_STATUS_FILE = "file/bot_status.json"
WHITELIST_FILE = "file/whitelist.json"
STATS_FILE = "file/stats.json"
WARNINGS_FILE = "file/warnings.json" # Файл для предупреждений
MUTELIST_FILE = "file/mutelist.json" # Файл для заблокированных пользователей
SPAM_PROTECTION_STATUS_FILE = "file/spam_protection_status.json" # Файл для статуса спам-защиты
USERS_FILE = "file/users.json" # Файл для известных пользователей
KNOWN_GROUPS_FILE = "file/known_groups.json" # Файл для известных групп/каналов
MESSAGE_LOG_FILE = "file/message_log.json" # Файл для логирования всех сообщений
GROUP_ADMINS_FILE = "file/group_admins.json" # Новый файл для администраторов групп
USER_DATA_FILE = "file/user_data.json" # Новый файл для данных о пользователях (для поиска по нику)

# --- Глобальные переменные для хранения данных ---
# (Будут загружаться из файлов при старте)
user_warnings = {} # {user_id: count}
# muted_users хранит список чатов, в которых пользователь был заблокирован
# Теперь muted_users будет хранить списки словарей, каждый из которых описывает одну блокировку
muted_users = {} # {user_id: [{"chat_id": int, "muted_until": float, "reason": str, "muted_by_admin_id": int}, ...]}
stats_data = {} # Для статистики бота
unique_users = set() # Для подсчета уникальных пользователей в текущей сессии
user_message_history = defaultdict(list) # Для отслеживания истории сообщений пользователей
spam_protection_enabled = True # Дефолтное состояние спам-защиты
users_set = set() # Set для хранения ID всех уникальных пользователей, с которыми бот взаимодействовал
known_groups_set = set() # Set для хранения ID всех уникальных групп/каналов, с которыми бот взаимодействовал
group_admins = {} # {group_id: list[int]} - для администраторов групп
user_data = {} # {user_id: {"username": str, "first_name": str, "last_name": str}} - для поиска пользователя по нику

# --- Настройки спам-фильтра ---
FORBIDDEN_WORDS = [
    # Категории: Незаконная деятельность, Нанесение серьезного вреда, Экстремизм, Расистские/Националистические оскорбления.
    # Общий мат и легкие оскорбления разрешены согласно запросу.
    "наркотики", "оружие", "взрывчатка", "терроризм", "экстремизм",
    "убийство", "насилие", "суицид", "мошенничество", "скам", "фишинг",
    "кардинг", "подделка документов", "торговля людьми", "рабство",
    "вымогательство", "педофил", "детская порнография", "нелегальный",
    "контрабанда", "отмывание денег", "фальшивомонетчиство",
    "взлом", "кража данных", "вирус", "оружие массового поражения",
    "призывы к агрессии", "пропаганда войны", "государственная измена",
    "торговля органами", "зоофилия", "некрофилия", "вербовка",
    "расизм", "нацизм", "фашизм", "ксенофобия", "дискриминация",
    "межнациональная рознь", "религиозная рознь",
    "чурка", "хач", "жид", "пиндос", "хохол", "кацап", "негр", "нигер", "черномазый", # Примеры расистских/националистических оскорблений
    "мaть-шлюха", "мaть-нации", # Примеры оскорблений про "мам нации" (пытаемся уловить суть запроса)
    "педо", "сектант", "насильник", # Дополнительные слова для серьезного вреда
]
MAX_WARNINGS = 2 # Количество предупреждений до блокировки

# --- Настройки флуд-контроля ---
MESSAGE_LIMIT = 3 # Количество сообщений для детекта флуда
TIME_WINDOW = 2 # Временное окно в секундах для детекта флуда (очень быстрый спам)

# --- Пути к папкам с MP3 файлами для смешного контента ---
MP3_10_FOLDER = "file/10mp3"
MP3_5_FOLDER = "file/5mp3"
MP3_269_FOLDER = "file/269mp3"
MP3_220_FOLDER = "file/220mp3"

# --- Вспомогательные функции для работы с файлами ---

def read_json_file(file_path: str) -> dict | list | None:
    """Универсальная функция для безопасного чтения JSON-файла."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Ошибка при чтении или парсинге файла {file_path}: {e}")
        return None

def write_json_file(file_path: str, data: dict | list):
    """Универсальная функция для безопасной записи JSON-файла."""
    try:
        # Убедимся, что директория существует
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка при записи файла {file_path}: {e}")

def append_to_message_log(message_data: dict):
    """Добавляет запись сообщения в message_log.json."""
    try:
        # Убедимся, что директория существует
        os.makedirs(os.path.dirname(MESSAGE_LOG_FILE), exist_ok=True)
        with open(MESSAGE_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(message_data, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"Ошибка при записи в message_log.json: {e}")

def load_data():
    """Загружает все необходимые данные из файлов при старте бота."""
    global user_warnings, muted_users, stats_data, unique_users, spam_protection_enabled, users_set, known_groups_set, group_admins, user_data

    warnings_data_raw = read_json_file(WARNINGS_FILE)
    if warnings_data_raw:
        if isinstance(warnings_data_raw, dict):
            user_warnings = {int(k): v for k, v in warnings_data_raw.items()}
        else:
            logger.warning(f"Обнаружен неожиданный формат файла {WARNINGS_FILE}. Ожидается словарь, получен {type(warnings_data_raw).__name__}. Инициализирую пустой словарь.")
            user_warnings = {}
    else:
        user_warnings = {}

    mutelist_data_raw = read_json_file(MUTELIST_FILE)
    if mutelist_data_raw:
        if isinstance(mutelist_data_raw, dict):
            temp_muted_users = {}
            for user_id_str, mute_list in mutelist_data_raw.items():
                user_id = int(user_id_str)
                if isinstance(mute_list, list):
                    temp_muted_users[user_id] = []
                    for mute_entry in mute_list:
                        # Проверяем, что все необходимые поля присутствуют, иначе используем дефолты
                        if isinstance(mute_entry, dict) and "chat_id" in mute_entry and "muted_until" in mute_entry:
                            temp_muted_users[user_id].append({
                                "chat_id": mute_entry.get("chat_id"),
                                "muted_until": mute_entry.get("muted_until"),
                                "reason": mute_entry.get("reason", "неизвестно"),
                                "muted_by_admin_id": mute_entry.get("muted_by_admin_id", None),
                                "human_readable_duration": mute_entry.get("human_readable_duration", "Навсегда"),
                                "timestamp_applied": mute_entry.get("timestamp_applied", time.time())
                            })
                else: # Старый формат {user_id: {"reason": str, "timestamp": float, "triggered_words_admin": list, "muted_in_chats": list[int]}}
                    logger.warning(f"Конвертация старого формата мута для пользователя {user_id_str}.")
                    temp_muted_users[user_id] = []
                    old_data = mute_list
                    reason = old_data.get("reason", "неизвестно")
                    muted_by_admin_id = None # В старом формате не было
                    timestamp = old_data.get("timestamp", time.time())
                    
                    for chat_id_old in old_data.get("muted_in_chats", []):
                        temp_muted_users[user_id].append({
                            "chat_id": chat_id_old,
                            "muted_until": float('inf'), # Бесконечность для старых перманентных мутов
                            "reason": reason,
                            "muted_by_admin_id": muted_by_admin_id,
                            "human_readable_duration": "Навсегда",
                            "timestamp_applied": timestamp
                        })
            muted_users = temp_muted_users
        else:
            logger.warning(f"Обнаружен неожиданный формат данных в {MUTELIST_FILE}. Ожидается словарь, получен {type(mutelist_data_raw).__name__}. Инициализирую пустой словарь.")
            muted_users = {}
    else:
        muted_users = {}

    spam_status_data = read_json_file(SPAM_PROTECTION_STATUS_FILE)
    if spam_status_data is not None and "enabled" in spam_status_data:
        spam_protection_enabled = spam_status_data["enabled"]
        logger.info(f"Статус спам-защиты загружен: {'ВКЛ' if spam_protection_enabled else 'ВЫКЛ'}")
    else:
        logger.info("Файл статуса спам-защиты не найден или пуст, используем значение по умолчанию (ВКЛ).")

    # Загрузка известных пользователей из USERS_FILE
    users_raw = read_json_file(USERS_FILE)
    if users_raw and isinstance(users_raw, list):
        users_set = set(int(uid) for uid in users_raw)
    else:
        logger.warning(f"Файл {USERS_FILE} не найден или имеет некорректный формат. Инициализирую пустой список известных пользователей.")
        users_set = set()

    # Загрузка известных групп
    known_groups_raw = read_json_file(KNOWN_GROUPS_FILE)
    if known_groups_raw and isinstance(known_groups_raw, list):
        known_groups_set = set(int(gid) for gid in known_groups_raw)
    else:
        logger.warning(f"Файл {KNOWN_GROUPS_FILE} не найден или имеет некорректный формат. Инициализирую пустой список известных групп.")
        known_groups_set = set()

    # Загрузка администраторов групп
    group_admins_raw = read_json_file(GROUP_ADMINS_FILE)
    if group_admins_raw and isinstance(group_admins_raw, dict):
        temp_group_admins = {}
        for group_id_str, admin_ids_list in group_admins_raw.items():
            try:
                temp_group_admins[int(group_id_str)] = [int(aid) for aid in admin_ids_list]
            except ValueError:
                logger.warning(f"Некорректный ID группы или админа в {GROUP_ADMINS_FILE}: {group_id_str}: {admin_ids_list}. Пропускаю запись.")
        group_admins = temp_group_admins
    else:
        logger.warning(f"Файл {GROUP_ADMINS_FILE} не найден или имеет некорректный формат. Инициализирую пустой словарь.")
        group_admins = {}
    
    # Загрузка данных о пользователях
    user_data_raw = read_json_file(USER_DATA_FILE)
    if user_data_raw and isinstance(user_data_raw, dict):
        temp_user_data = {}
        for user_id_str, data in user_data_raw.items():
            try:
                temp_user_data[int(user_id_str)] = data
            except ValueError:
                logger.warning(f"Некорректный ID пользователя в {USER_DATA_FILE}: {user_id_str}. Пропускаю запись.")
        user_data = temp_user_data
    else:
        logger.warning(f"Файл {USER_DATA_FILE} не найден или имеет некорректный формат. Инициализирую пустой словарь.")
        user_data = {}


    stats_data = read_json_file(STATS_FILE) or {
        'start_time': time.time(),
        'messages_received': 0,
        'messages_sent': 0,
        'unique_users': []
    }
    unique_users = set(stats_data.get('unique_users', [])) # Загружаем уникальных пользователей как set

    logger.info("Данные успешно загружены.")

def save_data():
    """Сохраняет все необходимые данные в файлы."""
    write_json_file(WARNINGS_FILE, user_warnings)
    write_json_file(MUTELIST_FILE, muted_users)
    write_json_file(SPAM_PROTECTION_STATUS_FILE, {"enabled": spam_protection_enabled})
    write_json_file(USERS_FILE, list(users_set)) # Сохраняем users_set в USERS_FILE
    write_json_file(KNOWN_GROUPS_FILE, list(known_groups_set))
    write_json_file(GROUP_ADMINS_FILE, group_admins) # Сохраняем администраторов групп
    write_json_file(USER_DATA_FILE, user_data) # Сохраняем данные о пользователях
    
    # Обновляем stats_data перед сохранением
    stats_data['unique_users'] = list(unique_users)
    write_json_file(STATS_FILE, stats_data)
    logger.info("Данные успешно сохранены.")

# --- Функции для обновления статуса бота ---

async def update_bot_status(context: ContextTypes.DEFAULT_TYPE):
    """Обновляет файл статуса бота."""
    status = {"last_seen_online": time.time()}
    write_json_file(BOT_STATUS_FILE, status)
    logger.debug("Статус бота обновлен.")

# --- Вспомогательная функция для отправки файлов и текста ---
async def _send_message_or_media(bot: Bot, chat_id: int, text: str | None, message_to_forward: Message | None):
    """
    Отправляет текстовое сообщение или медиафайл (фото, видео, GIF, документ, аудио) в указанный чат.
    Если есть message_to_forward и оно содержит медиа, отправляется медиа с текстом в качестве caption.
    Иначе отправляется обычное текстовое сообщение.
    """
    try:
        if message_to_forward:
            if message_to_forward.photo:
                # Отправляем самое большое доступное фото
                photo = message_to_forward.photo[-1]
                await bot.send_photo(chat_id=chat_id, photo=photo.file_id, caption=text, parse_mode='MarkdownV2' if text else None)
            elif message_to_forward.video:
                video = message_to_forward.video
                await bot.send_video(chat_id=chat_id, video=video.file_id, caption=text, parse_mode='MarkdownV2' if text else None)
            elif message_to_forward.animation:
                animation = message_to_forward.animation
                await bot.send_animation(chat_id=chat_id, animation=animation.file_id, caption=text, parse_mode='MarkdownV2' if text else None)
            elif message_to_forward.audio: # Добавлена обработка аудио
                audio = message_to_forward.audio
                await bot.send_audio(chat_id=chat_id, audio=audio.file_id, caption=text, parse_mode='MarkdownV2' if text else None)
            elif message_to_forward.document:
                document = message_to_forward.document
                await bot.send_document(chat_id=chat_id, document=document.file_id, caption=text, parse_mode='MarkdownV2' if text else None)
            elif text: # Если нет медиа, но есть текст в reply_to_message (что маловероятно для форварда медиа)
                await bot.send_message(chat_id=chat_id, text=text, parse_mode='MarkdownV2')
            else: # Если ни медиа, ни текста нет
                logger.warning(f"Попытка отправить пустое сообщение/медиа в чат {chat_id}.")
                return False
        elif text: # Если нет reply_to_message, но есть текст из команды
            await bot.send_message(chat_id=chat_id, text=text, parse_mode='MarkdownV2')
        else: # Сообщение полностью пустое
            logger.warning(f"Попытка отправить пустое сообщение/медиа в чат {chat_id}.")
            return False
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение/медиа в чат {chat_id}: {e}")
        return False

async def _send_broadcast_message(bot: Bot, chat_ids: list[int], text: str | None, message_to_reply: Message | None):
    """
    Отправляет сообщение или медиа нескольким получателям.
    Возвращает количество успешно отправленных сообщений и список чатов, в которые не удалось отправить.
    """
    sent_count = 0
    failed_chats = []
    if not chat_ids:
        logger.warning("Список получателей для рассылки пуст.")
        return 0, []

    for chat_id in chat_ids:
        success = await _send_message_or_media(bot, chat_id, text, message_to_reply)
        if success:
            sent_count += 1
        else:
            failed_chats.append(chat_id)
    return sent_count, failed_chats

# --- Вспомогательные функции для проверки прав ---
def is_global_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь глобальным администратором."""
    return user_id in ADMIN_ID

def is_group_admin(user_id: int, group_id: int) -> bool:
    """Проверяет, является ли пользователь администратором в конкретной группе."""
    return group_id in group_admins and user_id in group_admins[group_id]

def is_admin(user_id: int, chat_id: int | None = None) -> bool:
    """Проверяет, является ли пользователь администратором (глобальным или групповым)."""
    if is_global_admin(user_id):
        return True
    if chat_id and is_group_admin(user_id, chat_id):
        return True
    return False

# --- Вспомогательные функции для поиска пользователя ---
async def get_user_id_from_username(context: ContextTypes.DEFAULT_TYPE, username: str) -> int | None:
    """Пытается получить ID пользователя по его нику из кешированных данных."""
    cleaned_username = username.lstrip('@').lower()
    for uid, data in user_data.items():
        if data.get("username", "").lower() == cleaned_username:
            return uid
    
    # Если не нашли в локальных данных, можно попробовать получить из Telegram API,
    # но это требует либо chat_id (для get_chat_member), либо username (для search_by_username - не всегда доступно)
    # Для простоты, пока полагаемся на user_data, которая заполняется при каждом сообщении от пользователя.
    return None

async def _resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE, allow_username_lookup: bool = False) -> tuple[int | None, str | None]:
    """
    Resolves the target user ID from command arguments or a replied message.
    Returns (user_id, error_message) or (user_id, None) on success.
    """
    user_id = None
    error_message = None
    
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        return user_id, None
    
    if context.args:
        user_input = context.args[0]
        if user_input.replace('-', '').lstrip('+-').isdigit():
            user_id = int(user_input)
        elif allow_username_lookup:
            user_id = await get_user_id_from_username(context, user_input)
            if not user_id:
                error_message = f"Не удалось найти пользователя с ником `{escape_markdown(user_input, version=2)}`\\."
        else:
            error_message = "Неверный формат ID пользователя\\. Пожалуйста, введите числовой ID или ответьте на сообщение пользователя\\."
    else:
        error_message = "Пожалуйста, укажите ID пользователя или ответьте на сообщение пользователя\\."
        
    return user_id, error_message

def parse_duration(duration_str: str) -> timedelta | None:
    """
    Парсит строку длительности (например, '5d', '1h', '30m', '5d3h10m') в объект timedelta.
    Поддерживает комбинации дней, часов и минут.
    """
    if not duration_str:
        return None

    total_delta = timedelta()
    # Регулярное выражение для поиска чисел с единицами (d, h, m)
    # Ищет одну или несколько цифр, за которыми следует одна из букв d, h, m
    matches = re.findall(r'(\d+)([dhm])', duration_str.lower())

    if not matches: # Если нет совпадений, возможно, это невалидный формат
        return None

    for num_str, unit in matches:
        try:
            num = int(num_str)
            if unit == 'd':
                total_delta += timedelta(days=num)
            elif unit == 'h':
                total_delta += timedelta(hours=num)
            elif unit == 'm':
                total_delta += timedelta(minutes=num)
            # Игнорируем неизвестные единицы, но если нет совпадений, вернем None
        except ValueError:
            return None # Неверный формат числа

    # Если total_delta осталась нулевой, значит, не было валидных единиц
    if total_delta == timedelta(0):
        return None

    return total_delta

def get_human_readable_duration(td: timedelta) -> str:
    """Возвращает человекочитаемое представление длительности для timedelta."""
    # Эта функция должна вызываться только с конечными объектами timedelta.
    # Случай "Навсегда" обрабатывается вызывающими функциями на основе float('inf') для muted_until.
    
    seconds = int(td.total_seconds())
    if seconds < 0:
        return "Истекший срок" # Не должно происходить для корректных длительностей

    parts = []
    
    days = seconds // (24 * 3600)
    seconds %= (24 * 3600)
    if days > 0:
        parts.append(f"{days} дней")

    hours = seconds // 3600
    seconds %= 3600
    if hours > 0:
        parts.append(f"{hours} часов")

    minutes = seconds // 60
    seconds %= 60
    if minutes > 0:
        parts.append(f"{minutes} минут")

    if not parts:
        # Если длительность меньше минуты или равна 0
        if td == timedelta(0):
            return "0 секунд"
        else:
            return f"{seconds} секунд" # Для длительностей меньше минуты

    return " ".join(parts)

def get_random_mp3_file(folder_path: str) -> str | None:
    """Возвращает случайный путь к MP3 файлу из указанной папки."""
    if not os.path.exists(folder_path):
        logger.warning(f"Папка не найдена: {folder_path}")
        return None
    
    mp3_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.mp3')]
    if not mp3_files:
        logger.warning(f"В папке {folder_path} нет MP3 файлов.")
        return None
    
    return os.path.join(folder_path, random.choice(mp3_files))

# --- Обработчики команд ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    logger.info(f"Получена команда /start от пользователя {username} (ID: {user_id}) в чате {chat_id} ({chat_type})")

    # Обновление статистики
    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(user_id)

    # Сохраняем полные данные о пользователе
    user_data[user_id] = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name
    }

    response_text = "" # Инициализируем текст ответа

    if chat_type == 'private':
        if user_id in users_set: # Проверяем, зарегистрирован ли пользователь
            response_text = (
                f"Привет, {escape_markdown(username, version=2)}\\! Вы уже зарегистрированы\\. "
                f"Попробуйте команду `/help`\\."
            )
        else:
            users_set.add(user_id) # Добавляем пользователя в множество, если его там нет
            response_text = (
                f"Привет, {escape_markdown(username, version=2)}\\! Я бот, который поможет тебе с различными задачами\\. "
                f"Чтобы узнать, что я умею, используй команду `/help`\\."
            )
    elif chat_type in ['group', 'supergroup', 'channel']:
        known_groups_set.add(chat_id) # Добавляем группу в множество
        response_text = (
            f"Привет, {escape_markdown(username, version=2)}\\! Я бот, который поможет тебе с различными задачами\\. "
            f"Чтобы узнать, что я умею, используй команду `/help`\\."
        )
    save_data() # Сохраняем данные после потенциального изменения users_set или known_groups_set

    await update.message.reply_text(response_text, parse_mode='MarkdownV2')
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"Получена команда /help от пользователя {username} (ID: {user_id})")

    # Обновление статистики
    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(user_id)
    save_data()

    response_text = (
        "Я могу помочь тебе с различными задачами\\. Вот список доступных команд:\n"
        "`/start` \\- Начать взаимодействие с ботом\\.\n"
        "`/help` \\- Показать это сообщение помощи\\.\n"
        "`/id` \\- Показать ID текущего чата \\(в группе\\) или свой ID \\(в привате\\)\\.\n"
        "`/id me` \\- Показать свой ID\\.\n"
        "`/id` \\(в ответ на сообщение\\) \\- Показать ID чата и ID пользователя, чье сообщение процитировано\\.\n"
        "\n*Команды для администраторов \\(глобальных или групповых\\):*\n"
        "`/addw <user_id>` или \\(ответом на сообщение\\) `/addw` \\- Добавить пользователя в белый список\\.\n"
        "`/unwhite <user_id>` или \\(ответом на сообщение\\) `/unwhite` \\- Удалить пользователя из белого списка\\.\n"
        "`/listw` или `/show_whitelist` \\- Показать текущий белый список\\.\n"
        "`/unmute \\[user_id\\] \\[group_id\\|all\\]` \\- Показать список всех заблокированных пользователей \\(все чаты\\) или разблокировать пользователя\\.\n"
        "  \\- Без аргументов: Показать список всех заблокированных \\(все чаты\\)\\.\n"
        "  \\- `<user_id>`: Разблокировать пользователя глобально \\(везде\\)\\.\n"
        "  \\- `<user_id> <group_id>`: Разблокировать пользователя в конкретной группе\\.\n"
        "  \\- \\(ответом на сообщение\\) `/unmute \\[group_id\\|all\\]`: Разблокировать пользователя в текущей группе \\(или везде, если `all`\\)\\.\n"
        "`/mute <user_id> \\[group_id\\] \\[duration\\] \\[причина\\]` или \\(ответом на сообщение\\) `/mute \\[group_id\\] \\[duration\\] \\[причина\\]` \\- Заблокировать пользователя\\.\n"
        "  \\- `duration`: Время блокировки \\(например, `5d` \\(дней\\), `3h` \\(часов\\), `10m` \\(минут\\)\\) или их комбинации \\(например, `5d3h10m`\\)\\. Без `duration` \\- блокировка перманентна\\.\n"
        "  \\- Если в группе без `group_id`, блокировка в текущей группе\\. В привате `group_id` обязателен\\.\n"
        "`/mute_list` или `/mute list` \\- Показать список заблокированных пользователей в текущем чате\\.\n"
        "`/mute_all <user_id\\|username> \\[duration\\] \\[причина\\]` или \\(ответом на сообщение\\) `/mute_all \\[duration\\] \\[причина\\]` \\- Заблокировать пользователя во всех известных боту чатах\\.\n"
        "`/op <user_id> \\[group_id\\]` или \\(ответом на сообщение\\) `/op \\[group_id\\]` \\- Назначить пользователя администратором группы\\. Если в группе без `group_id`, назначит в текущей группе\\.\n"
        "`/deop <user_id> \\[group_id\\]` или \\(ответом на сообщение\\) `/deop \\[group_id\\]` \\- Снять административные права с пользователя группы\\. Если в группе без `group_id`, снимет в текущей группе\\.\n"
        "\n*Команды для рассылки \\(только для администраторов\\):*\n"
        "`/say \\[tc\\|all\\] \\<сообщение\\>` \\- Отправить сообщение\\.\n"
        "  \\- Без опций: Отправить всем известным пользователям \\(не группам\\)\\.\n"
        "  \\- `tc`: Отправить во все известные группы/каналы\\.\n"
        "  \\- `all`: Отправить всем известным пользователям и группам/каналам\\.\n"
        "  \\(Для отправки медиа/файлов: *ответьте* командой `/say` на файл с подписью\\.\\)\n"
        "`/spam \\[tc\\|all\\] \\<сообщение\\>` \\- Отправить сообщение\\.\n"
        "  \\- Без опций: Отправить всем известным пользователям \\(не группам\\)\\.\n"
        "  \\- `tc`: Отправить во все известные группы/каналы\\.\n"
        "  \\- `all`: Отправить всем известным пользователям и группам/каналам\\.\n"
        "  \\(Для отправки медиа/файлов: *ответьте* командой `/spam` на файл с подписью\\.\\)\n"
        "\n*Управление спам\\-защитой \\(только для администраторов\\):*\n"
        "`/save_on` \\- Включить спам\\-защиту\\.\n"
        "`/save_off` \\- Выключить спам\\-защиту\\.\n"
        "`/save on` \\- Включить спам\\-защиту \\(с аргументом\\)\\.\n"
        "`/save off` \\- Выключить спам\\-защиту \\(с аргументом\\)\\.\n"
        "`/save_list` \\- Показать текущий статус спам\\-защиты в этом чате\\.\n"
        "`/save list` \\- Показать текущий статус спам\\-защиты в этом чате \\(с аргументом\\)\\."
    )
    await update.message.reply_text(response_text, parse_mode='MarkdownV2')
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.effective_user.id
    current_chat_id = update.effective_chat.id
    response_text = ""

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(current_user_id)
    save_data()

    if context.args and context.args[0].lower() == 'me':
        response_text = f"Ваш ID: `{current_user_id}`\\."
    elif update.message.reply_to_message:
        replied_user_id = update.message.reply_to_message.from_user.id
        replied_user_name = update.message.reply_to_message.from_user.full_name or update.message.reply_to_message.from_user.username
        response_text = (
            f"ID чата: `{current_chat_id}`\\.\\n" 
            f"ID пользователя \\({escape_markdown(replied_user_name, version=2)}\\): `{replied_user_id}`\\."
        )
    elif update.effective_chat.type in ['group', 'supergroup', 'channel']:
        response_text = f"ID этого чата: `{current_chat_id}`\\."
    else: # Private chat without reply or arguments
        response_text = f"Ваш ID: `{current_user_id}`\\." 

    await update.message.reply_text(response_text, parse_mode='MarkdownV2')
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()


async def add_to_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    user_id_to_add, error_message = await _resolve_target_user(update, context)
    if error_message:
        await update.message.reply_text(error_message, parse_mode='MarkdownV2')
        return

    try:
        chat_id = str(update.effective_chat.id)

        whitelist_chats = read_json_file(WHITELIST_FILE) or {}
        if chat_id not in whitelist_chats:
            whitelist_chats[chat_id] = []

        if user_id_to_add not in whitelist_chats[chat_id]:
            whitelist_chats[chat_id].append(user_id_to_add)
            write_json_file(WHITELIST_FILE, whitelist_chats)
            await update.message.reply_text(f"Пользователь с ID `{user_id_to_add}` добавлен в белый список чата `{chat_id}`\\.", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(f"Пользователь с ID `{user_id_to_add}` уже находится в белом списке чата `{chat_id}`\\.", parse_mode='MarkdownV2')
    except ValueError:
        await update.message.reply_text("Неверный формат ID пользователя\\. Пожалуйста, введите числовой ID или ответьте на сообщение\\.", parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Ошибка при добавлении в белый список: {e}")
        await update.message.reply_text("Произошла ошибка при добавлении пользователя в белый список\\.", parse_mode='MarkdownV2')
    
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def remove_from_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    user_id_to_remove, error_message = await _resolve_target_user(update, context)
    if error_message:
        await update.message.reply_text(error_message, parse_mode='MarkdownV2')
        return

    try:
        chat_id = str(update.effective_chat.id)

        whitelist_chats = read_json_file(WHITELIST_FILE) or {}
        if chat_id in whitelist_chats and user_id_to_remove in whitelist_chats[chat_id]:
            whitelist_chats[chat_id].remove(user_id_to_remove)
            write_json_file(WHITELIST_FILE, whitelist_chats)
            await update.message.reply_text(f"Пользователь с ID `{user_id_to_remove}` удален из белого списка чата `{chat_id}`\\.", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(f"Пользователь с ID `{user_id_to_remove}` не найден в белом списке чата `{chat_id}`\\.", parse_mode='MarkdownV2')
    except ValueError:
        await update.message.reply_text("Неверный формат ID пользователя\\. Пожалуйста, введите числовой ID или ответьте на сообщение\\.", parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Ошибка при удалении из белого списка: {e}")
        await update.message.reply_text("Произошла ошибка при удалении пользователя из белого списка\\.", parse_mode='MarkdownV2')

    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def show_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    whitelist_chats = read_json_file(WHITELIST_FILE) or {}
    response_text = "*Текущий белый список:*\n\n"

    if not whitelist_chats:
        response_text += "Белый список пуст\\."
    else:
        for chat_id, users in whitelist_chats.items():
            # Удалены лишние 'n' и добавлен правильный перенос строки
            response_text += f"Чат ID: `{str(chat_id)}`\n" 
            if users:
                for user_id in users:
                    try:
                        user_info = await context.bot.get_chat_member(chat_id, user_id)
                        user_name = user_info.user.full_name or user_info.user.username or f"ID: {user_id}"
                        # Вывод ID и никнейма на отдельных строках
                        response_text += (
                            f"  \\- ID: `{str(user_id)}`\n"
                            f"    Ник: \\({escape_markdown(user_name, version=2)}\\)\n"
                        )
                    except Exception:
                        response_text += f"  \\- ID: `{str(user_id)}`\n    Ник: \\(Неизвестный пользователь\\)\n"
            else:
                response_text += "  \\(Список пользователей пуст\\)\n" 
            response_text += "\n" # Добавлен дополнительный перенос строки между чатами

    await update.message.reply_text(response_text, parse_mode='MarkdownV2')
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def unmute_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает список заблокированных пользователей (со всех чатов) или разблокирует пользователя.
    Использование:
    /unmute - показать список заблокированных (все чаты)
    /unmute <user_id> - разблокировать пользователя глобально
    /unmute <user_id> <group_id> - разблокировать пользователя в конкретной группе
    /unmute (reply to message) [group_id|all] - разблокировать пользователя в текущей группе (или везде, если 'all')
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    current_chat_id = update.effective_chat.id
    admin_id = update.effective_user.id
    
    user_id_to_unblock = None
    target_chat_id_to_unmute = None
    unmute_all_chats = False
    
    args_for_resolution = list(context.args)
    if update.message.reply_to_message:
        user_id_to_unblock = update.message.reply_to_message.from_user.id
        if args_for_resolution and args_for_resolution[0].lower() == 'all':
            unmute_all_chats = True
        elif args_for_resolution and args_for_resolution[0].replace('-', '').lstrip('+-').isdigit():
            target_chat_id_to_unmute = int(args_for_resolution[0])
        elif update.effective_chat.type in ['group', 'supergroup', 'channel']:
            target_chat_id_to_unmute = current_chat_id # Default to current group if replying and no specific group_id
    elif args_for_resolution:
        user_id_to_unblock_candidate, error_message = await _resolve_target_user(update, context, allow_username_lookup=False)
        if error_message:
            await update.message.reply_text(error_message, parse_mode='MarkdownV2')
            return
        user_id_to_unblock = user_id_to_unblock_candidate
        
        if len(args_for_resolution) > 1:
            if args_for_resolution[1].lower() == 'all':
                unmute_all_chats = True
            elif args_for_resolution[1].replace('-', '').lstrip('+-').isdigit():
                target_chat_id_to_unmute = int(args_for_resolution[1])
            else:
                await update.message.reply_text("Неверный формат ID группы или аргумента 'all'\\. Использование: `/unmute \\[user_id\\] \\[group_id\\|all\\]`", parse_mode='MarkdownV2')
                return
        else: # This is the case for /unmute <user_id> without further arguments
            if update.effective_chat.type in ['group', 'supergroup', 'channel']:
                target_chat_id_to_unmute = current_chat_id # Default to current group for /unmute <user_id> in a group
            else:
                unmute_all_chats = True # For private chat, /unmute <user_id> means global unmute

    if user_id_to_unblock is None: # No user ID specified, show list of muted users
        if not muted_users:
            response_text = "Список заблокированных пользователей пуст\\."
        else:
            response_text = "*Заблокированные пользователи \\(все чаты\\):*\n\n"
            for user_id, mutes_list in muted_users.items():
                if not mutes_list: # Пропускаем пользователей без активных мутов (может быть после удаления)
                    continue

                user_name_display = f"{user_id}"
                if user_id in user_data:
                    user_name_display = user_data[user_id].get('username') or user_data[user_id].get('first_name') or user_name_display
                
                for mute_entry in mutes_list:
                    reason = escape_markdown(mute_entry.get("reason", "неизвестно"), version=2)
                    muted_until_timestamp = mute_entry.get("muted_until", float('inf'))
                    timestamp_applied = mute_entry.get("timestamp_applied", 0)
                    
                    muted_until_str = "Навсегда"
                    if muted_until_timestamp != float('inf'):
                        dt_object = datetime.fromtimestamp(muted_until_timestamp)
                        muted_until_str = escape_markdown(dt_object.strftime('%Y\\-%m\\-%d %H\\:%M\\:%S'), version=2)
                    
                    human_readable_duration_for_entry = mute_entry.get("human_readable_duration")
                    # Здесь human_readable_duration_for_entry уже строка, не timedelta
                    if human_readable_duration_for_entry and human_readable_duration_for_entry != "Навсегда":
                         muted_until_str = f"{escape_markdown(human_readable_duration_for_entry, version=2)} \\(до {muted_until_str}\\)"

                    chat_id_for_entry = mute_entry.get("chat_id")
                    chat_name_for_entry = str(chat_id_for_entry)
                    try:
                        chat_info = await context.bot.get_chat(chat_id_for_entry)
                        chat_name_for_entry = chat_info.title or chat_info.first_name or chat_name_for_entry
                    except Exception:
                        pass # Cannot get chat info, use ID
                    
                    applied_time_str = "Неизвестно"
                    if timestamp_applied:
                        applied_dt_object = datetime.fromtimestamp(timestamp_applied)
                        applied_time_str = escape_markdown(applied_dt_object.strftime('%Y\\-%m\\-%d %H\\:%M\\:%S'), version=2)

                    # Формат вывода для каждой блокировки пользователя
                    response_text += (
                        f"\\- Пользователь: `{str(user_id)}` \\({escape_markdown(user_name_display, version=2)}\\)\\n"
                        f"  Причина: {reason}\\n"
                        f"  Заблокирован: {applied_time_str}\\n"
                        f"  Истекает: {muted_until_str}\\n"
                        f"  В чате: \\({escape_markdown(chat_name_for_entry, version=2)}: `{chat_id_for_entry}`\\)\\n\\n"
                    )
        await update.message.reply_text(response_text, parse_mode='MarkdownV2')
        return

    # Разблокировка пользователя
    if user_id_to_unblock not in muted_users or not muted_users[user_id_to_unblock]:
        await update.message.reply_text(f"Пользователь с ID `{user_id_to_unblock}` не найден в списке заблокированных\\.", parse_mode='MarkdownV2')
        return
    
    user_name_display = f"ID: {user_id_to_unblock}"
    if user_id_to_unblock in user_data:
        user_name_display = user_data[user_id_to_unblock].get('username') or user_data[user_id_to_unblock].get('first_name') or user_name_display

    removed_mutes_count = 0
    new_mutes_list = []
    removed_reasons = set() # Для сбора причин удаленных блокировок

    if unmute_all_chats:
        removed_mutes_count = len(muted_users[user_id_to_unblock])
        for entry in muted_users[user_id_to_unblock]:
            removed_reasons.add(entry.get("reason", "неизвестно"))
        
        del muted_users[user_id_to_unblock] # Remove all mutes
        if user_id_to_unblock in user_warnings:
            del user_warnings[user_id_to_unblock]
        
        reasons_text_plain = ', '.join(removed_reasons) if removed_reasons else "неизвестно"
        await update.message.reply_text(
            f"Пользователь ID: {user_id_to_unblock} разблокирован глобально (всего снято {removed_mutes_count} блокировок).\n"
            f"Причина(ы) блокировки: {reasons_text_plain}."
        )
        logger.info(f"Администратор {admin_id} разблокировал пользователя {user_id_to_unblock} глобально. Причины: {', '.join(removed_reasons)}.")
    elif target_chat_id_to_unmute:
        for mute_entry in muted_users[user_id_to_unblock]:
            if mute_entry["chat_id"] == target_chat_id_to_unmute:
                removed_mutes_count += 1
                removed_reasons.add(mute_entry.get("reason", "неизвестно"))
            else:
                new_mutes_list.append(mute_entry)
        
        muted_users[user_id_to_unblock] = new_mutes_list
        if not new_mutes_list: # Если больше нет активных мутов для этого пользователя
            if user_id_to_unblock in user_warnings:
                del user_warnings[user_id_to_unblock]
            del muted_users[user_id_to_unblock] # Удаляем пользователя из словаря, если все муты сняты

        if removed_mutes_count > 0:
            chat_name_for_response_plain = str(target_chat_id_to_unmute)
            try:
                chat_info = await context.bot.get_chat(target_chat_id_to_unmute)
                chat_name_for_response_plain = chat_info.title or chat_info.first_name or chat_name_for_response_plain
            except Exception:
                pass
            reasons_text_plain = ', '.join(removed_reasons) if removed_reasons else "неизвестно"
            await update.message.reply_text(
                f"Пользователь ID: {user_id_to_unblock} разблокирован в чате ({chat_name_for_response_plain}: {target_chat_id_to_unmute})\n"
                f"(снято {removed_mutes_count} блокировок).\n"
                f"Причина(ы) блокировки: {reasons_text_plain}."
            )
            logger.info(f"Администратор {admin_id} разблокировал пользователя {user_id_to_unblock} в чате {target_chat_id_to_unmute}. Причины: {', '.join(removed_reasons)}.")
        else:
            await update.message.reply_text(f"Пользователь {user_name_display} не был заблокирован в чате `{target_chat_id_to_unmute}`\\.", parse_mode='MarkdownV2')
    else: # Если указан только user_id_to_unblock, разблокируем глобально
        removed_mutes_count = len(muted_users[user_id_to_unblock])
        for entry in muted_users[user_id_to_unblock]:
            removed_reasons.add(entry.get("reason", "неизвестно"))
        
        del muted_users[user_id_to_unblock] # Remove all mutes
        if user_id_to_unblock in user_warnings:
            del user_warnings[user_id_to_unblock]
        
        reasons_text_plain = ', '.join(removed_reasons) if removed_reasons else "неизвестно"
        await update.message.reply_text(
            f"Пользователь ID: {user_id_to_unblock} разблокирован глобально (всего снято {removed_mutes_count} блокировок).\n"
            f"Причина(ы) блокировки: {reasons_text_plain}."
        )
        logger.info(f"Администратор {admin_id} разблокировал пользователя {user_id_to_unblock} глобально. Причины: {', '.join(removed_reasons)}.")

    save_data()
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Блокирует пользователя в одной группе или указанной группе.
    Использование: /mute <user_id> [group_id] [duration] [причина]
    Если в группе без group_id, блокировка в текущей группе. В привате group_id обязателен.
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    user_id_to_mute = None
    target_chat_id = None
    duration_str = None
    reason_parts = []
    
    # 1. Resolve target user ID
    if update.message.reply_to_message:
        user_id_to_mute = update.message.reply_to_message.from_user.id
        args_start_index = 0 # args will contain [group_id] [duration] [reason]
    elif context.args:
        try:
            user_id_to_mute = int(context.args[0])
            args_start_index = 1 # args will contain [group_id] [duration] [reason] starting from index 1
        except ValueError:
            await update.message.reply_text("Неверный формат ID пользователя\\. Пожалуйста, введите числовой ID или ответьте на сообщение\\.", parse_mode='MarkdownV2')
            return
    else:
        await update.message.reply_text("Пожалуйста, укажите ID пользователя или ответьте на сообщение\\. Использование: `/mute <user_id> \\[group_id\\] \\[duration\\] \\[причина\\]`\\nВ приватном чате ID группы обязателен\\.", parse_mode='MarkdownV2')
        return

    # 2. Determine target_chat_id, duration_str, and reason
    current_args_index = args_start_index
    
    # Try to parse group_id
    if len(context.args) > current_args_index and context.args[current_args_index].replace('-', '').lstrip('+-').isdigit():
        target_chat_id = int(context.args[current_args_index])
        current_args_index += 1
    elif update.effective_chat.type in ['group', 'supergroup', 'channel']:
        target_chat_id = update.effective_chat.id
    
    if not target_chat_id:
        await update.message.reply_text("В приватном чате для команды `/mute` обязательно укажите ID группы\\. Использование: `/mute <user_id> <group_id> \\[duration\\] \\[причина\\]`", parse_mode='MarkdownV2')
        return

    # Try to parse duration
    if len(context.args) > current_args_index:
        possible_duration_str = context.args[current_args_index].lower()
        # Проверяем, является ли следующий аргумент началом причины (не содержит d, h, m)
        if not re.search(r'[dhm]', possible_duration_str):
            # Если это не похоже на длительность, то это начало причины
            reason_parts = context.args[current_args_index:]
        else:
            duration_str = possible_duration_str
            current_args_index += 1
            reason_parts = context.args[current_args_index:]
    
    reason = "ручная блокировка администратором"
    if reason_parts:
        reason = " ".join(reason_parts)

    muted_until = float('inf') # По умолчанию навсегда
    human_readable_duration = "Навсегда"
    if duration_str:
        duration_delta = parse_duration(duration_str)
        if duration_delta:
            muted_until = (datetime.now() + duration_delta).timestamp()
            human_readable_duration = get_human_readable_duration(duration_delta)
        else:
            await update.message.reply_text("Неверный формат длительности\\. Используйте `5d`, `3h`, `10m` или их комбинации \\(например, `5d3h10m`\\)\\.", parse_mode='MarkdownV2')
            return

    # Добавляем или обновляем запись о блокировке
    if user_id_to_mute not in muted_users:
        muted_users[user_id_to_mute] = []
    
    # Проверяем, есть ли уже активная блокировка для этого чата
    existing_mute_index = -1
    for i, entry in enumerate(muted_users[user_id_to_mute]):
        if entry["chat_id"] == target_chat_id:
            existing_mute_index = i
            break

    mute_entry = {
        "chat_id": target_chat_id,
        "muted_until": muted_until,
        "reason": reason,
        "muted_by_admin_id": update.effective_user.id,
        "human_readable_duration": human_readable_duration, # Store this
        "timestamp_applied": datetime.now().timestamp() # New field
    }

    if existing_mute_index != -1:
        muted_users[user_id_to_mute][existing_mute_index] = mute_entry # Обновляем существующую
    else:
        muted_users[user_id_to_mute].append(mute_entry) # Добавляем новую
    
    # Очищаем предупреждения для блокируемого пользователя
    if user_id_to_mute in user_warnings:
        del user_warnings[user_id_to_mute]
    save_data()

    user_name_display_for_message_plain = user_data.get(user_id_to_mute, {}).get('username') or user_data.get(user_id_to_mute, {}).get('first_name', str(user_id_to_mute))
    reason_plain = reason

    mute_message_text = (
        f"Пользователь ({user_name_display_for_message_plain}) ID - {user_id_to_mute} успешно заблокирован в чате {target_chat_id}\n"
        f"Информация о прошлой блокировки\n"
        f"Время:{human_readable_duration}\n"
        f"Причина: {reason_plain}."
    )
    await update.message.reply_text(mute_message_text)
    logger.info(f"Администратор {update.effective_user.id} заблокировал пользователя {user_id_to_mute} по причине: {reason} {human_readable_duration} в чате {target_chat_id}")
    
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def handle_mute_with_args_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команды вида /mute <user_id> [group_id] [причина] и /mute list.
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    if context.args and context.args[0].lower() == 'list':
        await mute_list_command(update, context)
    else:
        # Если есть аргументы, и первый не 'list', то это команда mute пользователя
        await mute_command(update, context)


async def handle_say_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет сообщение, указанное администратором.
    Использование: /say [tc|all] <сообщение>
    Для отправки медиа: ответьте на медиафайл командой /say
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    user_id = update.effective_user.id
    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(user_id)
    save_data()

    target_chats = []
    message_text = None
    message_to_forward = update.message.reply_to_message # Получаем сообщение, на которое отвечают

    # Определяем, есть ли префикс и извлекаем текст
    args_lower = [arg.lower() for arg in context.args]
    if args_lower and args_lower[0] == 'tc':
        target_chats = list(known_groups_set)
        message_text = " ".join(context.args[1:])
    elif args_lower and args_lower[0] == 'all':
        target_chats = list(users_set.union(known_groups_set))
        message_text = " ".join(context.args[1:])
    else: # По умолчанию для /say - всем известным пользователям
        target_chats = list(users_set)
        message_text = " ".join(context.args)

    if not message_text and not message_to_forward:
        await update.message.reply_text("Пожалуйста, укажите сообщение для отправки или ответьте на медиафайл\\. Использование: `/say \\[tc\\|all\\] \\<сообщение\\>`", parse_mode='MarkdownV2')
        return

    sent_count, failed_chats = await _send_broadcast_message(context.bot, target_chats, message_text, message_to_forward)

    response_parts = [f"Сообщений отправлено: {sent_count}\\."] # Добавлен экранирующий символ
    if failed_chats:
        escaped_failed_chats = [f"`{str(chat_id)}`" for chat_id in failed_chats] 
        response_parts.append(f"Не удалось отправить в {len(failed_chats)} чат: {', '.join(escaped_failed_chats)}\\.") # Добавлен экранирующий символ
    
    final_response_text = " ".join(response_parts)
    await update.message.reply_text(final_response_text, parse_mode='MarkdownV2') # Сохраняем MarkdownV2 для всего сообщения
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + sent_count
    save_data()

async def handle_spam_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет сообщение, указанное администратором, всем известным пользователям или группам.
    Использование: /spam [tc|all] <сообщение>
    Для отправки медиа: ответьте на медиафайл командой /spam
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\", parse_mode='MarkdownV2')
        return

    user_id = update.effective_user.id
    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(user_id)
    save_data()

    target_chats = []
    message_text = None
    message_to_forward = update.message.reply_to_message  # Получаем сообщение, на которое отвечают

    args_lower = [arg.lower() for arg in context.args]
    if args_lower and args_lower[0] == 'tc':
        target_chats = list(known_groups_set)
        message_text = " ".join(context.args[1:])
    elif args_lower and args_lower[0] == 'all':
        target_chats = list(users_set.union(known_groups_set))
        message_text = " ".join(context.args[1:])
    else:  # По умолчанию для /spam - только пользователи
        target_chats = list(users_set)
        message_text = " ".join(context.args)

    if not message_text and not message_to_forward:
        await update.message.reply_text(
            "Пожалуйста, укажите сообщение для отправки или ответьте на медиафайл\\."
            "Использование: `/spam \\[tc\\|all\\] \\<сообщение\\>`",
            parse_mode='MarkdownV2'
        )
        return

    # Модифицируем текст сообщения, добавляя подпись
    if message_text:
        message_text += "\n\n*Сообщение от администратора*"

    sent_count, failed_chats = await _send_broadcast_message(context.bot, target_chats, message_text, message_to_forward)

    response_parts = [f"Сообщений отправлено: {sent_count}\\."]  # Добавлен экранирующий символ
    if failed_chats:
        escaped_failed_chats = [f"`{str(chat_id)}`" for chat_id in failed_chats]
        response_parts.append(
            f"Не удалось отправить в {len(failed_chats)} чат: {', '.join(escaped_failed_chats)}\\."
        )  # Добавлен экранирующий символ

    final_response_text = " ".join(response_parts)
    await update.message.reply_text(final_response_text, parse_mode='MarkdownV2')  # Сохраняем MarkdownV2 для всего сообщения
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + sent_count
    save_data()

# --- Команды для управления спам-защитой ---

async def spam_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включает спам-защиту."""
    global spam_protection_enabled
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return
    spam_protection_enabled = True
    save_data()
    await update.message.reply_text("Спам\\-защита *ВКЛЮЧЕНА*\\.", parse_mode='MarkdownV2')
    logger.info(f"Администратор {update.effective_user.id} включил спам-защиту.")
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def spam_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выключает спам-защиту."""
    global spam_protection_enabled
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return
    spam_protection_enabled = False
    save_data()
    await update.message.reply_text("Спам\\-защита *ВЫКЛЮЧЕНА*\\.", parse_mode='MarkdownV2')
    logger.info(f"Администратор {update.effective_user.id} выключил спам-защиту.")
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def save_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущий статус спам-защиты в этом чате."""
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return
    status_text = "ВКЛЮЧЕНА" if spam_protection_enabled else "ВЫКЛЮЧЕНА"
    await update.message.reply_text(f"Спам\\-защита в данный момент: *{status_text}*\\.", parse_mode='MarkdownV2')
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def save_with_args_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команды вида /save on, /save off, /save list.
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите аргумент 'on', 'off' или 'list' после `/save`\\. Пример: `/save on` или `/save list`\\.", parse_mode='MarkdownV2')
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()
        return

    arg = context.args[0].lower()
    if arg == 'on':
        await spam_on_command(update, context)
    elif arg == 'off':
        await spam_off_command(update, context)
    elif arg == 'list':
        await save_list_command(update, context)
    else:
        await update.message.reply_text("Неизвестный аргумент\\. Используйте `/save on`, `/save off` или `/save list`\\.", parse_mode='MarkdownV2')
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def mute_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Показывает список заблокированных пользователей только в текущем чате.
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    current_chat_id = update.effective_chat.id
    response_text = f"*Заблокированные пользователи в этом чате \\(`{current_chat_id}`\\):*\n\n"
    
    muted_in_this_chat = False
    for user_id, mutes_list in muted_users.items():
        for mute_entry in mutes_list:
            if mute_entry["chat_id"] == current_chat_id:
                muted_in_this_chat = True
                reason = escape_markdown(mute_entry.get("reason", "неизвестно"), version=2)
                muted_until_timestamp = mute_entry.get("muted_until", float('inf'))
                
                muted_by_admin = mute_entry.get("muted_by_admin_id")
                admin_info = ""
                if muted_by_admin and muted_by_admin in user_data:
                    admin_username = user_data[muted_by_admin].get("username") or user_data[muted_by_admin].get("first_name")
                    if admin_username:
                        admin_info = f" \\(админ: {escape_markdown(admin_username, version=2)}\\)"

                if muted_until_timestamp == float('inf'):
                    muted_until_str = "Навсегда"
                else:
                    dt_object = datetime.fromtimestamp(muted_until_timestamp)
                    muted_until_str = escape_markdown(dt_object.strftime('%Y\\-%m\\-%d %H\\:%M\\:%S'), version=2)
                
                user_name_display = f"ID: {user_id}"
                if user_id in user_data:
                    user_name_display = user_data[user_id].get('username') or user_data[user_id].get('first_name') or user_name_display
                
                response_text += (
                    f"\\- `{str(user_id)}` \\({escape_markdown(user_name_display, version=2)}\\)\\n"
                    f"  Причина: {reason}{admin_info}\\n"
                    f"  Заблокирован до: {muted_until_str}\\.\\n"
                )
    
    if not muted_in_this_chat:
        response_text += "В этом чате нет заблокированных пользователей\\."

    await update.message.reply_text(response_text, parse_mode='MarkdownV2')
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()

async def mute_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Блокирует пользователя во всех известных боту чатах.
    Использование: /mute_all <user_id|username> [duration] [причина] или ответом на сообщение /mute_all [duration] [причина]
    """
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    user_id_to_mute = None
    duration_str = None
    reason_parts = []
    
    # 1. Resolve target user ID
    if update.message.reply_to_message:
        user_id_to_mute = update.message.reply_to_message.from_user.id
        args_start_index = 0 # args will contain [duration] [reason]
    elif context.args:
        user_id_to_mute_candidate, error_message = await _resolve_target_user(update, context, allow_username_lookup=True)
        if error_message:
            await update.message.reply_text(error_message, parse_mode='MarkdownV2')
            return
        user_id_to_mute = user_id_to_mute_candidate
        args_start_index = 1 # args will contain [duration] [reason] starting from index 1
    else:
        await update.message.reply_text("Пожалуйста, укажите ID пользователя/ник или ответьте на сообщение\\. Использование: `/mute_all <user_id\\|username> \\[duration\\] \\[причина\\]`", parse_mode='MarkdownV2')
        return

    current_args_index = args_start_index
    # Try to parse duration
    if len(context.args) > current_args_index:
        possible_duration_str = context.args[current_args_index].lower()
        # Проверяем, является ли следующий аргумент началом причины (не содержит d, h, m)
        if not re.search(r'[dhm]', possible_duration_str):
            # Если это не похоже на длительность, то это начало причины
            reason_parts = context.args[current_args_index:]
        else:
            duration_str = possible_duration_str
            current_args_index += 1
            reason_parts = context.args[current_args_index:]
    
    reason = "глобальная блокировка администратором"
    if reason_parts:
        reason = " ".join(reason_parts)

    muted_until = float('inf') # По умолчанию навсегда
    human_readable_duration = "Навсегда"
    if duration_str:
        duration_delta = parse_duration(duration_str)
        if duration_delta:
            muted_until = (datetime.now() + duration_delta).timestamp()
            human_readable_duration = get_human_readable_duration(duration_delta)
        else:
            await update.message.reply_text("Неверный формат длительности\\. Используйте `5d`, `3h`, `10m` или их комбинации \\(например, `5d3h10m`\\)\\.", parse_mode='MarkdownV2')
            return

    # Добавляем или обновляем записи о блокировке во всех известных чатах
    if user_id_to_mute not in muted_users:
        muted_users[user_id_to_mute] = []
    
    user_name_display_for_message_plain = user_data.get(user_id_to_mute, {}).get('username') or user_data.get(user_id_to_mute, {}).get('first_name', str(user_id_to_mute))

    # Объединяем всех известных пользователей и группы для глобальной блокировки
    all_chats_to_mute_in = list(known_groups_set.union(users_set))

    newly_muted_chats = []
    updated_mutes_count = 0

    for chat_id_to_mute in all_chats_to_mute_in:
        existing_mute_index = -1
        for i, entry in enumerate(muted_users[user_id_to_mute]):
            if entry["chat_id"] == chat_id_to_mute:
                existing_mute_index = i
                break
        
        mute_entry = {
            "chat_id": chat_id_to_mute,
            "muted_until": muted_until,
            "reason": reason,
            "muted_by_admin_id": update.effective_user.id,
            "human_readable_duration": human_readable_duration, # Store this
            "timestamp_applied": datetime.now().timestamp() # New field
        }

        if existing_mute_index != -1:
            muted_users[user_id_to_mute][existing_mute_index] = mute_entry
            updated_mutes_count += 1
        else:
            muted_users[user_id_to_mute].append(mute_entry)
            newly_muted_chats.append(chat_id_to_mute)
    
    # Clear warnings for the user
    if user_id_to_mute in user_warnings:
        del user_warnings[user_id_to_mute]
    save_data()

    muted_until_display = ""
    if muted_until != float('inf'):
        dt_obj = datetime.fromtimestamp(muted_until)
        muted_until_display = escape_markdown(dt_obj.strftime('%Y\\-%m\\-%d %H\\:%M\\:%S'), version=2)

    duration_info = ""
    if human_readable_duration != "Навсегда":
        duration_info = f" на {human_readable_duration} "
        if muted_until != float('inf'):
            duration_info += f"\\(до {muted_until_display}\\)"
    elif muted_until == float('inf'):
        duration_info = " навсегда"

    response_parts = [
        f"Пользователь ({user_name_display_for_message_plain}) ID - {user_id_to_mute} успешно заблокирован глобально",
        "Информация о прошлой блокировки",
        f"Время:{human_readable_duration}",
        f"Причина: {reason}."
    ]
    
    # Добавляем информацию о новых/обновленных блокировках, если есть
    if newly_muted_chats:
        escaped_newly_muted_chats = [f"`{chat_id}`" for chat_id in newly_muted_chats]
        response_parts.append(f"Новые блокировки добавлены в чаты: {', '.join(escaped_newly_muted_chats)}.")
    if updated_mutes_count > 0:
        response_parts.append(f"Обновлено {updated_mutes_count} существующих блокировок.")
    
    await update.message.reply_text("\n".join(response_parts))
    logger.info(f"Администратор {update.effective_user.id} глобально заблокировал пользователя {user_id_to_mute} по причине: {reason} {duration_info}.")
    
    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
    save_data()


async def op_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Назначает пользователя администратором группы.
    Использование: /op <user_id> [group_id] или ответом на сообщение /op [group_id]
    """
    if not is_global_admin(update.effective_user.id): # Только глобальные админы могут добавлять/удалять групповых админов
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\. Только глобальные администраторы могут назначать других администраторов групп\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    target_user_id, error_message = await _resolve_target_user(update, context)
    if error_message:
        await update.message.reply_text(error_message, parse_mode='MarkdownV2')
        return

    try:
        target_group_id = None
        args_offset = 0 # Смещение для парсинга group_id в context.args
        if not update.message.reply_to_message:
            args_offset = 1 # Если не ответ, user_id был args[0], group_id может быть args[1]

        if len(context.args) > args_offset and context.args[args_offset].replace('-', '').lstrip('+-').isdigit():
            target_group_id = int(context.args[args_offset])
        elif update.effective_chat.type in ['group', 'supergroup']:
            target_group_id = update.effective_chat.id
        
        if not target_group_id:
            await update.message.reply_text("Для назначения админа вне текущей группы, пожалуйста, укажите ID группы\\. Использование: `/op <user_id> <group_id>` или \\(ответом на сообщение\\) `/op <group_id>`", parse_mode='MarkdownV2')
            stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            save_data()
            return

        if is_global_admin(target_user_id):
            await update.message.reply_text(f"Пользователь с ID `{target_user_id}` является глобальным администратором и не может быть добавлен/удален из групповых администраторов\\.", parse_mode='MarkdownV2')
            stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            save_data()
            return

        if target_group_id not in group_admins:
            group_admins[target_group_id] = []
        
        if target_user_id not in group_admins[target_group_id]:
            group_admins[target_group_id].append(target_user_id)
            save_data()
            user_info_str = f"`{target_user_id}`"
            if target_user_id in user_data:
                user_info_str = f"`{target_user_id}` \\({escape_markdown(user_data[target_user_id].get('username') or user_data[target_user_id].get('first_name'), version=2)}\\)"
            
            await update.message.reply_text(
                f"Пользователь {user_info_str} теперь администратор в группе с ID `{target_group_id}`\\.",
                parse_mode='MarkdownV2'
            )
            logger.info(f"Администратор {update.effective_user.id} добавил {target_user_id} как админа в группе {target_group_id}.")
        else:
            await update.message.reply_text(
                f"Пользователь с ID `{target_user_id}` уже является администратором в группе с ID `{target_group_id}`\\.",
                parse_mode='MarkdownV2'
            )
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()

    except ValueError:
        await update.message.reply_text("Неверный формат ID пользователя или группы\\. Пожалуйста, введите числовые ID\\.", parse_mode='MarkdownV2')
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()
    except Exception as e:
        logger.error(f"Ошибка при добавлении администратора: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при добавлении администратора\\.", parse_mode='MarkdownV2')
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()

async def deop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Снимает права администратора с пользователя группы.
    Использование: /deop <user_id> [group_id] или ответом на сообщение /deop [group_id]
    """
    if not is_global_admin(update.effective_user.id): # Только глобальные админы могут добавлять/удалять групповых админов
        await update.message.reply_text("У вас нет прав для выполнения этой команды\\. Только глобальные администраторы могут снимать других администраторов групп\\.", parse_mode='MarkdownV2')
        return

    stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
    unique_users.add(update.effective_user.id)
    save_data()

    target_user_id, error_message = await _resolve_target_user(update, context)
    if error_message:
        await update.message.reply_text(error_message, parse_mode='MarkdownV2')
        return

    try:
        target_group_id = None
        args_offset = 0
        if not update.message.reply_to_message:
            args_offset = 1

        if len(context.args) > args_offset and context.args[args_offset].replace('-', '').lstrip('+-').isdigit():
            target_group_id = int(context.args[args_offset])
        elif update.effective_chat.type in ['group', 'supergroup']:
            target_group_id = update.effective_chat.id
        
        if not target_group_id:
            await update.message.reply_text("Для снятия админа вне текущей группы, пожалуйста, укажите ID группы\\. Использование: `/deop <user_id> <group_id>` или \\(ответом на сообщение\\) `/deop <group_id>`", parse_mode='MarkdownV2')
            stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            save_data()
            return

        if is_global_admin(target_user_id):
            await update.message.reply_text(f"Пользователь с ID `{target_user_id}` является глобальным администратором и не может быть добавлен/удален из групповых администраторов\\.", parse_mode='MarkdownV2')
            stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            save_data()
            return

        if target_group_id in group_admins and target_user_id in group_admins[target_group_id]:
            group_admins[target_group_id].remove(target_user_id)
            if not group_admins[target_group_id]: # Удаляем запись о группе, если в ней больше нет админов
                del group_admins[target_group_id]
            save_data()
            user_info_str = f"`{target_user_id}`"
            if target_user_id in user_data:
                user_info_str = f"`{target_user_id}` \\({escape_markdown(user_data[target_user_id].get('username') or user_data[target_user_id].get('first_name'), version=2)}\\)"

            await update.message.reply_text(
                f"Пользователь {user_info_str} более не является администратором в группе с ID `{target_group_id}`\\.",
                parse_mode='MarkdownV2'
            )
            logger.info(f"Администратор {update.effective_user.id} снял {target_user_id} с админа в группе {target_group_id}.")
        else:
            await update.message.reply_text(
                f"Пользователь с ID `{target_user_id}` не является администратором в группе с ID `{target_group_id}`\\.",
                parse_mode='MarkdownV2'
            )
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()

    except ValueError:
        await update.message.reply_text("Неверный формат ID пользователя или группы\\. Пожалуйста, введите числовые ID\\.", parse_mode='MarkdownV2')
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()
    except Exception as e:
        logger.error(f"Ошибка при снятии администратора: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при снятии администратора\\.", parse_mode='MarkdownV2')
        stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
        save_data()

# --- Обработчик текстовых сообщений (для спам-фильтра и смешного контента) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        user = update.effective_user
        user_id = user.id
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        username = user.username or user.first_name
        message_date = update.message.date # Получаем дату сообщения
        message_text = update.message.text if update.message.text else "" # Получаем исходный текст
        message_text_lower = message_text.lower() # Для проверок на спам

        logger.info(f"Получено сообщение от {username} (ID: {user_id}) в чате {chat_id} ({chat_type}): '{message_text}'")

        # Логирование всех входящих сообщений
        message_log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "username": username,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "message_id": update.message.message_id,
            "text": message_text,
            "is_command": bool(update.message.text and update.message.text.startswith('/'))
            # Можно добавить больше полей, если нужно: photo, video, document, etc.
        }
        append_to_message_log(message_log_entry)

        # Обновление статистики и известных чатов/пользователей
        stats_data['messages_received'] = stats_data.get('messages_received', 0) + 1
        unique_users.add(user_id)
        
        # Сохраняем полные данные о пользователе
        user_data[user_id] = {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }

        if chat_type == 'private':
            users_set.add(user_id) # Добавляем пользователя в users_set
        elif chat_type in ['group', 'supergroup', 'channel']:
            known_groups_set.add(chat_id)
        save_data()

        # 1. Проверка на заблокированных пользователей (muted_users)
        if user_id in muted_users:
            is_muted_in_this_chat = False
            for mute_entry in muted_users[user_id]:
                if mute_entry["chat_id"] == chat_id and datetime.now().timestamp() < mute_entry.get("muted_until", float('inf')):
                    is_muted_in_this_chat = True
                    break
            
            if is_muted_in_this_chat:
                logger.info(f"Сообщение от заблокированного пользователя {user_id} в чате {chat_id} будет удалено.")
                try:
                    await update.message.delete()
                    logger.info(f"Сообщение от {user_id} в чате {chat_id} удалено.")
                except Exception as e:
                    logger.error(f"Не удалось удалить сообщение от заблокированного пользователя {user_id} в чате {chat_id}: {e}")
                return # Прекращаем обработку сообщения
            else:
                logger.debug(f"Пользователь {user_id} заблокирован в других чатах или его мут истек в этом чате ({chat_id}).")


        # 2. Проверка на белый список (не применять смешной контент и спам-фильтр к whitelisted)
        whitelist_chats = read_json_file(WHITELIST_FILE) or {}
        if str(chat_id) in whitelist_chats and user_id in whitelist_chats[str(chat_id)]:
            logger.info(f"Пользователь {user_id} в белом списке, смешной контент и спам-фильтр не применяются.")
            return # Прекращаем обработку, если пользователь в белом списке

        # --- Смешной контент: Ответ на вопрос "Ты сосал?" ---
        suck_keywords = ["сосал", "сосал?"]
        # Реагируем, если в сообщении есть "бот" (любой регистр) И одно из ключевых слов "сосал"
        if "бот" in message_text_lower and any(keyword in message_text_lower for keyword in suck_keywords):
            choices = ["да", "конечно", "нет", "Не сосал", MP3_10_FOLDER, MP3_5_FOLDER]
            weights = [0.10, 0.10, 0.325, 0.325, 0.10, 0.05] # Сумма должна быть 1.0 (20% да/конечно, 65% нет/не сосал, 10% 10mp3, 5% 5mp3)
            
            chosen_response = random.choices(choices, weights=weights, k=1)[0]
            
            if chosen_response in ["да", "конечно", "нет", "Не сосал"]:
                await update.message.reply_text(chosen_response) # Убрал escape_markdown, так как это простой текст
            else: # Это путь к MP3 файлу
                mp3_path = get_random_mp3_file(chosen_response)
                if mp3_path:
                    try:
                        with open(mp3_path, 'rb') as audio_file:
                            await context.bot.send_audio(chat_id=chat_id, audio=audio_file)
                    except Exception as e:
                        logger.error(f"Не удалось отправить MP3 файл {mp3_path}: {e}")
                        await update.message.reply_text("Извините, не могу отправить аудиофайл.") 
                else:
                    await update.message.reply_text("Извините, не могу найти аудиофайл.") 
            stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            save_data()
            return # Прекращаем обработку после смешного ответа
        else:
            logger.debug(f"Пропускаю реакцию на 'сосал' в чате {chat_id} из-за отсутствия 'бот' или ключевых слов.")

        # --- Смешной контент: Реакция на оскорбления ---
        insult_keywords = [
            "тупой", "говно", "идиот", "дебил", "урод", "дурак", "кретин", "отстой", "отброс", "чмо",
            "ублюдок", "мразь", "сука", "пидор", "хуй", "блядь", "гандон", "гнида", "долбоёб",
            "ебанат", "пиздец", "уебок", "чмошник", "мразь", "урод", "козел", "свинья", "тварь",
            "лох", "мудак", "конченый", "ушлепок", "дегенерат", "ублюдочный", "мразота", "шлюха",
            "пидорас", "хуесос", "говнюк", "ублюдина"
        ]
        # Реагируем, если в сообщении есть "бот" (любой регистр) И одно из ключевых слов-оскорблений
        if "бот" in message_text_lower and any(keyword in message_text_lower for keyword in insult_keywords):
            choices = [MP3_269_FOLDER, MP3_220_FOLDER, "angry_emoji"]
            weights = [0.69, 0.20, 0.01] # Сумма должна быть 1.0
            
            chosen_reaction = random.choices(choices, weights=weights, k=1)[0]
            
            if chosen_reaction == "angry_emoji":
                # Можно использовать Unicode смайлик или стикер ID, если есть
                await update.message.reply_text("😡") # Злой смайлик
            else: # Это путь к MP3 файлу
                mp3_path = get_random_mp3_file(chosen_reaction)
                if mp3_path:
                    try:
                        with open(mp3_path, 'rb') as audio_file:
                            await context.bot.send_audio(chat_id=chat_id, audio=audio_file)
                    except Exception as e:
                        logger.error(f"Не удалось отправить MP3 файл {mp3_path}: {e}")
                        await update.message.reply_text("Извините, не могу отправить аудиофайл.") 
                else:
                    await update.message.reply_text("Извините, не могу найти аудиофайл.") 
            stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            save_data()
            return # Прекращаем обработку после смешного ответа
        else:
            logger.debug(f"Пропускаю реакцию на оскорбления в чате {chat_id} из-за отсутствия 'бот' или ключевых слов.")


        # Только запускаем проверки спама/флуда, если спам-защита включена
        if not spam_protection_enabled:
            logger.debug("Спам-защита ВЫКЛ. Пропускаем проверку сообщения на спам/флуд.")
            return # Пропускаем остальную логику спам-фильтра

        is_spam = False
        spam_reasons_for_admin = []
        spam_reasons_for_user = []
        detected_forbidden_words_in_message = [] # Инициализация здесь

        # 3. Проверка на запрещенные слова
        if message_text_lower: # Проверяем только если есть текст
            for word in FORBIDDEN_WORDS:
                if word in message_text_lower:
                    is_spam = True
                    detected_forbidden_words_in_message.append(word)
            
            if detected_forbidden_words_in_message:
                # Для админа: указываем все найденные запрещенные слова
                spam_reasons_for_admin.append(f"запрещенное слово: '{', '.join(detected_forbidden_words_in_message)}'")
                # Для пользователя: общая формулировка
                spam_reasons_for_user.append("запрещенное слово")


        # 4. Проверка на флуд
        current_time = time.time()
        # Очищаем старые записи
        user_message_history[user_id] = [
            (ts, msg_id) for ts, msg_id in user_message_history[user_id] if current_time - ts < TIME_WINDOW
        ]
        user_message_history[user_id].append((current_time, update.message.message_id))
        logger.debug(f"История сообщений для пользователя {user_id}: {len(user_message_history[user_id])} сообщений за {TIME_WINDOW}с. Лимит: {MESSAGE_LIMIT}")

        if len(user_message_history[user_id]) > MESSAGE_LIMIT:
            is_spam = True
            spam_reasons_for_admin.append("флуд (слишком частые сообщения)")
            spam_reasons_for_user.append("флуд (слишком частые сообщения)")
            user_message_history[user_id].clear() # Очищаем историю флуда после срабатывания

        # Формируем итоговые строки причин
        final_spam_reason_admin = ", ".join(spam_reasons_for_admin) if spam_reasons_for_admin else "неизвестная причина"
        final_spam_reason_user = ", ".join(spam_reasons_for_user) if spam_reasons_for_user else "неизвестная причина"

        # 5. Действия при обнаружении спама (общая логика для слов и флуда)
        if is_spam:
            # Получаем количество предупреждений ДО инкремента для отображения N-го предупреждения
            current_warning_count = user_warnings.get(user_id, 0) + 1
            user_warnings[user_id] = current_warning_count
            save_data() # Сохраняем обновленные предупреждения

            # Удаляем сообщение/сообщения, вызвавшие спам/предупреждение/блокировку
            try:
                # Для флуда и запрещенных слов просто удаляем текущее сообщение
                await update.message.delete()
                logger.info(f"Сообщение от {user_id} удалено (причина: {final_spam_reason_admin}).")
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение от {user_id} (причина: {final_spam_reason_admin}): {e}")
            
            if current_warning_count >= MAX_WARNINGS:
                # Добавляем блокировку в muted_users для текущего чата
                if user_id not in muted_users:
                    muted_users[user_id] = []
                
                mute_entry = {
                    "chat_id": chat_id,
                    "muted_until": float('inf'), # Автоматическая блокировка навсегда
                    "reason": final_spam_reason_admin,
                    "muted_by_admin_id": None, # Автоматическая блокировка, нет админа
                    "human_readable_duration": "Навсегда",
                    "timestamp_applied": datetime.now().timestamp()
                }

                # Проверяем, есть ли уже активная блокировка для этого чата
                existing_mute_index = -1
                for i, entry in enumerate(muted_users[user_id]):
                    if entry["chat_id"] == chat_id:
                        existing_mute_index = i
                        break
                
                if existing_mute_index != -1:
                    muted_users[user_id][existing_mute_index] = mute_entry # Обновляем
                else:
                    muted_users[user_id].append(mute_entry) # Добавляем

                if user_id in user_warnings: # Удаляем из предупреждений после блокировки
                    del user_warnings[user_id]
                save_data() # Сохраняем обновленный muted_users и предупреждения
                
                # Уведомляем пользователя и админа о блокировке
                try:
                    ban_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # Сообщение для пользователя (причина без слова-триггера)
                    block_message_for_user = escape_markdown(
                        f"Пользователь {username} (ID: `{user_id}`), вы были заблокированы за спам/нарушение правил ({final_spam_reason_user}). "
                        f"Ваши сообщения будут автоматически удаляться. Это ваше {current_warning_count}-е предупреждение.", 
                        version=2
                    )
                    # Сообщение для админа (причина со словом-триггером, если есть)
                    admin_reason_detail = final_spam_reason_admin

                    block_message_for_admin = escape_markdown(
                        f"Пользователь {username} (ID: `{user_id}`) был заблокирован за спам/нарушение правил ({admin_reason_detail}). "
                        f"Его сообщения будут автоматически удаляться. Дата/Время блокировки: {ban_time_str}. Это было его {current_warning_count}-е предупреждение.",
                        version=2
                    )
                    await context.bot.send_message(chat_id=chat_id, text=block_message_for_user, parse_mode='MarkdownV2')
                    
                    # Отправляем сообщение глобальному админу, если это не он сам, или если это приватный чат
                    if update.effective_user.id != ADMIN_ID[0] or chat_type == 'private':
                        await context.bot.send_message(chat_id=ADMIN_ID[0], text=block_message_for_admin, parse_mode='MarkdownV2')
                    
                    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 2 
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление о блокировке: {e}")
            else:
                # Отправляем предупреждение
                try:
                    warning_message_text = escape_markdown(
                        f"Предупреждение {current_warning_count}/{MAX_WARNINGS} для {username} (ID: `{user_id}`): "
                        f"Ваше сообщение удалено из-за подозрения на спам ({final_spam_reason_user}). Пожалуйста, ознакомьтесь с правилами чата.",
                        version=2
                    )
                    await context.bot.send_message(chat_id=chat_id, text=warning_message_text, parse_mode='MarkdownV2')
                    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1 
                except Exception as e:
                    logger.error(f"Не удалось отправить предупреждение: {e}")
            save_data() # Сохраняем данные после всех операций
            return # Прекращаем обработку, сообщение обработано
    
    logger.info(f"Сообщение от {username} прошло проверку на спам.")

async def check_and_unmute_periodically(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Периодически проверяет истекшие блокировки и снимает их.
    """
    global muted_users
    current_time = datetime.now().timestamp()
    users_to_unmute_notification = defaultdict(list) # {user_id: [mute_entry, mute_entry, ...]}
    
    users_to_remove_completely = []

    for user_id, mutes_list in list(muted_users.items()): # Итерируем по копии, чтобы можно было изменять оригинал
        new_mutes_list = []
        user_has_active_mutes = False
        for mute_entry in mutes_list:
            if mute_entry.get("muted_until", float('inf')) < current_time:
                # Блокировка истекла
                users_to_unmute_notification[user_id].append(mute_entry)
                logger.info(f"Автоматическая разблокировка пользователя {user_id} в чате {mute_entry['chat_id']} (истек срок).")
            else:
                new_mutes_list.append(mute_entry)
                user_has_active_mutes = True
        
        if not user_has_active_mutes:
            users_to_remove_completely.append(user_id)
        else:
            muted_users[user_id] = new_mutes_list # Обновляем список блокировок для пользователя

    for user_id in users_to_remove_completely:
        if user_id in muted_users:
            del muted_users[user_id]
        if user_id in user_warnings:
            del user_warnings[user_id]
        logger.info(f"Пользователь {user_id} полностью разблокирован (все блокировки истекли).")
    
    save_data() # Сохраняем изменения после массового обновления

    # Отправка уведомлений о разблокировке
    for user_id, unmute_entries in users_to_unmute_notification.items():
        user_name = user_data.get(user_id, {}).get("username") or user_data.get(user_id, {}).get("first_name", f"ID: {user_id}")
        
        for entry in unmute_entries:
            chat_id_unmuted = entry["chat_id"]
            reason = entry.get("reason", "неизвестно") # Не экрамируем здесь, если хотим plain
            human_readable_duration = entry.get("human_readable_duration", "Навсегда")

            chat_name_display = str(chat_id_unmuted)
            try:
                chat_info = await context.bot.get_chat(chat_id_unmuted)
                chat_name_display = chat_info.title or chat_info.first_name or chat_name_display
            except Exception:
                pass # Не удалось получить информацию о чате
            
            unmute_message = (
                f"Пользователь {user_name} (ID: {user_id}), ваша блокировка ({reason}) в чате {chat_name_display} (ID: {chat_id_unmuted}) на {human_readable_duration} истекла и была снята автоматически."
            )
            try:
                await context.bot.send_message(chat_id=chat_id_unmuted, text=unmute_message) # Без MarkdownV2
                stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о разблокировке пользователю {user_id} в чате {chat_id_unmuted}: {e}")

    # Также отправить уведомление глобальному админу, если mute был не в его чате
    for user_id, unmute_entries in users_to_unmute_notification.items():
        user_name = user_data.get(user_id, {}).get("username") or user_data.get(user_id, {}).get("first_name", f"ID: {user_id}")
        for entry in unmute_entries:
            chat_id_unmuted = entry["chat_id"]
            reason = entry.get("reason", "неизвестно") # Не экрамируем здесь, если хотим plain
            human_readable_duration = entry.get("human_readable_duration", "Навсегда")

            if chat_id_unmuted != ADMIN_ID[0]: # Если разблокировка произошла не в чате админа (чтобы избежать дублирования)
                chat_name_display = str(chat_id_unmuted)
                try:
                    chat_info = await context.bot.get_chat(chat_id_unmuted)
                    chat_name_display = chat_info.title or chat_info.first_name or chat_name_display
                except Exception:
                    pass
                admin_unmute_notification = (
                    f"(Авторазблокировка) Пользователь {user_name} (ID: {user_id}) был автоматически разблокирован в чате {chat_name_display} (ID: {chat_id_unmuted}) (Причина: {reason}, Длительность: {human_readable_duration}), так как срок его блокировки истек."
                )
                try:
                    await context.bot.send_message(chat_id=ADMIN_ID[0], text=admin_unmute_notification) # Без MarkdownV2
                    stats_data['messages_sent'] = stats_data.get('messages_sent', 0) + 1
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление админу о авторазблокировке пользователя {user_id} в чате {chat_id_unmuted}: {e}")
    save_data()


# --- Основная функция запуска бота ---

def main() -> None:
    try:
        # Убедимся, что папка 'file' существует
        os.makedirs('file', exist_ok=True)
        # Создаем подпапки для MP3, если они не существуют
        os.makedirs(MP3_10_FOLDER, exist_ok=True)
        os.makedirs(MP3_5_FOLDER, exist_ok=True)
        os.makedirs(MP3_269_FOLDER, exist_ok=True)
        os.makedirs(MP3_220_FOLDER, exist_ok=True)
        
        # Загружаем данные при старте
        load_data()

        # !!! ВАЖНО: Убедитесь, что BOT_TOKEN является правильным и актуальным!
        application = Application.builder().token(BOT_TOKEN).build()

        # Обновление статуса бота каждые 10 секунд
        job_queue = application.job_queue
        job_queue.run_repeating(update_bot_status, interval=10, first=5)
        # Запуск периодической проверки истекших блокировок каждые 60 секунд
        job_queue.run_repeating(check_and_unmute_periodically, interval=60, first=30)


        # Добавление обработчиков команд
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("id", id_command)) # Новая команда /id
        application.add_handler(CommandHandler(["addw", "add_to_whitelist"], add_to_whitelist))
        application.add_handler(CommandHandler(["unwhite", "remove_from_whitelist"], remove_from_whitelist))
        application.add_handler(CommandHandler(["listw", "show_whitelist"], show_whitelist))
        application.add_handler(CommandHandler("unmute", unmute_command_handler))
        application.add_handler(CommandHandler("mute_all", mute_all_command)) # Новая команда /mute_all
        application.add_handler(CommandHandler("op", op_command)) # Новая команда /op
        application.add_handler(CommandHandler("deop", deop_command)) # Новая команда /deop
        application.add_handler(CommandHandler("say", handle_say_command))
        # Обработчики для спам-защиты
        application.add_handler(CommandHandler("save_on", spam_on_command)) 
        application.add_handler(CommandHandler("save_off", spam_off_command))
        application.add_handler(CommandHandler("save_list", save_list_command)) 
        application.add_handler(CommandHandler("save", save_with_args_command)) # Команда с аргументами (для "on"/"off"/"list")
        application.add_handler(CommandHandler("mute_list", mute_list_command)) # Новая прямая команда для списка блокировок в текущем чате
        application.add_handler(CommandHandler("mute", handle_mute_with_args_command)) # Обработчик для /mute list и /mute <user_id>


        application.add_handler(CommandHandler("spam", handle_spam_broadcast_command)) # Теперь /spam только для рассылки

        # Обработчик для всех сообщений (должен быть после команд, чтобы команды обрабатывались первыми)
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

        logger.info("🤖 Основной бот запущен! Ожидаю сообщений...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Бот завершил работу из-за критической ошибки при запуске: {e}", exc_info=True)
    finally:
        print("Бот остановлен.")
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    main()
