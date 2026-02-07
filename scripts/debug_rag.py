import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.getcwd())

load_dotenv()

from database import session, FaqTopic, FaqMessage
from logic.ai_helper import get_ai_helper

async def main():
    print("--- 1. Inspecting DB Content ---")
    topics = session.query(FaqTopic).all()
    print(f"Total Topics: {len(topics)}")
    for t in topics:
        msg_count = len(t.messages)
        content_preview = ""
        if t.messages:
            content_preview = t.messages[0].text[:50] if t.messages[0].text else "[Photo]"
        print(f"ID: {t.id} | Topic: '{t.topic}' | Msgs: {msg_count} | First: {content_preview}")
        
    print("\n--- 2. Testing RAG Retrieval ---")
    query = "сколько дают опыта за хронику жреца"
    print(f"Query: '{query}'")
    
    ai = get_ai_helper()
    if not ai:
        print("Failed to init AI helper")
        return

    # Manually run the embedding and score logic to see raw scores
    query_embedding = await ai.embed_text(query)
    if not query_embedding:
        print("Failed to compute query embedding")
        return
        
    print("Query embedding computed.")
    
    import json
    import math

    def cosine_similarity(v1, v2):
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))
        if magnitude1 == 0 or magnitude2 == 0:
            return 0
        return dot_product / (magnitude1 * magnitude2)

    scored_topics = []
    print("\n--- Scores ---")
    for topic in topics:
        if not topic.embedding:
            print(f"Topic '{topic.topic}' has NO embedding.")
            continue
            
        try:
            topic_embedding = json.loads(topic.embedding)
            score = cosine_similarity(query_embedding, topic_embedding)
            print(f"Topic: '{topic.topic}' | Score: {score:.4f}")
            scored_topics.append((score, topic))
        except Exception as e:
            print(f"Error processing topic {topic.id}: {e}")

    scored_topics.sort(key=lambda x: x[0], reverse=True)
    
    print("\n--- Top 5 Matches ---")
    for score, t in scored_topics[:5]:
        print(f"Score: {score:.4f} | Topic: {t.topic}")

    # Check against current threshold
    threshold = 0.35
    valid_matches = [t for s, t in scored_topics if s > threshold]
    print(f"\nMatches above {threshold}: {len(valid_matches)}")

if __name__ == "__main__":
    asyncio.run(main())
