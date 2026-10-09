"""
Daily AI news writer. Runs in GitHub Actions with the free Gemini API.

1. Find: Gemini (with Google Search) picks one AI story from the last 48 hours.
2. Read: this script opens the real pages from Google's search results and keeps readable pages
   about the story, one per site. If fewer than two, it searches once more for other reports.
3. Write: Gemini writes the article from ONLY those page texts, citing them as [1], [2]...
   so every citation points to a page that was actually read.
4. Publishes only if the article cites 2+ different sites, the pages are recent (72 hours),
   the story is new to the site, the title is plain and no phrase is repeated (no keyword stuffing).
5. Saves content/posts/<slug>.json, then scripts/build-site.py renders the site.

If a check fails it tries a different story, up to three times, then skips the day.
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

def generate(prompt, search):
    """Calls Gemini, retrying busy/rate-limit errors and falling back to a lighter model."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["API_KEY"])
    tools = [types.Tool(google_search=types.GoogleSearch())] if search else None
    config = types.GenerateContentConfig(tools=tools, temperature=0.3 if search else 0.5)
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


def ask(prompt, search=False):
    """Returns (text, search results). Search results carry Google's real links to the pages it found."""
    resp = generate(prompt, search)
    grounded = []
    try:
        for chunk in resp.candidates[0].grounding_metadata.grounding_chunks or []:
            if chunk.web and chunk.web.uri:
                grounded.append({"uri": chunk.web.uri, "title": chunk.web.title or ""})
    except (AttributeError, IndexError, TypeError):
        pass
    return resp.text or "", grounded


