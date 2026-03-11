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
prompt = "Perform a Google Search for 'top news {today}'. Based on the results, write an SEO-optimized blog post in HTML."
# ... (inside your run_robot function)

# 1. Create a unique timestamp
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 2. Add a hidden SEO comment at the bottom to force a 'change' for Git
final_content = response.text + f"\n\n"

# 3. Save the file
with open(filename, "w", encoding="utf-8") as f:
    f.write(final_content)

print(f"File {filename} saved with unique timestamp: {timestamp}")

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
