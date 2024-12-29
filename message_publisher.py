import asyncio
import nest_asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
    CallbackContext
)

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import ImportChatInviteRequest

# ----------------------------------------------------------------------
# 1) Настройки для TELETHON (UserBot)
# ----------------------------------------------------------------------
API_ID = 28406559            # <-- Ваш api_id (получите на my.telegram.org)
API_HASH = "0baefc97e763c3351740e5aed948e4ed"   # <-- Ваш api_hash
SESSION_FILE = "session_user.session"  # Файл для хранения сессии Telethon
PHONE_NUMBER = "+995568863212"  # <-- Ваш номер телефона (для первой авторизации)

# ----------------------------------------------------------------------
# 2) Настройки для БОТА (python-telegram-bot)
# ----------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8187461631:AAGQL8wD_FNuIBMPx-EvjuOJrN-FHAwVjR0"  # <-- Токен "управляющего" бота

# Включаем логирование (по желанию, для отладки)
logging.basicConfig(
    format='[%(asctime)s][%(levelname)s] %(message)s',
    level=logging.INFO
)

# Патчим вложенные циклы (некоторые среды этого требуют)
nest_asyncio.apply()

# ---------- Глобальные словари для хранения данных ----------
texts = {}        # { id: "текст" }
chats = {}        # { chat_name: "ссылка_или_username" }
sets_info = {}    # { setname: { 'text_id': int, 'chat_name': str, 'interval': float, 'job': Job } }


# ----------------------------------------------------------------------
# ИНИЦИАЛИЗАЦИЯ TELETHON (юзербот)
# ----------------------------------------------------------------------
# Создаём клиента Telethon, который будет авторизоваться как реальный пользователь
userbot = TelegramClient(SESSION_FILE, API_ID, API_HASH)

async def telethon_start():
    """
    Запуск юзербота Telethon. Если файл сессии отсутствует или устарел,
    запросит телефон и код авторизации. После первого успешного входа
    сохранит сессию в SESSION_FILE.
    """
    await userbot.start(phone=PHONE_NUMBER)
    # Если используется двухфакторная аутентификация (пароль), запросим пароль
    if await userbot.is_user_authorized() is False:
        try:
            await userbot.sign_in(PHONE_NUMBER)
        except SessionPasswordNeededError:
            pw = input("Введите пароль от двухфакторной аутентификации: ")
            await userbot.sign_in(password=pw)
    print("Telethon userbot: авторизация успешна!")


# ----------------------------------------------------------------------
# Вспомогательная функция для отправки сообщения через Telethon
# ----------------------------------------------------------------------
async def send_message_as_user(chat_link_or_username: str, text: str):
    """
    Отправляем сообщение в указанный чат/канал/группу
    через юзербот (Telethon) от имени реального пользователя.
    """
    # Возможно, если это приватная ссылка вида t.me/+xxxx или joinchat/xxxx,
    # нужно сначала выполнить ImportChatInviteRequest, чтобы "присоединиться".
    # Пример:
    # if "joinchat" in chat_link_or_username or "+":
    #     invite_hash = chat_link_or_username.split('/')[-1]
    #     await userbot(ImportChatInviteRequest(invite_hash))

    await userbot.send_message(chat_link_or_username, text)


# ----------------------------------------------------------------------
# CALLBACK-функция (JobQueue), вызывается каждые N секунд
# ----------------------------------------------------------------------
async def job_send_message(context: CallbackContext):
    """
    Функция, которую вызывает JobQueue. Берём данные из job.data
    и через Telethon отправляем сообщение "от имени пользователя".
    """
    job_data = context.job.data
    text_id = job_data['text_id']
    chat_name = job_data['chat_name']

    # Проверяем, что нужные значения ещё существуют
    if text_id not in texts:
        return  # Текст был удалён из словаря
    if chat_name not in chats:
        return  # Чат удалён или переименован

    # Получаем итоговый текст и "ссылку/username" чата
    message_text = texts[text_id]
    chat_link_or_username = chats[chat_name]

    # Отправляем через Telethon
    await send_message_as_user(chat_link_or_username, message_text)


