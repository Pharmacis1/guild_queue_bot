import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from sqlalchemy import text

# Add project root to sys.path
sys.path.append(os.getcwd())

load_dotenv()

from database import session, FaqTopic, FaqMessage
from logic.ai_helper import get_ai_helper

async def main():
    print("--- Fixing Missing Embeddings ---")
    
    ai = get_ai_helper()
    if not ai:
        print("Failed to init AI helper")
        return

    # Find topics with no embedding or empty embedding
    topics = session.query(FaqTopic).filter((FaqTopic.embedding.is_(None)) | (FaqTopic.embedding == '[]')).all()
    print(f"Found {len(topics)} topics needing embeddings.")
    
    for t in topics:
        print(f"Processing Topic ID {t.id}: '{t.topic}'")
        
        # Reconstruct full text
        full_text = f"Topic: {t.topic}\n"
        for m in t.messages:
            if m.text:
                full_text += m.text + "\n"
            if m.photo_id:
                full_text += "[Photo]\n"
        
        # Compute
        print(f"  - Computing embedding for {len(full_text)} chars...")
        try:
            emb = await ai.embed_text(full_text)
            if emb:
                t.embedding = json.dumps(emb)
                session.commit()
                print("  - Saved!")
            else:
                print("  - Failed (returned empty)")
        except Exception as e:
            print(f"  - Error: {e}")
            
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
