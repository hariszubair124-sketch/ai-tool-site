import os
import re
import time
import json
import unicodedata
import argparse
from datetime import datetime

# ── Only import genai when not in dry-run mode ──
def get_client():
    from google import genai
    return genai.Client(api_key=os.environ.get("API_KEY"))


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

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
    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + '…'
    return text


def validate_structure(posts_dir, filepath):
    """
    Checks the file will land directly inside posts_dir — no nested subfolders.
    """
    expected_dir = os.path.abspath(posts_dir)
    actual_dir   = os.path.abspath(os.path.dirname(filepath))
    if expected_dir != actual_dir:
        raise ValueError(
            f"\n❌ STRUCTURE ERROR: File would be saved to wrong location!"
            f"\n   Expected dir : {expected_dir}"
            f"\n   Actual dir   : {actual_dir}"
            f"\n   Filepath     : {filepath}"
        )
    print(f"   ✅ Structure OK  → {filepath}")


def update_manifests(posts_dir, new_post):
    """
    Keeps two manifest files up to date:
    - ai-news/files.json  : ordered list of all .html filenames (oldest → newest)
    - ai-news/index.json  : latest 20 posts with metadata, newest first
    """

    # ── files.json ──
    files_path = os.path.join(posts_dir, 'files.json')
    if os.path.exists(files_path):
        with open(files_path, 'r', encoding='utf-8') as f:
            files_list = json.load(f)
    else:
        existing = sorted(
            [fn for fn in os.listdir(posts_dir) if fn.endswith('.html')],
            key=lambda fn: os.path.getmtime(os.path.join(posts_dir, fn))
        )
        files_list = existing

    filename = os.path.basename(new_post['url'].lstrip('/').replace('ai-news/', ''))
    if filename not in files_list:
        files_list.append(filename)

    with open(files_path, 'w', encoding='utf-8') as f:
        json.dump(files_list, f, indent=2)

    # ── index.json ──
    index_path = os.path.join(posts_dir, 'index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            index_list = json.load(f)
    else:
        index_list = []

    index_list = [p for p in index_list if p.get('url') != new_post['url']]
    index_list.insert(0, new_post)
    index_list = index_list[:20]

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_list, f, indent=2, ensure_ascii=False)

    print(f"   📋 files.json  → {len(files_list)} file(s) listed")
    print(f"   📋 index.json  → {len(index_list)} post(s) indexed")


# ══════════════════════════════════════════
# DRY RUN
# ══════════════════════════════════════════

FAKE_HTML = """<!-- META: NVIDIA has forged a 2 billion dollar strategic alliance with Nebius to build next-gen hyperscale AI cloud infrastructure. -->
<article>
<h1>NVIDIA Forges $2 Billion Strategic Alliance with Nebius to Build Next-Gen Hyperscale AI Cloud</h1>
<h2>What the Deal Means for AI Infrastructure</h2>
<p>NVIDIA and Nebius have announced a landmark <strong>$2 billion partnership</strong> aimed at accelerating the development of hyperscale AI cloud computing infrastructure across Europe and beyond.</p>
<h2>Why This Matters</h2>
<p>The deal signals a major shift in how large-scale AI compute is being financed and deployed outside of the United States, giving European developers access to cutting-edge GPU clusters at scale.</p>
<h2>What's Next</h2>
<p>Both companies expect the first data centers under this agreement to come online by late 2025, with full capacity reached through 2026.</p>
</article>"""