# ----------------------------------------------------------------------
#  Команды управляющего БОТА (python-telegram-bot)
# ----------------------------------------------------------------------

# /start
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот-«управляющий». Принимаю команды и отправляю их через юзербот.\n"
        "Наберите /help для списка команд."
    )

# /help
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text_help = (
        "Доступные команды:\n\n"
        "— Управление текстами —\n"
        "/addtext <text>        Добавить текст\n"
        "/showtexts             Показать все тексты\n"
        "/deletetext <id>       Удалить текст по ID\n"
        "/deletealltext         Удалить все тексты\n\n"

        "— Управление чатами —\n"
        "/addchat <link> <name> Добавить чат (ссылка/username + имя)\n"
        "/showchats             Показать все чаты\n"
        "/deletechat <name>     Удалить чат по имени\n"
        "/deleteallchat         Удалить все чаты\n\n"

        "— Управление наборами (sets) —\n"
        "/addset <setname> <text_id> <chat_name> <time>\n"
        "   Каждые <time> сек бот-юзер будет отправлять текст <text_id> в чат <chat_name>.\n"
        "/deleteset <setname>   Удалить набор по имени\n"
        "/deleteallset          Удалить все наборы\n\n"
        "— Прочие —\n"
        "/showsets              Показать все активные наборы\n"
    )
    await update.message.reply_text(text_help)


# ==================== 1) Управление текстами ====================

