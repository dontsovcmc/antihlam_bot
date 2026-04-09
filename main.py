import asyncio
import signal

from telegram.ext import Application, MessageHandler, CommandHandler, filters
from log import logger

import settings
from bot.handlers import start_command, login_command, status_command, ads_command, text_handler, error_handler
from bot.conversation import get_conversation_handler

logger.info('Hello from Avito Bot')


async def main() -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown(loop))

    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # ConversationHandler для создания объявлений (фото → LLM → цена → публикация)
    application.add_handler(get_conversation_handler())

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("ads", ads_command))

    # Текстовые сообщения (логин flow, ответы покупателям)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    application.add_error_handler(error_handler)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Запускаем фоновый цикл опроса Avito Messenger
    try:
        from avito.messenger import messenger_loop
        await application.create_task(messenger_loop(application))
    except asyncio.CancelledError:
        pass

    # Закрываем Playwright
    try:
        from avito.browser import BrowserManager
        browser = BrowserManager.get_instance()
        await browser.close_all()
    except Exception:
        pass

    await application.updater.stop()
    await application.stop()
    await application.shutdown()


def shutdown(loop):
    logger.info("Received shutdown signal...")
    for task in asyncio.all_tasks(loop):
        task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
