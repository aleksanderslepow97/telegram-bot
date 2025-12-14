import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ContentType, PreCheckoutQuery, LabeledPrice
from aiogram.utils import executor
import config
from database import db, User, Payment, Service
from keyboards import (
    get_main_keyboard, get_admin_keyboard,
    get_payment_amount_keyboard, get_payment_method_keyboard,
    get_services_keyboard, get_admin_services_keyboard
)
from payment_system import PaymentManager

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

# Инициализация менеджера платежей
payment_manager = PaymentManager(bot)


# Состояния FSM
class PaymentStates(StatesGroup):
    """Состояния для процесса оплаты"""
    waiting_for_amount = State()
    waiting_for_payment_method = State()
    waiting_for_custom_amount = State()


class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_service_name = State()
    waiting_for_service_description = State()
    waiting_for_service_price = State()


# Вспомогательные функции
async def get_or_create_user(telegram_user: types.User):
    """Получение или создание пользователя в базе данных

    Args:
        telegram_user (types.User): Объект пользователя из Telegram

    Returns:
        User: Объект пользователя из базы данных
    """
    session = db.get_session()
    user = session.query(User).filter(User.telegram_id == telegram_user.id).first()

    if not user:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            is_admin=telegram_user.id in config.Config.ADMINS
        )
        session.add(user)
        session.commit()

    session.close()
    return user


async def update_user_balance(user_id: int, amount: float):
    """Обновление баланса пользователя

    Args:
        user_id (int): ID пользователя
        amount (float): Сумма для пополнения (может быть отрицательной)

    Returns:
        bool: Успешность операции
    """
    try:
        session = db.get_session()
        user = session.query(User).filter(User.telegram_id == user_id).first()

        if user:
            user.balance += amount
            session.commit()
            session.close()
            return True

        session.close()
        return False
    except Exception as e:
        logger.error(f"Ошибка обновления баланса: {e}")
        return False


# Обработчики команд
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработчик команды /start

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я — бот для оплаты услуг. Вот что я умею:\n\n"
        f"💳 Пополнить баланс — пополните ваш внутренний счет\n"
        f"🛒 Услуги — просмотр и покупка доступных услуг\n"
        f"💰 Мой баланс — проверка текущего баланса\n"
        f"📊 История платежей — просмотр ваших транзакций\n"
        f"🆘 Помощь — справка по использованию бота\n\n"
        f"Ваш ID: {user.id}\n"
        f"Ваш баланс: {user.balance:.2f} RUB"
    )

    if user.is_admin:
        welcome_text += "\n\n👑 Вы администратор бота!"

    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    """Обработчик команды /admin (только для администраторов)

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    if not user.is_admin:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    admin_text = (
        f"👑 Админ-панель\n\n"
        f"ID: {user.id}\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"Баланс: {user.balance:.2f} RUB\n\n"
        f"Выберите действие:"
    )

    await message.answer(admin_text, reply_markup=get_admin_keyboard())


@dp.message_handler(text="💳 Пополнить баланс")
async def cmd_deposit(message: types.Message):
    """Обработчик кнопки пополнения баланса

    Args:
        message (types.Message): Сообщение от пользователя
    """
    await message.answer(
        "💳 Выберите сумму для пополнения баланса:",
        reply_markup=get_payment_amount_keyboard()
    )


@dp.message_handler(text="💰 Мой баланс")
async def cmd_balance(message: types.Message):
    """Обработчик кнопки проверки баланса

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    balance_text = (
        f"💰 Ваш баланс: {user.balance:.2f} RUB\n\n"
        f"ID пользователя: {user.id}\n"
        f"Telegram ID: {user.telegram_id}"
    )

    await message.answer(balance_text)


