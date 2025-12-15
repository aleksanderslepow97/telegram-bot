"""
Модуль для реализации реферальной системы
"""

import uuid
from datetime import datetime, timedelta
from database import db, Base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean


class ReferralLink(Base):
    """Модель реферальной ссылки"""

    __tablename__ = 'referral_links'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False)
    link = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    max_uses = Column(Integer, nullable=True)  # Максимальное количество использований
    current_uses = Column(Integer, default=0)
    reward_amount = Column(Float, default=0.0)  # Вознаграждение за привлечение
    reward_percent = Column(Float, default=10.0)  # Процент от платежа реферала


class Referral(Base):
    """Модель реферала"""

    __tablename__ = 'referrals'

    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, nullable=False, index=True)  # Тот, кто пригласил
    referred_id = Column(Integer, nullable=False, index=True)  # Тот, кого пригласили
    referral_link_id = Column(Integer, ForeignKey('referral_links.id'), nullable=True)
    registered_at = Column(DateTime, default=datetime.utcnow)
    has_made_payment = Column(Boolean, default=False)
    total_referral_reward = Column(Float, default=0.0)


class ReferralSystem:
    """Класс для управления реферальной системой"""

    def __init__(self):
        self.db = db

    def generate_referral_code(self, user_id: int, custom_code: str = None) -> ReferralLink:
        """Генерация реферального кода

        Args:
            user_id (int): ID пользователя
            custom_code (str, optional): Пользовательский код. По умолчанию None.

        Returns:
            ReferralLink: Объект реферальной ссылки
        """
        session = self.db.get_session()

        if custom_code:
            # Проверяем, не занят ли пользовательский код
            existing = session.query(ReferralLink).filter(
                ReferralLink.code == custom_code
            ).first()

            if existing:
                session.close()
                raise ValueError("Этот код уже занят")

            code = custom_code
        else:
            # Генерируем уникальный код
            code = str(uuid.uuid4())[:8].upper()

            # Проверяем на уникальность
            while session.query(ReferralLink).filter(ReferralLink.code == code).first():
                code = str(uuid.uuid4())[:8].upper()

        # Создаем реферальную ссылку
        link = f"https://t.me/your_bot?start=ref_{code}"  # Замените на имя вашего бота

        referral_link = ReferralLink(
            user_id=user_id,
            code=code,
            link=link,
            expires_at=datetime.utcnow() + timedelta(days=30),  # Срок действия 30 дней
            max_uses=100  # Максимальное количество использований
        )

        session.add(referral_link)
        session.commit()
        session.refresh(referral_link)
        session.close()

        return referral_link

    def register_referral(self, referrer_id: int, referred_id: int, referral_code: str = None) -> bool:
        """Регистрация реферала

        Args:
            referrer_id (int): ID пригласившего пользователя
            referred_id (int): ID приглашенного пользователя
            referral_code (str, optional): Реферальный код. По умолчанию None.

        Returns:
            bool: Успешность регистрации
        """
        session = self.db.get_session()

        # Проверяем, не зарегистрирован ли уже этот реферал
        existing = session.query(Referral).filter(
            Referral.referred_id == referred_id
        ).first()

        if existing:
            session.close()
            return False

        # Если передан код, находим ссылку
        referral_link_id = None
        if referral_code:
            referral_link = session.query(ReferralLink).filter(
                ReferralLink.code == referral_code,
                ReferralLink.is_active == True,
                ReferralLink.user_id == referrer_id
            ).first()

            if referral_link:
                referral_link_id = referral_link.id

                # Проверяем лимит использований
                if referral_link.max_uses and referral_link.current_uses >= referral_link.max_uses:
                    session.close()
                    return False

                # Увеличиваем счетчик использований
                referral_link.current_uses += 1
                session.commit()

        # Создаем запись о реферале
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            referral_link_id=referral_link_id
        )

        session.add(referral)
        session.commit()
        session.close()

        return True

    def calculate_referral_reward(self, payment_amount: float, referral: Referral) -> float:
        """Расчет вознаграждения за реферала

        Args:
            payment_amount (float): Сумма платежа
            referral (Referral): Объект реферала

        Returns:
            float: Сумма вознаграждения
        """
        session = self.db.get_session()

        # Получаем настройки реферальной ссылки, если она есть
        if referral.referral_link_id:
            referral_link = session.query(ReferralLink).filter(
                ReferralLink.id == referral.referral_link_id
            ).first()

            if referral_link:
                # Используем настройки из ссылки
                if referral_link.reward_percent > 0:
                    reward = payment_amount * (referral_link.reward_percent / 100)
                else:
                    reward = referral_link.reward_amount
            else:
                # Используем стандартные настройки (10%)
                reward = payment_amount * 0.1
        else:
            # Используем стандартные настройки (10%)
            reward = payment_amount * 0.1

        session.close()

        return reward

    def get_user_referrals(self, user_id: int) -> list:
        """Получение списка рефералов пользователя

        Args:
            user_id (int): ID пользователя

        Returns:
            list: Список рефералов
        """
        session = self.db.get_session()

        referrals = session.query(Referral).filter(
            Referral.referrer_id == user_id
        ).order_by(Referral.registered_at.desc()).all()

        session.close()

        return referrals

    def get_user_referral_stats(self, user_id: int) -> dict:
        """Получение статистики рефералов пользователя

        Args:
            user_id (int): ID пользователя

        Returns:
            dict: Статистика рефералов
        """
        session = self.db.get_session()

        # Общее количество рефералов
        total_referrals = session.query(Referral).filter(
            Referral.referrer_id == user_id
        ).count()

        # Количество активных рефералов (совершивших платеж)
        active_referrals = session.query(Referral).filter(
            Referral.referrer_id == user_id,
            Referral.has_made_payment == True
        ).count()

        # Общее вознаграждение
        total_reward = session.query(db.func.sum(Referral.total_referral_reward)).filter(
            Referral.referrer_id == user_id
        ).scalar() or 0

        # Рефералы за последние 30 дней
        month_ago = datetime.utcnow() - timedelta(days=30)
        recent_referrals = session.query(Referral).filter(
            Referral.referrer_id == user_id,
            Referral.registered_at >= month_ago
        ).count()

        session.close()

        return {
            "total_referrals": total_referrals,
            "active_referrals": active_referrals,
            "total_reward": total_reward,
            "recent_referrals": recent_referrals
        }

    def get_referral_links(self, user_id: int) -> list:
        """Получение реферальных ссылок пользователя

        Args:
            user_id (int): ID пользователя

        Returns:
            list: Список реферальных ссылок
        """
        session = self.db.get_session()

        links = session.query(ReferralLink).filter(
            ReferralLink.user_id == user_id
        ).order_by(ReferralLink.created_at.desc()).all()

        session.close()

        return links
