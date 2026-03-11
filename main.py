import os
import re
import time
import json
import unicodedata
from google import genai
from google.genai import types
from datetime import datetime

client = genai.Client(api_key=os.environ.get("API_KEY"))


def slugify(value):
    """Turns 'Hello World!' into 'hello-world'"""
    value = re.sub(r'<[^>]+>', '', value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def extract_title(html):
    """Extracts clean text from the first <h1> tag."""
    match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return ""


def extract_meta(html):
    """Extracts <!-- META: ... --> description comment."""
    match = re.search(r'<!--\s*META:\s*(.*?)\s*-->', html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_excerpt(html, max_len=140):
    """Strips all HTML tags and returns a plain-text excerpt."""
    # Remove script/style blocks
    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all tags
    text = re.sub(r'<[^>]+>', '', html)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + '…'
    return text


def update_manifests(posts_dir, new_post):
    """
    Keeps two manifest files up to date:
    - posts/files.json  : ordered list of all .html filenames (oldest → newest)
    - posts/index.json  : latest 20 posts with metadata, newest first
    These are read by the homepage to auto-display the latest blog cards.
    """

    # ── files.json ──────────────────────────────────────────────────────────
    files_path = os.path.join(posts_dir, 'files.json')
    if os.path.exists(files_path):
        with open(files_path, 'r', encoding='utf-8') as f:
            files_list = json.load(f)
    else:
        # First run: discover existing .html files, sorted by modification time
        existing = sorted(
            [fn for fn in os.listdir(posts_dir) if fn.endswith('.html')],
            key=lambda fn: os.path.getmtime(os.path.join(posts_dir, fn))
        )
        files_list = existing

    filename = os.path.basename(new_post['url'])
    if filename not in files_list:
        files_list.append(filename)

    with open(files_path, 'w', encoding='utf-8') as f:
        json.dump(files_list, f, indent=2)

    # ── index.json ──────────────────────────────────────────────────────────
    index_path = os.path.join(posts_dir, 'index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            index_list = json.load(f)
    else:
        index_list = []

    # Avoid duplicates (re-runs on the same day)
    index_list = [p for p in index_list if p.get('url') != new_post['url']]
    # Prepend newest post
    index_list.insert(0, new_post)
    # Keep only the latest 20 entries
    index_list = index_list[:20]

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_list, f, indent=2, ensure_ascii=False)

    print(f"📋 Manifests updated — {len(files_list)} total posts indexed.")


def call_gemini_with_backoff(prompt, max_retries=4):
    """Calls Gemini API with exponential backoff on 429 quota errors."""
    wait_times = [30, 60, 120, 300]  # 30s → 1min → 2min → 5min

    for attempt in range(max_retries):
        try:
            print(f"🔄 API attempt {attempt + 1} of {max_retries}...")
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            return response

        except Exception as e:
            error_str = str(e)
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                if attempt < max_retries - 1:
                    wait = wait_times[attempt]
                    print(f"⏳ Quota hit (429). Waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    print("❌ All retry attempts exhausted due to quota limits.")
                    raise
            else:
                print(f"❌ Non-quota error: {error_str}")
                raise


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
        print(f"🚀 Starting research for {today_date}...")
        response = call_gemini_with_backoff(prompt)

        if not response.text:
            print("❌ AI returned empty content.")
            exit(1)

        html = response.text

        # ── Build filename from <h1> ─────────────────────────────────────
        title = extract_title(html)
        clean_filename = slugify(title) if title else f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"
        if not clean_filename:
            clean_filename = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"

            posts_dir = "ai-news"
            os.makedirs(posts_dir, exist_ok=True)          # creates ai-news/ only
            filename  = f"{clean_filename}.html"            # just the filename, no folders
            filepath  = os.path.join(posts_dir, filename)   # ai-news/nvidia-forges....html

# Safety check — never let filepath create subfolders

        # ── Inject timestamp fingerprint ────────────────────────────────
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_html = html + f"\n\n<!-- generated: {timestamp} -->\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_html)

        print(f"✅ Post saved:  {filepath}")
        print(f"📅 Timestamp:   {timestamp}")
        print(f"📝 Title:       {title}")

        # ── Update manifests so homepage can auto-discover this post ────
        meta    = extract_meta(final_html)
        excerpt = meta if meta else extract_excerpt(final_html)
        date_str = datetime.now().strftime("%b %d, %Y")

        new_post = {
            "url": f"/ai-news/{filename}",
            "title":   title or clean_filename.replace('-', ' ').title(),
            "excerpt": excerpt,
            "date":    date_str,
        }
        update_manifests(posts_dir, new_post)

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)


if __name__ == "__main__":
    run_robot()
