import os
from google import genai
from google.genai import types
from datetime import datetime

# 1. Setup
client = genai.Client(api_key=os.environ.get("API_KEY"))

# 2. Get Today's Date Dynamically
today = datetime.now().strftime("%B %d, %Y") 

# 3. The Dynamic Prompt
# Now the date changes every single time the script runs!
prompt = f"Perform a Google Search for 'top AI news {today}'. Based on the results, write an SEO-optimized blog post in HTML."

def run_robot():
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        
        # ... (rest of the slugify and saving logic goes here)
        print(f"Robot successfully researched news for {today}")
        
    except Exception as e:
        print(f"Error: {e}")

run_robot()