def run_dry_run(posts_dir):
    print("\n" + "═" * 55)
    print("  DRY RUN MODE — No API calls will be made")
    print("═" * 55 + "\n")

    today_date = datetime.now().strftime("%B %d, %Y")
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"📅 Simulated date : {today_date}")
    print(f"📁 Target folder  : {posts_dir}/\n")

    # Step 1
    print("─" * 40)
    print("STEP 1 — Simulating API response (fake HTML)")
    html = FAKE_HTML
    print(f"   ✅ Fake HTML generated ({len(html)} chars)")

    # Step 2
    print("\nSTEP 2 — Extracting title & building filename")
    title = extract_title(html)
    if not title:
        title = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"
        print(f"   ⚠️  No <h1> found, using fallback: {title}")
    else:
        print(f"   📝 Title found   : {title}")

    clean_filename = slugify(title)
    if not clean_filename:
        clean_filename = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"
        print(f"   ⚠️  Empty slug, using fallback: {clean_filename}")
    else:
        print(f"   🔗 Slug generated: {clean_filename}")

    filename = f"{clean_filename}.html"
    print(f"   📄 Filename      : {filename}")

    # Step 3
    print("\nSTEP 3 — Validating file path structure")
    os.makedirs(posts_dir, exist_ok=True)
    filepath = os.path.join(posts_dir, filename)

    try:
        validate_structure(posts_dir, filepath)
    except ValueError as e:
        print(e)
        exit(1)

    # Step 4
    print("\nSTEP 4 — Building final HTML with timestamp")
    final_html = html + f"\n\n<!-- generated: {timestamp} -->\n"
    print(f"   ✅ Timestamp injected : {timestamp}")
    print(f"   ✅ Total HTML size    : {len(final_html)} chars")

    # Step 5
    print("\nSTEP 5 — Writing file to disk")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print(f"   ✅ File written : {filepath}")
    print(f"   📦 File size    : {os.path.getsize(filepath)} bytes")

    # Step 6
    print("\nSTEP 6 — Extracting metadata for manifests")
    meta    = extract_meta(final_html)
    excerpt = meta if meta else extract_excerpt(final_html)
    print(f"   📌 Meta desc : {excerpt[:80]}…")

    new_post = {
        "url":     f"/ai-news/{filename}",
        "title":   title,
        "excerpt": excerpt,
        "date":    datetime.now().strftime("%b %d, %Y"),
    }
    print(f"   ✅ Post object built")

    # Step 7
    print("\nSTEP 7 — Updating manifests")
    update_manifests(posts_dir, new_post)

    # Step 8
    print("\nSTEP 8 — Final verification")
    files_ok = os.path.exists(os.path.join(posts_dir, 'files.json'))
    index_ok = os.path.exists(os.path.join(posts_dir, 'index.json'))
    post_ok  = os.path.exists(filepath)

    print(f"   {'✅' if post_ok  else '❌'} Post file  : {filepath}")
    print(f"   {'✅' if files_ok else '❌'} files.json : {posts_dir}/files.json")
    print(f"   {'✅' if index_ok else '❌'} index.json : {posts_dir}/index.json")

    print(f"\n📂 Folder contents of '{posts_dir}/':")
    for fn in sorted(os.listdir(posts_dir)):
        size  = os.path.getsize(os.path.join(posts_dir, fn))
        icon  = "📄" if fn.endswith('.html') else "📋"
        # Flag any unexpected subfolders
        if os.path.isdir(os.path.join(posts_dir, fn)):
            print(f"   ⚠️  SUBFOLDER DETECTED → {fn}/  ← this should not exist!")
        else:
            print(f"   {icon} {fn}  ({size} bytes)")

    print("\n" + "═" * 55)
    print("  ✅ DRY RUN PASSED — Structure is correct")
    print("  Run without --dry-run to use the real API")
    print("═" * 55 + "\n")


# ══════════════════════════════════════════
# LIVE RUN
# ══════════════════════════════════════════

def call_gemini_with_backoff(client, prompt, max_retries=4):
    from google.genai import types
    wait_times = [30, 60, 120, 300]

    for attempt in range(max_retries):
        try:
            print(f"🔄 API attempt {attempt + 1} of {max_retries}...")
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
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


def run_live(posts_dir):
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
        print(f"🚀 Starting live run for {today_date}...")
        client   = get_client()
        response = call_gemini_with_backoff(client, prompt)

        if not response.text:
            print("❌ AI returned empty content.")
            exit(1)

        html  = response.text
        title = extract_title(html)

        clean_filename = slugify(title) if title else ""
        if not clean_filename:
            clean_filename = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"

        os.makedirs(posts_dir, exist_ok=True)
        filename = f"{clean_filename}.html"
        filepath = os.path.join(posts_dir, filename)

        try:
            validate_structure(posts_dir, filepath)
        except ValueError as e:
            print(e)
            exit(1)

        timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_html = html + f"\n\n<!-- generated: {timestamp} -->\n"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html)

        print(f"✅ Post saved  : {filepath}")
        print(f"📅 Timestamp   : {timestamp}")
        print(f"📝 Title       : {title}")

        meta    = extract_meta(final_html)
        excerpt = meta if meta else extract_excerpt(final_html)

        new_post = {
            "url":     f"/ai-news/{filename}",
            "title":   title or clean_filename.replace('-', ' ').title(),
            "excerpt": excerpt,
            "date":    datetime.now().strftime("%b %d, %Y"),
        }
        update_manifests(posts_dir, new_post)

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)


# ══════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Blog Writer for webonlinetools.com")
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test file structure and manifests without calling the Gemini API'
    )
    parser.add_argument(
        '--posts-dir',
        default='ai-news',
        help='Folder to save posts into (default: ai-news)'
    )
    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(args.posts_dir)
    else:
        run_live(args.posts_dir)
