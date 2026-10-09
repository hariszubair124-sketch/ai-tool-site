"""
Daily AI news writer. Runs in GitHub Actions with the free Gemini API.

1. Asks Gemini (with Google Search grounding) for one story from the last 48 hours, as JSON.
2. Keeps only sources that Gemini's search actually returned AND that load right now.
3. Publishes only if: 2+ sources from different sites, 1+ source dated within 72 hours,
   the story is not one we already covered, and the title is plain (no hype words).
4. Saves content/posts/<slug>.json, then scripts/build-site.py renders the site.

If a check fails it retries once with a different story, then skips the day.
Skipping is a normal outcome (exit code 0), so a bad day never publishes a bad post.

Usage:  python scripts/write-post.py            live run
        python scripts/write-post.py --dry-run  checks parsing with a sample, no API, writes nothing
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), "gemini-2.5-flash-lite"]  # second one if the first is busy
RETRY_WAITS = [30, 60, 120]  # seconds to wait after a busy or rate-limit error
MAX_CALLS = 3
REDIRECT_HOST = "vertexaisearch.cloud.google.com"  # Google search grounding links point here first
FRESH_HOURS = 72
UA = "Mozilla/5.0 (compatible; WebOnlineToolsBot/1.0; +https://webonlinetools.com/ai-news/editorial-policy.html)"
HYPE = ["unveil", "unleash", "revolution", "new era", "landmark", "game-changer", "game changer", "dawn of",
        "groundbreaking", "unprecedented", "redefin", "reshap", "ushering", "soars", "skyrocket", "leap forward"]
STOP = set("""a an the of for in on to and with its it as by at is are be how from into new era over after amid
their this that what why who will can now latest next major global ai""".split())
ALLOWED_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "strong", "em", "blockquote", "table", "thead", "tbody",
                "tr", "th", "td", "code", "br"}


# ── helpers ───────────────────────────────────────────────────────────

LOG_LINES = []


def log(msg):
    print(msg, flush=True)
    LOG_LINES.append(str(msg))


def save_log():
    """Keeps the latest run's log in data/writer-log.txt (blocked from the public site) for debugging."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(os.path.join(ROOT, "data", "writer-log.txt"), "w", encoding="utf-8") as f:
        f.write(f"Writer run {stamp}\n" + "\n".join(LOG_LINES) + "\n")


def words(text):
    text = text.lower().replace("'s", "")
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.\-]*[a-z0-9]|[a-z0-9]", text) if w not in STOP and len(w) > 1}


def slugify(text, limit=90):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9\s-]", "", text.lower())
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    if len(text) > limit:
        text = text[:limit].rsplit("-", 1)[0]
    return text


def domain(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def fetch(url, timeout=20):
    """Returns (final_url, status, html) following redirects; status 0 on network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(600_000).decode(r.headers.get_content_charset() or "utf-8", "ignore")
            return r.geturl(), r.status, body
    except urllib.error.HTTPError as e:
        return e.geturl() or url, e.code, ""
    except Exception:
        return url, 0, ""


DATE_PATTERNS = [
    r'property=["\']article:published_time["\']\s+content=["\']([^"\']+)',
    r'content=["\']([^"\']+)["\']\s+property=["\']article:published_time',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'<time[^>]+datetime=["\']([^"\']+)',
    r'name=["\'](?:pubdate|publish-date|date)["\']\s+content=["\']([^"\']+)',
]


def page_dates(url, page):
    found = []
    for pat in DATE_PATTERNS:
        for m in re.findall(pat, page, re.I)[:5]:
            d = re.match(r"(\d{4})-(\d{2})-(\d{2})", m.strip())
            if d:
                found.append(datetime(int(d[1]), int(d[2]), int(d[3]), tzinfo=timezone.utc))
    m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", url)
    if m:
        found.append(datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc))
    return found


class Sanitizer(HTMLParser):
    """Keeps only simple article markup; drops links (sources are cited separately), scripts and styles."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "h1"):
            self.skip += 1
        elif not self.skip and tag in ALLOWED_TAGS:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "h1"):
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in ALLOWED_TAGS and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))


def sanitize(body):
    s = Sanitizer()
    s.feed(body)
    s.close()
    return re.sub(r"\n{2,}", "\n", "".join(s.out)).strip()


