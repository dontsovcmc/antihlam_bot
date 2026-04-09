from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def price_keyboard(price_low: int, price_mid: int, price_high: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора цены: 3 варианта + своя цена + отмена."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{price_low:,} ₽".replace(',', ' '), callback_data=f"price:{price_low}"),
            InlineKeyboardButton(f"{price_mid:,} ₽".replace(',', ' '), callback_data=f"price:{price_mid}"),
            InlineKeyboardButton(f"{price_high:,} ₽".replace(',', ' '), callback_data=f"price:{price_high}"),
        ],
        [
            InlineKeyboardButton("Своя цена", callback_data="price:custom"),
            InlineKeyboardButton("Отмена", callback_data="cancel"),
        ],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения публикации."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✓ Опубликовать", callback_data="publish")],
        [
            InlineKeyboardButton("Изменить описание", callback_data="edit_description"),
            InlineKeyboardButton("Изменить цену", callback_data="edit_price"),
        ],
        [InlineKeyboardButton("Отмена", callback_data="cancel")],
    ])
