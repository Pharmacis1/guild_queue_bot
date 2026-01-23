![AI Assisted](https://img.shields.io/badge/AI-Assisted-blue?style=flat-square&logo=openai)
# Guild Queue Bot 🛡️

Телеграм-бот с веб-интерфейсом для управления очередями, событиями и банком гильдии в MMORPG (Perfect World).

Помогает автоматизировать запись на ивенты (УФ, КХ, Метеориты), распределение наград, уведомления и ведение учета активности.

## 🚀 Основные возможности (Features)

### 🤖 Telegram Bot
*   **Система очередей:** Запись в очереди с лимитами (УФ, Метеориты, КХ и другие).
*   **Мультиаккаунтинг:** Привязка нескольких персонажей (Основа + Твины) к одному аккаунту.
*   **Интеграция с Google Sheets:** Авто-валидация никнеймов по таблице гильдии.
*   **Уведомления:** Напоминания о событиях по расписанию (Cron/APScheduler).
*   **Админка:** Управление очередями, массовая выдача наград, логирование действий.

### 🌐 Web Interface (FastAPI)
*   **Панель управления:** Удобный просмотр статистики и списков через браузер.
*   **Парсинг цен (Playwright):** Автоматический мониторинг цен на предметы с комиссионки (парсинг `pwdatabase`/`pwcats`).
*   **Визуализация:** Отображение иконок предметов и аватарок классов.

### 🛠️ Надежность и Деплой
*   **Docker & Docker Compose:** Простой и быстрый запуск в контейнерах.
*   **Авто-бекапы:** Ежедневное резервное копирование базы данных (`guild_bot.db`) в папку `backups/`.
*   **Reverse Proxy:** Настроен `Caddy` для автоматического HTTPS (опционально) и маршрутизации.

## 🛠 Технологический стек (Tech Stack)

*   **Core:** Python 3.10+
*   **Bot Framework:** aiogram 3.x (асинхронный)
*   **Web Backend:** FastAPI + Uvicorn
*   **Brouser Automation:** Playwright (для парсинга)
*   **Database:** SQLite + SQLAlchemy (Async ORM)
*   **Scheduler:** APScheduler
*   **Deployment:** Docker, Docker Compose, Caddy

## 📦 Быстрый старт (Docker) - Рекомендуется

Для запуска вам понадобится установленный **Docker** и **Docker Compose**.

1.  **Клонируйте репозиторий:**
    ```bash
    git clone https://github.com/Pharmacis1/guild_queue_bot.git
    cd guild_queue_bot
    ```

2.  **Настройка окружения:**
    *   Создайте файл `.env`. Пример переменных:
        ```env
        BOT_TOKEN=ваш_телеграм_токен
        WEB_PORT=8081
        # Другие настройки при необходимости
        ```
    *   Положите файл `credentials.json` (Google Service Account) в корень проекта для доступа к таблицам.

3.  **Запуск:**
    ```bash
    docker compose up -d --build
    ```

Бот запустится в фоне. 
*   Бот доступен в Telegram.
*   Веб-интерфейс доступен по адресу: `http://localhost`.

## 🔧 Ручная установка (для разработки)

Если вы хотите запустить проект без Docker (например, для отладки):

1.  **Установите зависимости:**
    ```bash
    pip install -r requirements.txt
    playwright install chromium  # Важно для работы парсера
    ```

2.  **Запуск:**
    ```bash
    python main.py
    ```

## 📝 Лицензия
Project is open for educational purposes.