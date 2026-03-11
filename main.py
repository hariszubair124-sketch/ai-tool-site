import os
import re
import unicodedata
from google import genai
from google.genai import types
from datetime import datetime

# 1. Setup - Correct variable name for your GitHub Secret
client = genai.Client(api_key=os.environ.get("API_KEY"))

def slugify(value):
    """Turns 'Hello World!' into 'hello-world'"""
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

def run_robot():
    # Dynamic Date: This changes every day automatically
    today_date = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""
    Research the top AI news story for today, {today_date}. 
    Write a professional, SEO-optimized HTML blog post.
    Include <h1> for the title, <h2> for subheadings, and <ul> for key points.
    Do not include <html> or <body> tags, just the <article> content.
    """
    
    try:
        print(f"Starting research for {today_date}...")
        
        # 2. Call Gemini with Search Grounding
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )

        if response.text:
            # 3. Create SEO-friendly filename from the first line (Title)
            first_line = response.text.split('\n')[0].replace('#', '').strip()
            clean_filename = slugify(first_line)
            filename = f"{clean_filename}.html"
            
            # 4. The "Force Change" Fingerprint
            # Adding a timestamp ensures Git always sees a difference in the file
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            final_html = response.text + f"\n\n"

            # 5. Save the file
            with open(filename, "w", encoding="utf-8") as f:
                f.write(final_html)
            
            print(f"Success! Created {filename} at {timestamp}")
            
            # 6. Optional: Update index.html
            # We can add logic here later to auto-link the new file
        else:
            print("AI returned empty content. Quota might be low.")

    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    run_robot()
