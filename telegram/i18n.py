from typing import Literal


Language = Literal["ru", "en"]
DEFAULT_LANGUAGE: Language = "ru"


TEXTS: dict[str, dict[Language, str]] = {
    "my_urls": {"ru": "📋 Мои URL", "en": "📋 My URLs"},
    "add_url": {"ru": "➕ Добавить URL", "en": "➕ Add URL"},
    "help_button": {"ru": "❓ Помощь", "en": "❓ Help"},
    "admin_panel_btn": {"ru": "🛠 Админ-панель", "en": "🛠 Admin panel"},
    "status": {"ru": "📊 Статус бота", "en": "📊 Bot status"},
    "reload_urls": {"ru": "🔄 Перезагрузить URL", "en": "🔄 Reload URLs"},
    "pause": {"ru": "⏸️ Пауза", "en": "⏸️ Pause"},
    "resume": {"ru": "▶️ Продолжить", "en": "▶️ Resume"},
    "broadcast": {"ru": "📢 Рассылка всем", "en": "📢 Broadcast to all"},
    "back": {"ru": "🔙 Назад", "en": "🔙 Back"},
    "url_type": {"ru": "🔗 URL", "en": "🔗 URL"},
    "keyword_type": {"ru": "🔤 Ключевое слово", "en": "🔤 Keyword"},
    "name_placeholder": {"ru": "Введите имя поиска...", "en": "Enter a search name..."},
    "keyword_placeholder": {"ru": "Введите ключевое слово...", "en": "Enter a keyword..."},
    "url_placeholder": {"ru": "Введите URL...", "en": "Enter a URL..."},
    "type_placeholder": {"ru": "Выберите URL или ключевое слово...", "en": "Choose a URL or keyword..."},
    "broadcast_placeholder": {"ru": "Введите текст рассылки...", "en": "Enter broadcast text..."},
    "language_prompt": {
        "ru": "Выберите язык / Choose language",
        "en": "Выберите язык / Choose language",
    },
    "language_saved": {
        "ru": "✅ Язык сохранён: Русский.",
        "en": "✅ Language saved: English.",
    },
    "language_changed": {
        "ru": "✅ Язык изменён на русский.",
        "en": "✅ Language changed to English.",
    },
    "welcome": {
        "ru": "Добро пожаловать в Mercari Watcher!\n\nВыберите действие в меню ниже.",
        "en": "Welcome to Mercari Watcher!\n\nChoose an action from the menu below.",
    },
    "cancelled": {"ru": "❌ Действие отменено.", "en": "❌ Action cancelled."},
    "no_permission": {
        "ru": "⛔ У вас нет прав администратора для этого действия.",
        "en": "⛔ You do not have administrator permissions for this action.",
    },
    "choose_search_type": {
        "ru": "📌 Выберите тип поиска:",
        "en": "📌 Choose the search type:",
    },
    "enter_search_name": {
        "ru": "✏️ Придумайте имя для этого поиска.\n\nНапример:\nКроссовки Nike",
        "en": "✏️ Create a name for this search.\n\nFor example:\nNike sneakers",
    },
    "enter_keyword": {
        "ru": "🔤 Отправьте ключевое слово для поиска.\n\nОно же будет использовано как имя.\n\nНапример:\nNike кроссовки",
        "en": "🔤 Send a keyword to search for.\n\nIt will also be used as the name.\n\nFor example:\nNike sneakers",
    },
    "enter_url": {
        "ru": "🔗 Отлично! Теперь отправьте URL для этого поиска.\n\nИмя: <b>{name}</b>\n\nПример URL:\nhttps://jp.mercari.com/en/search?category_id=7021",
        "en": "🔗 Great! Now send the URL for this search.\n\nName: <b>{name}</b>\n\nURL example:\nhttps://jp.mercari.com/en/search?category_id=7021",
    },
    "internal_error": {"ru": "❌ Внутренняя ошибка.", "en": "❌ Internal error."},
    "url_renamed": {"ru": "✅ URL переименован в: {name}", "en": "✅ URL renamed to: {name}"},
    "url_not_found": {"ru": "❌ URL не найден", "en": "❌ URL not found"},
    "no_urls": {
        "ru": "У вас нет отслеживаемых URL.\nДобавьте через кнопку ➕ Добавить URL",
        "en": "You have no tracked URLs.\nAdd one using the ➕ Add URL button",
    },
    "unknown_command": {
        "ru": "❌ Неизвестная команда: {command}\n\nИспользуй кнопки внизу или /help для справки.",
        "en": "❌ Unknown command: {command}\n\nUse the buttons below or /help for assistance.",
    },
    "error": {"ru": "❌ Ошибка: {error}", "en": "❌ Error: {error}"},
    "help": {
        "ru": "❓ Помощь\n\nЭтот бот отслеживает новые объявления на Mercari Japan.\n\nКогда появляется новое объявление, бот отправляет его название, цену и ссылку.\n\nОсновные действия:\n\n➕ Добавить URL\nДобавьте ссылку на поиск Mercari или укажите ключевое слово.\n\n📋 Мои URL\nПросмотрите все сохранённые поиски. Для каждого поиска можно:\n• посмотреть подробности;\n• переименовать его;\n• удалить его.\n\nИспользуйте только ссылки с домена jp.mercari.com.",
        "en": "❓ Help\n\nThis bot tracks new listings on Mercari Japan.\n\nWhen a new listing appears, the bot sends its title, price, and link.\n\nMain actions:\n\n➕ Add URL\nAdd a Mercari search link or enter a keyword.\n\n📋 My URLs\nView all saved searches. For each search you can:\n• view details;\n• rename it;\n• delete it.\n\nUse only links from the jp.mercari.com domain.",
    },
    "url_list": {"ru": "Ваши URL (страница {page}/{total}):", "en": "Your URLs (page {page}/{total}):"},
    "url_list_short": {"ru": "Ваши URL:", "en": "Your URLs:"},
    "url_detail": {
        "ru": "<b>{name}</b>\n\n🔗 <b>URL парсинга:</b>\n{url}\n\n📌 <b>Добавлен по:</b> {source}",
        "en": "<b>{name}</b>\n\n🔗 <b>Search URL:</b>\n{url}\n\n📌 <b>Added by:</b> {source}",
    },
    "keyword_source": {"ru": "ключевому слову", "en": "keyword"},
    "url_source": {"ru": "прямой ссылке", "en": "direct URL"},
    "rename_choose": {
        "ru": "✏️ <b>Выберите URL для переименования:</b>",
        "en": "✏️ <b>Choose a URL to rename:</b>",
    },
    "rename_prompt": {
        "ru": "✏️ Введите новое имя для URL (<b>{name}</b>).",
        "en": "✏️ Enter a new name for the URL (<b>{name}</b>).",
    },
    "rename_selected": {
        "ru": "✅ Выбран URL (<b>{name}</b>).",
        "en": "✅ URL selected (<b>{name}</b>).",
    },
    "rename_cancelled": {"ru": "❌ Переименование отменено.", "en": "❌ Rename cancelled."},
    "delete_confirm": {"ru": "🗑 Удалить URL <b>{name}</b>?", "en": "🗑 Delete URL <b>{name}</b>?"},
    "deleted": {"ru": "✅ URL <b>{name}</b> удалён.", "en": "✅ URL <b>{name}</b> deleted."},
    "not_found_named": {"ru": "❌ URL <b>{name}</b> не найден.", "en": "❌ URL <b>{name}</b> not found."},
    "new_listing": {
        "ru": "Новое объявление\n\nНазвание:\n{title}\n\nЦена:\n{price:,} JPY\n\nСсылка:\n{url}",
        "en": "New listing\n\nTitle:\n{title}\n\nPrice:\n{price:,} JPY\n\nLink:\n{url}",
    },
    "admin_panel": {
        "ru": "🛠 <b>Админ-панель</b>\n\nДоступные действия:\n📊 <b>Статус бота</b> — сводка состояния\n🔄 <b>Перезагрузить URL</b> — немедленный цикл проверки\n⏸️ <b>Пауза</b> / ▶️ <b>Продолжить</b> — остановка/возобновление watcher'а\n📢 <b>Рассылка всем</b> — отправить сообщение всем пользователям\n🔙 <b>Назад</b> — выйти из админ-панели",
        "en": "🛠 <b>Admin panel</b>\n\nAvailable actions:\n📊 <b>Bot status</b> — state summary\n🔄 <b>Reload URLs</b> — run an immediate check cycle\n⏸️ <b>Pause</b> / ▶️ <b>Resume</b> — pause/resume the watcher\n📢 <b>Broadcast to all</b> — send a message to all users\n🔙 <b>Back</b> — leave the admin panel",
    },
    "broadcast_prompt": {
        "ru": "📢 <b>Рассылка всем</b>\n\nОтправьте текст сообщения, которое получат все пользователи бота.\nПоддерживается HTML-разметка Telegram.\n\nДля отмены отправьте /admin_back.",
        "en": "📢 <b>Broadcast to all</b>\n\nSend the message text that all bot users will receive.\nTelegram HTML formatting is supported.\n\nTo cancel, send /admin_back.",
    },
    "admin_status": {
        "ru": "📊 <b>Статус бота</b>\n\nWatcher: {state}\nОчередь сообщений: {queue}\nСкорость отправки: {current}/{target} msg/s\nАктивных URL: {urls}\nПользователей: {users}",
        "en": "📊 <b>Bot status</b>\n\nWatcher: {state}\nMessage queue: {queue}\nSend rate: {current}/{target} msg/s\nActive URLs: {urls}\nUsers: {users}",
    },
    "paused": {"ru": "⏸️ ПРИОСТАНОВЛЕН", "en": "⏸️ PAUSED"},
    "running": {"ru": "▶️ работает", "en": "▶️ running"},
    "url_added": {
        "ru": "URL добавлен\nИмя: {name}\n\nПервая проверка начнётся в следующем цикле",
        "en": "URL added\nName: {name}\n\nThe first check will start in the next cycle",
    },
    "url_exists": {"ru": "URL уже существует", "en": "URL already exists"},
    "provide_search": {
        "ru": "Укажите ключевое слово или URL.",
        "en": "Provide a keyword or URL.",
    },
    "invalid_domain": {
        "ru": "URL должен быть с домена jp.mercari.com",
        "en": "URL must be from jp.mercari.com",
    },
    "url_parse_error": {"ru": "Не удалось разобрать URL: {error}", "en": "Could not parse URL: {error}"},
    "url_deleted": {"ru": "URL удалён", "en": "URL deleted"},
    "invalid_id": {
        "ru": "Укажите ID URL для удаления. Пример:\n/remove 2",
        "en": "Provide the URL ID to delete. Example:\n/remove 2",
    },
    "rename_usage": {
        "ru": "Укажите ID и новое имя. Пример:\n/rename 2 | Adidas Sneakers",
        "en": "Provide the ID and new name. Example:\n/rename 2 | Adidas Sneakers",
    },
    "reload_started": {
        "ru": "🔄 Немедленная перезагрузка всех URL инициирована.",
        "en": "🔄 Immediate reload of all URLs has been initiated.",
    },
    "admin_pause": {
        "ru": "⏸️ Watcher приостановлен. Циклы проверки пропускаются до команды ▶️ Продолжить.",
        "en": "⏸️ Watcher paused. Check cycles are skipped until ▶️ Resume is used.",
    },
    "admin_resume": {
        "ru": "▶️ Watcher возобновлён. Циклы проверки продолжатся.",
        "en": "▶️ Watcher resumed. Check cycles will continue.",
    },
    "admin_back": {"ru": "Вы вышли из админ-панели.", "en": "You left the admin panel."},
    "broadcast_sent": {"ru": "📢 Сообщение отправлено {count} пользователю(ям).", "en": "📢 Message sent to {count} user(s)."},
    "broadcast_header": {"ru": "📢 <b>Сообщение от администратора</b>\n\n{text}", "en": "📢 <b>Message from the administrator</b>\n\n{text}"},
    "terms_of_use_button": {"ru": "Условия использования", "en": "Terms of Use"},
    "terms_of_use_text": {
        "ru": "Оформляя покупку в нашем боте, вы автоматически принимаете условия использования нашего сервиса, представленные ниже",
        "en": "By making a purchase in our bot, you automatically accept the terms of use of our service presented below",
    },
    "user_agreement_button": {"ru": "Пользовательское соглашение", "en": "User Agreement"},
    "privacy_policy_button": {"ru": "Политика конфиденциальности", "en": "Privacy Policy"},
    "startup": {"ru": "Mercari Watcher запущен\n\nБот начал отслеживать новые объявления.", "en": "Mercari Watcher started\n\nThe bot started tracking new listings."},
    "shutdown": {"ru": "Mercari Watcher остановлен\n\nБот завершил работу.", "en": "Mercari Watcher stopped\n\nThe bot has shut down."},
}


def text(key: str, language: str, **values: object) -> str:
    lang: Language = "en" if language == "en" else "ru"
    template = TEXTS[key][lang]
    return template.format(**values)
