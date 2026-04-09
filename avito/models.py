from pydantic import BaseModel


class AdMetadata(BaseModel):
    """Результат генерации объявления через LLM."""
    category: str           # Категория Avito, например "Электроника / Телефоны"
    title: str              # Заголовок объявления (макс 50 символов)
    description: str        # Подробное описание, 2-3 абзаца
    price_low: int          # Низкая цена (быстрая продажа)
    price_mid: int          # Средняя цена (рекомендуемая)
    price_high: int         # Высокая цена
    condition: str          # "Б/у" или "Новое"


class AvitoChat(BaseModel):
    """Чат в Avito Messenger."""
    chat_id: str
    user_name: str
    last_message: str
    unread_count: int
    item_id: str | None = None
    item_title: str | None = None


class AvitoMessage(BaseModel):
    """Сообщение в чате Avito Messenger."""
    message_id: str
    chat_id: str
    author_id: str
    text: str
    timestamp: int
    is_read: bool = False
