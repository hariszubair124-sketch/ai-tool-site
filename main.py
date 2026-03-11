import os
import re
import unicodedata
from google import genai
from google.genai import types
from datetime import datetime

client = genai.Client(api_key=os.environ.get("API_KEY"))

def slugify(value):
    """Turns 'Hello World!' into 'hello-world'"""
    value = re.sub(r'<[^>]+>', '', value)  # Strip HTML tags
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

def run_robot():
    today_date = datetime.now().strftime("%B %d, %Y")

    prompt = f"""
You are an expert technology journalist and SEO content strategist writing for webonlinetools.com — a website focused on free online tools for productivity, file conversion, text editing, and web utilities.

Today's date is {today_date}. Your task is to research and write a high-quality, publish-ready HTML blog post about the most significant and authentic AI or tech news story from today.

---

## CONTENT RULES

### 1. Authenticity First
- Only write about REAL, verifiable news from today ({today_date}) using your search grounding
- DO NOT fabricate events, quotes, statistics, or product launches
- If no major AI story exists for today, cover the most recent credible story within the last 48 hours
- Cite real sources naturally within the content (e.g., "According to Google's official blog...")

### 2. Semantic Content Structure
- The article must have ONE clear topic — do not mix multiple unrelated news stories
- Cover the WHO, WHAT, WHEN, WHERE, WHY, and HOW of the story
- Include background context so readers unfamiliar with the topic can understand it
- Add a "Why This Matters" section explaining the real-world impact
- End with a "What's Next" or forward-looking paragraph

### 3. SEO & Keyword Guidelines
- Use the primary keyword naturally in the <h1>, first paragraph, and at least 2 subheadings
- Use semantic/LSI keywords throughout — related terms, synonyms, and contextual phrases
- DO NOT keyword stuff — every sentence must read naturally for a human reader
- Target keyword density: 1–2% maximum
- Include a meta description as an HTML comment at the top: <!-- META: your description here -->

### 4. HTML Structure Requirements
- Start directly with <!-- META: ... --> then the <article> tag
- Use <h1> for the main title (only ONE h1)
- Use <h2> for major sections (4–6 subheadings)
- Use <h3> for any sub-points within sections
- Use <p> for all body paragraphs (minimum 3 sentences each)
- Use <ul> or <ol> for lists — maximum 1 list per section
- Use <strong> to bold only genuinely important terms or facts (max 5 per article)
- Use <blockquote> for any real quotes from official sources
- Do NOT include <html>, <head>, <body>, or <style> tags

### 5. Writing Quality Standards
- Tone: Professional, informative, and accessible — like a trusted tech journalist
- Reading level: Aim for Grade 8–10 (clear, not dumbed down)
- Word count: 700–1000 words of actual body content
- No filler phrases like "In conclusion", "It's worth noting", "In today's digital age"
- No AI-sounding openers — start the article body with a strong, direct statement of the news
- Vary sentence length naturally — mix short punchy sentences with longer explanatory ones

### 6. Relevance to webonlinetools.com
- Where genuinely relevant, briefly connect the story to online tools, productivity, or web utilities
- This should feel natural, not forced — only include if it truly fits the story

---

Now write the blog post based on today's most important and authentic AI/tech news story.
"""

    try:
        print(f"Starting research for {today_date}...")

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )

        if response.text:
            # Extract clean title from first <h1> tag for the filename
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', response.text, re.IGNORECASE | re.DOTALL)
            if h1_match:
                clean_title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
            else:
                # Fallback: use first non-empty line stripped of HTML
                for line in response.text.split('\n'):
                    clean_title = re.sub(r'<[^>]+>', '', line).strip()
                    if clean_title and not clean_title.startswith('<!--'):
                        break

            clean_filename = slugify(clean_title)

            # Fallback filename if slug is somehow empty
            if not clean_filename:
                clean_filename = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"

            # Save to /posts/ folder to keep repo organized
            os.makedirs("posts", exist_ok=True)
            filename = f"posts/{clean_filename}.html"

            # Inject timestamp fingerprint so Git always sees a real change
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            final_html = response.text + f"\n\n<!-- generated: {timestamp} -->\n"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(final_html)

            print(f"✅ Success! Created: {filename}")
            print(f"📅 Timestamp: {timestamp}")
            print(f"📝 Title: {clean_title}")

        else:
            print("❌ AI returned empty content. Quota might be exhausted.")
            exit(1)

    except Exception as e:
        print(f"❌ Error occurred: {e}")
        exit(1)

if __name__ == "__main__":
    run_robot()