@dp.message_handler(text="🛒 Услуги")
async def cmd_services(message: types.Message):
    """Обработчик кнопки просмотра услуг

    Args:
        message (types.Message): Сообщение от пользователя
    """
    session = db.get_session()
    services = session.query(Service).filter(Service.is_active == True).all()
    session.close()

    if not services:
        await message.answer("😔 На данный момент услуги отсутствуют.")
        return

    services_text = "🛒 Доступные услуги:\n\n"
    for service in services:
        services_text += f"• {service.name}\n"
        services_text += f"  Описание: {service.description}\n"
        services_text += f"  Цена: {service.price:.2f} {service.currency}\n\n"

    await message.answer(services_text, reply_markup=get_services_keyboard(services))


@dp.message_handler(text="📊 История платежей")
async def cmd_payment_history(message: types.Message):
    """Обработчик кнопки истории платежей

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    session = db.get_session()
    payments = session.query(Payment).filter(
        Payment.user_id == user.id
    ).order_by(Payment.created_at.desc()).limit(10).all()
    session.close()

    if not payments:
        await message.answer("📊 У вас пока нет платежей.")
        return

    history_text = "📊 История ваших платежей:\n\n"
    for payment in payments:
        status_emoji = {
            "pending": "⏳",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫"
        }.get(payment.status, "❓")

        history_text += f"{status_emoji} {payment.amount:.2f} {payment.currency}\n"
        history_text += f"  Дата: {payment.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        history_text += f"  Статус: {payment.status}\n"
        if payment.completed_at:
            history_text += f"  Завершен: {payment.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
        history_text += "\n"

    await message.answer(history_text)


@dp.message_handler(text="🆘 Помощь")
async def cmd_help(message: types.Message):
    """Обработчик кнопки помощи

    Args:
        message (types.Message): Сообщение от пользователя
    """
    help_text = (
        "🆘 Помощь по использованию бота:\n\n"
        "💳 Пополнить баланс — пополнение вашего внутреннего счета\n"
        "🛒 Услуги — просмотр и покупка доступных услуг\n"
        "💰 Мой баланс — проверка текущего баланса\n"
        "📊 История платежей — просмотр ваших транзакций\n\n"
        "Для пополнения баланса:\n"
        "1. Нажмите '💳 Пополнить баланс'\n"
        "2. Выберите сумму или введите свою\n"
        "3. Выберите способ оплаты\n"
        "4. Оплатите счет\n\n"
        "Для покупки услуги:\n"
        "1. Нажмите '🛒 Услуги'\n"
        "2. Выберите нужную услугу\n"
        "3. Оплатите счет\n\n"
        "Если у вас возникли проблемы, обратитесь к администратору."
    )

    await message.answer(help_text)


# Обработчики админ-панели
@dp.message_handler(text="📊 Статистика")
async def cmd_admin_stats(message: types.Message):
    """Обработчик кнопки статистики (админ)

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    if not user.is_admin:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    session = db.get_session()

    # Статистика пользователей
    total_users = session.query(User).count()
    new_users_today = session.query(User).filter(
        db.func.date(User.created_at) == db.func.date('now')
    ).count()

    # Статистика платежей
    total_payments = session.query(Payment).count()
    completed_payments = session.query(Payment).filter(Payment.status == "completed").count()
    total_revenue = session.query(db.func.sum(Payment.amount)).filter(
        Payment.status == "completed"
    ).scalar() or 0

    # Статистика услуг
    total_services = session.query(Service).count()
    active_services = session.query(Service).filter(Service.is_active == True).count()

    session.close()

    stats_text = (
        "📊 Статистика бота:\n\n"
        f"👥 Пользователи:\n"
        f"  Всего: {total_users}\n"
        f"  Новых сегодня: {new_users_today}\n\n"
        f"💳 Платежи:\n"
        f"  Всего: {total_payments}\n"
        f"  Успешных: {completed_payments}\n"
        f"  Общая выручка: {total_revenue:.2f} RUB\n\n"
        f"🛒 Услуги:\n"
        f"  Всего: {total_services}\n"
        f"  Активных: {active_services}"
    )

    await message.answer(stats_text)


