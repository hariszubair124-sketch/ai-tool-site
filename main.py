import os
from google import genai
from google.genai import types
from datetime import datetime

# Setup
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# SEO Prompt with Search Grounding
prompt = "Find the top AI news from today, March 11, 2026. Write a detailed blog post with 3 main sections. Use <h2> for headers. Focus on facts and industry impact."

def run_news_bot():
    # 1. Fetch Today's News with Search Grounding
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    
    # 2. Extract Data
    full_text = response.text
    title = full_text.split('\n')[0].replace('#', '').strip()
    description = f"Latest AI updates for {datetime.now().strftime('%B %d, %Y')}: {title[:100]}..."
    
    # 3. Inject into Template
    with open("template.html", "r") as f:
        html_output = f.read()
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    html_output = html_output.replace("{{TITLE}}", title)
    html_output = html_output.replace("{{DESCRIPTION}}", description)
    html_output = html_output.replace("{{DATE}}", date_str)
    html_output = html_output.replace("{{CONTENT}}", full_text)

    filename = f"news-{date_str}.html"
    with open(filename, "w") as f:
        f.write(html_output)

    # 4. Feature on Homepage (Auto-Linking)
    with open("index.html", "r") as f:
        index_content = f.read()
    
    new_entry = f'<li class="news-item"><span class="date">{date_str}</span><a href="{filename}">{title}</a></li>\n'
    if "" in index_content:
        index_content = index_content.replace("", f"\n{new_entry}")
        with open("index.html", "w") as f:
            f.write(index_content)

run_news_bot()
