import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

try:
    print("Fetching https://pwobs.com/capella/players/4208 ...")
    response = requests.get("https://pwobs.com/capella/players/4208", headers=headers, timeout=10)
    print(f"Status: {response.status_code}")

    if "player-equipment" in response.text:
        print("SUCCESS: Found 'player-equipment' in HTML response.")
        print("SSR is WORKING.")
    else:
        print("FAILURE: 'player-equipment' NOT found in HTML response.")
        print("Content might be CSR (Client Side Rendered).")
        print("Partial content preview:")
        print(response.text[:500])

except Exception as e:
    print(f"Error: {e}")
