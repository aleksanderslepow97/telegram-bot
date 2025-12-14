import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Класс для хранения конфигурации бота"""

    # Токен бота от @BotFather
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # Настройки платежной системы
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")  # Токен от BotFather для платежей

    # Настройки для стороннего платежного провайдера (например, ЮKassa)
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

    # Настройки базы данных
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///payments.db")

    # Настройки Redis для хранения состояний (опционально)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost")

    # Админы бота
    ADMINS = list(map(int, os.getenv("ADMINS", "").split(','))) if os.getenv("ADMINS") else []

    @classmethod
    def validate(cls):
        """Проверка наличия обязательных переменных окружения"""
        required_vars = ['BOT_TOKEN']
        missing_vars = [var for var in required_vars if not getattr(cls, var)]

        if missing_vars:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
