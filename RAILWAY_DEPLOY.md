# Деплой на Railway

## Быстрый старт

### 1. Создайте проект на Railway

1. Зайдите на [railway.com](https://railway.com) и авторизуйтесь
2. Нажмите **New Project** → **Deploy from GitHub repo**
3. Выберите этот репозиторий

### 2. Настройте переменные окружения

В настройках сервиса (Variables) добавьте следующие переменные:

| Переменная | Обязательная | Описание | Пример |
|------------|--------------|----------|--------|
| `BOT_TOKEN` | ✅ | Токен Telegram бота от @BotFather | `123456:ABC-DEF...` |
| `ADMIN_IDS` | ✅ | ID администраторов через запятую | `123456789,987654321` |
| `REQUIRED_CHANNEL` | ✅ | Username канала для проверки подписки | `@your_channel` |
| `SUPABASE_URL` | ⚠️ | URL вашего Supabase проекта | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | ⚠️ | Anon/Service key Supabase | `eyJ...` |
| `RATE_LIMIT_REQUESTS` | ❌ | Лимит запросов в час (по умолчанию: 5) | `5` |
| `RATE_LIMIT_HOURS` | ❌ | Период лимита в часах (по умолчанию: 1) | `1` |
| `MAX_REVIEWS` | ❌ | Максимум отзывов (по умолчанию: 1000) | `1000` |
| `MAX_QUESTIONS` | ❌ | Максимум вопросов (по умолчанию: 1000) | `1000` |
| `PARSER_HEADLESS` | ❌ | Headless режим браузера (по умолчанию: True) | `True` |
| `PARSER_TIMEOUT` | ❌ | Таймаут парсера в мс (по умолчанию: 60000) | `60000` |

⚠️ = Рекомендуется для production (локальная SQLite база не сохраняется при рестарте)

### 3. Деплой

После добавления переменных Railway автоматически:
1. Соберёт Docker образ
2. Запустит бота

## Структура проекта для Railway

```
├── railway.json      # Конфигурация Railway
├── Dockerfile        # Сборка Docker образа
├── .railwayignore    # Файлы, исключённые из деплоя
├── requirements.txt  # Python зависимости
└── bot.py           # Точка входа
```

## Особенности деплоя

### Playwright в Docker
Dockerfile настроен для корректной работы Playwright с Chromium:
- Установлены все системные зависимости
- Chromium установлен с флагом `--with-deps`
- Headless режим включен по умолчанию

### База данных
- **Локальная SQLite** (`bot_data.db`): Не сохраняется между рестартами
- **Рекомендация**: Используйте Supabase для production (уже интегрировано в проект)

### Логирование
Логи доступны в Railway Dashboard → Logs

## Мониторинг

### В Railway Dashboard:
- **Logs**: Логи в реальном времени
- **Metrics**: CPU, RAM, Network usage
- **Deployments**: История деплоев с возможностью rollback

### Полезные команды Railway CLI:
```bash
# Установка CLI
npm install -g @railway/cli

# Логин
railway login

# Просмотр логов
railway logs

# Переменные окружения
railway variables
```

## Troubleshooting

### Бот не запускается
1. Проверьте логи в Railway Dashboard
2. Убедитесь, что `BOT_TOKEN` указан корректно
3. Проверьте, что бот не запущен где-то ещё (конфликт polling)

### Ошибки Playwright
1. Убедитесь, что `PARSER_HEADLESS=True`
2. Проверьте логи на ошибки Chromium
3. Playwright требует много памяти — рассмотрите upgrade плана

### Ошибки подписки на канал
1. Бот должен быть администратором канала `REQUIRED_CHANNEL`
2. Канал должен быть публичным или бот должен быть участником

## Стоимость

Railway предлагает:
- **Trial**: $5 кредитов бесплатно
- **Hobby**: $5/месяц + usage
- **Pro**: $20/месяц + usage

Для Telegram бота с Playwright рекомендуется минимум **Hobby** план.
