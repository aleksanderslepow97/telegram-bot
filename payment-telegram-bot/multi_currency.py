"""
Модуль для поддержки нескольких валют
"""

from datetime import datetime
from typing import Dict, Optional
import aiohttp
from database import db, Base
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean


class CurrencyRate(Base):
    """Модель курса валюты"""

    __tablename__ = 'currency_rates'

    id = Column(Integer, primary_key=True)
    base_currency = Column(String(10), nullable=False, default="RUB")
    target_currency = Column(String(10), nullable=False)
    rate = Column(Float, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class SupportedCurrency(Base):
    """Модель поддерживаемой валюты"""

    __tablename__ = 'supported_currencies'

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    symbol = Column(String(10))
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    decimal_places = Column(Integer, default=2)
    created_at = Column(DateTime, default=datetime.utcnow)


class CurrencyConverter:
    """Класс для конвертации валют"""

    def __init__(self):
        self.db = db
        self.cache: Dict[str, float] = {}
        self.cache_timeout = 3600  # 1 час в секундах

    async def get_exchange_rate(self, base_currency: str, target_currency: str) -> Optional[float]:
        """Получение курса обмена валют

        Args:
            base_currency (str): Базовая валюта
            target_currency (str): Целевая валюта

        Returns:
            Optional[float]: Курс обмена или None в случае ошибки
        """
        if base_currency == target_currency:
            return 1.0

        cache_key = f"{base_currency}_{target_currency}"

        # Проверяем кэш
        if cache_key in self.cache:
            rate, timestamp = self.cache[cache_key]
            if (datetime.utcnow() - timestamp).seconds < self.cache_timeout:
                return rate

        # Проверяем базу данных
        session = self.db.get_session()
        currency_rate = session.query(CurrencyRate).filter(
            CurrencyRate.base_currency == base_currency,
            CurrencyRate.target_currency == target_currency,
            CurrencyRate.is_active == True
        ).first()

        if currency_rate and (datetime.utcnow() - currency_rate.last_updated).seconds < self.cache_timeout:
            self.cache[cache_key] = (currency_rate.rate, datetime.utcnow())
            session.close()
            return currency_rate.rate

        session.close()

        # Получаем курс из внешнего API
        rate = await self._fetch_exchange_rate(base_currency, target_currency)

        if rate:
            # Сохраняем в кэш
            self.cache[cache_key] = (rate, datetime.utcnow())

            # Сохраняем в базу данных
            await self._save_exchange_rate(base_currency, target_currency, rate)

        return rate

    async def _fetch_exchange_rate(self, base_currency: str, target_currency: str) -> Optional[float]:
        """Получение курса обмена из внешнего API

        Args:
            base_currency (str): Базовая валюта
            target_currency (str): Целевая валюта

        Returns:
            Optional[float]: Курс обмена или None в случае ошибки
        """
        try:
            # Используем бесплатный API exchangerate-api.com
            url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        rates = data.get('rates', {})
                        return rates.get(target_currency)

            # Альтернативный API
            url = f"https://api.exchangerate.host/latest?base={base_currency}&symbols={target_currency}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        rates = data.get('rates', {})
                        return rates.get(target_currency)

        except Exception as e:
            print(f"Ошибка получения курса валют: {e}")
            return None

    async def _save_exchange_rate(self, base_currency: str, target_currency: str, rate: float):
        """Сохранение курса обмена в базу данных

        Args:
            base_currency (str): Базовая валюта
            target_currency (str): Целевая валюта
            rate (float): Курс обмена
        """
        session = self.db.get_session()

        # Ищем существующую запись
        currency_rate = session.query(CurrencyRate).filter(
            CurrencyRate.base_currency == base_currency,
            CurrencyRate.target_currency == target_currency
        ).first()

        if currency_rate:
            currency_rate.rate = rate
            currency_rate.last_updated = datetime.utcnow()
        else:
            currency_rate = CurrencyRate(
                base_currency=base_currency,
                target_currency=target_currency,
                rate=rate
            )
            session.add(currency_rate)

        session.commit()
        session.close()

    async def convert_amount(self, amount: float, from_currency: str, to_currency: str) -> Optional[float]:
        """Конвертация суммы из одной валюты в другую

        Args:
            amount (float): Сумма для конвертации
            from_currency (str): Исходная валюта
            to_currency (str): Целевая валюта

        Returns:
            Optional[float]: Конвертированная сумма или None в случае ошибки
        """
        rate = await self.get_exchange_rate(from_currency, to_currency)

        if rate is None:
            return None

        return amount * rate

    async def format_currency(self, amount: float, currency_code: str) -> str:
        """Форматирование суммы с символом валюты

        Args:
            amount (float): Сумма
            currency_code (str): Код валюты

        Returns:
            str: Отформатированная сумма
        """
        session = self.db.get_session()

        currency = session.query(SupportedCurrency).filter(
            SupportedCurrency.code == currency_code,
            SupportedCurrency.is_active == True
        ).first()

        session.close()

        if currency and currency.symbol:
            # Форматирование с символом валюты
            if currency.symbol.startswith('$') or currency.symbol.startswith('€') or currency.symbol.startswith('£'):
                return f"{currency.symbol}{amount:.{currency.decimal_places}f}"
            else:
                return f"{amount:.{currency.decimal_places}f} {currency.symbol}"
        else:
            # Форматирование с кодом валюты
            return f"{amount:.2f} {currency_code}"

    async def get_supported_currencies(self) -> list:
        """Получение списка поддерживаемых валют

        Returns:
            list: Список поддерживаемых валют
        """
        session = self.db.get_session()

        currencies = session.query(SupportedCurrency).filter(
            SupportedCurrency.is_active == True
        ).order_by(SupportedCurrency.code).all()

        session.close()

        return currencies

    async def add_supported_currency(self, code: str, name: str, symbol: str = "",
                                     decimal_places: int = 2, is_default: bool = False) -> bool:
        """Добавление поддерживаемой валюты

        Args:
            code (str): Код валюты (например, USD, EUR, RUB)
            name (str): Название валюты
            symbol (str, optional): Символ валюты. По умолчанию "".
            decimal_places (int, optional): Количество знаков после запятой. По умолчанию 2.
            is_default (bool, optional): Является ли валютой по умолчанию. По умолчанию False.

        Returns:
            bool: Успешность добавления
        """
        session = self.db.get_session()

        # Проверяем, существует ли уже валюта
        existing = session.query(SupportedCurrency).filter(
            SupportedCurrency.code == code
        ).first()

        if existing:
            session.close()
            return False

        # Если это валюта по умолчанию, сбрасываем флаг у других валют
        if is_default:
            session.query(SupportedCurrency).update({SupportedCurrency.is_default: False})

        # Добавляем валюту
        currency = SupportedCurrency(
            code=code,
            name=name,
            symbol=symbol,
            decimal_places=decimal_places,
            is_default=is_default
        )

        session.add(currency)
        session.commit()
        session.close()

        return True

    async def get_default_currency(self) -> Optional[SupportedCurrency]:
        """Получение валюты по умолчанию

        Returns:
            Optional[SupportedCurrency]: Валюта по умолчанию или None
        """
        session = self.db.get_session()

        currency = session.query(SupportedCurrency).filter(
            SupportedCurrency.is_default == True,
            SupportedCurrency.is_active == True
        ).first()

        session.close()

        return currency
