from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import FaqTopic, get_setting
from logic.ai_helper import get_ai_helper
from loader import bot

router = Router()
session = None

@router.message(Command("ask"))
async def cmd_ask(message: types.Message, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await cmd_ask(message, session)
    ai = get_ai_helper()
    if not ai:
        await message.answer("⚠️ AI сервис недоступен.")
        return

    query = message.text.replace("/ask", "").strip()
    if not query:
        await message.answer("ℹ️ Напишите вопрос после команды, например:\n/ask Какой код от сундука по хронике мага?")
        return

    wait_msg = await message.answer("🤖 Думаю...")
    
    # RAG Search
    relevant_topics = await ai.find_relevant_topics(query, session=session)
    
    if not relevant_topics:
        # Check if we have ANY topics
        stmt_count = select(func.count(FaqTopic.id))
        result_count = await session.execute(stmt_count)
        all_count = result_count.scalar()
        
        if all_count == 0:
             await wait_msg.edit_text("⚠️ База знаний пока пуста.")
             return
        
        if all_count < 20:
             stmt_topics = select(FaqTopic).options(selectinload(FaqTopic.messages))
             result_topics = await session.execute(stmt_topics)
             relevant_topics = result_topics.scalars().all()
        else:
             await wait_msg.edit_text("🤔 Не нашел ничего похожего в базе знаний.")
             return

    # Build context
    context_text = ""
    for t in relevant_topics:
        context_text += f"\n--- Topic: {t.topic} ---\n"
        # Since we use selectinload, t.messages should be loaded
        for m in t.messages:
            if m.text:
                context_text += m.text + "\n"
            if m.photo_id:
                context_text += "[Contains Photo]\n"
    
    answer = await ai.get_answer(query, context_text)
    await wait_msg.edit_text(answer)
    
    # Check for photos in the most relevant topic
    if relevant_topics:
        best_topic = relevant_topics[0]
        photos = [m.photo_id for m in best_topic.messages if m.photo_id]
        if photos:
            for pid in photos:
                try:
                    await message.answer_photo(pid, caption=f"📸 Из темы: {best_topic.topic}")
                except Exception as e:
                    print(f"Error sending photo: {e}")

@router.message(Command("summary"))
async def cmd_summary(message: types.Message, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await cmd_summary(message, session)
    ai = get_ai_helper()
    if not ai:
        await message.answer("⚠️ AI сервис недоступен.")
        return
    
    # Restrict to groups only
    if message.chat.type == "private":
        await message.answer("⚠️ Эта команда работает только в группах.")
        return
    
    # Check permissions? Or allow anyone? Request said "bot could make summary... and publish in separate channel chosen by master"
    # Usually summary depends on context.
    
    target_channel_id = await get_setting(session, "summary_channel_id")
    if not target_channel_id:
        await message.answer("⚠️ Канал для публикации саммари не настроен Мастером.")
        return
    
    from logic.chat_logger import get_new_messages, mark_summary_done
    
    # Get messages from DB
    
    db_msgs = await get_new_messages(session, message.chat.id, message.message_thread_id)
    
    if not db_msgs:
        await message.answer("⚠️ Нет новых сообщений для саммари (с момента последнего отчета).")
        return
        
    # Format messages
    msgs = [f"{m.user_name}: {m.text}" for m in db_msgs]
    
    wait_msg = await message.answer("📝 Генерирую саммари...")
    summary = await ai.summarize_chat(msgs)
    
    await wait_msg.delete()
    
        
    # Post to target channel
    try:
        src_link = message.get_url()
        header = f"📰 <b>Саммари обсуждения</b>\nИсточник: <a href='{src_link}'>{message.chat.title}</a>\n\n"
        
        target_thread_id = await get_setting(session, "summary_thread_id")
        # Ensure it's int if present
        if target_thread_id:
            try:
                target_thread_id = int(target_thread_id)
            except ValueError:
                target_thread_id = None
        else:
            target_thread_id = None
            
        await bot.send_message(target_channel_id, header + summary, parse_mode="HTML", message_thread_id=target_thread_id)
        
        # Mark as done
        await mark_summary_done(session, message.chat.id, message.message_thread_id)
        
        await message.answer("✅ Саммари опубликовано в канале.")
    except Exception as e:
        await message.answer(f"❌ Ошибка публикации: {e}")

# Catch-all to log messages
@router.message(F.text & ~F.command)
async def log_messages(message: types.Message, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await log_messages(message, session)
    # Determine user name
    name = message.from_user.first_name
    if message.from_user.last_name:
        name += f" {message.from_user.last_name}"
    
    # Use database logger
    thread_id = message.message_thread_id
    from logic.chat_logger import log_message
    
    # Run in executor to avoid blocking? SQLAlchemy session is sync, but small write is fast.
    # Ideally should be async or in background task.
    # For now, keep it simple.
    await log_message(
        session=session,
        chat_id=message.chat.id,
        thread_id=thread_id,
        user_id=message.from_user.id,
        user_name=name,
        text=message.text
    )
