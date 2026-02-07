from dotenv import load_dotenv
import os
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("Error: API KEY not found")
else:
    client = genai.Client(api_key=api_key)
    try:
        # Use sync client for script
        print("Listing models...")
        for m in client.models.list(config={"query_base": True}):
             print(f"Model: {m.name}")
    except Exception as e:
        print(f"Error: {e}")
