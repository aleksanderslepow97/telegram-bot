import logging

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

import config
from admin_notifications import AdminNotifier
from database import db, Service
from export_system import ExportSystem
from keyboards import (
    get_referral_keyboard, get_currency_keyboard,
    get_subscription_keyboard
)
from multi_currency import CurrencyConverter, SupportedCurrency
from payment_system import PaymentManager
from promo_system import PromoSystem
from referral_system import ReferralSystem
from subscription_system import SubscriptionSystem, SubscriptionStatus

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=config.Config.BOT_TOKEN)

# Используем Redis для хранения состояний, если он доступен
try:
    storage = RedisStorage2(config.Config.REDIS_URL)
except:
    storage = MemoryStorage()

dp = Dispatcher(bot, storage=storage)

# Инициализация всех систем
payment_manager = PaymentManager(bot)
admin_notifier = AdminNotifier(bot)
referral_system = ReferralSystem()
promo_system = PromoSystem()
subscription_system = SubscriptionSystem(bot)
currency_converter = CurrencyConverter()
export_system = ExportSystem()


# Состояния FSM
class PaymentStates(StatesGroup):
    """Состояния для процесса оплаты"""
    waiting_for_amount = State()
    waiting_for_payment_method = State()
    waiting_for_custom_amount = State()
    waiting_for_promo_code = State()


class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_service_name = State()
    waiting_for_service_description = State()
    waiting_for_service_price = State()
    waiting_for_promo_code = State()
    waiting_for_promo_discount = State()
    waiting_for_currency_code = State()
    waiting_for_currency_name = State()


class ReferralStates(StatesGroup):
    """Состояния для реферальной системы"""
    waiting_for_referral_code = State()


# Новые обработчики команд для расширенной функциональности

@dp.message_handler(commands=['referral'])
async def cmd_referral(message: types.Message):
    """Обработчик команды /referral"""
    user = await get_or_create_user(message.from_user)

    # Получаем статистику рефералов
    stats = referral_system.get_user_referral_stats(user.id)

    # Получаем реферальные ссылки
    links = referral_system.get_referral_links(user.id)

    text = (
        f"👥 *Реферальная система*\n\n"
        f"*Всего рефералов:* {stats['total_referrals']}\n"
        f"*Активных рефералов:* {stats['active_referrals']}\n"
        f"*Рефералов за 30 дней:* {stats['recent_referrals']}\n"
        f"*Общее вознаграждение:* {stats['total_reward']:.2f} RUB\n\n"
        f"За каждого приглашенного друга вы получаете {config.Config.REFERRAL_REWARD_PERCENT}% от его первого платежа!"
    )

    keyboard = get_referral_keyboard(links)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.message_handler(commands=['promo'])
async def cmd_promo(message: types.Message):
    """Обработчик команды /promo"""
    user = await get_or_create_user(message.from_user)

    text = (
        "🎫 *Промокоды и скидки*\n\n"
        "Введите промокод для получения скидки:\n"
        "Или используйте команду /promo_apply [код]"
    )

    await message.answer(text, parse_mode="Markdown")
    await PaymentStates.waiting_for_promo_code.set()


@dp.message_handler(commands=['subscription'])
async def cmd_subscription(message: types.Message):
    """Обработчик команды /subscription"""
    user = await get_or_create_user(message.from_user)

    session = db.get_session()
    plans = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.is_active == True
    ).all()

    # Проверяем текущую подписку пользователя
    current_subscription = session.query(UserSubscription).filter(
        UserSubscription.user_id == user.id,
        UserSubscription.status == SubscriptionStatus.ACTIVE
    ).first()

    session.close()

    if current_subscription:
        plan = current_subscription.plan
        text = (
            f"✅ *Ваша текущая подписка*\n\n"
            f"*План:* {plan.name}\n"
            f"*Цена:* {plan.price:.2f} {plan.currency}\n"
            f"*Статус:* {current_subscription.status.value}\n"
            f"*Следующий платеж:* {current_subscription.next_billing_date.strftime('%d.%m.%Y')}\n"
            f"*Автопродление:* {'Включено' if current_subscription.auto_renewal else 'Выключено'}"
        )
    else:
        text = "🛒 *Доступные подписки*\n\nВыберите план подписки:"

    keyboard = get_subscription_keyboard(plans, current_subscription)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.message_handler(commands=['currency'])
async def cmd_currency(message: types.Message):
    """Обработчик команды /currency"""
    user = await get_or_create_user(message.from_user)

    currencies = await currency_converter.get_supported_currencies()
    default_currency = await currency_converter.get_default_currency()

    text = (
        "💰 *Настройки валюты*\n\n"
        f"*Текущая валюта по умолчанию:* {default_currency.code if default_currency else 'RUB'}\n\n"
        "Выберите валюту для отображения цен:"
    )

    keyboard = get_currency_keyboard(currencies)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.message_handler(commands=['export'])