@dp.message_handler(text="👥 Пользователи")
async def cmd_admin_users(message: types.Message):
    """Обработчик кнопки управления пользователями (админ)

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    if not user.is_admin:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    session = db.get_session()
    users = session.query(User).order_by(User.created_at.desc()).limit(10).all()
    session.close()

    users_text = "👥 Последние 10 пользователей:\n\n"
    for user_item in users:
        users_text += f"ID: {user_item.id}\n"
        users_text += f"  Telegram: @{user_item.username or 'нет'}\n"
        users_text += f"  Имя: {user_item.first_name or ''} {user_item.last_name or ''}\n"
        users_text += f"  Баланс: {user_item.balance:.2f} RUB\n"
        users_text += f"  Регистрация: {user_item.created_at.strftime('%d.%m.%Y')}\n"
        users_text += f"  Админ: {'Да' if user_item.is_admin else 'Нет'}\n\n"

    await message.answer(users_text)


@dp.message_handler(text="💼 Управление услугами")
async def cmd_admin_services(message: types.Message):
    """Обработчик кнопки управления услугами (админ)

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    if not user.is_admin:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    session = db.get_session()
    services = session.query(Service).order_by(Service.created_at.desc()).all()
    session.close()

    if not services:
        await message.answer("😔 Услуги отсутствуют.")
        return

    await message.answer(
        "💼 Управление услугами:\n\nВыберите услугу для редактирования:",
        reply_markup=get_admin_services_keyboard(services)
    )


@dp.message_handler(text="💳 Платежи")
async def cmd_admin_payments(message: types.Message):
    """Обработчик кнопки управления платежами (админ)

    Args:
        message (types.Message): Сообщение от пользователя
    """
    user = await get_or_create_user(message.from_user)

    if not user.is_admin:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    session = db.get_session()
    payments = session.query(Payment).order_by(Payment.created_at.desc()).limit(10).all()
    session.close()

    payments_text = "💳 Последние 10 платежей:\n\n"
    for payment in payments:
        status_emoji = {
            "pending": "⏳",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫"
        }.get(payment.status, "❓")

        payments_text += f"{status_emoji} Платеж #{payment.id}\n"
        payments_text += f"  Пользователь: {payment.user_id}\n"
        payments_text += f"  Сумма: {payment.amount:.2f} {payment.currency}\n"
        payments_text += f"  Статус: {payment.status}\n"
        payments_text += f"  Дата: {payment.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"

    await message.answer(payments_text)


@dp.message_handler(text="🔙 В меню")
async def cmd_back_to_menu(message: types.Message):
    """Обработчик кнопки возврата в меню

    Args:
        message (types.Message): Сообщение от пользователя
    """
    await cmd_start(message)


