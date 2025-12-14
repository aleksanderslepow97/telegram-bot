from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.web_app_info import WebAppInfo


def get_main_keyboard():
    """Основная клавиатура бота

    Returns:
        ReplyKeyboardMarkup: Основная клавиатура
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💳 Пополнить баланс"))
    keyboard.add(KeyboardButton("🛒 Услуги"), KeyboardButton("💰 Мой баланс"))
    keyboard.add(KeyboardButton("📊 История платежей"), KeyboardButton("🆘 Помощь"))
    return keyboard


def get_admin_keyboard():
    """Клавиатура администратора

    Returns:
        ReplyKeyboardMarkup: Клавиатура администратора
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📊 Статистика"))
    keyboard.add(KeyboardButton("👥 Пользователи"), KeyboardButton("💼 Управление услугами"))
    keyboard.add(KeyboardButton("💳 Платежи"), KeyboardButton("🔙 В меню"))
    return keyboard


def get_payment_amount_keyboard():
    """Клавиатура для выбора суммы пополнения

    Returns:
        InlineKeyboardMarkup: Клавиатура с суммами
    """
    keyboard = InlineKeyboardMarkup(row_width=3)
    amounts = [100, 200, 500, 1000, 2000, 5000]
    for amount in amounts:
        keyboard.insert(InlineKeyboardButton(f"{amount} RUB", callback_data=f"pay_{amount}"))
    keyboard.add(InlineKeyboardButton("💳 Другая сумма", callback_data="custom_amount"))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return keyboard


def get_payment_method_keyboard(amount):
    """Клавиатура для выбора метода оплаты

    Args:
        amount (float): Сумма платежа

    Returns:
        InlineKeyboardMarkup: Клавиатура с методами оплаты
    """
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("💳 Telegram Payments",
                                      callback_data=f"payment_method_telegram_{amount}"))
    keyboard.add(InlineKeyboardButton("💳 ЮKassa",
                                      callback_data=f"payment_method_yookassa_{amount}"))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return keyboard


def get_services_keyboard(services):
    """Клавиатура для выбора услуги

    Args:
        services (list): Список услуг

    Returns:
        InlineKeyboardMarkup: Клавиатура с услугами
    """
    keyboard = InlineKeyboardMarkup()
    for service in services:
        keyboard.add(InlineKeyboardButton(
            f"{service.name} - {service.price} RUB",
            callback_data=f"service_{service.id}"
        ))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return keyboard


def get_admin_services_keyboard(services):
    """Клавиатура для управления услугами (админ)

    Args:
        services (list): Список услуг

    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями над услугами
    """
    keyboard = InlineKeyboardMarkup()
    for service in services:
        status = "✅" if service.is_active else "❌"
        keyboard.add(InlineKeyboardButton(
            f"{status} {service.name} - {service.price} RUB",
            callback_data=f"admin_service_{service.id}"
        ))
    keyboard.add(InlineKeyboardButton("➕ Добавить услугу", callback_data="add_service"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    return keyboard
