import base64
import json

import anthropic
from log import logger
from avito.models import AdMetadata
import settings


SYSTEM_PROMPT = """Ты — эксперт по созданию объявлений на Avito.ru.
Тебе дают фотографию вещи и краткое описание от продавца.
Твоя задача — сгенерировать полноценное объявление для Avito.

Требования:
- Категория: выбери наиболее подходящую категорию Avito (например "Электроника / Телефоны / iPhone", "Мебель и интерьер / Столы и стулья")
- Заголовок: краткий, до 50 символов, привлекательный
- Описание: 2-3 абзаца на русском языке. Опиши вещь подробно, укажи достоинства, состояние. Не приукрашивай, будь честным.
- Цены: предложи 3 варианта цены в рублях:
  - price_low: для быстрой продажи (ниже рынка)
  - price_mid: рекомендуемая рыночная цена
  - price_high: если не спешить с продажей
- Состояние: "Б/у" или "Новое"

Ответь строго в формате JSON:
{
  "category": "...",
  "title": "...",
  "description": "...",
  "price_low": 1000,
  "price_mid": 1500,
  "price_high": 2000,
  "condition": "Б/у"
}"""


async def generate_ad_metadata(photo_bytes: bytes, user_description: str) -> AdMetadata:
    """
    Отправляет фото и описание в Claude API, возвращает структурированные данные для объявления.

    :param photo_bytes: JPEG/PNG фото вещи
    :param user_description: краткое описание от пользователя
    :return: AdMetadata с категорией, названием, описанием и 3 вариантами цен
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')

    message = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": photo_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Описание от продавца: {user_description}",
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text
    logger.debug(f"LLM response: {response_text}")

    # Извлекаем JSON из ответа (может быть обёрнут в ```json ... ```)
    json_text = response_text
    if '```json' in json_text:
        json_text = json_text.split('```json')[1].split('```')[0]
    elif '```' in json_text:
        json_text = json_text.split('```')[1].split('```')[0]

    data = json.loads(json_text.strip())
    return AdMetadata(**data)