# Обработчики колбэков
@dp.callback_query_handler(lambda c: c.data.startswith('pay_'))
async def process_payment_amount(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора суммы платежа

    Args:
        callback_query (types.CallbackQuery): Колбэк-запрос
        state (FSMContext): Состояние FSM
    """
    if callback_query.data == 'custom_amount':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "💳 Введите сумму для пополнения (в RUB):"
        )
        await PaymentStates.waiting_for_custom_amount.set()
        return

    if callback_query.data == 'cancel':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "❌ Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        await state.finish()
        return

    amount = float(callback_query.data.split('_')[1])

    # Сохраняем сумму в состоянии
    await state.update_data(amount=amount)

    # Показываем выбор метода оплаты
    providers = payment_manager.get_available_providers()

    if not providers:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "😔 На данный момент оплата недоступна. Попробуйте позже."
        )
        return

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"💳 Вы выбрали сумму: {amount} RUB\n\nВыберите способ оплаты:",
        reply_markup=get_payment_method_keyboard(amount)
    )

    await PaymentStates.waiting_for_payment_method.set()


@dp.callback_query_handler(lambda c: c.data.startswith('payment_method_'))
async def process_payment_method(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора метода оплаты

    Args:
        callback_query (types.CallbackQuery): Колбэк-запрос
        state (FSMContext): Состояние FSM
    """
    if callback_query.data == 'cancel':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "❌ Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        await state.finish()
        return

    # Получаем метод оплаты и сумму
    data_parts = callback_query.data.split('_')
    provider = data_parts[2]
    amount = float(data_parts[3])

    user = await get_or_create_user(callback_query.from_user)

    await bot.answer_callback_query(callback_query.id)

    # Создаем платеж
    payment_data = await payment_manager.create_payment(
        provider=provider,
        user_id=user.id,
        amount=amount,
        currency="RUB",
        description="Пополнение баланса"
    )

    if not payment_data:
        await bot.send_message(
            callback_query.from_user.id,
            "😔 Произошла ошибка при создании платежа. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        await state.finish()
        return

    # Обрабатываем разные типы платежей
    if provider == "telegram":
        # Отправляем инвойс для Telegram Payments
        prices = [LabeledPrice(label="Пополнение баланса", amount=int(amount * 100))]

        await bot.send_invoice(
            chat_id=callback_query.from_user.id,
            title="Пополнение баланса",
            description=f"Пополнение баланса на сумму {amount} RUB",
            payload=payment_data["payload"],
            provider_token=config.Config.PAYMENT_PROVIDER_TOKEN,
            currency="RUB",
            prices=prices,
            start_parameter="payment",
            need_name=False,
            need_email=False,
            need_phone_number=False,
            need_shipping_address=False,
            is_flexible=False
        )

    elif provider == "yookassa":
        # Отправляем ссылку для оплаты через ЮKassa
        payment_text = (
            f"💳 Оплата через ЮKassa\n\n"
            f"Сумма: {amount} RUB\n"
            f"ID платежа: {payment_data['payment_id']}\n\n"
            f"Для оплаты перейдите по ссылке:\n"
            f"{payment_data['confirmation_url']}\n\n"
            f"После оплаты статус платежа обновится автоматически."
        )

        await bot.send_message(
            callback_query.from_user.id,
            payment_text,
            reply_markup=get_main_keyboard()
        )

    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith('service_'))
async def process_service_selection(callback_query: types.CallbackQuery):
    """Обработчик выбора услуги

    Args:
        callback_query (types.CallbackQuery): Колбэк-запрос
    """
    if callback_query.data == 'cancel':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "❌ Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        return

    service_id = int(callback_query.data.split('_')[1])

    session = db.get_session()
    service = session.query(Service).filter(Service.id == service_id).first()
    user = await get_or_create_user(callback_query.from_user)
    session.close()

    if not service:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "😔 Услуга не найдена.",
            reply_markup=get_main_keyboard()
        )
        return

    if user.balance < service.price:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            f"❌ Недостаточно средств на балансе.\n\n"
            f"Стоимость услуги: {service.price:.2f} RUB\n"
            f"Ваш баланс: {user.balance:.2f} RUB\n\n"
            f"Пополните баланс для покупки услуги."
        )
        return

    # Списываем средства
    success = await update_user_balance(user.telegram_id, -service.price)

    if success:
        # Создаем запись о покупке
        session = db.get_session()
        payment = Payment(
            user_id=user.id,
            amount=service.price,
            currency=service.currency,
            status="completed",
            payment_provider="internal",
            invoice_payload=f"Покупка услуги: {service.name}"
        )
        session.add(payment)
        session.commit()
        session.close()

        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            f"✅ Услуга '{service.name}' успешно приобретена!\n\n"
            f"💳 С вашего счета списано: {service.price:.2f} RUB\n"
            f"💰 Текущий баланс: {user.balance - service.price:.2f} RUB\n\n"
            f"Описание услуги:\n{service.description}",
            reply_markup=get_main_keyboard()
        )
    else:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.from_user.id,
            "😔 Произошла ошибка при покупке услуги. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )


