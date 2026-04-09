import asyncio

from log import logger
from avito.browser import BrowserManager
from avito.models import AdMetadata
from db import db_manager


class SessionExpiredError(Exception):
    pass


class PublishError(Exception):
    pass


async def publish_ad(telegram_user_id: int, ad_meta: AdMetadata,
                     price: int, description: str, photo_path: str) -> str:
    """
    Публикует объявление на Avito через браузерную автоматизацию.

    :param telegram_user_id: ID пользователя Telegram
    :param ad_meta: метаданные объявления от LLM
    :param price: выбранная цена
    :param description: описание (возможно отредактированное)
    :param photo_path: путь к файлу фото
    :return: URL опубликованного объявления
    :raises SessionExpiredError: если сессия Avito истекла
    :raises PublishError: при ошибке публикации
    """
    browser = BrowserManager.get_instance()

    # Проверяем сессию
    if not await browser.check_session(telegram_user_id):
        db_manager.update_browser_session(telegram_user_id, False)
        raise SessionExpiredError("Сессия Авито истекла. Отправьте /login для повторного входа.")

    page = await browser.get_page(telegram_user_id)

    try:
        # Переходим на страницу создания объявления
        await page.goto('https://www.avito.ru/additem', wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(3)

        # Проверяем, не перенаправило ли на логин
        if '/login' in page.url or '/auth' in page.url:
            raise SessionExpiredError("Сессия Авито истекла.")

        # 1. Категория — вводим в поиск
        category_input = page.locator('[data-marker="category-select/input"]')
        if await category_input.count() == 0:
            category_input = page.locator('input[placeholder*="категор"]')
        if await category_input.count() == 0:
            # Пробуем нажать кнопку выбора категории
            category_btn = page.locator('[data-marker="category-select/button"]')
            if await category_btn.count() > 0:
                await category_btn.click()
                await asyncio.sleep(1)
            category_input = page.locator('input[placeholder*="категор"]')

        if await category_input.count() > 0:
            # Берём последний уровень категории для поиска
            category_search = ad_meta.category.split('/')[-1].strip()
            await category_input.fill(category_search)
            await asyncio.sleep(2)

            # Кликаем первый результат
            suggestion = page.locator('[data-marker="category-select/suggestion"]').first
            if await suggestion.count() == 0:
                suggestion = page.locator('.suggest-item, [class*="suggest"]').first
            if await suggestion.count() > 0:
                await suggestion.click()
                await asyncio.sleep(2)
        else:
            logger.warning("Category input not found, skipping category selection")

        # Ждём загрузки формы после выбора категории
        await asyncio.sleep(3)

        # 2. Название
        title_input = page.locator('[data-marker="item-form/title"] input')
        if await title_input.count() == 0:
            title_input = page.locator('input[data-marker="title"]')
        if await title_input.count() == 0:
            title_input = page.locator('#title, input[name="title"]')

        if await title_input.count() > 0:
            await title_input.fill(ad_meta.title)
            await asyncio.sleep(1)
        else:
            logger.warning("Title input not found")

        # 3. Описание
        desc_textarea = page.locator('[data-marker="item-form/description"] textarea')
        if await desc_textarea.count() == 0:
            desc_textarea = page.locator('textarea[data-marker="description"]')
        if await desc_textarea.count() == 0:
            desc_textarea = page.locator('#description, textarea[name="description"]')

        if await desc_textarea.count() > 0:
            await desc_textarea.fill(description)
            await asyncio.sleep(1)
        else:
            logger.warning("Description textarea not found")

        # 4. Цена
        price_input = page.locator('[data-marker="item-form/price"] input')
        if await price_input.count() == 0:
            price_input = page.locator('input[data-marker="price"]')
        if await price_input.count() == 0:
            price_input = page.locator('#price, input[name="price"]')

        if await price_input.count() > 0:
            await price_input.fill(str(price))
            await asyncio.sleep(1)
        else:
            logger.warning("Price input not found")

        # 5. Загрузка фото
        file_input = page.locator('input[type="file"]').first
        if await file_input.count() > 0:
            await file_input.set_input_files(photo_path)
            await asyncio.sleep(3)  # ждём загрузки фото
        else:
            logger.warning("File input not found")

        # 6. Скроллим вниз и ждём
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(2)

        # 7. Submit
        submit_btn = page.locator('[data-marker="item-form/submit"]')
        if await submit_btn.count() == 0:
            submit_btn = page.locator('button[type="submit"]')

        if await submit_btn.count() > 0:
            await submit_btn.click()
            await asyncio.sleep(5)
        else:
            # Сохраняем скриншот для отладки
            screenshot_path = f"/tmp/avito_submit_not_found_{telegram_user_id}.png"
            await page.screenshot(path=screenshot_path)
            raise PublishError(f"Кнопка 'Опубликовать' не найдена. Скриншот: {screenshot_path}")

        # 8. Проверяем результат
        # Ждём перехода на страницу успеха или ошибки
        await asyncio.sleep(5)
        result_url = page.url

        # Если остались на форме — возможно ошибка валидации
        if '/additem' in result_url:
            screenshot_path = f"/tmp/avito_validation_error_{telegram_user_id}.png"
            await page.screenshot(path=screenshot_path)
            raise PublishError(f"Ошибка валидации формы. Скриншот: {screenshot_path}")

        logger.info(f"Ad published for user {telegram_user_id}: {result_url}")
        return result_url

    except (SessionExpiredError, PublishError):
        raise
    except Exception as e:
        screenshot_path = f"/tmp/avito_error_{telegram_user_id}.png"
        try:
            await page.screenshot(path=screenshot_path)
        except Exception:
            pass
        raise PublishError(f"Ошибка: {e}. Скриншот: {screenshot_path}")
    finally:
        await page.close()
