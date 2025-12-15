import uuid

import aiohttp

import config
from database import db, Payment


class PaymentSystem:
    """Базовый класс для платежных систем"""

    def __init__(self):
        self.provider_name = "base"

    async def create_payment(self, user_id, amount, currency="RUB", description=""):
        """Создание платежа

        Args:
            user_id (int): ID пользователя
            amount (float): Сумма платежа
            currency (str, optional): Валюта. По умолчанию "RUB".
            description (str, optional): Описание платежа. По умолчанию "".

        Returns:
            dict: Данные для оплаты или None в случае ошибки
        """
        raise NotImplementedError("Метод create_payment должен быть реализован")

    async def check_payment(self, payment_id):
        """Проверка статуса платежа

        Args:
            payment_id (str): ID платежа в платежной системе

        Returns:
            dict: Статус платежа или None в случае ошибки
        """
        raise NotImplementedError("Метод check_payment должен быть реализован")


class TelegramPaymentSystem(PaymentSystem):
    """Платежная система Telegram"""

    def __init__(self, bot):
        super().__init__()
        self.provider_name = "telegram"
        self.bot = bot

    async def create_payment(self, user_id, amount, currency="RUB", description="Пополнение баланса"):
        """Создание платежа через Telegram Payments

        Args:
            user_id (int): ID пользователя
            amount (float): Сумма платежа
            currency (str, optional): Валюта. По умолчанию "RUB".
            description (str, optional): Описание платежа. По умолчанию "Пополнение баланса".

        Returns:
            dict: Данные для отправки инвойса или None в случае ошибки
        """
        try:
            # Генерируем уникальный ID для платежа
            invoice_payload = str(uuid.uuid4())

            # Создаем платеж в базе данных
            session = db.get_session()
            payment = Payment(
                user_id=user_id,
                amount=amount,
                currency=currency,
                payment_provider=self.provider_name,
                invoice_payload=invoice_payload
            )
            session.add(payment)
            session.commit()
            payment_id = payment.id
            session.close()

            # Формируем данные для инвойса
            prices = [{
                "label": description,
                "amount": int(amount * 100)  # Сумма в копейках/центах
            }]

            return {
                "title": "Пополнение баланса",
                "description": description,
                "payload": invoice_payload,
                "provider_token": config.Config.PAYMENT_PROVIDER_TOKEN,
                "currency": currency,
                "prices": prices,
                "payment_id": payment_id
            }

        except Exception as e:
            print(f"Ошибка создания платежа Telegram: {e}")
            return None

    async def check_payment(self, payment_id):
        """Проверка статуса платежа (для Telegram платежи обрабатываются через webhook)

        Args:
            payment_id (str): ID платежа в платежной системе

        Returns:
            dict: Статус платежа
        """
        # В реальном приложении здесь должна быть логика проверки статуса
        return {"status": "completed"}


class YooKassaPaymentSystem(PaymentSystem):
    """Платежная система ЮKassa"""

    def __init__(self):
        super().__init__()
        self.provider_name = "yookassa"
        self.base_url = "https://api.yookassa.ru/v3"

    async def _make_request(self, method, endpoint, data=None):
        """Выполнение запроса к API ЮKassa

        Args:
            method (str): HTTP метод
            endpoint (str): Эндпоинт API
            data (dict, optional): Данные для запроса. По умолчанию None.

        Returns:
            dict: Ответ API
        """
        auth = aiohttp.BasicAuth(
            login=config.Config.YOOKASSA_SHOP_ID,
            password=config.Config.YOOKASSA_SECRET_KEY
        )

        headers = {
            "Idempotence-Key": str(uuid.uuid4()),
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method,
                    f"{self.base_url}/{endpoint}",
                    auth=auth,
                    headers=headers,
                    json=data
            ) as response:
                return await response.json()

    async def create_payment(self, user_id, amount, currency="RUB", description="Пополнение баланса"):
        """Создание платежа через ЮKassa

        Args:
            user_id (int): ID пользователя
            amount (float): Сумма платежа
            currency (str, optional): Валюта. По умолчанию "RUB".
            description (str, optional): Описание платежа. По умолчанию "Пополнение баланса".

        Returns:
            dict: Данные для оплаты или None в случае ошибки
        """
        try:
            # Создаем платеж в базе данных
            session = db.get_session()
            payment = Payment(
                user_id=user_id,
                amount=amount,
                currency=currency,
                payment_provider=self.provider_name
            )
            session.add(payment)
            session.commit()
            payment_id = payment.id
            session.close()

            # Создаем платеж в ЮKassa
            payment_data = {
                "amount": {
                    "value": str(amount),
                    "currency": currency
                },
                "payment_method_data": {
                    "type": "bank_card"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/your_bot_username"  # Замените на имя вашего бота
                },
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "payment_id": payment_id
                }
            }

            response = await self._make_request("POST", "payments", payment_data)

            if "id" in response:
                # Обновляем платеж в базе данных
                session = db.get_session()
                payment = session.query(Payment).filter(Payment.id == payment_id).first()
                if payment:
                    payment.provider_payment_id = response["id"]
                    session.commit()
                session.close()

                return {
                    "payment_id": payment_id,
                    "confirmation_url": response["confirmation"]["confirmation_url"],
                    "yookassa_payment_id": response["id"]
                }
            else:
                return None

        except Exception as e:
            print(f"Ошибка создания платежа ЮKassa: {e}")
            return None

    async def check_payment(self, payment_id):
        """Проверка статуса платежа в ЮKassa

        Args:
            payment_id (str): ID платежа в ЮKassa

        Returns:
            dict: Статус платежа
        """
        try:
            response = await self._make_request("GET", f"payments/{payment_id}")
            return {"status": response.get("status", "unknown")}
        except Exception as e:
            print(f"Ошибка проверки платежа ЮKassa: {e}")
            return {"status": "unknown"}


class PaymentManager:
    """Менеджер платежных систем"""

    def __init__(self, bot=None):
        self.systems = {}
        self.bot = bot

        # Инициализация платежных систем
        if config.Config.PAYMENT_PROVIDER_TOKEN:
            self.systems["telegram"] = TelegramPaymentSystem(bot)

        if config.Config.YOOKASSA_SHOP_ID and config.Config.YOOKASSA_SECRET_KEY:
            self.systems["yookassa"] = YooKassaPaymentSystem()

    async def create_payment(self, provider, user_id, amount, currency="RUB", description=""):
        """Создание платежа через выбранного провайдера

        Args:
            provider (str): Название платежной системы
            user_id (int): ID пользователя
            amount (float): Сумма платежа
            currency (str, optional): Валюта. По умолчанию "RUB".
            description (str, optional): Описание платежа. По умолчанию "".

        Returns:
            dict: Результат создания платежа или None
        """
        if provider not in self.systems:
            return None

        return await self.systems[provider].create_payment(
            user_id, amount, currency, description
        )

    async def check_payment(self, provider, payment_id):
        """Проверка статуса платежа

        Args:
            provider (str): Название платежной системы
            payment_id (str): ID платежа

        Returns:
            dict: Статус платежа
        """
        if provider not in self.systems:
            return {"status": "unknown"}

        return await self.systems[provider].check_payment(payment_id)

    def get_available_providers(self):
        """Получение списка доступных платежных систем

        Returns:
            list: Список доступных платежных систем
        """
        return list(self.systems.keys())
