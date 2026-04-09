# CLAUDE.md

## Project Overview

Telegram-бот для автоматизации размещения объявлений на Avito.ru. Пользователь присылает фото и описание вещи, бот генерирует объявление через Claude API (категория, название, описание, 3 варианта цены) и публикует на Avito через браузерную автоматизацию (Playwright). Также мониторит входящие сообщения покупателей через Avito Messenger API и пересылает в Telegram.

## Tech Stack

- Python 3.12, python-telegram-bot 21.9
- Playwright (chromium) — браузерная автоматизация для публикации на Avito
- Anthropic SDK — Claude API с vision для генерации объявлений
- SQLite — хранение пользователей, объявлений, сообщений
- Docker

## Architecture

```
User (Telegram DM)
    │
    ├── фото + описание → bot/conversation.py (ConversationHandler)
    │       │
    │       ├── llm/generator.py (Claude API vision) → AdMetadata (категория, название, описание, 3 цены)
    │       │
    │       └── avito/publisher.py (Playwright) → avito.ru/additem → ссылка на объявление
    │
    ├── /login → bot/handlers.py → avito/browser.py (Playwright login flow)
    │
    └── ответы покупателям → reply-to-message → avito/messenger.py → Avito Messenger API
                                                       ↑
                                          фоновый polling каждые 30 сек
```

### Ключевые модули

| Модуль | Назначение |
|--------|-----------|
| `main.py` | Entry point, регистрация handlers, запуск messenger loop |
| `settings.py` | Загрузка `config.yml` |
| `db.py` | SQLite: таблицы users, ads, messages |
| `bot/conversation.py` | ConversationHandler: фото → LLM → выбор цены → подтверждение → публикация |
| `bot/handlers.py` | Команды /start, /login, /status, /ads; текстовые сообщения |
| `bot/keyboards.py` | InlineKeyboard: 3 кнопки цен + "Своя цена" + "Отмена"; кнопка "Опубликовать" |
| `llm/generator.py` | Claude API с vision: фото+текст → AdMetadata |
| `avito/browser.py` | BrowserManager: persistent context per user, login через SMS |
| `avito/publisher.py` | Заполнение формы avito.ru/additem через Playwright |
| `avito/messenger.py` | Avito Messenger API: polling чатов, пересылка в Telegram, отправка ответов |
| `avito/models.py` | Pydantic: AdMetadata, AvitoChat, AvitoMessage |

## Setup

### 1. Окружение

```bash
python -m venv ../antihlam_bot_venv
source ../antihlam_bot_venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Конфигурация

```bash
cp config.yml.template config.yml
```

Заполнить `config.yml` (описание каждого параметра ниже).

### 3. Где получить токены

#### `bot_token` — Telegram Bot API

1. Открыть @BotFather в Telegram: https://t.me/BotFather
2. Отправить `/newbot`, задать имя и username
3. BotFather вернёт токен вида `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

#### `allowed_user_ids` — Telegram User ID

1. Открыть @userinfobot в Telegram: https://t.me/userinfobot
2. Отправить любое сообщение — бот ответит вашим ID (число)
3. Или в любом боте: `update.effective_user.id` в логах при `/start`

#### `anthropic.api_key` — Ключ Claude API

1. Зайти на https://console.anthropic.com/
2. Settings → API Keys → Create Key
3. Скопировать ключ вида `sk-ant-api03-...`
4. Для vision-запросов нужен тариф с доступом к моделям Sonnet/Opus

#### `avito.client_id` / `avito.client_secret` — Avito Developer API (для Messenger)

1. Зайти на https://developers.avito.ru/
2. Авторизоваться через аккаунт Avito
3. "Мои приложения" → "Создать приложение"
4. Тип: "Веб-приложение", указать название
5. В разделе приложения будут `client_id` и `client_secret`
6. Нужные scope: `messenger:read`, `messenger:write`
7. **Примечание:** Messenger API не обязателен для публикации объявлений — можно оставить пустым и использовать только генерацию + публикацию

## Commands

```bash
# Запуск
source ../antihlam_bot_venv/bin/activate
python main.py

# Тесты
pytest

# Docker
docker compose up -d
docker compose logs -f
```

## Conversation Flow

```
IDLE → [фото + подпись] → GENERATING (Claude API) → CHOOSE_PRICE
  ↓
CHOOSE_PRICE: сгенерированное объявление + 3 кнопки с ценами
  [45 000 ₽]  [50 000 ₽]  [55 000 ₽]
  [Своя цена]  [Отмена]
  ├── выбор цены → CONFIRMING
  ├── "Своя цена" → EDIT_PRICE → CONFIRMING
  └── "Отмена" → IDLE

CONFIRMING: итоговый вид объявления
  ├── [✓ Опубликовать] → PUBLISHING (Playwright) → IDLE + ссылка
  ├── [Изменить описание] → EDIT_DESCRIPTION → CONFIRMING
  ├── [Изменить цену] → CHOOSE_PRICE
  └── [Отмена] → IDLE
```

## Rules

- NEVER read or commit `.env` / `config.yml` files
- NEVER put tokens/secrets in code or commands — все секреты только в `config.yml`
- Always run `pytest` before commits
- Never commit to master — работа только в feature-ветках
- NEVER use `git stash` — вместо этого temporary commit
- ALWAYS rebase before push: `git checkout master && git remote update && git pull && git checkout - && git rebase master`
- CSS-селекторы в `publisher.py` могут устареть при обновлении Avito — проверять при ошибках публикации
