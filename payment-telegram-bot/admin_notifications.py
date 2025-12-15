"""
Модуль для отправки уведомлений администраторам о важных событиях
"""

from datetime import datetime, timedelta
from database import db, User, Payment, Service
from aiogram import Bot
import config


class AdminNotifier:
    """Класс для управления уведомлениями администраторам"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.last_notification_time = {}

    async def notify_new_payment(self, payment: Payment, user: User):
        """Уведомление о новом платеже

        Args:
            payment (Payment): Объект платежа
            user (User): Объект пользователя
        """
        if not config.Config.ADMINS:
            return

        payment_time = payment.created_at.strftime('%d.%m.%Y %H:%M')

        message = (
            "💰 *НОВЫЙ ПЛАТЕЖ*\n\n"
            f"*ID платежа:* `{payment.id}`\n"
            f"*Пользователь:* {user.first_name} {user.last_name or ''}\n"
            f"*Username:* @{user.username or 'нет'}\n"
            f"*User ID:* `{user.id}`\n"
            f"*Telegram ID:* `{user.telegram_id}`\n"
            f"*Сумма:* {payment.amount:.2f} {payment.currency}\n"
            f"*Провайдер:* {payment.payment_provider}\n"
            f"*Время:* {payment_time}\n"
            f"*Статус:* {payment.status}"
        )

        for admin_id in config.Config.ADMINS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления админу {admin_id}: {e}")

    async def notify_large_payment(self, payment: Payment, user: User, threshold: float = 5000):
        """Уведомление о крупном платеже

        Args:
            payment (Payment): Объект платежа
            user (User): Объект пользователя
            threshold (float): Порог крупного платежа
        """
        if payment.amount < threshold:
            return

        message = (
            "⚠️ *КРУПНЫЙ ПЛАТЕЖ*\n\n"
            f"*Сумма:* {payment.amount:.2f} {payment.currency}\n"
            f"*Пользователь:* {user.first_name} {user.last_name or ''}\n"
            f"*User ID:* `{user.id}`\n"
            f"*Время:* {payment.created_at.strftime('%d.%m.%Y %H:%M')}"
        )

        for admin_id in config.Config.ADMINS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления админу {admin_id}: {e}")

    async def notify_new_user(self, user: User):
        """Уведомление о новом пользователе

        Args:
            user (User): Объект пользователя
        """
        if not config.Config.ADMINS:
            return

        # Проверяем, чтобы не спамить уведомлениями
        user_key = f"new_user_{user.id}"
        now = datetime.now()

        if user_key in self.last_notification_time:
            if now - self.last_notification_time[user_key] < timedelta(minutes=5):
                return

        self.last_notification_time[user_key] = now

        message = (
            "👤 *НОВЫЙ ПОЛЬЗОВАТЕЛЬ*\n\n"
            f"*Имя:* {user.first_name} {user.last_name or ''}\n"
            f"*Username:* @{user.username or 'нет'}\n"
            f"*Telegram ID:* `{user.telegram_id}`\n"
            f"*Время регистрации:* {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"*Реферал:* {'Да' if user.referred_by else 'Нет'}"
        )

        for admin_id in config.Config.ADMINS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления админу {admin_id}: {e}")

    async def notify_suspicious_activity(self, user: User, activity_type: str, details: str = ""):
        """Уведомление о подозрительной активности

        Args:
            user (User): Объект пользователя
            activity_type (str): Тип активности
            details (str): Детали активности
        """
        message = (
            "🚨 *ПОДОЗРИТЕЛЬНАЯ АКТИВНОСТЬ*\n\n"
            f"*Тип:* {activity_type}\n"
            f"*Пользователь:* {user.first_name} {user.last_name or ''}\n"
            f"*Username:* @{user.username or 'нет'}\n"
            f"*Telegram ID:* `{user.telegram_id}`\n"
            f"*Детали:* {details}"
        )

        for admin_id in config.Config.ADMINS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления админу {admin_id}: {e}")

    async def send_daily_report(self):
        """Отправка ежедневного отчета администраторам"""
        session = db.get_session()

        # Статистика за последние 24 часа
        yesterday = datetime.now() - timedelta(days=1)

        # Новые пользователи
        new_users = session.query(User).filter(User.created_at >= yesterday).count()

        # Новые платежи
        new_payments = session.query(Payment).filter(Payment.created_at >= yesterday).count()

        # Успешные платежи
        successful_payments = session.query(Payment).filter(
            Payment.created_at >= yesterday,
            Payment.status == "completed"
        ).count()

        # Общая выручка
        revenue = session.query(db.func.sum(Payment.amount)).filter(
            Payment.created_at >= yesterday,
            Payment.status == "completed"
        ).scalar() or 0

        # Популярные услуги
        from sqlalchemy import func
        popular_services = session.query(
            Payment.invoice_payload,
            func.count(Payment.id).label('count')
        ).filter(
            Payment.created_at >= yesterday,
            Payment.status == "completed"
        ).group_by(Payment.invoice_payload).order_by(func.count(Payment.id).desc()).limit(5).all()

        session.close()

        report_date = datetime.now().strftime('%d.%m.%Y')

        message = (
            f"📊 *ЕЖЕДНЕВНЫЙ ОТЧЕТ ({report_date})*\n\n"
            f"*Новые пользователи:* {new_users}\n"
            f"*Новые платежи:* {new_payments}\n"
            f"*Успешные платежи:* {successful_payments}\n"
            f"*Общая выручка:* {revenue:.2f} RUB\n\n"
            "*Топ-5 популярных услуг:*\n"
        )

        for i, (service_name, count) in enumerate(popular_services, 1):
            message += f"{i}. {service_name}: {count} покупок\n"

        for admin_id in config.Config.ADMINS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки отчета админу {admin_id}: {e}")

    async def notify_service_purchased(self, payment: Payment, user: User, service: Service):
        """Уведомление о покупке услуги

        Args:
            payment (Payment): Объект платежа
            user (User): Объект пользователя
            service (Service): Объект услуги
        """
        message = (
            "🛒 *ПОКУПКА УСЛУГИ*\n\n"
            f"*Услуга:* {service.name}\n"
            f"*Цена:* {service.price:.2f} {service.currency}\n"
            f"*Пользователь:* {user.first_name} {user.last_name or ''}\n"
            f"*Username:* @{user.username or 'нет'}\n"
            f"*User ID:* `{user.id}`\n"
            f"*Время:* {payment.created_at.strftime('%d.%m.%Y %H:%M')}"
        )

        for admin_id in config.Config.ADMINS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка отправки уведомления админу {admin_id}: {e}")
