import time
import asyncio

import aiohttp
from log import logger
from db import db_manager
from avito.models import AvitoChat, AvitoMessage
import settings

AVITO_API_BASE = 'https://api.avito.ru'


class AvitoMessengerClient:
    """Клиент для Avito Messenger API."""

    def __init__(self):
        self._tokens: dict[int, dict] = {}  # telegram_user_id -> {access_token, refresh_token, expires_at}

    async def _get_token(self, telegram_user_id: int) -> str:
        """Возвращает актуальный access_token, обновляет если истёк."""
        user = db_manager.get_user_by_telegram_id(telegram_user_id)
        if not user or not user.get('access_token'):
            raise RuntimeError("Нет токена Avito. Требуется OAuth-авторизация.")

        if user['token_expires_at'] > int(time.time()) + 60:
            return user['access_token']

        # Обновляем токен
        return await self._refresh_token(telegram_user_id, user['refresh_token'])

    async def _refresh_token(self, telegram_user_id: int, refresh_token: str) -> str:
        """Обновляет access_token через refresh_token."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{AVITO_API_BASE}/token/',
                data={
                    'grant_type': 'refresh_token',
                    'client_id': settings.AVITO_CLIENT_ID,
                    'client_secret': settings.AVITO_CLIENT_SECRET,
                    'refresh_token': refresh_token,
                },
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Token refresh failed: {resp.status} {text}")

                data = await resp.json()
                access_token = data['access_token']
                new_refresh = data.get('refresh_token', refresh_token)
                expires_at = int(time.time()) + data.get('expires_in', 86400)

                db_manager.update_user_tokens(telegram_user_id, access_token, new_refresh, expires_at)
                return access_token

    async def get_chats(self, telegram_user_id: int, avito_user_id: str) -> list[AvitoChat]:
        """Получает список чатов с непрочитанными сообщениями."""
        token = await self._get_token(telegram_user_id)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{AVITO_API_BASE}/messenger/v3/accounts/{avito_user_id}/chats',
                headers={'Authorization': f'Bearer {token}'},
                params={'unread_only': 'true'},
            ) as resp:
                if resp.status == 403:
                    # Avito возвращает 403 вместо 401 при истёкшем токене
                    await self._refresh_token(telegram_user_id,
                                              db_manager.get_user_by_telegram_id(telegram_user_id)['refresh_token'])
                    return await self.get_chats(telegram_user_id, avito_user_id)

                if resp.status != 200:
                    logger.error(f"get_chats error: {resp.status}")
                    return []

                data = await resp.json()
                chats = []
                for chat in data.get('chats', []):
                    chats.append(AvitoChat(
                        chat_id=str(chat['id']),
                        user_name=chat.get('users', [{}])[0].get('name', 'Покупатель'),
                        last_message=chat.get('last_message', {}).get('content', {}).get('text', ''),
                        unread_count=chat.get('unread_count', 0),
                        item_id=str(chat.get('context', {}).get('value', {}).get('id', '')),
                        item_title=chat.get('context', {}).get('value', {}).get('title'),
                    ))
                return chats

    async def get_messages(self, telegram_user_id: int, avito_user_id: str,
                          chat_id: str) -> list[AvitoMessage]:
        """Получает сообщения из чата."""
        token = await self._get_token(telegram_user_id)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{AVITO_API_BASE}/messenger/v2/accounts/{avito_user_id}/chats/{chat_id}/messages/',
                headers={'Authorization': f'Bearer {token}'},
            ) as resp:
                if resp.status != 200:
                    logger.error(f"get_messages error: {resp.status}")
                    return []

                data = await resp.json()
                messages = []
                for msg in data.get('messages', []):
                    messages.append(AvitoMessage(
                        message_id=str(msg['id']),
                        chat_id=chat_id,
                        author_id=str(msg.get('author_id', '')),
                        text=msg.get('content', {}).get('text', ''),
                        timestamp=msg.get('created', 0),
                        is_read=msg.get('is_read', False),
                    ))
                return messages

    async def send_message(self, telegram_user_id: int, avito_user_id: str,
                          chat_id: str, text: str):
        """Отправляет сообщение в чат Avito."""
        token = await self._get_token(telegram_user_id)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{AVITO_API_BASE}/messenger/v1/accounts/{avito_user_id}/chats/{chat_id}/messages/',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                },
                json={
                    'message': {'text': text},
                    'type': 'text',
                },
            ) as resp:
                if resp.status not in (200, 201):
                    text_resp = await resp.text()
                    raise RuntimeError(f"send_message error: {resp.status} {text_resp}")


messenger_client = AvitoMessengerClient()


async def reply_to_buyer(user_id: int, avito_chat_id: str, text: str):
    """Отправляет ответ покупателю через Avito Messenger API."""
    user = db_manager.get_user_by_telegram_id(user_id)
    if not user or not user.get('avito_user_id'):
        raise RuntimeError("Аккаунт Avito не привязан.")

    await messenger_client.send_message(
        telegram_user_id=user_id,
        avito_user_id=user['avito_user_id'],
        chat_id=avito_chat_id,
        text=text,
    )


async def messenger_loop(application):
    """Фоновый цикл опроса Avito Messenger для всех пользователей."""
    from telegram.ext import Application

    logger.info("Messenger loop started")

    while True:
        try:
            # Получаем всех пользователей с активными токенами
            import sqlite3
            with sqlite3.connect('antihlam_bot.db') as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT telegram_user_id, avito_user_id
                    FROM users
                    WHERE access_token IS NOT NULL AND avito_user_id IS NOT NULL
                ''')
                users = [dict(row) for row in cursor.fetchall()]

            for user in users:
                try:
                    chats = await messenger_client.get_chats(
                        user['telegram_user_id'],
                        user['avito_user_id'],
                    )

                    for chat in chats:
                        if chat.unread_count == 0:
                            continue

                        messages = await messenger_client.get_messages(
                            user['telegram_user_id'],
                            user['avito_user_id'],
                            chat.chat_id,
                        )

                        for msg in messages:
                            if msg.is_read:
                                continue
                            if msg.author_id == user['avito_user_id']:
                                continue  # наше сообщение

                            # Пересылаем в Telegram
                            item_info = f" по «{chat.item_title}»" if chat.item_title else ""
                            text = (
                                f"💬 <b>Сообщение от {chat.user_name}</b>{item_info}:\n\n"
                                f"{msg.text}"
                            )
                            sent = await application.bot.send_message(
                                chat_id=user['telegram_user_id'],
                                text=text,
                                parse_mode='HTML',
                            )

                            # Сохраняем маппинг для ответов
                            db_user = db_manager.get_user_by_telegram_id(user['telegram_user_id'])
                            if db_user:
                                db_manager.save_message(
                                    user_id=db_user['id'],
                                    avito_chat_id=chat.chat_id,
                                    avito_ad_id=chat.item_id or '',
                                    telegram_message_id=sent.message_id,
                                    direction='in',
                                    text=msg.text,
                                    timestamp=msg.timestamp,
                                )

                except Exception as e:
                    logger.error(f"Messenger error for user {user['telegram_user_id']}: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Messenger loop error: {e}")

        await asyncio.sleep(settings.AVITO_MESSENGER_POLL_INTERVAL)

    logger.info("Messenger loop stopped")
