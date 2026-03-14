import os
import re
import time
import json
import unicodedata
import argparse
from datetime import datetime


def get_client():
    from google import genai
    return genai.Client(api_key=os.environ.get("API_KEY"))


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

def sanitize_response(text):
    """
    Gemini sometimes wraps output in markdown code fences.
    This strips them so we get clean HTML only.
    """
    text = text.strip()
    # Remove opening ```html or ``` fence
    text = re.sub(r'^```[a-zA-Z]*\s*\n', '', text)
    # Remove closing ``` fence
    text = re.sub(r'\n```\s*$', '', text)
    return text.strip()


def slugify(value):
    """Turns 'Hello World!' into 'hello-world'"""
    value = re.sub(r'<[^>]+>', '', value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    value = re.sub(r'[-\s]+', '-', value)
    return value.strip('-_')


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


def build_filepath(posts_dir, title):
    """
    Builds a safe, FLAT filepath from a title.
    Guaranteed: returns posts_dir/something.html with NO subfolders ever.
    """
    slug = slugify(title) if title else ""
    if not slug:
        slug = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"

    # os.path.basename strips any accidental slashes or path separators
    filename = os.path.basename(slug + ".html")

    # Fallback if filename is somehow empty
    if not filename or filename == ".html":
        filename = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}.html"

    filepath = os.path.join(posts_dir, filename)

    # Hard validation — file must be directly inside posts_dir
    if os.path.abspath(os.path.dirname(filepath)) != os.path.abspath(posts_dir):
        raise ValueError(
            f"❌ STRUCTURE ERROR: {filepath} is not directly inside {posts_dir}/"
        )

    return filepath, filename


def update_manifests(posts_dir, new_post):
    """
    Keeps two manifest files up to date inside posts_dir:
    - files.json : ordered list of .html filenames (oldest → newest)
    - index.json : latest 20 posts with metadata (newest first)
    """

    # ── files.json ──
    files_path = os.path.join(posts_dir, 'files.json')
    if os.path.exists(files_path):
        with open(files_path, 'r', encoding='utf-8') as f:
            files_list = json.load(f)
    else:
        # First run: scan folder — FILES ONLY, never subfolders
        files_list = sorted(
            [
                fn for fn in os.listdir(posts_dir)
                if fn.endswith('.html')
                and os.path.isfile(os.path.join(posts_dir, fn))  # ← KEY FIX
            ],
            key=lambda fn: os.path.getmtime(os.path.join(posts_dir, fn))
        )

    # Always use basename — strip any path prefix from the URL
    filename = os.path.basename(new_post['url'])
    if filename and filename not in files_list:
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

    # Remove duplicate if re-running same post
    index_list = [p for p in index_list if p.get('url') != new_post['url']]
    index_list.insert(0, new_post)
    index_list = index_list[:20]

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_list, f, indent=2, ensure_ascii=False)

    print(f"   📋 files.json → {len(files_list)} file(s)")
    print(f"   📋 index.json → {len(index_list)} post(s)")


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
    print(f"📅 Date          : {today_date}")
    print(f"📁 Target folder : {posts_dir}/\n")

    # Step 1 — Fake response + sanitize
    print("─" * 40)
    print("STEP 1 — Simulating API response")
    html = sanitize_response(FAKE_HTML)
    print(f"   ✅ HTML ready ({len(html)} chars)")

    # Step 2 — Title + filename
    print("\nSTEP 2 — Title extraction & filename")
    title = extract_title(html)
    print(f"   📝 Title    : {title or '(none — fallback will be used)'}")

    os.makedirs(posts_dir, exist_ok=True)

    try:
        filepath, filename = build_filepath(posts_dir, title)
    except ValueError as e:
        print(f"   {e}")
        exit(1)

    print(f"   🔗 Filename : {filename}")
    print(f"   📂 Filepath : {filepath}")
    print(f"   ✅ Structure OK — flat inside {posts_dir}/")

    # Step 3 — Write file
    print("\nSTEP 3 — Writing file")
    final_html = html + f"\n\n<!-- generated: {timestamp} -->\n"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print(f"   ✅ Written  : {filepath} ({os.path.getsize(filepath)} bytes)")

    # Step 4 — Manifests
    print("\nSTEP 4 — Updating manifests")
    meta    = extract_meta(final_html)
    excerpt = meta if meta else extract_excerpt(final_html)
    new_post = {
        "url":     f"/ai-news/{filename}",
        "title":   title or filename.replace('.html', '').replace('-', ' ').title(),
        "excerpt": excerpt,
        "date":    datetime.now().strftime("%b %d, %Y"),
    }
    update_manifests(posts_dir, new_post)

    # Step 5 — Verify
    print("\nSTEP 5 — Verification")
    all_ok = True

    for label, path in [
        ("Post file ", filepath),
        ("files.json", os.path.join(posts_dir, 'files.json')),
        ("index.json", os.path.join(posts_dir, 'index.json')),
    ]:
        exists = os.path.exists(path)
        print(f"   {'✅' if exists else '❌'} {label} : {path}")
        if not exists:
            all_ok = False

    print(f"\n📂 Contents of '{posts_dir}/':")
    for fn in sorted(os.listdir(posts_dir)):
        full = os.path.join(posts_dir, fn)
        if os.path.isdir(full):
            print(f"   ⚠️  SUBFOLDER DETECTED (should NOT exist) → {fn}/")
            all_ok = False
        else:
            icon = "📄" if fn.endswith('.html') else "📋"
            print(f"   {icon} {fn}  ({os.path.getsize(full)} bytes)")

    print("\n" + "═" * 55)
    if all_ok:
        print("  ✅ DRY RUN PASSED — structure is correct")
    else:
        print("  ❌ DRY RUN FAILED — see warnings above")
    print("  Run without --dry-run to use the real API")
    print("═" * 55 + "\n")

    if not all_ok:
        exit(1)


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