async def cmd_export(message: types.Message):
    """Обработчик команды /export (только для администраторов)"""
    user = await get_or_create_user(message.from_user)

    if not user.is_admin:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 CSV платежей", callback_data="export_payments_csv"),
        InlineKeyboardButton("📊 Excel платежей", callback_data="export_payments_excel"),
        InlineKeyboardButton("👥 CSV пользователей", callback_data="export_users_csv"),
        InlineKeyboardButton("📈 JSON статистика", callback_data="export_statistics_json"),
        InlineKeyboardButton("📋 Детальный отчет", callback_data="export_detailed_report"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_export")
    )

    await message.answer("📤 *Экспорт данных*\n\nВыберите формат экспорта:",
                         parse_mode="Markdown", reply_markup=keyboard)


# Новые обработчики колбэков для расширенной функциональности

@dp.callback_query_handler(lambda c: c.data.startswith('referral_'))
async def process_referral_callback(callback_query: types.CallbackQuery):
    """Обработчик колбэков реферальной системы"""
    action = callback_query.data.split('_')[1]

    if action == 'create':
        # Создание новой реферальной ссылки
        user = await get_or_create_user(callback_query.from_user)

        try:
            referral_link = referral_system.generate_referral_code(user.id)

            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(
                callback_query.from_user.id,
                f"✅ *Новая реферальная ссылка создана!*\n\n"
                f"*Код:* `{referral_link.code}`\n"
                f"*Ссылка:* {referral_link.link}\n"
                f"*Срок действия:* {referral_link.expires_at.strftime('%d.%m.%Y')}\n"
                f"*Максимум использований:* {referral_link.max_uses or '∞'}\n\n"
                f"Поделитесь этой ссылкой с друзьями и получайте {config.Config.REFERRAL_REWARD_PERCENT}% от их первого платежа!",
                parse_mode="Markdown"
            )
        except Exception as e:
            await bot.answer_callback_query(callback_query.id, "Ошибка создания ссылки")

    elif action == 'stats':
        # Показать статистику
        user = await get_or_create_user(callback_query.from_user)
        stats = referral_system.get_user_referral_stats(user.id)

        text = (
            f"📊 *Статистика рефералов*\n\n"
            f"*Всего рефералов:* {stats['total_referrals']}\n"
            f"*Активных рефералов:* {stats['active_referrals']}\n"
            f"*Рефералов за 30 дней:* {stats['recent_referrals']}\n"
            f"*Общее вознаграждение:* {stats['total_reward']:.2f} RUB"
        )

        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id, text, parse_mode="Markdown")


