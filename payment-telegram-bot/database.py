from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import config

Base = declarative_base()


class User(Base):
    """Модель пользователя"""

    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_admin = Column(Boolean, default=False)


class Payment(Base):
    """Модель платежа"""

    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    status = Column(String(50), default="pending")  # pending, completed, failed, cancelled
    payment_provider = Column(String(50))  # telegram, yookassa, etc.
    provider_payment_id = Column(String(100))  # ID платежа в платежной системе
    invoice_payload = Column(Text)  # Дополнительные данные
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Service(Base):
    """Модель услуги"""

    __tablename__ = 'services'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Database:
    """Класс для работы с базой данных"""

    def __init__(self, db_url=None):
        """Инициализация подключения к базе данных

        Args:
            db_url (str, optional): URL подключения к БД. По умолчанию берется из config.
        """
        self.db_url = db_url or config.Config.DATABASE_URL
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self):
        """Создание таблиц в базе данных"""
        Base.metadata.create_all(self.engine)

    def get_session(self):
        """Получение сессии базы данных

        Returns:
            Session: Сессия SQLAlchemy
        """
        return self.SessionLocal()


# Инициализация базы данных
db = Database()
db.init_db()
