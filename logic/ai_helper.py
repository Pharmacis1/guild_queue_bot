
import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

from collections import deque

class MessageCache:
    def __init__(self, max_len=50):
        self.cache = {}  # Key: (chat_id, thread_id), Value: deque of strings
        self.max_len = max_len

    def add_message(self, chat_id, thread_id, user_name, text):
        key = (chat_id, thread_id)
        if key not in self.cache:
            self.cache[key] = deque(maxlen=self.max_len)
        
        # Format: "User: Message"
        self.cache[key].append(f"{user_name}: {text}")

    def get_messages(self, chat_id, thread_id):
        key = (chat_id, thread_id)
        return list(self.cache.get(key, []))

# Global Cache
message_cache = MessageCache()

from sqlalchemy.ext.asyncio import AsyncSession
from google import genai
from google.genai import types

class GeminiHelper:
    def __init__(self):
        # Support both naming conventions
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY (or GOOGLE_API_KEY) not found in environment variables")
        
        self.client = genai.Client(api_key=api_key)
        
        # Using Gemini 2.5 Flash as requested (Paid Plan) - Primary
        self.model_name = 'gemini-2.5-flash'
        
        # Priority list of models to try
        self.models_to_try = [
            'gemini-2.5-flash',       # Primary (Paid, High Quota)
            'gemini-2.0-flash-lite',  # Backup 1 (Fast)
            'gemma-3-27b-it',         # Backup 2 (Deep Reserve)
        ]
        
        # Simple in-memory cache: {query_hash: (answer, timestamp)}
        self._answer_cache = {}

    async def get_answer(self, question: str, context: str) -> str:
        """
        Generates an answer to the question based on the provided context (FAQ topics).
        """
        # 1. Check Cache
        clean_q = question.strip().lower()
        if clean_q in self._answer_cache:
            print(f"✨ Returning cached answer for: {clean_q}")
            return self._answer_cache[clean_q]

        prompt = f"""
You are a helpful assistant for a game guild. Answer the user's question using ONLY the provided context.
If the answer is not in the context, say "I don't have information about that yet."

IMPORTANT: You must ALWAYS answer in RUSSIAN language, regardless of the language of the question or context.
Tone: Friendly, helpful, concise.

Context:
{context}

Question: {question}
"""
        last_error = None
        
        # Try models in sequence
        for model in self.models_to_try:
            try:
                # print(f"Trying model: {model}...")
                response = await self.client.aio.models.generate_content(
                    model=model,
                    contents=prompt
                )
                answer = response.text
                
                # 2. Save to Cache (if successful)
                self._answer_cache[clean_q] = answer
                return answer
                
            except Exception as e:
                error_msg = str(e)
                if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "503" in error_msg or "UNAVAILABLE" in error_msg:
                    print(f"Model {model} exhausted or overloaded. Switching...")
                    last_error = e
                    continue
                else:
                    # If it's another error (e.g. bad request), fail immediately
                    return f"Error with model {model}: {e}"
        
        # If we ran out of models
        if last_error:
            error_msg = str(last_error)
            import re
            match = re.search(r"retry in (\d+(\.\d+)?)s", error_msg)
            seconds = match.group(1) if match else "60"
            try:
                seconds = str(int(float(seconds)) + 1)
            except:
                pass
            return f"🥵 Все модели перегрелись! (Даже запасные). Отдыхаем {seconds} сек."
            
        return "⚠️ Не удалось получить ответ от нейросети."

    async def summarize_chat(self, messages: list[str]) -> str:
        """
        Summarizes a list of chat messages.
        """
        if not messages:
            return "No messages to summarize."
            
        chat_text = "\n".join(messages)
        
        prompt = f"""
        You are a helpful and chill assistant for a game guild "Arahnius". 
        Summarize the following conversation in RUSSIAN language.
        
        Tone: Informal, friendly, gamer-style. Avoid corporate speak. 
        Use standard HTML tags ONLY: <b>, <i>, <u>, <s>, <code>, <pre>.
        Do NOT use Markdown.
        
        Structure the summary as:
        <b>🗣 О чем болтали:</b>
        - (Key topics discussed)
        
        <b>🌡 Атмосфера:</b>
        - (Overall vibe: friendly, tense, joking, or raid-focused)
        
        <b>✅ До чего договорились:</b>
        - (Decisions made, if any)
        
        <b>⚔️ Планы и действия:</b>
        - (Action items, raids, events)
        
        <b>👀 Мемасики:</b>
        - (Funny moments, off-topic, or drama - keep it brief)
        
        Context messages:
        {chat_text}
        """
        
        last_error = None
        
        for model in self.models_to_try:
            try:
                response = await self.client.aio.models.generate_content(
                    model=model,
                    contents=prompt
                )
                return self.sanitize_html(response.text)
                
            except Exception as e:
                error_msg = str(e)
                if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "503" in error_msg or "UNAVAILABLE" in error_msg:
                    print(f"Model {model} exhausted or overloaded. Switching...")
                    last_error = e
                    continue
                else:
                    return f"Error with model {model}: {e}"
        
        if last_error:
            error_msg = str(last_error)
            import re
            match = re.search(r"retry in (\d+(\.\d+)?)s", error_msg)
            seconds = match.group(1) if match else "60"
            try:
                seconds = str(int(float(seconds)) + 1)
            except:
                pass
            return f"🥵 Слишком много болтали! (Все модели заняты). Отдыхаем {seconds} сек."
            
        return "⚠️ Не удалось создать саммари (все модели недоступны)."

    def sanitize_html(self, text: str) -> str:
        # Simple sanitizer to remove unsupported tags
        import re
        # Remove <p> and </p>, replace </p> with double newline for spacing
        text = text.replace("</p>", "\n\n").replace("<p>", "")
        text = text.replace("<br>", "\n").replace("<br/>", "\n")
        # Remove <ul> <ol> <li>, usually standard text structure is enough
        text = text.replace("<ul>", "").replace("</ul>", "")
        text = text.replace("<ol>", "").replace("</ol>", "")
        text = text.replace("<li>", "- ").replace("</li>", "")
        # Remove headers
        text = re.sub(r"<h[1-6]>", "<b>", text)
        text = re.sub(r"</h[1-6]>", "</b>\n", text)
        return text

    async def embed_text(self, text: str) -> list[float]:
        """
        Computes the embedding vector for the given text.
        """
        try:
            # New SDK usage for embeddings
            # Model: 'gemini-embedding-001' is the available model for this key
            result = await self.client.aio.models.embed_content(
                model="gemini-embedding-001",
                contents=text
            )
            return result.embeddings[0].values
        except Exception as e:
            print(f"Error computing embedding: {e}")
            return []

    async def find_relevant_topics(self, query: str, session: Optional[AsyncSession] = None, limit: int = 15):
        """
        Finds the most relevant topics for the query using Cosine Similarity.
        """
        from database import FaqTopic, select, AsyncSessionLocal
        import json
        import math

        if session is None:
            async with AsyncSessionLocal() as temp_session:
                return await self._find_relevant_topics_impl(temp_session, query, limit)
        return await self._find_relevant_topics_impl(session, query, limit)

    async def _find_relevant_topics_impl(self, session, query, limit):
        from database import FaqTopic, select
        import json
        import math
        
        query_embedding = await self.embed_text(query)
        if not query_embedding:
            return []

        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(FaqTopic).options(selectinload(FaqTopic.messages)).filter(FaqTopic.embedding.isnot(None))
        )
        topics = result.scalars().all()
        scored_topics = []

        def cosine_similarity(v1, v2):
            dot_product = sum(a * b for a, b in zip(v1, v2))
            magnitude1 = math.sqrt(sum(a * a for a in v1))
            magnitude2 = math.sqrt(sum(b * b for b in v2))
            if magnitude1 == 0 or magnitude2 == 0:
                return 0
            return dot_product / (magnitude1 * magnitude2)

        # Calculate all scores first
        for topic in topics:
            try:
                topic_embedding = json.loads(topic.embedding)
                score = cosine_similarity(query_embedding, topic_embedding)
                scored_topics.append((score, topic))
            except Exception:
                continue

        # Sort by score DESC
        scored_topics.sort(key=lambda x: x[0], reverse=True)
        
        if len(scored_topics) <= limit:
             return [t[1] for t in scored_topics]

        filtered_topics = []
        for score, topic in scored_topics:
            if score > 0.25:
                filtered_topics.append(topic)
                
        return filtered_topics[:limit]

# Global instance
ai_helper = None

def get_ai_helper():
    global ai_helper
    if ai_helper is None:
        try:
            ai_helper = GeminiHelper()
        except ValueError as e:
            print(f"AI Helper init failed: {e}")
            return None
    return ai_helper
