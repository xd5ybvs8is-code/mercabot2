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
        "ru": (
            "👋 Добро пожаловать!\n\n"
            "Этот бот поможет вам отслеживать новые объявления на Mercari Japan.\n\n\n"
            "Как только появится новое объявление, соответствующее вашему поиску, вы сразу получите:\n"
            "• 🏷️ название товара;\n"
            "• 💴 цену;\n"
            "• 🔗 ссылку на объявление."
        ),
        "en": (
            "👋 Welcome!\n\n"
            "This bot helps you track new listings on Mercari Japan.\n\n\n"
            "As soon as a new listing matching your search appears, you'll immediately receive:\n"
            "• 🏷️ item title;\n"
            "• 💴 price;\n"
            "• 🔗 listing link."
        ),
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
    "support_button": {"ru": "Техподдержка", "en": "Tech Support"},
    "startup": {"ru": "Mercari Watcher запущен\n\nБот начал отслеживать новые объявления.", "en": "Mercari Watcher started\n\nThe bot started tracking new listings."},
    "shutdown": {"ru": "Mercari Watcher остановлен\n\nБот завершил работу.", "en": "Mercari Watcher stopped\n\nThe bot has shut down."},
    "subscription_btn": {"ru": "💎 Купить подписку", "en": "💎 Buy Subscription"},
    "subscription_status_btn": {"ru": "💎 Моя подписка", "en": "💎 My Subscription"},
    "subscription_title": {
        "ru": "💎 Подписка Mercari jp Parser\n\nПодписка открывает доступ к отслеживанию новых объявлений на Mercari Japan:\n\n• Мгновенные уведомления о новых товарах\n• Отслеживание по ключевым словам и ссылкам\n\nВыберите срок подписки:",
        "en": "💎 Mercari jp Parser Subscription\n\nSubscription gives access to tracking new listings on Mercari Japan:\n\n• Instant notifications for new items\n• Tracking by keywords and links\n\nChoose a subscription period:",
    },
    "sub_7d": {"ru": "7 дней — 100₽", "en": "7 days — 100₽"},
    "sub_30d": {"ru": "30 дней — 300₽", "en": "30 days — 300₽"},
    "no_subscription": {
        "ru": "💎 Для этого действия нужна активная подписка.\n\nНажмите «💎 Купить подписку» в меню.",
        "en": "💎 An active subscription is required for this action.\n\nPress «💎 Buy Subscription» in the menu.",
    },
    "invoice_created": {
        "ru": "✅ Счёт на оплату создан.\n\n📦 {plan}\n\n⏳ На оплату даётся 30 минут.",
        "en": "✅ Invoice created.\n\n📦 {plan}\n\n⏳ You have 30 minutes to pay.",
    },
    "invoice_error": {
        "ru": "❌ Не удалось создать счёт. Попробуйте позже.",
        "en": "❌ Failed to create invoice. Please try again later.",
    },
    "subscription_status_title": {
        "ru": "💎 <b>Моя подписка</b>",
        "en": "💎 <b>My Subscription</b>",
    },
    "subscription_status_active": {
        "ru": "✅ Статус: <b>Активна</b>\n⏰ До: <b>{expires}</b>\n📦 План: <b>{plan}</b>",
        "en": "✅ Status: <b>Active</b>\n⏰ Until: <b>{expires}</b>\n📦 Plan: <b>{plan}</b>",
    },
    "subscription_status_pending": {
        "ru": "⏳ Статус: <b>Ожидает оплаты</b>\n\nСчёт ещё не оплачен.",
        "en": "⏳ Status: <b>Awaiting payment</b>\n\nThe invoice has not been paid yet.",
    },
    "subscription_status_no": {
        "ru": "❌ У вас нет активной подписки.\n\nНажмите кнопку ниже чтобы приобрести:",
        "en": "❌ You don't have an active subscription.\n\nPress the button below to purchase:",
    },
    "subscription_extend_btn": {
        "ru": "💎 Продлить подписку",
        "en": "💎 Extend Subscription",
    },
    "trial_button": {
        "ru": "🎁 Пробный доступ (12 часов)",
        "en": "🎁 Trial Access (12 hours)",
    },
    "trial_prompt": {
        "ru": "🎁 Вы можете получить <b>пробный доступ на 12 часов</b> бесплатно!\n\nПробный доступ даётся только <b>один раз</b>.",
        "en": "🎁 You can get a <b>12-hour trial access</b> for free!\n\nTrial access is available only <b>once</b>.",
    },
    "trial_activated": {
        "ru": "✅ <b>Пробный доступ активирован на 12 часов!</b>\n\nТеперь вы можете добавлять URL и получать уведомления о новых объявлениях.\n\nПодписка истечёт автоматически.",
        "en": "✅ <b>Trial access activated for 12 hours!</b>\n\nNow you can add URLs and receive notifications about new listings.\n\nThe subscription will expire automatically.",
    },
    "trial_already_used": {
        "ru": "❌ Вы уже использовали пробный доступ.\n\nПриобретите подписку для продолжения.",
        "en": "❌ You have already used your trial access.\n\nPurchase a subscription to continue.",
    },
    "trial_plan_label": {
        "ru": "Пробный (12 часов)",
        "en": "Trial (12 hours)",
    },
    "pay_invoice": {
        "ru": "💳 Оплатить",
        "en": "💳 Pay",
    },
    "check_payment": {
        "ru": "🔄 Проверить оплату",
        "en": "🔄 Check Payment",
    },
    "invoice_cancelled": {
        "ru": "⏰ Счёт на оплату отменён.\n\nВремя на оплату истекло (30 минут). Создайте новый счёт.",
        "en": "⏰ Invoice cancelled.\n\nPayment time expired (30 minutes). Create a new invoice.",
    },
    "invoice_not_paid": {
        "ru": "⏳ Счёт ещё не оплачен. Попробуйте позже.",
        "en": "⏳ Invoice not paid yet. Try again later.",
    },
    "invoice_paid_now": {
        "ru": "✅ Оплата подтверждена!\n\n📦 {plan}\n⏰ До: {expires}",
        "en": "✅ Payment confirmed!\n\n📦 {plan}\n⏰ Until: {expires}",
    },
}


def text(key: str, language: str, **values: object) -> str:
    lang: Language = "en" if language == "en" else "ru"
    template = TEXTS[key][lang]
    return template.format(**values)