# /addtext <text>
async def cmd_addtext(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = ' '.join(context.args)
    if text.strip():
        text_id = len(texts)
        texts[text_id] = text
        await update.message.reply_text(f"Текст добавлен. ID = {text_id}")
    else:
        await update.message.reply_text("Ошибка: текст не указан. Пример: /addtext Привет!")

# /showtexts
async def cmd_showtexts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if texts:
        lines = [f"{tid}: {txt}" for tid, txt in texts.items()]
        await update.message.reply_text("Список сохранённых текстов:\n" + "\n".join(lines))
    else:
        await update.message.reply_text("Нет ни одного сохранённого текста.")

# /deletetext <id>
async def cmd_deletetext(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Укажите ID текста. Пример: /deletetext 0")
        return

    try:
        text_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID текста должен быть числом.")
        return

    if text_id in texts:
        del texts[text_id]
        await update.message.reply_text(f"Текст с ID {text_id} удалён.")
    else:
        await update.message.reply_text(f"Текст с ID {text_id} не найден.")

# /deletealltext
async def cmd_deletealltext(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texts.clear()
    await update.message.reply_text("Все тексты удалены.")


# ==================== 2) Управление чатами ====================

# /addchat <link> <name>
async def cmd_addchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Нужно указать ссылку/username и имя.\nПример:\n/addchat @mychannel mychat"
        )
        return

    link = context.args[0]
    name = context.args[1]
    if name in chats:
        await update.message.reply_text(f"Чат с именем '{name}' уже существует.")
        return

    chats[name] = link
    await update.message.reply_text(f"Чат '{name}' добавлен. Ссылка/username: {link}")

# /showchats
async def cmd_showchats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if chats:
        lines = [f"{chat_name}: {link}" for chat_name, link in chats.items()]
        await update.message.reply_text("Список чатов:\n" + "\n".join(lines))
    else:
        await update.message.reply_text("Список чатов пуст.")

# /deletechat <name>
async def cmd_deletechat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Укажите имя чата. Пример: /deletechat mychat")
        return

    name = context.args[0]
    if name in chats:
        del chats[name]
        await update.message.reply_text(f"Чат '{name}' удалён.")
    else:
        await update.message.reply_text(f"Чат '{name}' не найден.")

# /deleteallchat
async def cmd_deleteallchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chats.clear()
    await update.message.reply_text("Все чаты удалены.")


# ==================== 3) Управление наборами (sets) ====================

# /addset <setname> <text_id> <chat_name> <interval>
async def cmd_addset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 4:
        await update.message.reply_text(
            "Нужно указать 4 параметра: <setname> <text_id> <chat_name> <time>\n"
            "Пример: /addset morning_news 0 mychat 60"
        )
        return

    set_name = context.args[0]
    try:
        text_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("text_id должен быть числом.")
        return

    chat_name = context.args[2]
    try:
        interval = float(context.args[3])
    except ValueError:
        await update.message.reply_text("time должен быть числом (секунды).")
        return

    # Проверяем, существуют ли text_id и chat_name
    if text_id not in texts:
        await update.message.reply_text(f"Текст с ID {text_id} не найден.")
        return
    if chat_name not in chats:
        await update.message.reply_text(f"Чат с именем '{chat_name}' не найден.")
        return

    # Если набор с таким именем уже есть — удаляем старую задачу
    if set_name in sets_info:
        old_job = sets_info[set_name]['job']
        old_job.schedule_removal()
        del sets_info[set_name]

    # Создаём job в JobQueue
    job = context.job_queue.run_repeating(
        job_send_message,
        interval=interval,
        first=interval,
        data={
            'text_id': text_id,
            'chat_name': chat_name
        }
    )

    # Сохраняем инфу о наборе
    sets_info[set_name] = {
        'text_id': text_id,
        'chat_name': chat_name,
        'interval': interval,
        'job': job
    }

    await update.message.reply_text(
        f"Набор '{set_name}' создан. Каждые {interval} сек будет отправляться "
        f"текст с ID {text_id} в чат '{chat_name}' (от имени юзербота)."
    )

# /deleteset <setname>
async def cmd_deleteset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Укажите имя набора. Пример: /deleteset morning_news")
        return

    set_name = context.args[0]
    if set_name in sets_info:
        job = sets_info[set_name]['job']
        job.schedule_removal()
        del sets_info[set_name]
        await update.message.reply_text(f"Набор '{set_name}' удалён.")
    else:
        await update.message.reply_text(f"Набор '{set_name}' не найден.")

# /deleteallset
async def cmd_deleteallset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for sname, sdata in sets_info.items():
        sdata['job'].schedule_removal()
    sets_info.clear()
    await update.message.reply_text("Все наборы удалены.")

# (необязательная) команда /showsets — для удобства просмотра текущих расписаний
async def cmd_showsets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if sets_info:
        lines = []
        for sname, data in sets_info.items():
            lines.append(
                f"'{sname}': text_id={data['text_id']}, "
                f"chat_name={data['chat_name']}, interval={data['interval']} сек"
            )
        await update.message.reply_text("Активные наборы:\n" + "\n".join(lines))
    else:
        await update.message.reply_text("Нет активных наборов.")


# ----------------------------------------------------------------------
# ФУНКЦИЯ ЗАПУСКА ПРИЛОЖЕНИЯ
# ----------------------------------------------------------------------
async def main():
    # 1) Запустим Telethon (userbot)
    await telethon_start()

    # 2) Запустим нашего Telegram-бота (python-telegram-bot)
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем хендлеры команд
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))

    # Тексты
    application.add_handler(CommandHandler("addtext", cmd_addtext))
    application.add_handler(CommandHandler("showtexts", cmd_showtexts))
    application.add_handler(CommandHandler("deletetext", cmd_deletetext))
    application.add_handler(CommandHandler("deletealltext", cmd_deletealltext))

    # Чаты
    application.add_handler(CommandHandler("addchat", cmd_addchat))
    application.add_handler(CommandHandler("showchats", cmd_showchats))
    application.add_handler(CommandHandler("deletechat", cmd_deletechat))
    application.add_handler(CommandHandler("deleteallchat", cmd_deleteallchat))

    # Наборы (sets)
    application.add_handler(CommandHandler("addset", cmd_addset))
    application.add_handler(CommandHandler("deleteset", cmd_deleteset))
    application.add_handler(CommandHandler("deleteallset", cmd_deleteallset))
    application.add_handler(CommandHandler("showsets", cmd_showsets))  # Доп. команда

    print("=== Бот и юзербот запущены. Нажмите Ctrl+C для остановки. ===")
    await application.run_polling()


# ----------------------------------------------------------------------
# Точка входа
# ----------------------------------------------------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Остановка по Ctrl+C")