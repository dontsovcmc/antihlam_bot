import os
import asyncio

from playwright.async_api import async_playwright, BrowserContext, Page
from log import logger
import settings


class BrowserManager:
    """Управляет Playwright браузерами с persistent context для каждого пользователя."""

    _instance = None
    _playwright = None
    _browser = None
    _contexts: dict[int, BrowserContext] = {}

    @classmethod
    def get_instance(cls) -> 'BrowserManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_playwright(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    def _user_data_dir(self, telegram_user_id: int) -> str:
        path = os.path.join(settings.BROWSER_DATA_DIR, str(telegram_user_id))
        os.makedirs(path, exist_ok=True)
        return path

    async def get_context(self, telegram_user_id: int) -> BrowserContext:
        """Возвращает persistent browser context для пользователя (создаёт лениво)."""
        if telegram_user_id in self._contexts:
            return self._contexts[telegram_user_id]

        await self._ensure_playwright()

        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self._user_data_dir(telegram_user_id),
            headless=settings.BROWSER_HEADLESS,
            locale=settings.BROWSER_LOCALE,
            timezone_id=settings.BROWSER_TIMEZONE,
            viewport={'width': 1920, 'height': 1080},
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ],
        )
        self._contexts[telegram_user_id] = context
        logger.info(f"Browser context created for user {telegram_user_id}")
        return context

    async def get_page(self, telegram_user_id: int) -> Page:
        """Возвращает новую страницу в контексте пользователя."""
        context = await self.get_context(telegram_user_id)
        page = await context.new_page()
        return page

    async def check_session(self, telegram_user_id: int) -> bool:
        """Проверяет, активна ли сессия Avito (не перенаправляет на логин)."""
        try:
            page = await self.get_page(telegram_user_id)
            await page.goto('https://www.avito.ru/profile', wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)

            url = page.url
            await page.close()

            is_logged_in = '/login' not in url and '/auth' not in url
            logger.info(f"Session check for {telegram_user_id}: {'active' if is_logged_in else 'expired'} (url={url})")
            return is_logged_in
        except Exception as e:
            logger.error(f"Session check error for {telegram_user_id}: {e}")
            return False

    async def start_login(self, telegram_user_id: int, phone: str) -> bytes | None:
        """
        Начинает процесс входа: открывает Avito, вводит телефон.
        Возвращает скриншот страницы после ввода телефона.
        """
        try:
            page = await self.get_page(telegram_user_id)
            self._contexts[f'{telegram_user_id}_login_page'] = page

            await page.goto('https://www.avito.ru/login', wait_until='domcontentloaded', timeout=20000)
            await asyncio.sleep(3)

            # Ищем поле ввода телефона
            phone_input = page.locator('input[data-marker="login-form/phone-input"]')
            if await phone_input.count() == 0:
                phone_input = page.locator('input[type="tel"]')
            if await phone_input.count() == 0:
                phone_input = page.locator('input[name="login"]')

            if await phone_input.count() > 0:
                await phone_input.click()
                await asyncio.sleep(0.5)
                await phone_input.fill(phone)
                await asyncio.sleep(1)

                # Нажимаем кнопку "Продолжить" или "Войти"
                submit_btn = page.locator('button[data-marker="login-form/submit"]')
                if await submit_btn.count() == 0:
                    submit_btn = page.locator('button[type="submit"]')

                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    await asyncio.sleep(3)

            screenshot = await page.screenshot()
            return screenshot

        except Exception as e:
            logger.error(f"start_login error for {telegram_user_id}: {e}")
            return None

    async def complete_login(self, telegram_user_id: int, code: str) -> tuple[bool, bytes]:
        """
        Вводит SMS-код для завершения логина.
        Возвращает (success, screenshot).
        """
        page = self._contexts.get(f'{telegram_user_id}_login_page')
        if not page:
            raise RuntimeError("Нет активного процесса логина. Отправьте /login заново.")

        try:
            # Ищем поле для кода
            code_input = page.locator('input[data-marker="login-form/code-input"]')
            if await code_input.count() == 0:
                code_input = page.locator('input[inputmode="numeric"]')
            if await code_input.count() == 0:
                code_input = page.locator('input[type="text"]').first

            if await code_input.count() > 0:
                await code_input.fill(code)
                await asyncio.sleep(1)

                # Пробуем нажать submit
                submit_btn = page.locator('button[type="submit"]')
                if await submit_btn.count() > 0:
                    await submit_btn.click()

                await asyncio.sleep(5)

            screenshot = await page.screenshot()

            # Проверяем успешность — URL должен уйти со страницы логина
            url = page.url
            success = '/login' not in url and '/auth' not in url

            await page.close()
            # Убираем временную ссылку
            self._contexts.pop(f'{telegram_user_id}_login_page', None)

            return success, screenshot

        except Exception as e:
            logger.error(f"complete_login error for {telegram_user_id}: {e}")
            screenshot = await page.screenshot() if page else b''
            return False, screenshot

    async def close_context(self, telegram_user_id: int):
        """Закрывает браузерный контекст пользователя."""
        context = self._contexts.pop(telegram_user_id, None)
        if context:
            await context.close()
            logger.info(f"Browser context closed for user {telegram_user_id}")

    async def close_all(self):
        """Закрывает все контексты."""
        for uid in list(self._contexts.keys()):
            if isinstance(uid, int):
                await self.close_context(uid)
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
