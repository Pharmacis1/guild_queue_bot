from datetime import datetime
import asyncio
from database import AsyncSessionLocal, User, Event, get_msk_now, select
import logging

async def send_db_upload_reminder(bot, time_window_hours: float):
    try:
        async with AsyncSessionLocal() as session:
            # Check freshness
            latest_event_result = await session.execute(
                select(Event).filter(Event.timestamp.isnot(None)).order_by(Event.timestamp.desc())
            )
            latest_event = latest_event_result.scalar_one_or_none()

            now_msk = get_msk_now()
            is_fresh = False

            if latest_event:
                if latest_event.timestamp:
                    from loader import MSK
                    event_time_msk = datetime.fromtimestamp(latest_event.timestamp, tz=MSK).replace(tzinfo=None)
                    diff = now_msk - event_time_msk
                else:
                    try:
                        event_time_msk = datetime.strptime(latest_event.event_date, "%Y-%m-%d %H:%M:%S")
                        diff = now_msk - event_time_msk
                    except:
                        diff = None

                if diff is not None and diff.total_seconds() < time_window_hours * 3600:
                    is_fresh = True
                    logging.info(f"DB is fresh (last update {diff.total_seconds()/60:.1f} mins ago, within {time_window_hours} hour window). Skipping reminder.")
            
            if is_fresh:
                return

            # Find Masters
            masters_result = await session.execute(select(User).filter_by(is_master=True))
            masters = masters_result.scalars().all()
            if not masters:
                return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        text = (
            "🔔 <b>Напоминание!</b>\n\n"
            "Пожалуйста, запустите <code>FactionBoard4-29.exe</code> и проскрольте историю гильдии в игре, "
            "чтобы не потерять события.\n\n"
            "<i>Примерное рекомендуемое время для скролинга истории гильдии:\n"
            "Ежедневно: в 12:00 (до вечернего пика) и в 21:30 (после).\n"
            "По средам (дополнительно): в 18:30 и 20:00(чтобы не потерялись танцы и адепты).</i>"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Инструкция по обновлению сайта", callback_data="instruction_upload_db")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])

        sent_count = 0
        for master in masters:
            try:
                await bot.send_message(
                    chat_id=master.telegram_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as e:
                logging.error(f"Failed to send DB reminder to master {master.telegram_id}: {e}")

        logging.info(f"Sent DB update reminder to {sent_count} masters.")

    except Exception as e:
        logging.error(f"Error in send_db_upload_reminder: {e}", exc_info=True)
