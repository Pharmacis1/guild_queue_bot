import os
import asyncio
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

async def main():
    client = genai.Client(api_key=api_key)
    model_id = "gemini-2.0-flash-lite" 

    # 1. RAG Scenario
    # 3 typical FAQ topics (~150 words each) + Question
    faq_stub = "This is a sample FAQ topic about guild raids. " * 10 # ~80 tokens
    context = f"Topic 1: {faq_stub}\nTopic 2: {faq_stub}\nTopic 3: {faq_stub}"
    question = "How do I join the raid and what are the requirements?"
    rag_prompt = f"Context:\n{context}\n\nQuestion: {question}"
    
    rag_res = await client.aio.models.count_tokens(model=model_id, contents=rag_prompt)
    print(f"RAG Request (3 Topics + Q): {rag_res.total_tokens} tokens")
    
    # 2. Summary Scenario
    # 50 messages of casual chat (~15 words each)
    chat_stub = "User: Hello, does anyone know when the event starts? I need to prepare my gear."
    chat_history = "\n".join([chat_stub for _ in range(50)])
    summary_prompt = f"Summarize this:\n{chat_history}"
    
    sum_res = await client.aio.models.count_tokens(model=model_id, contents=summary_prompt)
    print(f"Summary Request (50 Messages): {sum_res.total_tokens} tokens")
    
    # Analysis
    print("-" * 30)
    print(f"RAG Capacity at 15k TPM: {15000 / rag_res.total_tokens:.1f} request/min")
    print(f"Summary Capacity at 15k TPM: {15000 / sum_res.total_tokens:.1f} request/min")

if __name__ == "__main__":
    asyncio.run(main())
