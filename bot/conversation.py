import os
import time

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler,
    filters,
)

from log import logger
from db import db_manager
from llm.generator import generate_ad_metadata
from bot.keyboards import price_keyboard, confirm_keyboard
import settings

# Состояния ConversationHandler
IDLE, GENERATING, CHOOSE_PRICE, CONFIRMING, EDIT_PRICE, EDIT_DESCRIPTION, PUBLISHING = range(7)

# Ключи в context.user_data
AD_META = 'ad_meta'          # AdMetadata от LLM
AD_PRICE = 'ad_price'        # выбранная цена
AD_DESCRIPTION = 'ad_description'  # описание (может быть отредактировано)
AD_PHOTO_PATH = 'ad_photo_path'    # путь к сохранённому фото
AD_ID = 'ad_id'              # id записи в БД


def is_allowed(user_id: int) -> bool:
    """Проверяет, разрешён ли пользователь."""
    if not settings.ALLOWED_USER_IDS:
        return True  # если список пуст — доступ для всех
    return user_id in settings.ALLOWED_USER_IDS


async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь прислал фото (с подписью или без)."""
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("У вас нет доступа к этому боту.")
        return ConversationHandler.END

    photo = update.message.photo[-1]  # наибольшее разрешение
    caption = update.message.caption or ""

    if not caption.strip():
        await update.message.reply_text("Пришлите фото с подписью — кратким описанием вещи.")
        return IDLE

    await update.message.reply_text("⏳ Генерирую объявление...")

    # Скачиваем фото
    file = await context.bot.get_file(photo.file_id)
    photo_dir = os.path.join(settings.DATA_PATH, 'photos', str(user_id))
    os.makedirs(photo_dir, exist_ok=True)
    photo_path = os.path.join(photo_dir, f"{int(time.time())}_{photo.file_unique_id}.jpg")
    await file.download_to_drive(photo_path)

    # Читаем фото для LLM
    with open(photo_path, 'rb') as f:
        photo_bytes = f.read()

    try:
        ad_meta = await generate_ad_metadata(photo_bytes, caption)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        await update.message.reply_text(f"Ошибка генерации: {e}\nПопробуйте ещё раз.")
        return IDLE

    # Сохраняем в context
    context.user_data[AD_META] = ad_meta
    context.user_data[AD_DESCRIPTION] = ad_meta.description
    context.user_data[AD_PHOTO_PATH] = photo_path

    # Показываем результат + выбор цены
    text = (
        f"📦 <b>Категория:</b> {ad_meta.category}\n"
        f"📝 <b>Название:</b> {ad_meta.title}\n"
        f"📄 <b>Состояние:</b> {ad_meta.condition}\n\n"
        f"<b>Описание:</b>\n{ad_meta.description}\n\n"
        f"Выберите цену:"
    )
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=price_keyboard(ad_meta.price_low, ad_meta.price_mid, ad_meta.price_high),
    )
    return CHOOSE_PRICE


async def price_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь выбрал цену из предложенных."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel":
        await query.edit_message_text("Объявление отменено.")
        return ConversationHandler.END

    if data == "price:custom":
        await query.edit_message_text("Введите свою цену (число в рублях):")
        return EDIT_PRICE

    # price:12345
    price = int(data.split(":")[1])
    context.user_data[AD_PRICE] = price
    return await _show_confirmation(query, context)


async def custom_price_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь ввёл свою цену."""
    text = update.message.text.strip().replace(' ', '')
    try:
        price = int(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите положительное число. Попробуйте ещё раз:")
        return EDIT_PRICE

    context.user_data[AD_PRICE] = price
    return await _show_confirmation_from_message(update, context)


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кнопок на экране подтверждения."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel":
        await query.edit_message_text("Объявление отменено.")
        return ConversationHandler.END

    if data == "edit_price":
        ad_meta = context.user_data[AD_META]
        await query.edit_message_text(
            "Выберите цену или введите свою:",
            reply_markup=price_keyboard(ad_meta.price_low, ad_meta.price_mid, ad_meta.price_high),
        )
        return CHOOSE_PRICE

    if data == "edit_description":
        await query.edit_message_text("Введите новое описание:")
        return EDIT_DESCRIPTION

    if data == "publish":
        return await _publish_ad(query, context)

    return CONFIRMING


async def description_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь ввёл новое описание."""
    context.user_data[AD_DESCRIPTION] = update.message.text.strip()
    return await _show_confirmation_from_message(update, context)


async def _show_confirmation(query, context) -> int:
    """Показывает итоговое объявление для подтверждения (из callback)."""
    ad_meta = context.user_data[AD_META]
    price = context.user_data[AD_PRICE]
    description = context.user_data.get(AD_DESCRIPTION, ad_meta.description)

    text = (
        f"📦 <b>{ad_meta.title}</b>\n"
        f"💰 <b>Цена:</b> {price:,} ₽\n".replace(',', ' ') +
        f"📁 {ad_meta.category}\n"
        f"📄 {ad_meta.condition}\n\n"
        f"{description}\n\n"
        f"Публикуем?"
    )
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=confirm_keyboard())
    return CONFIRMING


async def _show_confirmation_from_message(update: Update, context) -> int:
    """Показывает итоговое объявление для подтверждения (из обычного сообщения)."""
    ad_meta = context.user_data[AD_META]
    price = context.user_data[AD_PRICE]
    description = context.user_data.get(AD_DESCRIPTION, ad_meta.description)

    text = (
        f"📦 <b>{ad_meta.title}</b>\n"
        f"💰 <b>Цена:</b> {price:,} ₽\n".replace(',', ' ') +
        f"📁 {ad_meta.category}\n"
        f"📄 {ad_meta.condition}\n\n"
        f"{description}\n\n"
        f"Публикуем?"
    )
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=confirm_keyboard())
    return CONFIRMING


async def _publish_ad(query, context) -> int:
    """Публикует объявление на Avito через Playwright."""
    user_id = query.from_user.id
    ad_meta = context.user_data[AD_META]
    price = context.user_data[AD_PRICE]
    description = context.user_data.get(AD_DESCRIPTION, ad_meta.description)
    photo_path = context.user_data[AD_PHOTO_PATH]

    # Создаём запись в БД
    db_user_id = db_manager.get_or_create_user(user_id)
    ad_id = db_manager.create_ad(
        user_id=db_user_id,
        title=ad_meta.title,
        description=description,
        price=price,
        category=ad_meta.category,
        photo_path=photo_path,
    )
    context.user_data[AD_ID] = ad_id

    await query.edit_message_text("🚀 Публикую на Авито...")

    try:
        from avito.publisher import publish_ad
        result_url = await publish_ad(user_id, ad_meta, price, description, photo_path)
        db_manager.update_ad_status(ad_id, 'published', avito_url=result_url)
        await query.edit_message_text(
            f"✅ Объявление опубликовано!\n{result_url}",
        )
    except Exception as e:
        logger.error(f"Publish error for user {user_id}: {e}")
        db_manager.update_ad_status(ad_id, 'failed')
        await query.edit_message_text(
            f"❌ Ошибка публикации: {e}\n\n"
            f"Проверьте, что вы залогинены (/login) и попробуйте снова."
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена через команду /cancel."""
    await update.message.reply_text("Объявление отменено.")
    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    """Возвращает ConversationHandler для создания объявления."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
        ],
        states={
            IDLE: [
                MessageHandler(filters.PHOTO, photo_received),
            ],
            CHOOSE_PRICE: [
                CallbackQueryHandler(price_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_price_entered),
            ],
            EDIT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_price_entered),
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirm_callback),
            ],
            EDIT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, description_entered),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r'^/cancel$'), cancel),
        ],
        per_user=True,
        per_chat=True,
    )
