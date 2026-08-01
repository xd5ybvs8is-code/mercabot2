from typing import Any

# Reply keyboard layout — основные кнопки, видимые всем пользователям.
MAIN_KEYBOARD: list[list[dict[str, str]]] = [
    [{"text": "📋 Мои URL"}],
    [{"text": "➕ Добавить URL"}],
    [{"text": "❓ Помощь"}],
]

# Дополнительный ряд, видимый только администраторам.
ADMIN_ENTRY_ROW: list[dict[str, str]] = [{"text": "🛠 Админ-панель"}]

# Layout админ-панели (показывается при входе в /admin_panel).
ADMIN_KEYBOARD: list[list[dict[str, str]]] = [
    [{"text": "📊 Статус бота"}, {"text": "🔄 Перезагрузить URL"}],
    [{"text": "⏸️ Пауза"}, {"text": "▶️ Продолжить"}],
    [{"text": "📢 Рассылка всем"}],
    [{"text": "🔙 Назад"}],
]

# Layout для отмены действия (при ожидании ввода).
CANCEL_KEYBOARD: list[list[dict[str, str]]] = [
    [{"text": "🔙 Назад"}],
]

# Layout выбора типа поиска (URL или ключевое слово).
ADD_TYPE_KEYBOARD: list[list[dict[str, str]]] = [
    [{"text": "🔗 URL"}, {"text": "🔤 Ключевое слово"}],
    [{"text": "🔙 Назад"}],
]


def build_keyboard_markup(
    is_admin: bool = False,
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build reply keyboard markup.

    Базовая клавиатура одинакова для всех. Если is_admin=True, к ней
    добавляется ряд с кнопкой входа в админ-панель — её видит только
    администратор. Сам layout админ-панели (ADMIN_KEYBOARD) отправляется
    отдельным сообщением при входе в /admin_panel, а не каждой отправкой.
    """
    keyboard = [row[:] for row in MAIN_KEYBOARD]
    if is_admin:
        keyboard.append(ADMIN_ENTRY_ROW[:])
    result: dict[str, Any] = {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


def build_admin_keyboard_markup(
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build admin-panel reply keyboard markup."""
    result: dict[str, Any] = {
        "keyboard": [row[:] for row in ADMIN_KEYBOARD],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


def build_cancel_keyboard_markup(
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build cancel-only reply keyboard markup."""
    result: dict[str, Any] = {
        "keyboard": [row[:] for row in CANCEL_KEYBOARD],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    if placeholder:
        result["input_field_placeholder"] = placeholder
    return result


def build_add_type_keyboard_markup(
    placeholder: str | None = None,
) -> dict[str, Any]:
    """Build add-type reply keyboard markup."""
    result: dict[str, Any] = {
        "keyboard": [row[:] for row in ADD_TYPE_KEYBOARD],
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
    "❓ Помощь": "/help",
    # ── вход в админ-панель ──
    "🛠 Админ-панель": "/admin_panel",
    # ── действия внутри админ-панели ──
    "📊 Статус бота": "/admin_status",
    "🔄 Перезагрузить URL": "/admin_reload",
    "⏸️ Пауза": "/admin_pause",
    "▶️ Продолжить": "/admin_resume",
    "📢 Рассылка всем": "__await_broadcast__",
    "🔙 Назад": "/admin_back",
}

PAGE_SIZE = 9

# ── Inline-клавиатуры ─────────────────────────────────────────────


def build_confirm_delete_keyboard(url_id: int) -> dict[str, Any]:
    """Inline-клавиатура подтверждения удаления."""
    keyboard = [[
        {"text": "🗑 Удалить", "callback_data": f"confirm_{url_id}"},
        {"text": "❌ Отмена", "callback_data": "cancel_del"},
    ]]
    return {"inline_keyboard": keyboard}


def build_list_inline_keyboard() -> dict[str, Any]:
    """Inline-клавиатура под списком URL: Переименовать + Назад."""
    keyboard = [[
        {"text": "✏️ Переименовать URL", "callback_data": "rename_list"},
        {"text": "🔙 Назад", "callback_data": "list_back"},
    ]]
    return {"inline_keyboard": keyboard}


def build_list_items_inline_keyboard_paginated(
    urls: list, page: int, total_pages: int,
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


def build_url_detail_keyboard(url_id: int) -> dict[str, Any]:
    """Inline-клавиатура для деталей URL: Переименовать, Удалить, Назад."""
    keyboard = [[
        {"text": "✏️ Переименовать", "callback_data": f"rnm_{url_id}"},
        {"text": "🗑 Удалить", "callback_data": f"del_{url_id}"},
    ], [
        {"text": "🔙 Назад", "callback_data": "list_back"},
    ]]
    return {"inline_keyboard": keyboard}


def build_rename_inline_keyboard(urls: list) -> dict[str, Any]:
    """Inline-клавиатура со списком URL пользователя для переименования."""
    keyboard = []
    for row in urls:
        keyboard.append([{
            "text": row.name,
            "callback_data": f"rnm_{row.id}",
        }])
    keyboard.append([{"text": "🔙 Назад", "callback_data": "cancel_rename"}])
    return {"inline_keyboard": keyboard}


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