def first_json(text):
    text = re.sub(r"```[a-z]*", "", text or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the response")
    raw = text[start:end + 1]
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", raw), strict=False)


def find_prompt(today, covered, avoid):
    return f"""Today is {today}. Use Google Search to find ONE significant, verifiable news story about AI
(models, companies, products, research or policy) that was published in the last 48 hours.
Pick a story that at least two independent news outlets have reported, ideally with an official announcement.

Do not pick any of these stories, which are already covered:
{covered}
{("Also skip these, which were rejected:" + chr(10) + avoid) if avoid else ""}

Reply with only a JSON object:
{{"headline": "what happened, in plain words", "summary": "two sentences: who did what, and when",
  "company": "main company involved, or empty for government or policy stories"}}"""


def more_prompt(headline, summary):
    return f"""Use Google Search to find news reports and the official announcement about this story:
{headline}. {summary}
List what you found as a JSON object: {{"reports": [{{"title": "...", "publisher": "..."}}]}}"""


def write_prompt(today, headline, sources):
    blocks = "\n\n".join(
        f"[{i}] {s['title']} | {s['domain']} | {s['date'] or 'date unknown'}\n{s['text']}" for i, s in enumerate(sources, 1))
    return f"""You are a careful technology reporter. Today is {today}.
Write a news article about: {headline}

Use ONLY the numbered source texts below. Every fact, figure, date and quote must come from them.
Write in your own words; quotes must be exact and under 20 words. If the sources disagree, say so.

Return exactly two parts and nothing else.
Part 1, a JSON object (no markdown fences):
{{
  "title": "Plain headline, 45-65 characters, the way people search: '[Company] [does what]: [detail]'",
  "keyword": "the specific long-tail search query this story answers, 3-8 words, lowercase",
  "company": "main company the story is about, or empty for government or policy stories",
  "description": "Meta description, 140-155 characters, states the main fact and the date",
  "facts": {{"Who": "...", "What": "...", "When": "date as 7 October 2026", "Status": "..."}}
}}
Part 2, the article body as HTML between these marker lines:
<<<BODY>>>
...article HTML...
<<<END>>>

Rules for the body:
- 600-900 words. Allowed tags only: h2, h3, p, ul, ol, li, strong, em, blockquote. No h1, no links.
- Start with a paragraph (not a heading) of two sentences saying who did what, and when.
- Then 3-5 h2 sections phrased as reader questions, such as "What did the company announce?",
  "How does it work?", "Why does it matter?", "What happens next?".
- After every factual sentence put the number of the source it comes from, like [1] or [2].
  Use only the numbers listed below. Use as many different sources as genuinely support the facts.
- Natural, plain tone written for readers, not search engines. Never use: unveils, unleashes,
  revolutionizing, new era, landmark, game-changer, groundbreaking, unprecedented, redefines, reshaping.
- Don't repeat the company or product name in every sentence; after the first mention use "it", "the
  company", "the model" and so on. Never aim for a keyword density.
- Do not mention webonlinetools.com or "online tools".

SOURCES:
{blocks}"""


# ── reading the source pages ─────────────────────────────────────────

class TextExtractor(HTMLParser):
    """Collects readable paragraph text from a news page, skipping menus, scripts and footers."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "figure"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.in_p, self.parts, self.cur = 0, 0, [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("p", "li", "h2", "h3") and not self.skip:
            self.in_p += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("p", "li", "h2", "h3") and self.in_p:
            self.in_p -= 1
            text = re.sub(r"\s+", " ", "".join(self.cur)).strip()
            if len(text.split()) >= 6:
                self.parts.append(text)
            self.cur = []

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.cur.append(data)


def page_text(page, max_words=900):
    t = TextExtractor()
    try:
        t.feed(page)
    except Exception:
        pass
    seen, out = set(), []
    for p in t.parts:  # drop repeated boilerplate lines
        if p not in seen:
            seen.add(p)
            out.append(p)
    text = "\n".join(out)
    tokens = text.split(" ")
    return " ".join(tokens[:max_words])


def page_title(page):
    m = re.search(r"<title[^>]*>(.*?)</title>", page or "", re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()[:150] if m else ""


def read_sources(grounded, topic, have):
    """Opens each search result, keeps readable pages about the story (one per site)."""
    sites = {s["domain"] for s in have}
    out = []
    for g in grounded:
        final, status, page = fetch(g["uri"])
        d = domain(final)
        if not d or d == REDIRECT_HOST:
            log(f"   skip result (link did not open): {g.get('title') or '?'}")
            continue
        if d in sites:
            continue
        if status != 200:
            log(f"   skip {d} (HTTP {status}; the site blocks automated reading)")
            continue
        text = page_text(page)
        title = page_title(page) or g.get("title") or d
        overlap = len(topic & words(title + " " + text[:1500]))
        if len(text.split()) < 120:
            log(f"   skip {d} (too little readable text)")
            continue
        if overlap < 3:
            log(f"   skip {d} (not about this story: {title[:60]})")
            continue
        dates = page_dates(final, page)
        sites.add(d)
        out.append({"url": final, "domain": d, "title": title, "text": text, "dates": dates,
                    "date": max(dates).date().isoformat() if dates else ""})
        log(f"   read {d}: {title[:70]}")
    return out


def renumber(body, mapping):
    def repl(m):
        new = mapping.get(int(m.group(1)))
        return f"[{new}]" if new else ""
    return re.sub(r"\[(\d{1,2})\]", repl, body)




# ── checks ────────────────────────────────────────────────────────────

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

SAMPLE_FIND = {"headline": "Example Corp releases Model X", "summary": "Example Corp released Model X on 9 October 2026.",
               "company": "Example Corp"}
SAMPLE_SOURCES = [
    {"url": "https://example.com/model-x", "domain": "example.com", "title": "Introducing Model X",
     "text": "Example Corp released Model X today.", "dates": [], "date": ""},
    {"url": "https://news.example.org/model-x", "domain": "news.example.org", "title": "Example Corp's Model X",
     "text": "Reporters tested Model X.", "dates": [], "date": ""},
]
SAMPLE_ARTICLE = """{"title": "Example Corp releases Model X with a 1M-token context window",
 "keyword": "model x context window", "company": "Example Corp",
 "description": "Example Corp released Model X on 9 October 2026 with a one-million-token context window and lower prices for developers.",
 "facts": {"Who": "Example Corp", "What": "Released Model X", "When": "9 October 2026", "Status": "Available now"}}
<<<BODY>>>
<p>Example Corp released Model X on 9 October 2026. [1] Reporters tested it the same day. [2]</p>
""" + "".join(f"<p>{line} [{1 + n % 2}]</p>" for n, line in enumerate([
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
] * 4)) + "\n<<<END>>>"


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
    covered = "\n".join(f"- {p['title']}" for p in recent)
    rejected = []
    window_start, window_end = now - timedelta(hours=FRESH_HOURS), now + timedelta(days=1)

    for attempt in range(1, MAX_CALLS + 1):
        log(f"Attempt {attempt} of {MAX_CALLS}")
        try:
            # Step 1: find a story (search on).
            if args.dry_run:
                pick, grounded = SAMPLE_FIND, []
            else:
                text, grounded = ask(find_prompt(today, covered, "\n".join(f"- {t}" for t in rejected)), search=True)
                pick = first_json(text)
            headline = (pick.get("headline") or "").strip()
            if not headline:
                log("   no story found in the response")
                continue
            log(f"   story: {headline} ({len(grounded)} search results)")
            topic = words(headline + " " + pick.get("summary", "") + " " + pick.get("company", ""))

            # Step 2: read the real pages; search again if fewer than two sites are readable.
            sources = SAMPLE_SOURCES if args.dry_run else read_sources(grounded, topic, [])
            if len(sources) < 2 and not args.dry_run:
                _, more = ask(more_prompt(headline, pick.get("summary", "")), search=True)
                log(f"   searching for more reports ({len(more)} results)")
                sources += read_sources(more, topic, sources)
            if len(sources) < 2:
                log(f"   rejected '{headline}': only {len(sources)} readable source page(s) about it")
                rejected.append(headline)
                continue
            dated = [d for s in sources for d in s["dates"]]
            if dated and not any(window_start <= d <= window_end for d in dated):
                log(f"   rejected '{headline}': the source pages are older than {FRESH_HOURS} hours")
                rejected.append(headline)
                continue
            if not dated:
                log("   note: no publication dates found on the source pages")

            # Step 3: write only from those pages (search off).
            text = SAMPLE_ARTICLE if args.dry_run else ask(write_prompt(today, headline, sources[:6]))[0]
            story = parse_story(text)
        except Exception as e:
            log(f"   attempt failed: {type(e).__name__}: {str(e)[:200]}")
            continue

        body = sanitize(story.get("body", ""))
        cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", body) if 1 <= int(n) <= len(sources[:6])})
        cited_sites = {sources[n - 1]["domain"] for n in cited}
        problems = check_story(story, registry, now)
        if len(cited_sites) < 2:
            problems.append(f"the article cites only {len(cited_sites)} of the source sites")
        if problems:
            log(f"   rejected '{story.get('title', headline)}': {'; '.join(problems)}")
            rejected.append(headline)
            continue

        mapping = {old: new for new, old in enumerate(cited, 1)}
        post_sources = [{"title": sources[n - 1]["title"], "publisher": sources[n - 1]["domain"],
                         "date": sources[n - 1]["date"], "url": sources[n - 1]["url"]} for n in cited]
        slug = slugify(story["title"])
        if slug in {p["slug"] for p in registry}:
            slug = f"{slug}-{now.strftime('%Y-%m-%d')}"
        post = {
            "slug": slug,
            "title": story["title"].strip(),
            "description": story.get("description", "").strip()[:160],
            "keyword": story.get("keyword", "").strip().lower(),
            "published": now.replace(microsecond=0).isoformat(),
            "updated": "",
            "facts": {k: str(v) for k, v in (story.get("facts") or {}).items() if v},
            "company": (story.get("company") or pick.get("company") or "").strip(),
            "sources": post_sources,
            "related": [],
            "status": "verified",
            "body": renumber(body, mapping),
        }
        if args.dry_run:
            log(json.dumps({k: (v if k != "body" else v[:200] + "…") for k, v in post.items()}, indent=2))
            log("Dry run passed. Nothing written.")
            return 0
        path = os.path.join(ROOT, "content", "posts", slug + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(post, f, indent=2, ensure_ascii=False)
        log(f"Saved {path} with {len(post_sources)} sources: {', '.join(s['publisher'] for s in post_sources)}")
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
