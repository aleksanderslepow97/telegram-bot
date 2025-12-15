"""
Модуль для реализации системы подписок с автоматическим списанием
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship

from database import db, Base


class SubscriptionStatus(Enum):
    """Статусы подписки"""
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class SubscriptionPlan(Base):
    """Модель плана подписки"""

    __tablename__ = 'subscription_plans'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    billing_cycle_days = Column(Integer, nullable=False)  # Длительность цикла в днях
    trial_period_days = Column(Integer, default=0)  # Пробный период
    is_active = Column(Boolean, default=True)
    max_cancellations = Column(Integer, default=1)  # Максимальное количество отмен
    auto_renewal = Column(Boolean, default=True)  # Автоматическое продление
    created_at = Column(DateTime, default=datetime.utcnow)
    features = Column(Text)  # JSON с описанием возможностей


class UserSubscription(Base):
    """Модель подписки пользователя"""

    __tablename__ = 'user_subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey('subscription_plans.id'), nullable=False)
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=False)
    next_billing_date = Column(DateTime, nullable=False)
    trial_end_date = Column(DateTime, nullable=True)
    auto_renewal = Column(Boolean, default=True)
    cancellation_count = Column(Integer, default=0)
    total_paid = Column(Float, default=0.0)
    payment_method_id = Column(String(100), nullable=True)  # ID сохраненного метода оплаты
    last_payment_id = Column(Integer, ForeignKey('payments.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan = relationship("SubscriptionPlan")


class SubscriptionSystem:
    """Класс для управления подписками"""

    def __init__(self, bot=None):
        self.db = db
        self.bot = bot
        self._task = None

    def create_subscription_plan(self, name: str, description: str, price: float,
                                 billing_cycle_days: int, **kwargs) -> SubscriptionPlan:
        """Создание плана подписки

        Args:
            name (str): Название плана
            description (str): Описание плана
            price (float): Цена
            billing_cycle_days (int): Длительность цикла в днях
            **kwargs: Дополнительные параметры

        Returns:
            SubscriptionPlan: Объект плана подписки
        """
        session = self.db.get_session()

        plan = SubscriptionPlan(
            name=name,
            description=description,
            price=price,
            billing_cycle_days=billing_cycle_days,
            trial_period_days=kwargs.get('trial_period_days', 0),
            is_active=kwargs.get('is_active', True),
            max_cancellations=kwargs.get('max_cancellations', 1),
            auto_renewal=kwargs.get('auto_renewal', True),
            features=kwargs.get('features', '{}'),
            currency=kwargs.get('currency', 'RUB')
        )

        session.add(plan)
        session.commit()
        session.refresh(plan)
        session.close()

        return plan

    def subscribe_user(self, user_id: int, plan_id: int,
                       payment_method_id: str = None) -> Optional[UserSubscription]:
        """Оформление подписки пользователем

        Args:
            user_id (int): ID пользователя
            plan_id (int): ID плана подписки
            payment_method_id (str, optional): ID метода оплаты. По умолчанию None.

        Returns:
            Optional[UserSubscription]: Объект подписки или None в случае ошибки
        """
        session = self.db.get_session()

        # Получаем план подписки
        plan = session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id,
            SubscriptionPlan.is_active == True
        ).first()

        if not plan:
            session.close()
            return None

        # Проверяем, нет ли у пользователя активной подписки
        existing_subscription = session.query(UserSubscription).filter(
            UserSubscription.user_id == user_id,
            UserSubscription.status == SubscriptionStatus.ACTIVE
        ).first()

        if existing_subscription:
            session.close()
            return None

        # Рассчитываем даты
        now = datetime.utcnow()
        end_date = now + timedelta(days=plan.billing_cycle_days)
        next_billing_date = end_date

        # Если есть пробный период
        trial_end_date = None
        if plan.trial_period_days > 0:
            trial_end_date = now + timedelta(days=plan.trial_period_days)
            end_date = trial_end_date + timedelta(days=plan.billing_cycle_days)
            next_billing_date = trial_end_date

        # Создаем подписку
        subscription = UserSubscription(
            user_id=user_id,
            plan_id=plan_id,
            start_date=now,
            end_date=end_date,
            next_billing_date=next_billing_date,
            trial_end_date=trial_end_date,
            auto_renewal=plan.auto_renewal,
            payment_method_id=payment_method_id
        )

        session.add(subscription)
        session.commit()
        session.refresh(subscription)
        session.close()

        return subscription

    def cancel_subscription(self, user_id: int, subscription_id: int) -> bool:
        """Отмена подписки пользователем

        Args:
            user_id (int): ID пользователя
            subscription_id (int): ID подписки

        Returns:
            bool: Успешность отмены
        """
        session = self.db.get_session()

        subscription = session.query(UserSubscription).filter(
            UserSubscription.id == subscription_id,
            UserSubscription.user_id == user_id
        ).first()

        if not subscription:
            session.close()
            return False

        plan = session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == subscription.plan_id
        ).first()

        if not plan:
            session.close()
            return False

        # Проверяем лимит отмен
        if subscription.cancellation_count >= plan.max_cancellations:
            session.close()
            return False

        # Отменяем подписку
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.auto_renewal = False
        subscription.cancellation_count += 1
        subscription.updated_at = datetime.utcnow()

        session.commit()
        session.close()

        return True

    def pause_subscription(self, user_id: int, subscription_id: int) -> bool:
        """Приостановка подписки

        Args:
            user_id (int): ID пользователя
            subscription_id (int): ID подписки

        Returns:
            bool: Успешность приостановки
        """
        session = self.db.get_session()

        subscription = session.query(UserSubscription).filter(
            UserSubscription.id == subscription_id,
            UserSubscription.user_id == user_id,
            UserSubscription.status == SubscriptionStatus.ACTIVE
        ).first()

        if not subscription:
            session.close()
            return False

        subscription.status = SubscriptionStatus.PAUSED
        subscription.updated_at = datetime.utcnow()

        session.commit()
        session.close()

        return True

    def resume_subscription(self, user_id: int, subscription_id: int) -> bool:
        """Возобновление подписки

        Args:
            user_id (int): ID пользователя
            subscription_id (int): ID подписки

        Returns:
            bool: Успешность возобновления
        """
        session = self.db.get_session()

        subscription = session.query(UserSubscription).filter(
            UserSubscription.id == subscription_id,
            UserSubscription.user_id == user_id,
            UserSubscription.status == SubscriptionStatus.PAUSED
        ).first()

        if not subscription:
            session.close()
            return False

        subscription.status = SubscriptionStatus.ACTIVE
        subscription.updated_at = datetime.utcnow()

        session.commit()
        session.close()

        return True

    async def process_recurring_payments(self):
        """Обработка регулярных платежей для подписок"""
        session = self.db.get_session()

        now = datetime.utcnow()

        # Находим подписки, у которых наступила дата следующего платежа
        subscriptions = session.query(UserSubscription).filter(
            UserSubscription.status == SubscriptionStatus.ACTIVE,
            UserSubscription.auto_renewal == True,
            UserSubscription.next_billing_date <= now,
            UserSubscription.payment_method_id.isnot(None)
        ).all()

        for subscription in subscriptions:
            try:
                # Получаем план подписки
                plan = session.query(SubscriptionPlan).filter(
                    SubscriptionPlan.id == subscription.plan_id
                ).first()

                if not plan or not plan.is_active:
                    continue

                # Создаем платеж
                from database import Payment
                payment = Payment(
                    user_id=subscription.user_id,
                    amount=plan.price,
                    currency=plan.currency,
                    status="pending",
                    payment_provider="subscription",
                    invoice_payload=f"Автоплатеж за подписку: {plan.name}"
                )

                session.add(payment)
                session.commit()

                # Здесь должна быть логика списания средств через платежную систему
                # В реальном приложении используйте сохраненный payment_method_id

                # Для демонстрации считаем платеж успешным
                payment.status = "completed"
                payment.completed_at = now

                # Обновляем подписку
                subscription.last_payment_id = payment.id
                subscription.total_paid += plan.price

                # Обновляем даты
                subscription.next_billing_date = subscription.next_billing_date + timedelta(
                    days=plan.billing_cycle_days)
                subscription.end_date = subscription.next_billing_date
                subscription.updated_at = now

                # Отправляем уведомление пользователю
                if self.bot:
                    try:
                        await self.bot.send_message(
                            subscription.user_id,
                            f"✅ Произведен автоплатеж за подписку '{plan.name}' на сумму {plan.price:.2f} {plan.currency}\n"
                            f"Следующий платеж: {subscription.next_billing_date.strftime('%d.%m.%Y')}"
                        )
                    except:
                        pass

                session.commit()

            except Exception as e:
                print(f"Ошибка обработки регулярного платежа для подписки {subscription.id}: {e}")
                continue

        session.close()

    async def start_background_tasks(self):
        """Запуск фоновых задач для обработки подписок"""
        self._task = asyncio.create_task(self._subscription_worker())

    async def _subscription_worker(self):
        """Фоновая задача для обработки подписок"""
        while True:
            try:
                await self.process_recurring_payments()
                await self.check_expired_subscriptions()
            except Exception as e:
                print(f"Ошибка в фоновой задаче подписок: {e}")

            # Проверяем каждые 5 минут
            await asyncio.sleep(300)

    async def check_expired_subscriptions(self):
        """Проверка истекающих подписок"""
        session = self.db.get_session()

        now = datetime.utcnow()

        # Находим подписки, которые истекли
        expired_subscriptions = session.query(UserSubscription).filter(
            UserSubscription.status == SubscriptionStatus.ACTIVE,
            UserSubscription.end_date <= now
        ).all()

        for subscription in expired_subscriptions:
            subscription.status = SubscriptionStatus.EXPIRED
            subscription.updated_at = now

            # Отправляем уведомление
            if self.bot:
                try:
                    await self.bot.send_message(
                        subscription.user_id,
                        f"⚠️ Ваша подписка истекла. Продлите ее, чтобы продолжить пользоваться услугами."
                    )
                except:
                    pass

        session.commit()
        session.close()
