import os
import time
from google import genai
from google.genai import types
from datetime import datetime

# 1. SETUP - Using your correct secret name: API_KEY
api_key = os.environ.get("API_KEY")
client = genai.Client(api_key=api_key)

# 2. THE SEARCH-OPTIMIZED PROMPT
# We tell the AI to use ONE targeted search to save quota
prompt = """
Perform a single Google Search for 'top AI news March 11 2026'.
Based on the results, write an SEO-optimized blog post in HTML.
Include <h1>, <h2>, and <ul> tags. Focus on 'Information Gain'.
"""

def run_robot():
    try:
        print("Attempting generation with Search...")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        
        # 3. SAVE AND UPDATE
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"news-{date_str}.html"
        
        # Simple injection into your template logic
        with open("template.html", "r") as f:
            template = f.read()
            
        final_html = template.replace("{{CONTENT}}", response.text).replace("{{DATE}}", date_str)
        
        with open(filename, "w") as f:
            f.write(final_html)
            
        print(f"Success! Created {filename}")

    except Exception as e:
        print(f"Error occurred: {e}")

run_robot()