## CRITICAL OUTPUT FORMAT
- Output RAW HTML only — no markdown, no code fences, no backticks
- Do NOT wrap output in ```html or ``` blocks
- Start your response directly with: <!-- META: your description -->
- Then immediately: <article>
- End with: </article>

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

### 4. HTML Structure Requirements
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
- Vary sentence length naturally

### 6. Relevance to webonlinetools.com
- Where genuinely relevant, briefly connect the story to online tools, productivity, or web utilities
- This should feel natural, not forced

---

Now write the blog post. Remember: RAW HTML only, starting with <!-- META: -->
"""

    try:
        print(f"🚀 Starting live run for {today_date}...")
        client   = get_client()
        response = call_gemini_with_backoff(client, prompt)

        if not response.text:
            print("❌ AI returned empty content.")
            exit(1)

        # Sanitize: strip any markdown fences Gemini might add
        html  = sanitize_response(response.text)
        title = extract_title(html)

        print(f"📝 Title: {title or '(none — using fallback)'}")

        os.makedirs(posts_dir, exist_ok=True)

        try:
            filepath, filename = build_filepath(posts_dir, title)
        except ValueError as e:
            print(e)
            exit(1)

        timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_html = html + f"\n\n<!-- generated: {timestamp} -->\n"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html)

        print(f"✅ Saved    : {filepath}")
        print(f"📅 Time     : {timestamp}")

        meta    = extract_meta(final_html)
        excerpt = meta if meta else extract_excerpt(final_html)

        new_post = {
            "url":     f"/ai-news/{filename}",
            "title":   title or filename.replace('.html', '').replace('-', ' ').title(),
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
    parser.add_argument('--dry-run',   action='store_true', help='Test without API calls')
    parser.add_argument('--posts-dir', default='ai-news',   help='Folder to save posts (default: ai-news)')
    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(args.posts_dir)
    else:
        run_live(args.posts_dir)