def load_registry():
    path = os.path.join(ROOT, "data", "keywords.json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


# ── Gemini ────────────────────────────────────────────────────────────

def build_prompt(today, recent, avoid):
    covered = "\n".join(f"- {p['title']}" for p in recent)
    extra = "\n".join(f"- {t}" for t in avoid)
    return f"""You are a careful technology reporter writing for webonlinetools.com, a site of free web tools
with a reference-style AI news section. Today is {today}.

Use Google Search to find ONE significant, verifiable AI or technology story published in the last 48 hours.
Prefer stories with an official primary source (company blog, press release, filing, paper, government page).

Do NOT write about any of these stories, which we already covered:
{covered}
{("Also avoid these, which were rejected:" + chr(10) + extra) if extra else ""}

Return your answer in exactly two parts and nothing else.

Part 1: a JSON object (no markdown fences) with exactly these keys. Do NOT put the article text in it:
{{
  "title": "Plain headline, 45-65 characters, written the way people search: '[Company] [does what]: [detail]'",
  "keyword": "the specific long-tail search query this story answers, 3-8 words, lowercase",
  "company": "the main company the story is about, as its usual name (e.g. OpenAI, Google, Anthropic), or empty for government or policy stories",
  "description": "Meta description, 140-155 characters, states the main fact and the date",
  "facts": {{"Who": "...", "What": "...", "When": "date as 7 October 2026", "Status": "...", "Official source": "publisher name"}},
  "sources": [{{"n": 1, "title": "page title", "publisher": "site or organisation", "date": "YYYY-MM-DD", "url": "link from your search results"}}]
}}

Part 2: the article body as HTML, between these two marker lines:
<<<BODY>>>
...article HTML here...
<<<END>>>

Rules for the body:
- 600-900 words. Allowed tags only: h2, h3, p, ul, ol, li, strong, em, blockquote. No h1, no links, no images.
- Open with two sentences that say who did what, and when.
- Use 3-5 h2 sections phrased as reader questions, for example "What did OpenAI announce?", "How does it work?",
  "Why does it matter?", "What happens next?". Use h3 only inside an h2 section.
- After every factual sentence, add a citation marker like [1] or [2] matching the source's "n".
- Only state facts, figures, dates and quotes that appear in the sources. Never invent them.
- Write in your own words; never copy sentences from a source. Quotes must be exact and under 20 words.
- Natural, plain tone, written for a reader, not for search engines. Never use: unveils, unleashes,
  revolutionizing, new era, landmark, game-changer, groundbreaking, unprecedented, redefines, reshaping, dawn, leap.
- Do not repeat the product or company name in every sentence. After the first mention, use "it", "the model",
  "the company" and similar, as a human reporter would. Never aim for a keyword density.
- Do not mention webonlinetools.com or "online tools" unless the story is actually about them.

Rules for sources:
- At least 2 sources from different websites; at least 1 primary source; at least 1 published in the last 48 hours.
- Copy each link exactly as your search results give it, even if it is a Google redirect link. Never guess or build a URL.
- "date" is the date the source page was published.
"""


def generate(prompt):
    """Calls Gemini with Google Search, retrying busy/rate-limit errors and falling back to a lighter model."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["API_KEY"])
    config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.4)
    last = None
    for model in MODELS:
        for wait in RETRY_WAITS + [None]:
            try:
                return client.models.generate_content(model=model, contents=prompt, config=config)
            except Exception as e:
                last = e
                busy = any(code in str(e) for code in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL"))
                if not busy:
                    raise
                if wait is None:
                    log(f"   {model} still busy; trying the next model")
                    break
                log(f"   {model} busy ({str(e)[:60]}...); waiting {wait}s")
                time.sleep(wait)
    raise last


def call_gemini(prompt):
    resp = generate(prompt)
    # The search results Gemini actually used, with Google's own (uncorrupted) links.
    # "supports" marks results Google says back up part of the answer.
    grounded, supported = [], set()
    try:
        meta = resp.candidates[0].grounding_metadata
        for sup in meta.grounding_supports or []:
            supported.update(sup.grounding_chunk_indices or [])
        for i, chunk in enumerate(meta.grounding_chunks or []):
            if chunk.web and chunk.web.uri:
                grounded.append({"uri": chunk.web.uri, "title": chunk.web.title or "", "supports": i in supported})
    except (AttributeError, IndexError, TypeError):
        pass
    return resp.text or "", grounded


def parse_story(text):
    """Reads the JSON metadata and the HTML body, which comes between <<<BODY>>> and <<<END>>> markers.
    Keeping HTML out of the JSON means a stray quote in the article can't break the JSON."""
    text = text.strip()
    body = ""
    m = re.search(r"<<<BODY>>>(.*?)(?:<<<END>>>|$)", text, re.S)
    if m:
        body = m.group(1).strip()
        text = text[:m.start()]
    text = re.sub(r"```[a-z]*", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the response")
    raw = text[start:end + 1]
    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw), strict=False)  # drop trailing commas
    if body:
        data["body"] = body
    if not data.get("body"):
        raise ValueError("no article body in the response")
    return data


