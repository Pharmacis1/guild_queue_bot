import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.ai_helper import get_ai_helper

async def main():
    print(f"CWD: {os.getcwd()}")
    env_path = os.path.join(os.getcwd(), '.env')
    print(f"Env exists: {os.path.exists(env_path)}")
    
    print("Initializing AI Helper...")
    ai = get_ai_helper()
    if not ai:
        print("[FAIL] Failed to init AI Helper (Check API Key)")
        return

    print("Listing Models:")
    try:
        # ai.client is the genai.Client instance
        for m in ai.client.models.list():
            print(f"- {m.name}")
    except Exception as e:
        print(f"[ERROR] List models failed: {e}")

    print("Testing Generation...")
    response = await ai.get_answer("Overview", "This is a test context about a guild bot.")
    print(f"Response: {response}")
    
    if "Error" not in response:
        print("[PASS] API Test Passed")
    else:
        print("[WARN] API Test Warning")

if __name__ == "__main__":
    asyncio.run(main())
