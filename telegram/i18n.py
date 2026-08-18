from typing import Literal


Language = Literal["ru", "en"]
DEFAULT_LANGUAGE: Language = "ru"


TEXTS: dict[str, dict[Language, str]] = {
    "my_urls": {"ru": "📋 Мои URL", "en": "📋 My URLs"},
    "add_url": {"ru": "➕ Добавить URL", "en": "➕ Add URL"},
    "help_button": {"ru": "❓ FAQ", "en": "❓ FAQ"},
    "manage_urls": {"ru": "📁 Управление URL", "en": "📁 Manage URLs"},
    "url_management_title": {"ru": "📁 <b>Управление URL</b>\n\nВыберите действие:", "en": "📁 <b>Manage URLs</b>\n\nChoose an action:"},
    "admin_panel_btn": {"ru": "🛠 Админ-панель", "en": "🛠 Admin panel"},
    "status": {"ru": "📊 Статус бота", "en": "📊 Bot status"},
    "admin_stats_btn": {"ru": "📈 Статистика", "en": "📈 Statistics"},
    "reload_urls": {"ru": "🔄 Перезагрузить URL", "en": "🔄 Reload URLs"},
    "pause": {"ru": "⏸️ Пауза", "en": "⏸️ Pause"},
    "resume": {"ru": "▶️ Продолжить", "en": "▶️ Resume"},
    "broadcast": {"ru": "📢 Рассылка всем", "en": "📢 Broadcast to all"},
    "promo_codes": {"ru": "🎟 Промокоды", "en": "🎟 Promo codes"},
    "promo_create": {"ru": "➕ Создать промокод", "en": "➕ Create promo code"},
    "promo_list": {"ru": "📋 Список промокодов", "en": "📋 Promo code list"},
    "promo_deactivate": {"ru": "➖ Деактивировать промокод", "en": "➖ Deactivate promo code"},
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
    "back_to_main": {"ru": "↩️ Главное меню", "en": "↩️ Main menu"},
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
        "ru": "У вас нет отслеживаемых URL.\nДобавьте через 📁 Управление URL → ➕ Добавить URL",
        "en": "You have no tracked URLs.\nAdd one via 📁 Manage URLs → ➕ Add URL",
    },
    "unknown_command": {
        "ru": "❌ Неизвестная команда: {command}\n\nИспользуй кнопки внизу или /help для справки.",
        "en": "❌ Unknown command: {command}\n\nUse the buttons below or /help for assistance.",
    },
    "error": {"ru": "❌ Ошибка: {error}", "en": "❌ Error: {error}"},
    "help": {
        "ru": "❓ FAQ\n\nЭтот бот отслеживает новые объявления на Mercari Japan.\n\nКогда появляется новое объявление, бот отправляет его название, цену и ссылку.\n\nОсновные действия:\n\n📁 Управление URL\nРаздел для управления вашими поисками. Здесь можно:\n• ➕ Добавить URL — добавить ссылку или ключевое слово;\n• 📋 Мои URL — просмотреть, переименовать или удалить сохранённые поиски.\n\nИспользуйте только ссылки с домена jp.mercari.com.",
        "en": "❓ FAQ\n\nThis bot tracks new listings on Mercari Japan.\n\nWhen a new listing appears, the bot sends its title, price, and link.\n\nMain actions:\n\n📁 Manage URLs\nSection for managing your searches. Here you can:\n• ➕ Add URL — add a link or keyword;\n• 📋 My URLs — view, rename or delete saved searches.\n\nUse only links from the jp.mercari.com domain.",
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
    "rename_not_allowed": {
        "ru": "❌ URL, добавленный по ключевому слову, переименовать нельзя — имя не меняет сам поисковый URL.",
        "en": "❌ A keyword-based URL cannot be renamed — the name does not change the search URL itself.",
    },
    "delete_confirm": {"ru": "🗑 Удалить URL <b>{name}</b>?", "en": "🗑 Delete URL <b>{name}</b>?"},
    "deleted": {"ru": "✅ URL <b>{name}</b> удалён.", "en": "✅ URL <b>{name}</b> deleted."},
    "not_found_named": {"ru": "❌ URL <b>{name}</b> не найден.", "en": "❌ URL <b>{name}</b> not found."},
    "new_listing": {
        "ru": "Новое объявление\n\nНазвание:\n{title}\n\nЦена:\n{price:,} JPY\n\nСсылка:\n{url}",
        "en": "New listing\n\nTitle:\n{title}\n\nPrice:\n{price:,} JPY\n\nLink:\n{url}",
    },
    "admin_panel": {
        "ru": "🛠 <b>Админ-панель</b>\n\nДоступные действия:\n📊 <b>Статус бота</b> — сводка состояния\n📈 <b>Статистика</b> — подробная статистика по боту\n🔄 <b>Перезагрузить URL</b> — немедленный цикл проверки\n⏸️ <b>Пауза</b> / ▶️ <b>Продолжить</b> — остановка/возобновление watcher'а\n📢 <b>Рассылка всем</b> — отправить сообщение всем пользователям\n🎟 <b>Промокоды</b> — создать и управлять промокодами\n🔙 <b>Назад</b> — выйти из админ-панели",
        "en": "🛠 <b>Admin panel</b>\n\nAvailable actions:\n📊 <b>Bot status</b> — state summary\n📈 <b>Statistics</b> — detailed bot statistics\n🔄 <b>Reload URLs</b> — run an immediate check cycle\n⏸️ <b>Pause</b> / ▶️ <b>Resume</b> — pause/resume the watcher\n📢 <b>Broadcast to all</b> — send a message to all users\n🎟 <b>Promo codes</b> — create and manage promo codes\n🔙 <b>Back</b> — leave the admin panel",
    },
    "broadcast_prompt": {
        "ru": "📢 <b>Рассылка всем</b>\n\nОтправьте текст сообщения, которое получат все пользователи бота.\nПоддерживается HTML-разметка Telegram.\n\nДля отмены отправьте /admin_back.",
        "en": "📢 <b>Broadcast to all</b>\n\nSend the message text that all bot users will receive.\nTelegram HTML formatting is supported.\n\nTo cancel, send /admin_back.",
    },
    "admin_status": {
        "ru": "📊 <b>Статус бота</b>\n\nWatcher: {state}\nОчередь сообщений: {queue}\nСкорость отправки: {current}/{target} msg/s\nАктивных URL: {urls}\nПользователей: {users}",
        "en": "📊 <b>Bot status</b>\n\nWatcher: {state}\nMessage queue: {queue}\nSend rate: {current}/{target} msg/s\nActive URLs: {urls}\nUsers: {users}",
    },
    "admin_stats": {
        "ru": (
            "📈 <b>Статистика бота</b>\n\n"
            "🕐 Аптайм: {uptime}\n\n"
            "👀 <b>Мониторинг</b>\n"
            "Циклов: {cycles} (ошибок: {cycle_errors})\n"
            "Среднее время цикла: {avg_cycle} сек\n"
            "Запросов к Mercari: {requests} (ошибок: {request_errors})\n"
            "Средняя задержка API: {avg_latency} сек\n"
            "Найдено товаров: {items_found}\n\n"
            "📨 <b>Уведомления</b>\n"
            "Отправлено: {sent}\n"
            "Ошибок: {failed}\n"
            "Лимит 429: {rate_limited}\n"
            "Очередь: {queue}\n"
            "Outbox: {outbox}\n\n"
            "👥 <b>Пользователи и подписки</b>\n"
            "Пользователей: {users}\n"
            "Активных URL: {urls_active} (всего: {urls_total})\n"
            "Подписки: активных {subs_active}, ожидают {subs_pending}, истекло {subs_expired}\n"
            "Планы: {plans}\n"
            "Промокоды: {promo_users}\n"
            "Whitelist: {whitelist}\n"
            "Выручка: {revenue}\n\n"
            "🗄 <b>База данных</b>\n"
            "Размер: {db_size} МБ\n"
            "Товаров: {items_total} (сегодня: {items_today})\n"
            "Seen: {seen_total}"
        ),
        "en": (
            "📈 <b>Bot statistics</b>\n\n"
            "🕐 Uptime: {uptime}\n\n"
            "👀 <b>Monitoring</b>\n"
            "Cycles: {cycles} (errors: {cycle_errors})\n"
            "Average cycle time: {avg_cycle} sec\n"
            "Mercari requests: {requests} (errors: {request_errors})\n"
            "Average API latency: {avg_latency} sec\n"
            "Items found: {items_found}\n\n"
            "📨 <b>Notifications</b>\n"
            "Sent: {sent}\n"
            "Failed: {failed}\n"
            "Rate limit 429: {rate_limited}\n"
            "Queue: {queue}\n"
            "Outbox: {outbox}\n\n"
            "👥 <b>Users and subscriptions</b>\n"
            "Users: {users}\n"
            "Active URLs: {urls_active} (total: {urls_total})\n"
            "Subscriptions: active {subs_active}, pending {subs_pending}, expired {subs_expired}\n"
            "Plans: {plans}\n"
            "Promo codes: {promo_users}\n"
            "Whitelist: {whitelist}\n"
            "Revenue: {revenue}\n\n"
            "🗄 <b>Database</b>\n"
            "Size: {db_size} MB\n"
            "Items: {items_total} (today: {items_today})\n"
            "Seen: {seen_total}"
        ),
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
    "plan_7d": {"ru": "7 дней — 100₽", "en": "7 days — 100₽"},
    "plan_30d": {"ru": "30 дней — 300₽", "en": "30 days — 300₽"},
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
    "subscription_status_paid": {
        "ru": "💳 Оплачено: <b>{amount} {asset}</b> · {gateway}",
        "en": "💳 Paid: <b>{amount} {asset}</b> · {gateway}",
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
    "promo_enter_btn": {
        "ru": "🎟 Ввести промокод",
        "en": "🎟 Enter promo code",
    },
    "promo_code_prompt": {
        "ru": "🎟 <b>Введите промокод</b> одним сообщением.\n\nДля отмены нажмите «🔙 Назад».",
        "en": "🎟 <b>Enter your promo code</b> in one message.\n\nTo cancel, press «🔙 Back».",
    },
    "promo_code_placeholder": {
        "ru": "Введите промокод...",
        "en": "Enter promo code...",
    },
    "promo_applied": {
        "ru": "✅ Промокод применён: добавлено {days} дн.",
        "en": "✅ Promo code applied: {days} day(s) added.",
    },
    "promo_not_found": {
        "ru": "❌ Промокод не найден. Проверьте написание и попробуйте ещё раз.",
        "en": "❌ Promo code not found. Check the spelling and try again.",
    },
    "promo_inactive": {
        "ru": "❌ Этот промокод деактивирован.",
        "en": "❌ This promo code has been deactivated.",
    },
    "promo_used": {
        "ru": "❌ Этот промокод уже использован.",
        "en": "❌ This promo code has already been used.",
    },
    "promo_expired": {
        "ru": "❌ Срок действия этого промокода истёк.",
        "en": "❌ This promo code has expired.",
    },
    "promo_target": {
        "ru": "❌ Этот промокод предназначен для другого пользователя.",
        "en": "❌ This promo code is intended for another user.",
    },
    "promo_already_paid": {
        "ru": "❌ Этот промокод доступен только пользователям, которые ещё не оплачивали подписку.",
        "en": "❌ This promo code is available only to users who have never paid for a subscription.",
    },
    "promo_new_promo_used": {
        "ru": "❌ Вы уже использовали промокод для новых пользователей.",
        "en": "❌ You have already used a new-user promo code.",
    },
    "promo_pending": {
        "ru": "❌ Сначала завершите или отмените текущую оплату.",
        "en": "❌ Finish or cancel your current payment first.",
    },
    "promo_internal": {
        "ru": "❌ Не удалось применить промокод. Попробуйте позже.",
        "en": "❌ The promo code could not be applied. Please try again later.",
    },
    "promo_plan_label": {
        "ru": "Promo",
        "en": "Promo",
    },
    "subscription_expired": {
        "ru": "⚠️ Подписка закончилась\n\nВаши поиски временно приостановлены.\nПосле продления они продолжат работать автоматически.",
        "en": "⚠️ Subscription has ended\n\nYour searches are temporarily paused.\nAfter renewal they will continue working automatically.",
    },
    "subscription_expiring_soon": {
        "ru": "⚠️ Ваша подписка закончится через 1 день.\n\nПродлите её, чтобы поиски продолжили работать без перерыва.",
        "en": "⚠️ Your subscription expires in 1 day.\n\nExtend it to keep your searches running without interruption.",
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
    "trial_activated_alert": {
        "ru": "Пробный доступ активирован на 12 часов!",
        "en": "Trial access activated for 12 hours!",
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
    "paymethod_sbp": {
        "ru": "💳 СБП (QR-код)",
        "en": "💳 SBP (QR code)",
    },
    "paymethod_crypto": {
        "ru": "💎 USDT (CryptoBot)",
        "en": "💎 USDT (CryptoBot)",
    },
    "choose_payment_method": {
        "ru": "💎 <b>Выберите способ оплаты:</b>",
        "en": "💎 <b>Choose payment method:</b>",
    },
    "sbp_plan_7d": {
        "ru": "7 дней — 100₽ (СБП)",
        "en": "7 days — 100₽ (SBP)",
    },
    "sbp_plan_30d": {
        "ru": "30 дней — 300₽ (СБП)",
        "en": "30 days — 300₽ (SBP)",
    },
    "check_payment": {
        "ru": "🔄 Проверить оплату",
        "en": "🔄 Check Payment",
    },
    "cancel_invoice": {
        "ru": "❌ Отменить оплату",
        "en": "❌ Cancel Payment",
    },
    "invoice_cancelled_by_user": {
        "ru": "❌ Вы отменили оплату.\n\nСчёт аннулирован. Вы можете создать новый счёт.",
        "en": "❌ You cancelled the payment.\n\nThe invoice has been voided. You can create a new one.",
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
    "whitelist": {"ru": "👥 Управление доступом", "en": "👥 Manage Access"},
    "whitelist_grant": {"ru": "➕ Выдать доступ", "en": "➕ Grant Access"},
    "whitelist_revoke": {"ru": "➖ Забрать доступ", "en": "➖ Revoke Access"},
    "whitelist_list": {"ru": "📋 Список доступа", "en": "📋 Access List"},
    "whitelist_prompt": {
        "ru": "👥 <b>Управление доступом</b>\n\nВыберите действие:",
        "en": "👥 <b>Manage Access</b>\n\nChoose an action:",
    },
    "whitelist_grant_prompt": {
        "ru": "➕ <b>Выдать доступ</b>\n\nОтправьте Telegram user_id пользователя, которому нужно выдать бессрочный доступ.",
        "en": "➕ <b>Grant Access</b>\n\nSend the Telegram user_id of the user to grant unlimited access to.",
    },
    "whitelist_revoke_prompt": {
        "ru": "➖ <b>Забрать доступ</b>\n\nОтправьте Telegram user_id пользователя, у которого нужно забрать доступ.",
        "en": "➖ <b>Revoke Access</b>\n\nSend the Telegram user_id of the user whose access should be revoked.",
    },
    "whitelist_granted": {
        "ru": "✅ Доступ выдан пользователю <code>{user_id}</code>.",
        "en": "✅ Access granted to user <code>{user_id}</code>.",
    },
    "whitelist_already_granted": {
        "ru": "⚠️ Пользователь <code>{user_id}</code> уже имеет доступ.",
        "en": "⚠️ User <code>{user_id}</code> already has access.",
    },
    "whitelist_revoked": {
        "ru": "✅ Доступ у пользователя <code>{user_id}</code> отозван.",
        "en": "✅ Access revoked for user <code>{user_id}</code>.",
    },
    "whitelist_not_found": {
        "ru": "⚠️ Пользователь <code>{user_id}</code> не найден в списке доступа.",
        "en": "⚠️ User <code>{user_id}</code> not found in the access list.",
    },
    "whitelist_list_title": {
        "ru": "📋 <b>Пользователи с доступом</b>\n\n",
        "en": "📋 <b>Users with access</b>\n\n",
    },
    "whitelist_list_row": {
        "ru": "• <code>{user_id}</code> — выдан {granted_at} (админ: <code>{granted_by}</code>)\n",
        "en": "• <code>{user_id}</code> — granted {granted_at} (by: <code>{granted_by}</code>)\n",
    },
    "whitelist_list_empty": {
        "ru": "Список пуст.",
        "en": "The list is empty.",
    },
    "whitelist_placeholder": {
        "ru": "Введите Telegram user_id...",
        "en": "Enter Telegram user_id...",
    },
    "promo_panel": {
        "ru": "🎟 <b>Промокоды</b>\n\nВыберите действие:",
        "en": "🎟 <b>Promo codes</b>\n\nChoose an action:",
    },
    "promo_create_prompt": {
        "ru": (
            "➕ <b>Создание промокода</b>\n\n"
            "Отправьте параметры в формате:\n"
            "<code>дни | тип | user_id или - | дата окончания или - | код или -</code>\n\n"
            "Тип: <code>all</code> или <code>new_only</code>.\n"
            "Дата: <code>YYYY-MM-DD</code>.\n"
            "Код: своё название (буквы, цифры, дефис, до 32 символов) "
            "или <code>-</code> для автогенерации.\n\n"
            "Примеры:\n"
            "<code>7 | new_only | - | - | -</code>\n"
            "<code>30 | all | 123456789 | 2026-12-31 | SUMMER2026</code>"
        ),
        "en": (
            "➕ <b>Create promo code</b>\n\n"
            "Send parameters in this format:\n"
            "<code>days | type | user_id or - | expiration date or - | code or -</code>\n\n"
            "Type: <code>all</code> or <code>new_only</code>.\n"
            "Date: <code>YYYY-MM-DD</code>.\n"
            "Code: custom name (letters, digits, dash, up to 32 chars) "
            "or <code>-</code> for auto-generation.\n\n"
            "Examples:\n"
            "<code>7 | new_only | - | - | -</code>\n"
            "<code>30 | all | 123456789 | 2026-12-31 | SUMMER2026</code>"
        ),
    },
    "promo_create_invalid": {
        "ru": "❌ Неверный формат. Пример: <code>7 | new_only | - | - | -</code>",
        "en": "❌ Invalid format. Example: <code>7 | new_only | - | - | -</code>",
    },
    "promo_create_taken": {
        "ru": "❌ Промокод <code>{code}</code> уже существует.",
        "en": "❌ Promo code <code>{code}</code> already exists.",
    },
    "promo_create_placeholder": {
        "ru": "Например: 7 | new_only | - | - | -",
        "en": "Example: 7 | new_only | - | - | -",
    },
    "promo_created": {
        "ru": (
            "✅ <b>Промокод создан</b>\n\n"
            "Код: <code>{code}</code>\n"
            "Доступ: {days} дн.\n"
            "Аудитория: {audience}\n"
            "Пользователь: {target}\n"
            "Действует до: {expires}"
        ),
        "en": (
            "✅ <b>Promo code created</b>\n\n"
            "Code: <code>{code}</code>\n"
            "Access: {days} day(s)\n"
            "Audience: {audience}\n"
            "User: {target}\n"
            "Valid until: {expires}"
        ),
    },
    "promo_deactivate_prompt": {
        "ru": "➖ Отправьте промокод, который нужно деактивировать.",
        "en": "➖ Send the promo code to deactivate.",
    },
    "promo_deactivated": {
        "ru": "✅ Промокод <code>{code}</code> деактивирован.",
        "en": "✅ Promo code <code>{code}</code> deactivated.",
    },
    "promo_deactivate_not_found": {
        "ru": "❌ Активный промокод <code>{code}</code> не найден.",
        "en": "❌ Active promo code <code>{code}</code> not found.",
    },
    "promo_list_title": {
        "ru": "📋 <b>Промокоды</b>\n\n",
        "en": "📋 <b>Promo codes</b>\n\n",
    },
    "promo_list_row": {
        "ru": (
            "• <code>{code}</code> — {days} дн., {audience}, {status}\n"
            "  Пользователь: {target}; до: {expires}; использован: {redeemed}\n"
        ),
        "en": (
            "• <code>{code}</code> — {days} day(s), {audience}, {status}\n"
            "  User: {target}; until: {expires}; redeemed: {redeemed}\n"
        ),
    },
    "promo_list_empty": {
        "ru": "Промокодов пока нет.",
        "en": "There are no promo codes yet.",
    },
    "promo_audience_all": {"ru": "для всех", "en": "all users"},
    "promo_audience_new_only": {"ru": "для новых", "en": "new users only"},
    "promo_status_active": {"ru": "активен", "en": "active"},
    "promo_status_used": {"ru": "использован", "en": "used"},
    "promo_status_inactive": {"ru": "деактивирован", "en": "deactivated"},
    "promo_status_expired": {"ru": "истёк", "en": "expired"},
    "promo_never": {"ru": "—", "en": "—"},
    "sbp_invoice_created": {
        "ru": "✅ Ссылка на оплату через СБП создана.\n\n📦 {plan}\n\n⏳ На оплату даётся 30 минут.\n\nПерейдите по кнопке ниже для оплаты через QR-код.",
        "en": "✅ SBP payment link created.\n\n📦 {plan}\n\n⏳ You have 30 minutes to pay.\n\nFollow the button below to pay via QR code.",
    },
    "sbp_paid_now": {
        "ru": "✅ Оплата через СБП подтверждена!\n\n📦 {plan}\n⏰ До: {expires}",
        "en": "✅ SBP payment confirmed!\n\n📦 {plan}\n⏰ Until: {expires}",
    },
    "price_range_type": {"ru": "💴 Диапазон цены", "en": "💴 Price range"},
    "all_products_type": {"ru": "🛍️ Все товары", "en": "🛍️ All products"},
    "choose_keyword_filter": {
        "ru": "🔤 Ключевое слово: <b>{keyword}</b>\n\nВыберите вариант поиска:",
        "en": "🔤 Keyword: <b>{keyword}</b>\n\nChoose a search option:",
    },
    "price_filter_prompt": {
        "ru": "💴 <b>Фильтр цены</b>\n\nВыберите, как ограничить цену:",
        "en": "💴 <b>Price filter</b>\n\nChoose how to limit the price:",
    },
    "price_up_to": {"ru": "💴 До цены", "en": "💴 Up to price"},
    "price_from": {"ru": "💴 От цены", "en": "💴 From price"},
    "price_between": {"ru": "💴 От и до", "en": "💴 From and to"},
    "price_name_up_to": {"ru": "до {price} ¥", "en": "up to {price} ¥"},
    "price_name_from": {"ru": "от {price} ¥", "en": "from {price} ¥"},
    "enter_price_max": {
        "ru": "💴 Введите максимальную цену (до) в йенах.\n\nДопустимый диапазон: 300 – 9 999 999 йен.",
        "en": "💴 Enter the maximum price (up to) in yen.\n\nAllowed range: 300 – 9,999,999 yen.",
    },
    "enter_price_min": {
        "ru": "💴 Введите минимальную цену (от) в йенах.\n\nДопустимый диапазон: 300 – 9 999 999 йен.",
        "en": "💴 Enter the minimum price (from) in yen.\n\nAllowed range: 300 – 9,999,999 yen.",
    },
    "enter_price_range": {
        "ru": "💴 Введите диапазон цены в формате <b>от-до</b>.\n\nНапример: 1000-11000\n\nДопустимый диапазон: 300 – 9 999 999 йен.",
        "en": "💴 Enter the price range in the format <b>from-to</b>.\n\nExample: 1000-11000\n\nAllowed range: 300 – 9,999,999 yen.",
    },
    "price_placeholder": {
        "ru": "Введите цену в йенах...",
        "en": "Enter the price in yen...",
    },
    "price_range_placeholder": {
        "ru": "Введите цену от-до, напр. 1000-11000...",
        "en": "Enter price from-to, e.g. 1000-11000...",
    },
    "price_invalid": {
        "ru": "❌ Неверная цена.\n\nВведите целое число в диапазоне 300 – 9 999 999 йен.",
        "en": "❌ Invalid price.\n\nEnter an integer between 300 and 9,999,999 yen.",
    },
    "price_range_invalid": {
        "ru": "❌ Неверный диапазон цены.\n\nВведите в формате <b>от-до</b> (например 1000-11000).\nМинимум 300 йен, максимум 9 999 999 йен.",
        "en": "❌ Invalid price range.\n\nEnter in the format <b>from-to</b> (e.g. 1000-11000).\nMinimum 300 yen, maximum 9,999,999 yen.",
    },
}


def text(key: str, language: str, **values: object) -> str:
    lang: Language = "en" if language == "en" else "ru"
    template = TEXTS[key][lang]
    return template.format(**values)
