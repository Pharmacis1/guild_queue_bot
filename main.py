import asyncio
import logging
from aiogram import Bot

# Наш новый файл loader, где живут bot, dp и scheduler
from loader import bot, dp, scheduler

# Подключаем роутеры из папки handlers
from handlers import user, admin
from database import init_db, session, ScheduledAnnouncement

# Нужно импортировать функцию schedule_job, чтобы восстановить задачи при старте
# Поскольку она теперь в handlers/admin.py, импортируем оттуда
from handlers.admin import schedule_job

async def on_startup():
    # 1. Настройка команд меню
    from aiogram.types import BotCommand
    await bot.set_my_commands([BotCommand(command="/start", description="🏠 Главное меню")])
    
    # 2. Восстановление задач расписания
    tasks = session.query(ScheduledAnnouncement).filter_by(is_active=True).all()
    count = 0
    for t in tasks:
        if t.schedule_type != 'once_now':
            schedule_job(t, bot)
            count += 1
            
    # 3. Запуск планировщика
    scheduler.start()
    print(f"✅ Bot started. Jobs restored: {count}")

async def main():
    # Подключаем логику
    dp.include_router(user.router)
    dp.include_router(admin.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")