"""
Модуль для экспорта статистики в различные форматы
"""

import csv
import json
import io
from datetime import datetime, timedelta
import pandas as pd
from database import db, User, Payment, Service
from aiogram.types import InputFile


class ExportSystem:
    """Класс для экспорта статистики"""

    def __init__(self):
        self.db = db

    async def export_payments_csv(self, start_date: datetime = None, end_date: datetime = None) -> InputFile:
        """Экспорт платежей в CSV

        Args:
            start_date (datetime, optional): Начальная дата. По умолчанию None.
            end_date (datetime, optional): Конечная дата. По умолчанию None.

        Returns:
            InputFile: Файл CSV
        """
        session = self.db.get_session()

        # Формируем запрос
        query = session.query(Payment)

        if start_date:
            query = query.filter(Payment.created_at >= start_date)

        if end_date:
            query = query.filter(Payment.created_at <= end_date)

        payments = query.order_by(Payment.created_at.desc()).all()

        # Создаем CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)

        # Заголовки
        writer.writerow([
            'ID', 'User ID', 'Amount', 'Currency', 'Status',
            'Payment Provider', 'Provider Payment ID', 'Created At',
            'Completed At', 'Invoice Payload'
        ])

        # Данные
        for payment in payments:
            writer.writerow([
                payment.id,
                payment.user_id,
                payment.amount,
                payment.currency,
                payment.status,
                payment.payment_provider,
                payment.provider_payment_id or '',
                payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                payment.completed_at.strftime('%Y-%m-%d %H:%M:%S') if payment.completed_at else '',
                payment.invoice_payload or ''
            ])

        session.close()

        # Создаем файл для отправки
        csv_data = output.getvalue().encode('utf-8')
        file_obj = io.BytesIO(csv_data)

        filename = f"payments_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return InputFile(file_obj, filename=filename)

    async def export_payments_excel(self, start_date: datetime = None, end_date: datetime = None) -> InputFile:
        """Экспорт платежей в Excel

        Args:
            start_date (datetime, optional): Начальная дата. По умолчанию None.
            end_date (datetime, optional): Конечная дата. По умолчанию None.

        Returns:
            InputFile: Файл Excel
        """
        session = self.db.get_session()

        # Формируем запрос
        query = session.query(Payment)

        if start_date:
            query = query.filter(Payment.created_at >= start_date)

        if end_date:
            query = query.filter(Payment.created_at <= end_date)

        payments = query.order_by(Payment.created_at.desc()).all()

        # Подготавливаем данные
        data = []
        for payment in payments:
            data.append({
                'ID': payment.id,
                'User ID': payment.user_id,
                'Amount': payment.amount,
                'Currency': payment.currency,
                'Status': payment.status,
                'Payment Provider': payment.payment_provider,
                'Provider Payment ID': payment.provider_payment_id or '',
                'Created At': payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'Completed At': payment.completed_at.strftime('%Y-%m-%d %H:%M:%S') if payment.completed_at else '',
                'Invoice Payload': payment.invoice_payload or ''
            })

        session.close()

        # Создаем DataFrame
        df = pd.DataFrame(data)

        # Создаем Excel файл в памяти
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Payments', index=False)

            # Автоматически подгоняем ширину колонок
            worksheet = writer.sheets['Payments']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        filename = f"payments_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return InputFile(io.BytesIO(output.getvalue()), filename=filename)

    async def export_users_csv(self) -> InputFile:
        """Экспорт пользователей в CSV

        Returns:
            InputFile: Файл CSV
        """
        session = self.db.get_session()

        users = session.query(User).order_by(User.created_at.desc()).all()

        # Создаем CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)

        # Заголовки
        writer.writerow([
            'ID', 'Telegram ID', 'Username', 'First Name', 'Last Name',
            'Balance', 'Is Admin', 'Created At'
        ])

        # Данные
        for user in users:
            writer.writerow([
                user.id,
                user.telegram_id,
                user.username or '',
                user.first_name or '',
                user.last_name or '',
                user.balance,
                'Yes' if user.is_admin else 'No',
                user.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])

        session.close()

        # Создаем файл для отправки
        csv_data = output.getvalue().encode('utf-8')
        file_obj = io.BytesIO(csv_data)

        filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return InputFile(file_obj, filename=filename)

    async def export_statistics_json(self, days: int = 30) -> InputFile:
        """Экспорт статистики в JSON

        Args:
            days (int, optional): Количество дней для статистики. По умолчанию 30.

        Returns:
            InputFile: Файл JSON
        """
        session = self.db.get_session()

        start_date = datetime.utcnow() - timedelta(days=days)

        # Собираем статистику
        stats = {}

        # Общая статистика
        total_users = session.query(User).count()
        total_payments = session.query(Payment).count()
        total_revenue = session.query(db.func.sum(Payment.amount)).filter(
            Payment.status == "completed"
        ).scalar() or 0

        # Статистика за период
        recent_payments = session.query(Payment).filter(
            Payment.created_at >= start_date
        ).count()

        recent_revenue = session.query(db.func.sum(Payment.amount)).filter(
            Payment.created_at >= start_date,
            Payment.status == "completed"
        ).scalar() or 0

        # Новые пользователи за период
        new_users = session.query(User).filter(
            User.created_at >= start_date
        ).count()

        # Статистика по провайдерам платежей
        provider_stats = {}
        providers = session.query(
            Payment.payment_provider,
            db.func.count(Payment.id).label('count'),
            db.func.sum(Payment.amount).label('total')
        ).filter(
            Payment.status == "completed"
        ).group_by(Payment.payment_provider).all()

        for provider in providers:
            provider_stats[provider.payment_provider] = {
                'count': provider.count,
                'total': float(provider.total or 0)
            }

        # Статистика по услугам
        service_stats = {}
        services = session.query(Service).all()

        for service in services:
            service_payments = session.query(Payment).filter(
                Payment.invoice_payload.like(f"%{service.name}%"),
                Payment.status == "completed"
            ).all()

            service_stats[service.name] = {
                'price': service.price,
                'purchases': len(service_payments),
                'revenue': sum(p.amount for p in service_payments)
            }

        session.close()

        # Формируем JSON
        stats = {
            'export_date': datetime.now().isoformat(),
            'period_days': days,
            'period_start': start_date.isoformat(),
            'period_end': datetime.now().isoformat(),
            'total_statistics': {
                'total_users': total_users,
                'total_payments': total_payments,
                'total_revenue': total_revenue
            },
            'period_statistics': {
                'new_users': new_users,
                'recent_payments': recent_payments,
                'recent_revenue': recent_revenue
            },
            'payment_providers': provider_stats,
            'services': service_stats
        }

        # Создаем JSON файл
        json_data = json.dumps(stats, ensure_ascii=False, indent=2)
        file_obj = io.BytesIO(json_data.encode('utf-8'))

        filename = f"statistics_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        return InputFile(file_obj, filename=filename)

    async def export_detailed_report(self, report_type: str = "daily") -> InputFile:
        """Экспорт детализированного отчета

        Args:
            report_type (str, optional): Тип отчета (daily, weekly, monthly). По умолчанию "daily".

        Returns:
            InputFile: Файл отчета
        """
        session = self.db.get_session()

        # Определяем период в зависимости от типа отчета
        now = datetime.utcnow()

        if report_type == "daily":
            start_date = now - timedelta(days=1)
            date_format = "%Y-%m-%d"
        elif report_type == "weekly":
            start_date = now - timedelta(weeks=1)
            date_format = "%Y-%m-%d"
        elif report_type == "monthly":
            start_date = now - timedelta(days=30)
            date_format = "%Y-%m"
        else:
            start_date = now - timedelta(days=1)
            date_format = "%Y-%m-%d"

        # Собираем данные по дням
        daily_stats = []

        current_date = start_date
        while current_date <= now:
            next_date = current_date + timedelta(days=1)

            # Пользователи за день
            daily_users = session.query(User).filter(
                User.created_at >= current_date,
                User.created_at < next_date
            ).count()

            # Платежи за день
            daily_payments = session.query(Payment).filter(
                Payment.created_at >= current_date,
                Payment.created_at < next_date
            ).count()

            # Выручка за день
            daily_revenue = session.query(db.func.sum(Payment.amount)).filter(
                Payment.created_at >= current_date,
                Payment.created_at < next_date,
                Payment.status == "completed"
            ).scalar() or 0

            daily_stats.append({
                'date': current_date.strftime(date_format),
                'users': daily_users,
                'payments': daily_payments,
                'revenue': float(daily_revenue)
            })

            current_date = next_date

        session.close()

        # Создаем Excel отчет
        df = pd.DataFrame(daily_stats)

        # Добавляем итоги
        summary = {
            'date': 'ИТОГО',
            'users': df['users'].sum(),
            'payments': df['payments'].sum(),
            'revenue': df['revenue'].sum()
        }

        df_summary = pd.DataFrame([summary])
        df = pd.concat([df, df_summary], ignore_index=True)

        # Создаем Excel файл
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Report', index=False)

            # Добавляем график
            if len(daily_stats) > 1:
                from openpyxl.chart import LineChart, Reference

                workbook = writer.book
                worksheet = writer.sheets['Report']

                # Создаем график
                chart = LineChart()
                chart.title = f"{report_type.capitalize()} Revenue Trend"
                chart.style = 13
                chart.y_axis.title = 'Revenue'
                chart.x_axis.title = 'Date'

                # Данные для графика
                data = Reference(worksheet, min_col=4, min_row=2, max_row=len(daily_stats) + 1)
                categories = Reference(worksheet, min_col=1, min_row=2, max_row=len(daily_stats) + 1)

                chart.add_data(data, titles_from_data=True)
                chart.set_categories(categories)

                # Добавляем график на лист
                worksheet.add_chart(chart, "F2")

        filename = f"{report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return InputFile(io.BytesIO(output.getvalue()), filename=filename)
