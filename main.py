import os
import time
from google import genai
from google.genai import types
from datetime import datetime

# 1. Setup
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# 2. The Task
prompt = "Write a 300-word blog post in HTML about the latest AI news from March 2026."

# 3. The "Retry" Loop (Fixes 429 Errors)
def run_with_retry(max_attempts=3):
    for attempt in range(max_attempts):
        try:
            print(f"Attempt {attempt + 1}: Generating content...")
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview", 
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "429" in str(e):
                print("Server busy (429). Waiting 30 seconds to try again...")
                time.sleep(30)
            else:
                raise e
    return "Failed to generate content after several attempts."

# 4. Save the result
content = run_with_retry()
date_str = datetime.now().strftime("%Y-%m-%d")
filename = f"news-{date_str}.html"

with open(filename, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Finished! Created {filename}")
