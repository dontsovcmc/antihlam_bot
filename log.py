import os
from loguru import logger
from datetime import datetime

DATA_PATH = os.getenv('DATA_PATH', os.getcwd())
current_time = datetime.now().strftime('%Y%m%d-%H%M%S')
logger.add(f"{DATA_PATH}/logs/log_{current_time}.log", level="DEBUG", rotation="1 MB")

logger.info(f'DATA_PATH={DATA_PATH}')
