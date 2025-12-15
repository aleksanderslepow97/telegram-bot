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

    # Настройки реферальной системы
    REFERRAL_REWARD_PERCENT = float(os.getenv("REFERRAL_REWARD_PERCENT", "10.0"))
    REFERRAL_MIN_PAYMENT = float(os.getenv("REFERRAL_MIN_PAYMENT", "100.0"))

    # Настройки уведомлений
    NOTIFY_ON_NEW_USER = os.getenv("NOTIFY_ON_NEW_USER", "true").lower() == "true"
    NOTIFY_ON_PAYMENT = os.getenv("NOTIFY_ON_PAYMENT", "true").lower() == "true"
    NOTIFY_ON_LARGE_PAYMENT = os.getenv("NOTIFY_ON_LARGE_PAYMENT", "true").lower() == "true"
    LARGE_PAYMENT_THRESHOLD = float(os.getenv("LARGE_PAYMENT_THRESHOLD", "5000.0"))

    # Настройки валют
    DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "RUB")
    SUPPORTED_CURRENCIES = os.getenv("SUPPORTED_CURRENCIES", "RUB,USD,EUR").split(',')

    # Настройки экспорта
    EXPORT_MAX_ROWS = int(os.getenv("EXPORT_MAX_ROWS", "10000"))

    # Настройки подписок
    SUBSCRIPTION_CHECK_INTERVAL = int(os.getenv("SUBSCRIPTION_CHECK_INTERVAL", "300"))  # секунды

    # Настройки промокодов
    PROMO_CODE_LENGTH = int(os.getenv("PROMO_CODE_LENGTH", "8"))

    @classmethod
    def validate(cls):
        """Проверка наличия обязательных переменных окружения"""
        required_vars = ['BOT_TOKEN']
        missing_vars = [var for var in required_vars if not getattr(cls, var)]

        if missing_vars:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
