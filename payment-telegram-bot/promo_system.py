"""
Модуль для реализации системы промокодов и скидок
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, Enum as SQLEnum

from database import db, Base


class PromoCodeType(Enum):
    """Типы промокодов"""
    PERCENTAGE = "percentage"  # Процентная скидка
    FIXED = "fixed"  # Фиксированная сумма
    FREE_SERVICE = "free_service"  # Бесплатная услуга


class PromoCode(Base):
    """Модель промокода"""

    __tablename__ = 'promo_codes'

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    promo_type = Column(SQLEnum(PromoCodeType), default=PromoCodeType.PERCENTAGE)
    discount_value = Column(Float, nullable=False)  # Значение скидки (процент или сумма)
    max_discount = Column(Float, nullable=True)  # Максимальная сумма скидки для процентных
    min_order_amount = Column(Float, default=0.0)  # Минимальная сумма заказа
    service_id = Column(Integer, ForeignKey('services.id'), nullable=True)  # Для бесплатных услуг
    valid_from = Column(DateTime, default=datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)
    max_uses = Column(Integer, nullable=True)  # Максимальное количество использований
    current_uses = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)


class PromoCodeUsage(Base):
    """Модель использования промокода"""

    __tablename__ = 'promo_code_usages'

    id = Column(Integer, primary_key=True)
    promo_code_id = Column(Integer, ForeignKey('promo_codes.id'), nullable=False)
    user_id = Column(Integer, nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow)
    order_amount = Column(Float, nullable=False)
    discount_applied = Column(Float, nullable=False)
    payment_id = Column(Integer, ForeignKey('payments.id'), nullable=True)


class PromoSystem:
    """Класс для управления промокодами"""

    def __init__(self):
        self.db = db

    def create_promo_code(self, code: str, promo_type: PromoCodeType, discount_value: float,
                          valid_to: datetime = None, max_uses: int = None,
                          max_discount: float = None, min_order_amount: float = 0.0,
                          service_id: int = None, description: str = "") -> PromoCode:
        """Создание промокода

        Args:
            code (str): Код промокода
            promo_type (PromoCodeType): Тип промокода
            discount_value (float): Значение скидки
            valid_to (datetime, optional): Срок действия. По умолчанию None.
            max_uses (int, optional): Максимальное количество использований. По умолчанию None.
            max_discount (float, optional): Максимальная сумма скидки. По умолчанию None.
            min_order_amount (float, optional): Минимальная сумма заказа. По умолчанию 0.0.
            service_id (int, optional): ID услуги для бесплатной услуги. По умолчанию None.
            description (str, optional): Описание промокода. По умолчанию "".

        Returns:
            PromoCode: Объект промокода
        """
        session = self.db.get_session()

        # Проверяем, не существует ли уже такой код
        existing = session.query(PromoCode).filter(PromoCode.code == code).first()

        if existing:
            session.close()
            raise ValueError("Промокод с таким кодом уже существует")

        # Создаем промокод
        promo_code = PromoCode(
            code=code.upper(),
            promo_type=promo_type,
            discount_value=discount_value,
            valid_to=valid_to,
            max_uses=max_uses,
            max_discount=max_discount,
            min_order_amount=min_order_amount,
            service_id=service_id,
            description=description
        )

        session.add(promo_code)
        session.commit()
        session.refresh(promo_code)
        session.close()

        return promo_code

    def validate_promo_code(self, code: str, user_id: int, order_amount: float = 0.0) -> dict:
        """Валидация промокода

        Args:
            code (str): Код промокода
            user_id (int): ID пользователя
            order_amount (float, optional): Сумма заказа. По умолчанию 0.0.

        Returns:
            dict: Результат валидации
        """
        session = self.db.get_session()

        promo_code = session.query(PromoCode).filter(
            PromoCode.code == code.upper(),
            PromoCode.is_active == True
        ).first()

        if not promo_code:
            session.close()
            return {
                "valid": False,
                "message": "Промокод не найден"
            }

        # Проверяем срок действия
        now = datetime.utcnow()
        if promo_code.valid_from and promo_code.valid_from > now:
            session.close()
            return {
                "valid": False,
                "message": "Промокод еще не активен"
            }

        if promo_code.valid_to and promo_code.valid_to < now:
            session.close()
            return {
                "valid": False,
                "message": "Срок действия промокода истек"
            }

        # Проверяем лимит использований
        if promo_code.max_uses and promo_code.current_uses >= promo_code.max_uses:
            session.close()
            return {
                "valid": False,
                "message": "Лимит использований промокода исчерпан"
            }

        # Проверяем минимальную сумму заказа
        if order_amount < promo_code.min_order_amount:
            session.close()
            return {
                "valid": False,
                "message": f"Минимальная сумма заказа для этого промокода: {promo_code.min_order_amount:.2f} RUB"
            }

        # Проверяем, не использовал ли пользователь уже этот промокод
        existing_usage = session.query(PromoCodeUsage).filter(
            PromoCodeUsage.promo_code_id == promo_code.id,
            PromoCodeUsage.user_id == user_id
        ).first()

        if existing_usage:
            session.close()
            return {
                "valid": False,
                "message": "Вы уже использовали этот промокод"
            }

        # Рассчитываем скидку
        discount_info = self._calculate_discount(promo_code, order_amount)

        session.close()

        return {
            "valid": True,
            "promo_code": promo_code,
            "discount_amount": discount_info["discount_amount"],
            "final_amount": discount_info["final_amount"],
            "message": discount_info["message"]
        }

    def _calculate_discount(self, promo_code: PromoCode, order_amount: float) -> dict:
        """Расчет скидки по промокоду

        Args:
            promo_code (PromoCode): Объект промокода
            order_amount (float): Сумма заказа

        Returns:
            dict: Информация о скидке
        """
        if promo_code.promo_type == PromoCodeType.PERCENTAGE:
            # Процентная скидка
            discount_amount = order_amount * (promo_code.discount_value / 100)

            # Применяем максимальную скидку, если она установлена
            if promo_code.max_discount and discount_amount > promo_code.max_discount:
                discount_amount = promo_code.max_discount

            final_amount = order_amount - discount_amount
            message = f"Скидка {promo_code.discount_value}%"

        elif promo_code.promo_type == PromoCodeType.FIXED:
            # Фиксированная скидка
            discount_amount = min(promo_code.discount_value, order_amount)
            final_amount = order_amount - discount_amount
            message = f"Скидка {discount_amount:.2f} RUB"

        elif promo_code.promo_type == PromoCodeType.FREE_SERVICE:
            # Бесплатная услуга
            discount_amount = order_amount  # Вся сумма списывается
            final_amount = 0
            message = "Бесплатная услуга"

        else:
            discount_amount = 0
            final_amount = order_amount
            message = ""

        return {
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "message": message
        }

    def apply_promo_code(self, promo_code_id: int, user_id: int, order_amount: float,
                         payment_id: int = None) -> dict:
        """Применение промокода

        Args:
            promo_code_id (int): ID промокода
            user_id (int): ID пользователя
            order_amount (float): Сумма заказа
            payment_id (int, optional): ID платежа. По умолчанию None.

        Returns:
            dict: Результат применения промокода
        """
        session = self.db.get_session()

        promo_code = session.query(PromoCode).filter(PromoCode.id == promo_code_id).first()

        if not promo_code:
            session.close()
            return {
                "success": False,
                "message": "Промокод не найден"
            }

        # Рассчитываем скидку
        discount_info = self._calculate_discount(promo_code, order_amount)

        # Создаем запись об использовании
        usage = PromoCodeUsage(
            promo_code_id=promo_code_id,
            user_id=user_id,
            order_amount=order_amount,
            discount_applied=discount_info["discount_amount"],
            payment_id=payment_id
        )

        session.add(usage)

        # Увеличиваем счетчик использований
        promo_code.current_uses += 1

        # Если достигнут лимит использований, деактивируем промокод
        if promo_code.max_uses and promo_code.current_uses >= promo_code.max_uses:
            promo_code.is_active = False

        session.commit()
        session.close()

        return {
            "success": True,
            "discount_amount": discount_info["discount_amount"],
            "final_amount": discount_info["final_amount"],
            "message": discount_info["message"]
        }

    def get_promo_code_stats(self, promo_code_id: int) -> dict:
        """Получение статистики по промокоду

        Args:
            promo_code_id (int): ID промокода

        Returns:
            dict: Статистика промокода
        """
        session = self.db.get_session()

        promo_code = session.query(PromoCode).filter(PromoCode.id == promo_code_id).first()

        if not promo_code:
            session.close()
            return {}

        # Получаем статистику использований
        usages = session.query(PromoCodeUsage).filter(
            PromoCodeUsage.promo_code_id == promo_code_id
        ).all()

        total_uses = len(usages)
        total_discount = sum(usage.discount_applied for usage in usages)
        total_orders = sum(usage.order_amount for usage in usages)

        # Уникальные пользователи
        unique_users = len(set(usage.user_id for usage in usages))

        session.close()

        return {
            "code": promo_code.code,
            "type": promo_code.promo_type.value,
            "total_uses": total_uses,
            "current_uses": promo_code.current_uses,
            "max_uses": promo_code.max_uses,
            "total_discount": total_discount,
            "total_orders": total_orders,
            "unique_users": unique_users,
            "is_active": promo_code.is_active,
            "valid_from": promo_code.valid_from,
            "valid_to": promo_code.valid_to
        }
