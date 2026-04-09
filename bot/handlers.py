from telegram import Update
from telegram.ext import ContextTypes

from log import logger
from db import db_manager
from bot.conversation import is_allowed
import settings


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start."""
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("У вас нет доступа к этому боту.")
        return

    db_manager.get_or_create_user(user_id)
    await update.message.reply_text(
        "Привет! Я помогу разместить объявление на Авито.\n\n"
        "Отправьте мне <b>фото вещи</b> с подписью — кратким описанием.\n"
        "Я сгенерирую объявление и опубликую его.\n\n"
        "Команды:\n"
        "/login — привязать аккаунт Авито\n"
        "/status — статус сессии\n"
        "/ads — мои объявления\n"
        "/cancel — отменить текущее действие",
        parse_mode='HTML',
    )


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало привязки аккаунта Avito через Playwright."""
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    await update.message.reply_text(
        "🔐 Начинаю процесс входа в Авито.\n"
        "Введите номер телефона, привязанный к вашему аккаунту Авито\n"
        "(например: +79001234567):"
    )
    context.user_data['login_state'] = 'waiting_phone'


async def login_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода телефона при логине."""
    if context.user_data.get('login_state') != 'waiting_phone':
        return

    user_id = update.effective_user.id
    phone = update.message.text.strip()

    await update.message.reply_text("⏳ Открываю Авито и ввожу номер телефона...")

    try:
        from avito.browser import BrowserManager
        browser = BrowserManager.get_instance()
        screenshot = await browser.start_login(user_id, phone)

        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption="Авито отправил SMS-код. Введите код из SMS:"
            )
            context.user_data['login_state'] = 'waiting_code'
        else:
            await update.message.reply_text("Не удалось начать логин. Попробуйте позже.")
            context.user_data['login_state'] = None
    except Exception as e:
        logger.error(f"Login error for {user_id}: {e}")
        await update.message.reply_text(f"Ошибка: {e}")
        context.user_data['login_state'] = None


async def login_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка SMS-кода при логине."""
    if context.user_data.get('login_state') != 'waiting_code':
        return

    user_id = update.effective_user.id
    code = update.message.text.strip()

    await update.message.reply_text("⏳ Ввожу код...")

    try:
        from avito.browser import BrowserManager
        browser = BrowserManager.get_instance()
        success, screenshot = await browser.complete_login(user_id, code)

        if success:
            db_manager.update_browser_session(user_id, True)
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ Успешно! Аккаунт Авито привязан."
            )
        else:
            await update.message.reply_photo(
                photo=screenshot,
                caption="❌ Не удалось войти. Попробуйте /login заново."
            )
    except Exception as e:
        logger.error(f"Login code error for {user_id}: {e}")
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        context.user_data['login_state'] = None


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус сессии Avito."""
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    user = db_manager.get_user_by_telegram_id(user_id)
    if not user:
        await update.message.reply_text("Вы ещё не зарегистрированы. Отправьте /start")
        return

    session_status = "✅ Активна" if user['browser_session_valid'] else "❌ Не активна"
    await update.message.reply_text(
        f"<b>Статус сессии Авито:</b> {session_status}\n"
        f"Если сессия не активна — отправьте /login",
        parse_mode='HTML',
    )


async def ads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последние объявления пользователя."""
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    user = db_manager.get_user_by_telegram_id(user_id)
    if not user:
        await update.message.reply_text("Вы ещё не зарегистрированы. Отправьте /start")
        return

    ads = db_manager.get_user_ads(user['id'])
    if not ads:
        await update.message.reply_text("У вас пока нет объявлений.")
        return

    status_emoji = {
        'draft': '📝',
        'publishing': '🚀',
        'published': '✅',
        'failed': '❌',
    }

    lines = ["<b>Ваши объявления:</b>\n"]
    for ad in ads:
        emoji = status_emoji.get(ad['status'], '❓')
        url_part = f" — {ad['avito_url']}" if ad.get('avito_url') else ""
        lines.append(f"{emoji} {ad['title']} ({ad['price']:,} ₽){url_part}".replace(',', ' '))

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (логин flow или ответы на Avito сообщения)."""
    login_state = context.user_data.get('login_state')
    if login_state == 'waiting_phone':
        return await login_phone_handler(update, context)
    if login_state == 'waiting_code':
        return await login_code_handler(update, context)

    # Проверяем — может это ответ на сообщение покупателя
    if update.message.reply_to_message:
        reply_msg_id = update.message.reply_to_message.message_id
        original = db_manager.get_message_by_telegram_id(reply_msg_id)
        if original and original['direction'] == 'in':
            try:
                from avito.messenger import reply_to_buyer
                await reply_to_buyer(
                    original['user_id'],
                    original['avito_chat_id'],
                    update.message.text,
                )
                await update.message.reply_text("✅ Ответ отправлен покупателю.")
            except Exception as e:
                logger.error(f"Reply error: {e}")
                await update.message.reply_text(f"Ошибка отправки: {e}")
            return

    await update.message.reply_text(
        "Отправьте фото с подписью, чтобы создать объявление.\n"
        "Или используйте /help для списка команд."
    )


async def error_handler(update, context):
    """Обработчик ошибок."""
    logger.error(f"Update {update} caused error {context.error}")