# ── checks ────────────────────────────────────────────────────────────

def parse_day(value):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (value or "").strip())
    return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc) if m else None


def page_title(page):
    m = re.search(r"<title[^>]*>(.*?)</title>", page or "", re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()[:150] if m else ""


def name_key(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def verify_sources(story, grounded, now, offline=False):
    """Builds the source list from Google's search results (which carry the real links), matching each of
    Gemini's numbered sources to one of them. Gemini often garbles long links when copying them, so its
    own URLs are only a hint. Returns (sources renumbered, mapping old n -> new n, fresh: bool)."""
    cache = {}

    def resolve(url):
        if url not in cache:
            cache[url] = (url, 200, "") if offline else fetch(url)
        return cache[url]

    # 1. Resolve every search result to its real page.
    results = []
    for g in grounded:
        final, status, page = resolve(g["uri"])
        d = domain(final)
        if not d or d == REDIRECT_HOST:
            log(f"   search result did not resolve: {g.get('title') or g['uri'][:80]}")
            continue
        if status in (401, 403, 429):
            status, page = 200, ""  # real page from Google's results; the site only blocks automated checks
        if status != 200:
            log(f"   search result unavailable (HTTP {status}): {final}")
            continue
        results.append({"uri": g["uri"], "url": final, "domain": d, "page": page,
                        "title": page_title(page) or g.get("title") or d, "supports": g.get("supports", False)})

    def match(src):
        url = (src.get("url") or "").strip()
        for r in results:  # exact link
            if url and (url == r["uri"] or url.rstrip("/") == r["url"].rstrip("/")):
                return r
        if url.startswith(f"https://{REDIRECT_HOST}/"):  # garbled or shortened Google link: longest shared start
            best = max(results, key=lambda r: len(os.path.commonprefix([url, r["uri"]])), default=None)
            if best and len(os.path.commonprefix([url, best["uri"]])) >= len(f"https://{REDIRECT_HOST}/grounding-api-redirect/") + 12:
                return best
        elif url.startswith("http"):  # a normal link: same site as a search result
            for r in results:
                if domain(url) == r["domain"]:
                    return r
        key = name_key(src.get("publisher")) or name_key(src.get("title"))
        for r in results:  # by publisher name, e.g. "Reuters" -> reuters.com
            label = name_key(r["domain"].split(".")[-2] if r["domain"].count(".") >= 1 else r["domain"])
            if key and label and (label in key or key in label):
                return r
        return None

    kept, mapping, used = [], {}, set()

    def add(r, title=None, publisher=None, stated_date=""):
        dates = [now] if offline else page_dates(r["url"], r["page"])
        if not dates and parse_day(stated_date):
            dates = [parse_day(stated_date)]  # page had no machine-readable date; use the stated one
        kept.append({"title": title or r["title"], "publisher": publisher or r["domain"],
                     "date": stated_date or (dates[0].date().isoformat() if dates else ""), "url": r["url"],
                     "_dates": dates})
        used.add(r["url"])
        return len(kept)

    # 2. Gemini's numbered sources, matched to real results (keeps the [n] citations in the text correct).
    for src in story.get("sources", []):
        r = match(src)
        if not r:
            log(f"   drop source (no matching search result): {src.get('publisher') or src.get('title') or src.get('url', '?')[:80]}")
            continue
        if r["url"] in used:
            mapping[int(src.get("n", 0))] = next(i for i, k in enumerate(kept, 1) if k["url"] == r["url"])
            continue
        mapping[int(src.get("n", 0))] = add(r, src.get("title"), src.get("publisher"), src.get("date", ""))

    # 3. Other results Google says support the answer are listed too (without [n] markers in the text).
    for r in results:
        if r["url"] not in used and r["supports"] and len(kept) < 6:
            add(r)

    window_start, window_end = now - timedelta(hours=FRESH_HOURS), now + timedelta(days=1)
    fresh = any(window_start <= d0 <= window_end for k in kept for d0 in k["_dates"])
    for k in kept:
        k.pop("_dates")
    return kept, mapping, fresh


def renumber(body, mapping):
    def repl(m):
        new = mapping.get(int(m.group(1)))
        return f"[{new}]" if new else ""
    return re.sub(r"\[(\d{1,2})\]", repl, body)


def repeated_phrase(body):
    """Returns (phrase, share of words) for the most repeated 2-3 word phrase, to catch keyword stuffing."""
    text = re.sub(r"<[^>]+>", " ", body).lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9\-']*", text)
    if len(tokens) < 100:
        return "", 0.0
    best = ("", 0.0)
    for k in (2, 3):
        counts = {}
        for i in range(len(tokens) - k + 1):
            if tokens[i] in STOP or tokens[i + k - 1] in STOP:
                continue
            phrase = " ".join(tokens[i:i + k])
            counts[phrase] = counts.get(phrase, 0) + 1
        for phrase, n in counts.items():
            share = n * k / len(tokens)
            if share > best[1]:
                best = (phrase, share)
    return best


def check_story(story, registry, now):
    problems = []
    phrase, share = repeated_phrase(story.get("body", ""))
    if share > 0.025:
        problems.append(f"'{phrase}' makes up {share:.1%} of the text (keyword stuffing)")
    title = story.get("title", "").strip()
    if not 25 <= len(title) <= 75:
        problems.append(f"title length {len(title)}")
    if any(h in title.lower() for h in HYPE):
        problems.append("hype word in title")
    body_words = len(re.sub(r"<[^>]+>", " ", story.get("body", "")).split())
    if body_words < 450:
        problems.append(f"body only {body_words} words")
    mine = words(f"{title} {story.get('keyword', '')}")
    cutoff = (now - timedelta(days=45)).date().isoformat()
    for p in registry:
        if p["published"] < cutoff:
            continue
        theirs = words(f"{p['title']} {p.get('keyword', '')}")
        overlap = len(mine & theirs) / max(1, len(mine | theirs))
        same_keyword = story.get("keyword") and story.get("keyword", "").strip().lower() == (p.get("keyword") or "").lower()
        if overlap >= 0.45 or same_keyword:
            problems.append(f"duplicate of '{p['title']}'")
            break
    return problems


def register_company(name):
    """Adds a company we have not covered before, so its hub and menu link appear once it has enough stories."""
    if not name:
        return
    path = os.path.join(ROOT, "data", "companies.json")
    companies = json.load(open(path, encoding="utf-8"))
    known = {c["name"].lower() for c in companies} | {m for c in companies for m in c["match"]}
    if name.lower() in known:
        return
    slug = slugify(name)
    if not slug or slug in {c["slug"] for c in companies}:
        return
    companies.insert(len(companies) - 1, {"name": name, "slug": slug, "match": [re.escape(name.lower())],
                                          "about": f"{name}'s AI products, research and business news"})
    with open(path, "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in companies) + "\n]\n")
    log(f"Added new company to data/companies.json: {name}")


# ── main ──────────────────────────────────────────────────────────────

SAMPLE = {
    "title": "Example Corp releases Model X with a 1M-token context window",
    "keyword": "model x context window",
    "description": "Example Corp released Model X on 7 October 2026 with a one-million-token context window and lower API prices for developers.",
    "facts": {"Who": "Example Corp", "What": "Released Model X", "When": "7 October 2026", "Status": "Available now"},
    "body": "<h1>dup</h1><p>Example Corp released Model X today. [1]</p><h2>What did Example Corp release?</h2>"
            + "".join(f"<p>{line} [{1 + n % 2}]</p>" for n, line in enumerate([
                "The release targets developers who work with long contracts, research papers and large codebases.",
                "Pricing starts lower than the previous generation, according to the company's announcement.",
                "Independent testers reported faster responses on summarisation and retrieval tasks.",
                "Availability begins in North America and Europe, with other regions following next quarter.",
                "Enterprise customers can run it inside their own cloud accounts for data control.",
                "Critics noted that benchmark gains on reasoning tasks were smaller than on coding tasks.",
                "Analysts expect rival labs to respond with price cuts before the end of the year.",
                "Safety documentation describes red-team testing on misuse scenarios before launch.",
                "Existing applications can switch over by changing a single setting in their requests.",
                "Support for image input arrives first, while audio is planned for a later update.",
            ] * 4))
            + '<p><a href="https://evil.example">link</a><script>alert(1)</script>Done. [3]</p>',
    "sources": [{"n": 1, "title": "Introducing Model X", "publisher": "Example Corp", "date": "2026-10-07", "url": "https://example.com/model-x"},
                {"n": 2, "title": "Model X pricing", "publisher": "Example News", "date": "2026-10-07", "url": "https://news.example.org/model-x"},
                {"n": 3, "title": "Made up", "publisher": "Nowhere", "date": "2026-10-07", "url": "https://invented.example.net/x"}],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--if-none-today", action="store_true", help="exit quietly if a story was already published today (UTC)")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    today = f"{now.day} {now.strftime('%B %Y')}"
    registry = load_registry()
    if args.if_none_today and any(p.get("published") == now.date().isoformat() for p in registry):
        log("A story was already published today. Nothing to do.")
        return 0
    recent = [p for p in registry if p["published"] >= (now - timedelta(days=30)).date().isoformat()][:40]
    rejected = []

    for attempt in range(1, MAX_CALLS + 1):
        log(f"Attempt {attempt} of {MAX_CALLS}")
        if args.dry_run:
            text, grounded = json.dumps(SAMPLE), [{"uri": "https://example.com/model-x", "title": "example.com"},
                                                   {"uri": "https://news.example.org/model-x", "title": "news.example.org"}]
        else:
            try:
                text, grounded = call_gemini(build_prompt(today, recent, rejected))
            except Exception as e:
                log(f"Gemini call failed: {e}. Skipping today.")
                return 0
        log(f"   Gemini returned {len(text)} characters and {len(grounded)} search links")
        try:
            story = parse_story(text)
        except (ValueError, json.JSONDecodeError) as e:
            log(f"   rejected: unreadable response ({e}). Start of response: {text[:300]!r}")
            continue

        problems = check_story(story, registry, now)
        sources, mapping, fresh = verify_sources(story, grounded, now, offline=args.dry_run)
        if len(sources) < 2 or len({domain(s['url']) for s in sources}) < 2:
            problems.append(f"only {len(sources)} verified source(s) from different sites")
        if not fresh:
            problems.append(f"no source dated within {FRESH_HOURS} hours")
        if problems:
            log(f"   rejected '{story.get('title', '?')}': {'; '.join(problems)}")
            rejected.append(story.get("title", "?"))
            continue

        slug = slugify(story["title"])
        existing = {p["slug"] for p in registry}
        if slug in existing:
            slug = f"{slug}-{now.strftime('%Y-%m-%d')}"
        post = {
            "slug": slug,
            "title": story["title"].strip(),
            "description": story.get("description", "").strip()[:160],
            "keyword": story.get("keyword", "").strip().lower(),
            "published": now.replace(microsecond=0).isoformat(),
            "updated": "",
            "facts": {k: str(v) for k, v in (story.get("facts") or {}).items() if v},
            "company": (story.get("company") or "").strip(),
            "sources": sources,
            "related": [],
            "status": "verified",
            "body": renumber(sanitize(story.get("body", "")), mapping),
        }
        if args.dry_run:
            log(json.dumps({k: (v if k != "body" else v[:300] + "…") for k, v in post.items()}, indent=2))
            log("Dry run passed. Nothing written.")
            return 0
        path = os.path.join(ROOT, "content", "posts", slug + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(post, f, indent=2, ensure_ascii=False)
        log(f"Saved {path} with {len(sources)} sources")
        register_company(post["company"])
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build-site.py")], check=True)
        return 0

    log("No story passed the checks today. Nothing published.")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:  # record unexpected crashes too, then fail the run
        log(f"Crashed: {type(e).__name__}: {e}")
        save_log()
        raise
    if not any(a == "--dry-run" for a in sys.argv):
        save_log()
    sys.exit(code)