@dp.callback_query_handler(lambda c: c.data.startswith('promo_'))
async def process_promo_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик колбэков промокодов"""
    action = callback_query.data.split('_')[1]

    if action == 'apply':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "Введите промокод:"
        )
        await PaymentStates.waiting_for_promo_code.set()

    elif action == 'check':
        # Проверка промокода (админ)
        user = await get_or_create_user(callback_query.from_user)

        if not user.is_admin:
            await bot.answer_callback_query(callback_query.id, "Нет доступа")
            return

        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "Введите промокод для проверки:"
        )
        await AdminStates.waiting_for_promo_code.set()


@dp.callback_query_handler(lambda c: c.data.startswith('subscription_'))
async def process_subscription_callback(callback_query: types.CallbackQuery):
    """Обработчик колбэков подписок"""
    data_parts = callback_query.data.split('_')

    if len(data_parts) < 2:
        return

    action = data_parts[1]

    if action == 'buy':
        # Покупка подписки
        if len(data_parts) < 3:
            return

        plan_id = int(data_parts[2])
        user = await get_or_create_user(callback_query.from_user)

        subscription = subscription_system.subscribe_user(user.id, plan_id)

        if subscription:
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(
                callback_query.from_user.id,
                f"✅ *Подписка оформлена!*\n\n"
                f"Следующий платеж: {subscription.next_billing_date.strftime('%d.%m.%Y')}\n"
                f"Сумма: {subscription.plan.price:.2f} {subscription.plan.currency}",
                parse_mode="Markdown"
            )
        else:
            await bot.answer_callback_query(callback_query.id, "Ошибка оформления подписки")

    elif action == 'cancel':
        # Отмена подписки
        if len(data_parts) < 3:
            return

        subscription_id = int(data_parts[2])
        user = await get_or_create_user(callback_query.from_user)

        success = subscription_system.cancel_subscription(user.id, subscription_id)

        if success:
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(
                callback_query.from_user.id,
                "✅ *Подписка отменена!*\n\nВы можете возобновить ее в любое время."
            )
        else:
            await bot.answer_callback_query(callback_query.id, "Ошибка отмены подписки")


@dp.callback_query_handler(lambda c: c.data.startswith('export_'))
async def process_export_callback(callback_query: types.CallbackQuery):
    """Обработчик колбэков экспорта"""
    data_parts = callback_query.data.split('_')

    if len(data_parts) < 2:
        return

    export_type = data_parts[1]

    if export_type == 'cancel':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "Экспорт отменен."
        )
        return

    user = await get_or_create_user(callback_query.from_user)

    if not user.is_admin:
        await bot.answer_callback_query(callback_query.id, "Нет доступа")
        return

    await bot.answer_callback_query(callback_query.id, "Готовлю файл...")

    try:
        if export_type == 'payments_csv':
            file = await export_system.export_payments_csv()
            await bot.send_document(callback_query.from_user.id, file)

        elif export_type == 'payments_excel':
            file = await export_system.export_payments_excel()
            await bot.send_document(callback_query.from_user.id, file)

        elif export_type == 'users_csv':
            file = await export_system.export_users_csv()
            await bot.send_document(callback_query.from_user.id, file)

        elif export_type == 'statistics_json':
            file = await export_system.export_statistics_json()
            await bot.send_document(callback_query.from_user.id, file)

        elif export_type == 'detailed_report':
            file = await export_system.export_detailed_report()
            await bot.send_document(callback_query.from_user.id, file)

    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        await bot.send_message(
            callback_query.from_user.id,
            f"❌ Ошибка при экспорте: {str(e)}"
        )


# Обновленная функция запуска бота
async def on_startup(dp):
    """Функция, выполняемая при запуске бота"""
    logger.info("Бот запущен")

    # Создаем таблицы в базе данных
    from database import Base
    Base.metadata.create_all(db.engine)

    # Инициализируем поддерживаемые валюты
    await init_currencies()

    # Создаем тестовые данные, если их нет
    await create_sample_data()

    # Запускаем фоновые задачи
    await subscription_system.start_background_tasks()

    # Отправляем уведомление админам о запуске
    for admin_id in config.Config.ADMINS:
        try:
            await bot.send_message(
                admin_id,
                "✅ Бот запущен и готов к работе!"
            )
        except:
            pass


async def on_shutdown(dp):
    """Функция, выполняемая при выключении бота"""
    logger.info("Бот выключается")

    # Останавливаем фоновые задачи
    if subscription_system._task:
        subscription_system._task.cancel()

    await dp.storage.close()
    await dp.storage.wait_closed()


async def init_currencies():
    """Инициализация поддерживаемых валют"""
    session = db.get_session()

    # Проверяем, есть ли уже валюты
    if session.query(SupportedCurrency).count() == 0:
        currencies = [
            ("RUB", "Российский рубль", "₽", 2, True),
            ("USD", "Доллар США", "$", 2, False),
            ("EUR", "Евро", "€", 2, False),
            ("KZT", "Казахстанский тенге", "₸", 2, False),
            ("UAH", "Украинская гривна", "₴", 2, False)
        ]

        for code, name, symbol, decimal_places, is_default in currencies:
            currency = SupportedCurrency(
                code=code,
                name=name,
                symbol=symbol,
                decimal_places=decimal_places,
                is_default=is_default
            )
            session.add(currency)

        session.commit()
        logger.info("Инициализированы поддерживаемые валюты")

    session.close()


async def create_sample_data():
    """Создание тестовых данных"""
    session = db.get_session()

    # Создаем тестовые услуги
    if session.query(Service).count() == 0:
        services = [
            Service(
                name="Базовая подписка",
                description="Доступ к базовым функциям на 30 дней",
                price=299.0,
                currency="RUB"
            ),
            Service(
                name="Премиум подписка",
                description="Доступ ко всем функциям на 30 дней",
                price=999.0,
                currency="RUB"
            ),
            Service(
                name="Разовая консультация",
                description="Консультация со специалистом (60 минут)",
                price=1500.0,
                currency="RUB"
            )
        ]
        for service in services:
            session.add(service)

        session.commit()
        logger.info("Созданы тестовые услуги")

    # Создаем тестовые планы подписок
    if session.query(SubscriptionPlan).count() == 0:
        from subscription_system import SubscriptionPlan

        plans = [
            SubscriptionPlan(
                name="Месячная подписка",
                description="Полный доступ ко всем функциям на 30 дней",
                price=990.0,
                currency="RUB",
                billing_cycle_days=30,
                trial_period_days=7,
                features=json.dumps(["Доступ к базовым функциям", "Техническая поддержка", "Обновления"])
            ),
            SubscriptionPlan(
                name="Годовая подписка",
                description="Полный доступ ко всем функциям на 365 дней (экономия 20%)",
                price=9500.0,
                currency="RUB",
                billing_cycle_days=365,
                features=json.dumps(
                    ["Доступ ко всем функциям", "Приоритетная поддержка", "Ранний доступ к новым функциям"])
            )
        ]
        for plan in plans:
            session.add(plan)

        session.commit()
        logger.info("Созданы тестовые планы подписок")

    session.close()


if __name__ == '__main__':
    # Валидация конфигурации
    try:
        config.Config.validate()
    except ValueError as e:
        logger.error(str(e))
        exit(1)

    # Запуск бота
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
