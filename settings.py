import os
import yaml


def load_config(file_path):
    """Загружает конфигурацию из файла YAML."""
    try:
        with open(file_path, 'r') as file:
            config = yaml.safe_load(file)
            return config
    except FileNotFoundError:
        print(f"Файл {file_path} не найден.")
        raise
    except yaml.YAMLError as e:
        print(f"Ошибка парсинга YAML: {e}")
        raise


DATA_PATH = os.getenv('DATA_PATH', os.getcwd())

config = load_config(os.path.join(DATA_PATH, 'config.yml'))

TELEGRAM_BOT_TOKEN = config['bot_token']
ALLOWED_USER_IDS = set(config.get('allowed_user_ids', []))

ANTHROPIC_API_KEY = config['anthropic']['api_key']
ANTHROPIC_MODEL = config['anthropic'].get('model', 'claude-sonnet-4-20250514')

AVITO_CLIENT_ID = config.get('avito', {}).get('client_id', '')
AVITO_CLIENT_SECRET = config.get('avito', {}).get('client_secret', '')
AVITO_DEFAULT_ADDRESS = config.get('avito', {}).get('default_address', 'Москва')
AVITO_MESSENGER_POLL_INTERVAL = config.get('avito', {}).get('messenger_poll_interval_sec', 30)

BROWSER_HEADLESS = config.get('browser', {}).get('headless', True)
BROWSER_DATA_DIR = config.get('browser', {}).get('data_dir', './browser_data')
BROWSER_LOCALE = config.get('browser', {}).get('locale', 'ru-RU')
BROWSER_TIMEZONE = config.get('browser', {}).get('timezone', 'Europe/Moscow')