# Обработчики сообщений для состояний FSM
@dp.message_handler(state=PaymentStates.waiting_for_custom_amount)
async def process_custom_amount(message: types.Message, state: FSMContext):
    """Обработчик ввода пользовательской суммы

    Args:
        message (types.Message): Сообщение от пользователя
        state (FSMContext): Состояние FSM
    """
    try:
        amount = float(message.text)

        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля. Введите корректную сумму:")
            return

        if amount > 100000:  # Ограничение максимальной суммы
            await message.answer("❌ Сумма слишком большая. Введите сумму до 100 000 RUB:")
            return

        # Сохраняем сумму в состоянии
        await state.update_data(amount=amount)

        # Показываем выбор метода оплаты
        providers = payment_manager.get_available_providers()

        if not providers:
            await message.answer("😔 На данный момент оплата недоступна. Попробуйте позже.")
            await state.finish()
            return

        await message.answer(
            f"💳 Вы ввели сумму: {amount} RUB\n\nВыберите способ оплаты:",
            reply_markup=get_payment_method_keyboard(amount)
        )

        await PaymentStates.waiting_for_payment_method.set()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму (число):")


# Обработчики платежей
@dp.pre_checkout_query_handler()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Обработчик предварительного запроса на оплату (для Telegram Payments)

    Args:
        pre_checkout_query (PreCheckoutQuery): Предварительный запрос на оплату
    """
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message_handler(content_types=ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: types.Message):
    """Обработчик успешного платежа (для Telegram Payments)

    Args:
        message (types.Message): Сообщение об успешной оплате
    """
    payment_info = message.successful_payment

    # Ищем платеж в базе данных по invoice_payload
    session = db.get_session()
    payment = session.query(Payment).filter(
        Payment.invoice_payload == payment_info.invoice_payload
    ).first()

    if payment:
        # Обновляем статус платежа
        payment.status = "completed"
        payment.completed_at = db.func.now()
        payment.provider_payment_id = payment_info.telegram_payment_charge_id

        # Пополняем баланс пользователя
        user = session.query(User).filter(User.id == payment.user_id).first()
        if user:
            user.balance += payment.amount
            session.commit()

            await message.answer(
                f"✅ Платеж на сумму {payment.amount:.2f} {payment.currency} успешно завершен!\n\n"
                f"💰 Ваш баланс пополнен на {payment.amount:.2f} {payment.currency}\n"
                f"💳 Текущий баланс: {user.balance:.2f} {payment.currency}",
                reply_markup=get_main_keyboard()
            )
        else:
            session.commit()
            await message.answer(
                f"✅ Платеж на сумму {payment.amount:.2f} {payment.currency} успешно завершен!\n\n"
                f"Обратитесь к администратору для уточнения деталей."
            )
    else:
        await message.answer(
            "✅ Платеж успешно завершен!\n\n"
            "Обратитесь к администратору для уточнения деталей."
        )

    session.close()


# Обработчики ошибок
@dp.errors_handler()
async def errors_handler(update, exception):
    """Обработчик ошибок

    Args:
        update: Обновление, вызвавшее ошибку
        exception: Исключение

    Returns:
        bool: Флаг, указывающий, что ошибка обработана
    """
    logger.error(f"Ошибка при обработке обновления {update}: {exception}")
    return True


# Главная функция
async def on_startup(dp):
    """Функция, выполняемая при запуске бота

    Args:
        dp (Dispatcher): Диспетчер бота
    """
    logger.info("Бот запущен")

    # Создаем тестовые услуги, если их нет
    session = db.get_session()
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

    session.close()


async def on_shutdown(dp):
    """Функция, выполняемая при выключении бота

    Args:
        dp (Dispatcher): Диспетчер бота
    """
    logger.info("Бот выключается")
    await dp.storage.close()
    await dp.storage.wait_closed()


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
