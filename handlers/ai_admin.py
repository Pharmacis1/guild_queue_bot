from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database import session, User, FaqTopic, Settings, get_setting, set_setting
from states import AIAdminStates
from keyboards import get_back_btn, get_main_menu, get_master_ai_menu
from loader import bot

router = Router()

def is_master(user_id):
    u = session.query(User).filter_by(telegram_id=user_id).first()
    return u and u.is_master

@router.callback_query(F.data == "m_menu_ai")
async def open_ai_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🤖 **AI & FAQ Управление**", reply_markup=get_master_ai_menu(), parse_mode="Markdown"
    )

@router.callback_query(F.data == "m_ai_add")
async def cb_add_topic(callback: types.CallbackQuery, state: FSMContext):
    if not is_master(callback.from_user.id):
        return
    await callback.message.edit_text("✍️ Введите название темы (вопрос):", reply_markup=get_back_btn("m_menu_ai"))
    await state.set_state(AIAdminStates.waiting_for_topic)

@router.callback_query(F.data == "m_ai_list")
async def cb_list_topics(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id):
        return
    topics = session.query(FaqTopic).all()
    
    text = "📚 <b>Список тем FAQ:</b>\n"
    if not topics:
        text += "Список пуст."
    else:
        for t in topics:
            text += f"ID: <code>{t.id}</code> | <b>{t.topic}</b>\n"
    
    text += "\n<i>Для удаления/редактирования используйте команды:\n/delete_topic ID\n/edit_topic ID</i>"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("m_menu_ai"))

@router.callback_query(F.data == "m_ai_set_channel")
async def cb_set_channel(callback: types.CallbackQuery):
    await callback.answer("Используйте команду /set_summary_channel в целевом канале.", show_alert=True)


@router.message(Command("add_topic"))
async def cmd_add_topic(message: types.Message, state: FSMContext):
    if not is_master(message.from_user.id):
        return
    await message.answer("✍️ Введите название темы (вопрос):", reply_markup=get_back_btn())
    await state.set_state(AIAdminStates.waiting_for_topic)

@router.message(AIAdminStates.waiting_for_topic)
async def process_topic(message: types.Message, state: FSMContext):
    await state.update_data(topic_name=message.text, messages=[])
    await message.answer(
        "📝 Теперь присылайте контент (текст, фото).\n"
        "Вы можете прислать несколько сообщений подряд.\n"
        "Когда закончите, напишите /done."
    )
    await state.set_state(AIAdminStates.waiting_for_content)

@router.message(AIAdminStates.waiting_for_content)
async def process_content(message: types.Message, state: FSMContext):
    # Check for completion command
    if message.text == "/done":
        data = await state.get_data()
        topic_name = data.get('topic_name')
        messages_data = data.get('messages', [])
        
        if not messages_data:
            await message.answer("⚠️ Вы не добавили ни одного сообщения. Тема не создана.")
            await state.clear()
            return

        wait_msg = await message.answer("💾 Сохраняю тему и генерирую эмбеддинги...")
        
        # 1. Prepare full text for embedding
        full_text = f"Topic: {topic_name}\n"
        for m in messages_data:
            if m.get('text'):
                full_text += m['text'] + "\n"
            if m.get('photo'):
                full_text += "[Photo]\n"
        
        # 2. Compute embedding
        from logic.ai_helper import get_ai_helper
        ai = get_ai_helper()
        embedding = []
        if ai:
            embedding = await ai.embed_text(full_text)
            
        import json
        embedding_json = json.dumps(embedding) if embedding else None
        
        # 3. Save to DB
        new_topic = FaqTopic(
            topic=topic_name,
            created_by=message.from_user.id,
            embedding=embedding_json
        )
        session.add(new_topic)
        session.flush() # get ID
        
        # 4. Save messages
        from database import FaqMessage
        for i, m in enumerate(messages_data):
            faq_msg = FaqMessage(
                topic_id=new_topic.id,
                text=m.get('text'),
                photo_id=m.get('photo'),
                order_index=i
            )
            session.add(faq_msg)
            
        session.commit()
        
        await wait_msg.edit_text(
            f"✅ Тема '{topic_name}' успешно создана! ({len(messages_data)} сообщений)",
            reply_markup=get_main_menu(session.query(User).filter_by(telegram_id=message.from_user.id).first())
        )
        await state.clear()
        return

    # User sent a message content
    data = await state.get_data()
    msgs = data.get('messages', [])
    
    new_msg = {}
    if message.caption:
        new_msg['text'] = message.caption
    elif message.text:
        new_msg['text'] = message.text
        
    if message.photo:
        # Get largest photo
        new_msg['photo'] = message.photo[-1].file_id
        
    if not new_msg:
        await message.answer("⚠️ Тип сообщения не поддерживается (пришлите текст или фото).")
        return

    msgs.append(new_msg)
    await state.update_data(messages=msgs)
    await message.answer(f"➕ Сообщение добавлено (всего: {len(msgs)}). Напишите /done для завершения.")

