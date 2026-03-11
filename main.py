import os
import time
import random
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("API_KEY"))

def run_with_search_and_retry(prompt, attempts=3):
    for i in range(attempts):
        try:
            print(f"Attempt {i+1}: Calling Gemini with Search...")
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            return response.text
        except Exception as e:
            if "429" in str(e):
                # If we hit the limit, wait 60 seconds + a random bit of "jitter"
                wait_time = 60 + random.randint(1, 30)
                print(f"Quota hit. Waiting {wait_time}s before retrying...")
                time.sleep(wait_time)
            else:
                raise e
    return "Could not fetch news today due to Google Search limits."

# Use the function
news_content = run_with_search_and_retry("Find today's top 3 AI news stories.")
