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
    """Strip markdown code fences Gemini sometimes adds."""
    text = text.strip()
    text = re.sub(r'^```[a-zA-Z]*\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    return text.strip()


def slugify(value):
    value = re.sub(r'<[^>]+>', '', value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    value = re.sub(r'[-\s]+', '-', value)
    return value.strip('-_')


def extract_title(html):
    match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return ""


def extract_meta(html):
    match = re.search(r'<!--\s*META:\s*(.*?)\s*-->', html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_excerpt(html, max_len=160):
    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + '…'
    return text


def estimate_read_time(html):
    text  = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()
    words = len(text.split())
    mins  = max(1, round(words / 220))
    return f"{mins} min read"


def build_filepath(save_dir, title):
    """Builds a safe flat filepath. Never creates subfolders."""
    slug = slugify(title) if title else ""
    if not slug:
        slug = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}"
    filename = os.path.basename(slug + ".html")
    if not filename or filename == ".html":
        filename = f"ai-news-{datetime.now().strftime('%Y-%m-%d')}.html"
    filepath = os.path.join(save_dir, filename)
    if os.path.abspath(os.path.dirname(filepath)) != os.path.abspath(save_dir):
        raise ValueError(f"❌ STRUCTURE ERROR: {filepath} is not directly inside {save_dir}/")
    return filepath, filename


def build_full_page(save_dir, article_html, title, excerpt, filename, date_display, read_time, timestamp):
    """
    Reads template.html, replaces {{PLACEHOLDER}} tokens,
    returns a complete styled HTML page.
    """
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.html'),
        os.path.join(save_dir, 'template.html'),
        'template.html',
    ]

    template_path = None
    for c in candidates:
        if os.path.exists(c):
            template_path = c
            print(f"   ✅ template.html found: {c}")
            break

    if not template_path:
        print("   ❌ template.html NOT found — saving raw HTML")
        return article_html + f"\n\n<!-- generated: {timestamp} -->\n"

    with open(template_path, 'r', encoding='utf-8') as f:
        page = f.read()

    # Clean article body
    body = article_html
    body = re.sub(r'<!--\s*META:[^-]*-->', '', body)
    body = re.sub(r'<!--\s*generated:[^-]*-->', '', body)
    body = re.sub(r'^\s*<article[^>]*>', '', body, flags=re.IGNORECASE)
    body = re.sub(r'</article>\s*$', '', body, flags=re.IGNORECASE)
    body = body.strip()

    date_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for token, value in {
        '{{PAGE_TITLE}}':   title,
        '{{META_DESC}}':    excerpt,
        '{{FILENAME}}':     filename,
        '{{DATE_DISPLAY}}': date_display,
        '{{READ_TIME}}':    read_time,
        '{{DATE_ISO}}':     date_iso,
        '{{ARTICLE_BODY}}': body,
    }.items():
        page = page.replace(token, value)

    page += f"\n<!-- generated: {timestamp} -->\n"
    return page


def update_manifests(save_dir, new_post):
    """Updates files.json and index.json."""

    # ── files.json ──
    files_path = os.path.join(save_dir, 'files.json')
    if os.path.exists(files_path):
        with open(files_path, 'r', encoding='utf-8') as f:
            files_list = json.load(f)
    else:
        files_list = sorted(
            [fn for fn in os.listdir(save_dir)
             if fn.endswith('.html') and os.path.isfile(os.path.join(save_dir, fn))],
            key=lambda fn: os.path.getmtime(os.path.join(save_dir, fn))
        )

    filename = os.path.basename(new_post['url'])
    if filename and filename not in files_list:
        files_list.append(filename)

    with open(files_path, 'w', encoding='utf-8') as f:
        json.dump(files_list, f, indent=2)

    # ── index.json ──
    index_path = os.path.join(save_dir, 'index.json')
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

    print(f"   📋 files.json → {len(files_list)} file(s)")
    print(f"   📋 index.json → {len(index_list)} post(s)")


def update_sitemap(save_dir, filename, date_str):
    """
    Adds the new blog post URL into sitemap.xml between
    <!-- BLOG_POSTS_START --> and <!-- BLOG_POSTS_END --> markers.
    Skips if the URL already exists in the sitemap.
    """
    sitemap_path = os.path.join(save_dir, 'sitemap.xml')

    if not os.path.exists(sitemap_path):
        print("   ⚠️  sitemap.xml not found — skipping sitemap update")
        return

    with open(sitemap_path, 'r', encoding='utf-8') as f:
        sitemap = f.read()

    public_url = f"https://webonlinetools.com/ai-news/{filename}"

    # Skip if already exists
    if public_url in sitemap:
        print(f"   ℹ️  Sitemap already contains this URL — skipping")
        return

    new_entry = (
        f"  <url>\n"
        f"    <loc>{public_url}</loc>\n"
        f"    <lastmod>{date_str}</lastmod>\n"
        f"    <changefreq>monthly</changefreq>\n"
        f"    <priority>0.7</priority>\n"
        f"  </url>\n"
        f"  <!-- BLOG_POSTS_END -->"
    )

    # Inject before the closing marker
    if '<!-- BLOG_POSTS_END -->' in sitemap:
        sitemap = sitemap.replace('<!-- BLOG_POSTS_END -->', new_entry)
        with open(sitemap_path, 'w', encoding='utf-8') as f:
            f.write(sitemap)
        print(f"   🗺️  sitemap.xml updated → {public_url}")
    else:
        print("   ⚠️  sitemap.xml missing BLOG_POSTS_END marker — skipping")


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


def run_dry_run(save_dir):
    print("\n" + "═" * 55)
    print("  DRY RUN MODE — No API calls will be made")
    print("═" * 55 + "\n")

    today_date = datetime.now().strftime("%B %d, %Y")
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str   = datetime.now().strftime("%Y-%m-%d")

    print(f"📅 Date            : {today_date}")
    print(f"💾 Save to (GitHub): {save_dir}/")
    print(f"🌐 Public URL base : /ai-news/\n")

    print("─" * 40)
    print("STEP 1 — Simulating API response")
    html = sanitize_response(FAKE_HTML)
    print(f"   ✅ HTML ready ({len(html)} chars)")

    print("\nSTEP 2 — Title extraction & filename")
    title = extract_title(html)
    print(f"   📝 Title     : {title or '(none — fallback)'}")
    os.makedirs(save_dir, exist_ok=True)
    try:
        filepath, filename = build_filepath(save_dir, title)
    except ValueError as e:
        print(f"   {e}"); exit(1)
    print(f"   🔗 Filename  : {filename}")
    print(f"   💾 Saves to  : {filepath}")
    print(f"   🌐 Public URL: /ai-news/{filename}")

    print("\nSTEP 3 — Building full styled page from template")
    meta         = extract_meta(html)
    excerpt      = meta if meta else extract_excerpt(html)
    date_display = today_date
    read_time    = estimate_read_time(html)
    final_html   = build_full_page(save_dir, html, title, excerpt, filename, date_display, read_time, timestamp)
    print(f"   ✅ Page built ({len(final_html)} chars)")

    print("\nSTEP 4 — Writing file")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print(f"   ✅ Written : {filepath} ({os.path.getsize(filepath)} bytes)")

    print("\nSTEP 5 — Updating manifests")
    new_post = {
        "url":     f"/ai-news/{filename}",
        "title":   title or filename.replace('.html', '').replace('-', ' ').title(),
        "excerpt": excerpt,
        "date":    datetime.now().strftime("%b %d, %Y"),
    }
    update_manifests(save_dir, new_post)

    print("\nSTEP 6 — Updating sitemap")
    update_sitemap(save_dir, filename, date_str)

    print("\nSTEP 7 — Verification")
    all_ok = True
    IGNORED = {'.git', '.github', '__pycache__', 'node_modules'}

    for label, path in [
        ("Post file ", filepath),
        ("files.json", os.path.join(save_dir, 'files.json')),
        ("index.json", os.path.join(save_dir, 'index.json')),
        ("sitemap.xml", os.path.join(save_dir, 'sitemap.xml')),
    ]:
        exists = os.path.exists(path)
        print(f"   {'✅' if exists else '⚠️ '} {label} : {path}")

    print(f"\n📂 Files in '{save_dir}/' (deploy → Hostinger ai-news/):")
    for fn in sorted(os.listdir(save_dir)):
        full = os.path.join(save_dir, fn)
        if os.path.isdir(full):
            if fn in IGNORED: continue
            print(f"   ⚠️  UNEXPECTED SUBFOLDER → {fn}/")
            all_ok = False
        else:
            icon = "📄" if fn.endswith('.html') else "📋"
            print(f"   {icon} {fn}  ({os.path.getsize(full)} bytes)")

    print("\n" + "═" * 55)
    if all_ok:
        print("  ✅ DRY RUN PASSED")
        print("  GitHub root → Hostinger ai-news/ ✅")
        print("  Template applied ✅")
        print("  Sitemap updated ✅")
    else:
        print("  ❌ DRY RUN FAILED — see warnings above")
    print("  Run without --dry-run to use the real API")
    print("═" * 55 + "\n")
    if not all_ok: exit(1)


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
                model="gemini-2.5-flash",
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
                    print("❌ All retry attempts exhausted.")
                    raise
            else:
                print(f"❌ Non-quota error: {error_str}")
                raise


def run_live(save_dir):
    today_date = datetime.now().strftime("%B %d, %Y")
    date_str   = datetime.now().strftime("%Y-%m-%d")

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
- The article must have ONE clear topic
- Cover WHO, WHAT, WHEN, WHERE, WHY, HOW
- Add a "Why This Matters" section
- End with a "What's Next" paragraph

### 3. SEO & Keyword Guidelines
- Use primary keyword in <h1>, first paragraph, and 2+ subheadings
- Use semantic/LSI keywords throughout
- No keyword stuffing — every sentence must read naturally
- Target keyword density: 1–2%

### 4. HTML Structure Requirements
- Use <h1> for title (ONE only)
- Use <h2> for major sections (4–6)
- Use <h3> for sub-points
- Use <p> for paragraphs (min 3 sentences each)
- Use <ul> or <ol> for lists (max 1 per section)
- Use <strong> for key facts (max 5)
- Use <blockquote> for real quotes
- No <html>, <head>, <body>, <style> tags

### 5. Writing Quality
- Tone: professional, informative, accessible
- Word count: 700–1000 words
- No filler phrases
- Vary sentence length naturally

### 6. Relevance to webonlinetools.com
- Connect to online tools/productivity only where it fits naturally

---

Now write the blog post. RAW HTML only, starting with <!-- META: -->
"""

    try:
        print(f"🚀 Starting live run for {today_date}...")
        client   = get_client()
        response = call_gemini_with_backoff(client, prompt)

        if not response.text:
            print("❌ AI returned empty content.")
            exit(1)

        html  = sanitize_response(response.text)
        title = extract_title(html)
        print(f"📝 Title: {title or '(none — using fallback)'}")

        os.makedirs(save_dir, exist_ok=True)
        try:
            filepath, filename = build_filepath(save_dir, title)
        except ValueError as e:
            print(e); exit(1)

        timestamp    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta         = extract_meta(html)
        excerpt      = meta if meta else extract_excerpt(html)
        date_display = datetime.now().strftime("%B %d, %Y")
        read_time    = estimate_read_time(html)

        # Bake into template
        final_html = build_full_page(save_dir, html, title, excerpt, filename, date_display, read_time, timestamp)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html)

        print(f"✅ Saved    : {filepath}  →  /ai-news/{filename}")
        print(f"📅 Time     : {timestamp}")
        print(f"📦 Size     : {os.path.getsize(filepath)} bytes")

        new_post = {
            "url":     f"/ai-news/{filename}",
            "title":   title or filename.replace('.html', '').replace('-', ' ').title(),
            "excerpt": excerpt,
            "date":    datetime.now().strftime("%b %d, %Y"),
        }
        update_manifests(save_dir, new_post)
        update_sitemap(save_dir, filename, date_str)

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)


# ══════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Blog Writer for webonlinetools.com")
    parser.add_argument('--dry-run',   action='store_true', help='Test without API calls')
    parser.add_argument('--posts-dir', default='.',         help='Directory to save files (default: repo root)')
    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(args.posts_dir)
    else:
        run_live(args.posts_dir)