@router.message(Command("list_topics"))
async def cmd_list_topics(message: types.Message):
    if not is_master(message.from_user.id):
        return
    topics = session.query(FaqTopic).all()
    if not topics:
        await message.answer("Список тем пуст.")
        return
    
    text = "📚 <b>Список тем FAQ:</b>\n\n"
    for t in topics:
        text += f"ID: <code>{t.id}</code> | <b>{t.topic}</b>\n"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("delete_topic"))
async def cmd_delete_topic(message: types.Message):
    if not is_master(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: /delete_topic <ID>")
        return
    
    try:
        tid = int(args[1])
        t = session.get(FaqTopic, tid)
        if t:
            session.delete(t)
            session.commit()
            await message.answer(f"🗑 Тема ID {tid} удалена.")
        else:
            await message.answer("❌ Тема не найдена.")
    except ValueError:
        await message.answer("⚠️ ID должен быть числом.")

@router.message(Command("edit_topic"))
async def cmd_edit_topic(message: types.Message, state: FSMContext):
    if not is_master(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: /edit_topic <ID>")
        return
    
    try:
        tid = int(args[1])
        t = session.get(FaqTopic, tid)
        if t:
            await state.update_data(edit_id=tid)
            await message.answer(f"Редактирование темы: <b>{t.topic}</b>\n\nВведите новое содержание:", parse_mode="HTML", reply_markup=get_back_btn())
            await state.set_state(AIAdminStates.waiting_for_edit_content)
        else:
            await message.answer("❌ Тема не найдена.")
    except ValueError:
        await message.answer("⚠️ ID должен быть числом.")

@router.message(AIAdminStates.waiting_for_edit_content)
async def process_edit_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['edit_id']
    t = session.get(FaqTopic, tid)
    if t:
        t.content = message.text
        session.commit()
        await message.answer("✅ Тема обновлена.", reply_markup=get_main_menu(session.query(User).filter_by(telegram_id=message.from_user.id).first()))
    else:
        await message.answer("❌ Ошибка: тема не найдена.")
    await state.clear()

@router.message(Command("set_summary_channel"))
async def cmd_set_summary_channel(message: types.Message):
    if not is_master(message.from_user.id):
        return
    
    # If used in the target channel, just set it
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    
    set_setting("summary_channel_id", str(chat_id))
    if thread_id:
        set_setting("summary_thread_id", str(thread_id))
    else:
        set_setting("summary_thread_id", "")
        
    target = f"{message.chat.title} (ID: {chat_id})"
    if thread_id:
        target += f" [Topic: {thread_id}]"
        
    await message.answer(f"✅ Канал для саммари установлен: {target}")

@router.message(Command("save_faq"))
async def cmd_save_faq(message: types.Message):
    if not is_master(message.from_user.id):
        return

    if not message.reply_to_message:
        await message.answer("⚠️ Используйте эту команду в ответ на сообщение, которое хотите сохранить.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Укажите название темы: /save_faq Название темы")
        return
        
    topic_name = args[1]
    reply = message.reply_to_message
    
    # Extract content
    text = reply.caption if reply.caption else reply.text
    photo_id = reply.photo[-1].file_id if reply.photo else None
    
    if not text and not photo_id:
         await message.answer("⚠️ Сообщение пустое (нет текста и фото).")
         return

    wait_msg = await message.answer("💾 Сохраняю...")

    # Embed
    full_text = f"Topic: {topic_name}\n"
    if text: full_text += text
    if photo_id: full_text += "\n[Photo]"

    from logic.ai_helper import get_ai_helper
    ai = get_ai_helper()
    embedding = []
    if ai:
        embedding = await ai.embed_text(full_text)
    
    import json
    embedding_json = json.dumps(embedding) if embedding else None
    
    # Save
    new_topic = FaqTopic(
        topic=topic_name,
        created_by=message.from_user.id,
        embedding=embedding_json
    )
    session.add(new_topic)
    session.flush()
    
    from database import FaqMessage
    faq_msg = FaqMessage(
        topic_id=new_topic.id,
        text=text,
        photo_id=photo_id,
        order_index=0
    )
    session.add(faq_msg)
    session.commit()
    
    await wait_msg.edit_text(f"✅ Тема '{topic_name}' быстро сохранена!")
