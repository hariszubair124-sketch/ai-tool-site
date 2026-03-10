import os
from google import genai
from google.genai import types
from datetime import datetime

# 1. Connect to Gemini using your Secret Key
client = genai.Client(api_key=os.environ.get("API_KEY"))

# 2. Tell the AI what to research
prompt = """
Find the top 3 most important AI news stories from the last 24 hours. 
Write a high-quality blog post in HTML.
Include:
- A catchy <h1> title
- A 'Key Takeaways' bullet list
- <h2> headings for each story
- A 'Why it matters' section for each.
Ensure all links are real and functional.
"""


# 3. Run the research with Google Search Grounding
# Note: We added 'v1beta' to the model name so it can find the newest version
response = client.models.generate_content(
    model="gemini-3.1-flash-lite-preview", 
    contents=prompt,
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
)

date_str = datetime.now().strftime("%Y-%m-%d")
filename = f"news-{date_str}.html"

with open(filename, "w", encoding="utf-8") as f:
    f.write(response.text)

print(f"Robot finished! Created {filename}")
