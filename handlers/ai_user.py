from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database import session, FaqTopic, get_setting
from logic.ai_helper import get_ai_helper
from loader import bot

router = Router()

@router.message(Command("ask"))
async def cmd_ask(message: types.Message):
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
    relevant_topics = await ai.find_relevant_topics(query)
    
    if not relevant_topics:
        # Fallback to all topics if few? Or just say empty.
        # If DB has no embeddings yet, we might want to fallback to simple search?
        # For now, let's assume if no relevant found, we use all (if list is small) or fail.
        # But find_relevant_topics returns empty if query_embedding fails or no topics.
        
        # Check if we have ANY topics
        all_count = session.query(FaqTopic).count()
        if all_count == 0:
             await wait_msg.edit_text("⚠️ База знаний пока пуста.")
             return
        
        # If we have topics but RAG failed (maybe no embeddings yet), use legacy method?
        # Or just tell user "I don't know".
        # Let's try to fetch all if < 20 topics (legacy mode for small DB)
        if all_count < 20:
             relevant_topics = session.query(FaqTopic).all()
        else:
             await wait_msg.edit_text("🤔 Не нашел ничего похожего в базе знаний.")
             return

    # Build context
    context_text = ""
    for t in relevant_topics:
        context_text += f"\n--- Topic: {t.topic} ---\n"
        # Load messages
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
        # logic: if the answer seems positive, maybe show photo?
        # Simple approach: If topic has photos, send them.
        photos = [m.photo_id for m in best_topic.messages if m.photo_id]
        if photos:
            for pid in photos:
                try:
                    await message.answer_photo(pid, caption=f"📸 Из темы: {best_topic.topic}")
                except Exception as e:
                    print(f"Error sending photo: {e}")

@router.message(Command("summary"))
async def cmd_summary(message: types.Message):
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
    
    target_channel_id = get_setting("summary_channel_id")
    if not target_channel_id:
        await message.answer("⚠️ Канал для публикации саммари не настроен Мастером.")
        return
    
    from logic.chat_logger import get_new_messages, mark_summary_done
    
    # Get messages from DB
    
    db_msgs = get_new_messages(message.chat.id, message.message_thread_id)
    
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
        
        target_thread_id = get_setting("summary_thread_id")
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
        mark_summary_done(message.chat.id, message.message_thread_id)
        
        await message.answer("✅ Саммари опубликовано в канале.")
    except Exception as e:
        await message.answer(f"❌ Ошибка публикации: {e}")

# Catch-all to log messages
@router.message(F.text & ~F.command)
async def log_messages(message: types.Message):
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
    log_message(
        chat_id=message.chat.id,
        thread_id=thread_id,
        user_id=message.from_user.id,
        user_name=name,
        text=message.text
    )
