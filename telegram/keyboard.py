from typing import Any

from telegram.i18n import text


LANGUAGE_BUTTON = "🌐 Язык / Language"


def button_text(key: str, language: str) -> str:
    return text(key, language)


def build_keyboard_markup(
    is_admin: bool = False,
    language: str = "ru",
    placeholder: str | None = None,
    is_subscribed: bool = False,
) -> dict[str, Any]:
    """Build reply keyboard markup.

    Базовая клавиатура одинакова для всех. Если is_admin=True, к ней
    добавляется ряд с кнопкой входа в админ-панель — её видит только
    администратор. Сам layout админ-панели (ADMIN_KEYBOARD) отправляется
    отдельным сообщением при входе в /admin_panel, а не каждой отправкой.
    """
    sub_key = "subscription_btn" if not is_subscribed else "subscription_status_btn"
    keyboard = [
        [{"text": button_text(sub_key, language)}],
        [{"text": button_text("my_urls", language)}],
        [{"text": button_text("add_url", language)}],
        [{"text": button_text("help_button", language)}, {"text": LANGUAGE_BUTTON}],
    ]
    if is_admin:
        keyboard.append([{"text": button_text("admin_panel_btn", language)}])
    result: dict[str, Any] = {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


def build_admin_keyboard_markup(
    language: str = "ru",
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build admin-panel reply keyboard markup."""
    result: dict[str, Any] = {
        "keyboard": [
            [{"text": button_text("status", language)}, {"text": button_text("reload_urls", language)}],
            [{"text": button_text("pause", language)}, {"text": button_text("resume", language)}],
            [{"text": button_text("broadcast", language)}],
            [{"text": button_text("back", language)}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


def build_cancel_keyboard_markup(
    language: str = "ru",
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build cancel-only reply keyboard markup."""
    result: dict[str, Any] = {
        "keyboard": [
            [{"text": button_text("back", language)}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


def build_add_type_keyboard_markup(
    language: str = "ru",
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build add-type reply keyboard markup."""
    result: dict[str, Any] = {
        "keyboard": [
            [{"text": button_text("url_type", language)}, {"text": button_text("keyword_type", language)}],
            [{"text": button_text("back", language)}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


# Map button text → internal command.
# Пользовательские кнопки маппят в обычные команды;
# админские — в /admin_* команды или спец-состояния (см. bot.py).
BUTTON_ACTIONS: dict[str, str] = {
    # ── основные ──
    "📋 Мои URL": "__await_list__",
    "➕ Добавить URL": "__await_add__",
    "💎 Купить подписку": "__await_subscription__",
    "💎 Моя подписка": "__await_subscription__",
    "❓ Помощь": "/help",
    "📋 My URLs": "__await_list__",
    "➕ Add URL": "__await_add__",
    "💎 Buy Subscription": "__await_subscription__",
    "💎 My Subscription": "__await_subscription__",
    "❓ Help": "/help",
    LANGUAGE_BUTTON: "__language__",
    # ── вход в админ-панель ──
    "🛠 Админ-панель": "/admin_panel",
    "🛠 Admin panel": "/admin_panel",
    # ── действия внутри админ-панели ──
    "📊 Статус бота": "/admin_status",
    "🔄 Перезагрузить URL": "/admin_reload",
    "⏸️ Пауза": "/admin_pause",
    "▶️ Продолжить": "/admin_resume",
    "📢 Рассылка всем": "__await_broadcast__",
    "🔙 Назад": "/admin_back",
    "📊 Bot status": "/admin_status",
    "🔄 Reload URLs": "/admin_reload",
    "⏸️ Pause": "/admin_pause",
    "▶️ Resume": "/admin_resume",
    "📢 Broadcast to all": "__await_broadcast__",
    "🔙 Back": "/admin_back",
}

PAGE_SIZE = 9

# ── Inline-клавиатуры ─────────────────────────────────────────────


def build_language_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [[
            {"text": "🇷🇺 Русский", "callback_data": "lang_ru"},
            {"text": "🇬🇧 English", "callback_data": "lang_en"},
        ]],
    }


def build_confirm_delete_keyboard(url_id: int, language: str = "ru") -> dict[str, Any]:
    """Inline-клавиатура подтверждения удаления."""
    keyboard = [[
        {"text": "🗑 Delete" if language == "en" else "🗑 Удалить", "callback_data": f"confirm_{url_id}"},
        {"text": "❌ Cancel" if language == "en" else "❌ Отмена", "callback_data": "cancel_del"},
    ]]
    return {"inline_keyboard": keyboard}


def build_list_inline_keyboard(language: str = "ru") -> dict[str, Any]:
    """Inline-клавиатура под списком URL: Переименовать + Назад."""
    keyboard = [[
        {"text": "✏️ Rename URL" if language == "en" else "✏️ Переименовать URL", "callback_data": "rename_list"},
        {"text": "🔙 Back" if language == "en" else "🔙 Назад", "callback_data": "list_back"},
    ]]
    return {"inline_keyboard": keyboard}


def build_list_items_inline_keyboard_paginated(
    urls: list, page: int, total_pages: int, language: str = "ru",
) -> dict[str, Any]:
    """Paginated inline-клавиатура: 9 URL кнопок + навигация (◀ [стр] ▶)."""
    keyboard = []
    for row in urls:
        keyboard.append([{
            "text": row.name,
            "callback_data": f"info_{row.id}",
        }])
    nav_row = []
    if page > 0:
        nav_row.append({"text": "◀", "callback_data": "list_prev"})
    nav_row.append({"text": f"[ {page + 1}/{total_pages} ]", "callback_data": "none"})
    if page < total_pages - 1:
        nav_row.append({"text": "▶", "callback_data": "list_next"})
    keyboard.append(nav_row)
    return {"inline_keyboard": keyboard}


def build_url_detail_keyboard(url_id: int, language: str = "ru") -> dict[str, Any]:
    """Inline-клавиатура для деталей URL: Переименовать, Удалить, Назад."""
    keyboard = [[
        {"text": "✏️ Rename" if language == "en" else "✏️ Переименовать", "callback_data": f"rnm_{url_id}"},
        {"text": "🗑 Delete" if language == "en" else "🗑 Удалить", "callback_data": f"del_{url_id}"},
    ], [
        {"text": "🔙 Back" if language == "en" else "🔙 Назад", "callback_data": "list_back"},
    ]]
    return {"inline_keyboard": keyboard}


def build_rename_inline_keyboard(urls: list, language: str = "ru") -> dict[str, Any]:
    """Inline-клавиатура со списком URL пользователя для переименования."""
    keyboard = []
    for row in urls:
        keyboard.append([{
            "text": row.name,
            "callback_data": f"rnm_{row.id}",
        }])
    keyboard.append([{
        "text": "🔙 Back" if language == "en" else "🔙 Назад",
        "callback_data": "cancel_rename",
    }])
    return {"inline_keyboard": keyboard}


def build_help_inline_keyboard(language: str = "ru") -> dict[str, Any]:
    """Inline-клавиатура для сообщения помощи: кнопка 'Условия использования'."""
    return {"inline_keyboard": [
        [{"text": button_text("terms_of_use_button", language), "callback_data": "terms_open"}],
        [{"text": button_text("support_button", language), "url": "https://t.me/eeveek"}],
    ]}


def build_terms_inline_keyboard(language: str = "ru") -> dict[str, Any]:
    """Inline-клавиатура с условиями использования."""
    return {"inline_keyboard": [
        [{"text": button_text("user_agreement_button", language), "url": "https://telegra.ph/Polzovatelskoe-soglashenie-08-03-26"}],
        [{"text": button_text("privacy_policy_button", language), "url": "https://telegra.ph/Politika-konfidencialnosti-08-03-72"}],
        [{"text": button_text("back", language), "callback_data": "terms_back"}],
    ]}


def build_subscription_inline_keyboard(language: str = "ru") -> dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": button_text("sub_7d", language), "callback_data": "sub_7d"},
        {"text": button_text("sub_30d", language), "callback_data": "sub_30d"},
    ]]}


def build_trial_keyboard(language: str = "ru") -> dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": button_text("trial_button", language), "callback_data": "trial_activate"},
    ]]}


def build_invoice_keyboard(pay_url: str, invoice_id: int, language: str = "ru") -> dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": button_text("pay_invoice", language), "url": pay_url}],
        [{"text": button_text("check_payment", language), "callback_data": f"check_payment_{invoice_id}"}],
    ]}


# Множество админских действий — для проверки прав в bot.py.
ADMIN_BUTTON_ACTIONS: frozenset[str] = frozenset(
    {
        "/admin_panel",
        "/admin_status",
        "/admin_reload",
        "/admin_pause",
        "/admin_resume",
        "/admin_back",
        "__await_broadcast__",
    }
)
