"""
Builds everything served at /ai-news/ from the data files. Safe to run any time;
it regenerates the same output from the same inputs.

Reads:   content/posts/*.json, data/*.json, templates/editorial-policy.html, assets/ui.css,
         root-site/tools.json (footer links); header and footer come from scripts/uikit.py
Writes:  <slug>.html for each post, index.html, editorial-policy.html, sitemap.xml,
         feed.xml, index.json, files.json, data/keywords.json, .htaccess
"""
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone

import uikit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://webonlinetools.com"
BASE = "/ai-news/"
STATIC_PAGES = {"index.html", "editorial-policy.html"}
HUB_MIN = 4          # a company or topic gets its own hub page once it has this many stories
BRAND = " | Web Online Tools"
STOPWORDS = set("""a an the of for in on to and with its it as by at is are be how from into new era
over after amid after its their this that what why who will can now latest next major global ai""".split())
HYPEWORDS = set("""unveils unveil unleashes unleash revolutionizing revolutionizes revolutionize landmark
dawn leap game changer groundbreaking unprecedented redefines redefining reshaping reshape ushering
soars transforms transforming""".split())


def path(*parts):
    return os.path.join(ROOT, *parts)


def read(rel):
    with open(path(rel), encoding="utf-8") as f:
        return f.read()


def write(rel, text):
    with open(path(rel), "w", encoding="utf-8") as f:
        f.write(text)


def esc(text):
    return html.escape(text or "", quote=True)


def parse_date(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def nice_date(dt):
    return f"{dt.day} {dt.strftime('%B %Y')}"


def short_date(dt):
    return f"{dt.day} {dt.strftime('%b %Y')}"


def json_ld(data):
    text = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{text}\n</script>'


def topic_words(post):
    text = f"{post['title']} {post.get('keyword', '')}".lower().replace("'s", "")
    words = re.findall(r"[a-z0-9][a-z0-9.\-]*[a-z0-9]|[a-z0-9]", text)
    return {w for w in words if w not in STOPWORDS and w not in HYPEWORDS and len(w) > 1}


def seo_title(title):
    """Adds the brand to the title tag only when the whole tag stays within about 60 characters."""
    return title + BRAND if len(title + BRAND) <= 60 else title


# ── data ──────────────────────────────────────────────────────────────

def load_companies():
    entries = json.loads(read("data/companies.json"))
    for e in entries:
        e["patterns"] = [re.compile(r"(?<![a-z0-9])(?:" + m + r")(?![a-z0-9])") for m in e["match"]]
    return entries


def assign_categories(posts, companies):
    """Tags each post with the companies and topics named in its title; returns hubs that have enough stories."""
    for post in posts:
        title = post["title"].lower()
        found = []
        for e in companies:
            spots = [m.start() for pat in e["patterns"] for m in [pat.search(title)] if m]
            if spots:
                found.append((e.get("kind") == "topic", min(spots), e["slug"]))
        post["cats"] = [slug for _, _, slug in sorted(found)]
    counts = {}
    for post in posts:
        for slug in post["cats"]:
            counts[slug] = counts.get(slug, 0) + 1
    hubs = [dict(e, count=counts[e["slug"]]) for e in companies if counts.get(e["slug"], 0) >= HUB_MIN]
    hubs.sort(key=lambda h: (h.get("kind") == "topic", -h["count"]))
    return hubs

def load_posts():
    redirects = json.loads(read("data/redirects.json")) if os.path.exists(path("data/redirects.json")) else {}
    posts = []
    for fn in os.listdir(path("content/posts")):
        if not fn.endswith(".json"):
            continue
        post = json.loads(read(f"content/posts/{fn}"))
        if post["slug"] in redirects:
            continue
        post["publishedDt"] = parse_date(post["published"])
        post["updatedDt"] = parse_date(post.get("updated")) or post["publishedDt"]
        post["words"] = topic_words(post)
        posts.append(post)
    posts.sort(key=lambda p: p["publishedDt"], reverse=True)
    return posts, redirects


def related_posts(post, posts, count=4):
    scored = []
    for other in posts:
        if other is post:
            continue
        shared = len(post["words"] & other["words"])
        if shared >= 2:
            gap = abs((post["publishedDt"] - other["publishedDt"]).days)
            scored.append((shared, -gap, other))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    picks = [s[2] for s in scored[:count]]
    if len(picks) < count:  # top up with the nearest stories in time so no page is a dead end
        nearby = sorted((p for p in posts if p is not post and p not in picks),
                        key=lambda p: abs((post["publishedDt"] - p["publishedDt"]).total_seconds()))
        picks += nearby[:count - len(picks)]
    return picks



# ── presentation ──────────────────────────────────────────────────────
# Header, footer and icons come from scripts/uikit.py, shared with the homepage and tool pages.

ORG = {"@type": "Organization", "name": "Web Online Tools", "url": SITE + "/"}
AUTHOR = {"@type": "Organization", "name": "Web Online Tools Editorial", "url": SITE + BASE + "editorial-policy.html"}
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800'
         '&family=JetBrains+Mono:wght@400;500&display=swap">')


def read_time(post):
    words = len(re.sub(r"<[^>]+>", " ", post["body"]).split())
    return max(1, round(words / 230))


def link_citations(body, source_count):
    """Turns [1], [2] markers into links to the matching source, only when that source exists."""
    def repl(m):
        n = int(m.group(1))
        if 1 <= n <= source_count:
            return f'<sup class="cite"><a href="#source-{n}" aria-label="Source {n}">[{n}]</a></sup>'
        return ""
    return re.sub(r"\[(\d{1,2})\](?![^<]*</a>)", repl, body)


def breadcrumb_schema(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": url} for i, (name, url) in enumerate(items, 1)]}


def crumbs(items):
    """items: list of (label, href or None for the current page)."""
    parts = []
    for label, href in items:
        parts.append(f'<a href="{href}">{esc(label)}</a>' if href else f'<span aria-current="page">{esc(label)}</span>')
    return '<nav class="crumbs" aria-label="Breadcrumb">' + '<span class="sep">/</span>'.join(parts) + "</nav>"


def render_page(main, *, title, description, canonical, schema, reg, hubs, ogtype="article", ogtitle=None,
                current="news", extra_script=""):
    css_version = hashlib.md5(read("assets/ui.css").encode()).hexdigest()[:8]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{uikit.JS_FLAG}
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="{ogtype}">
<meta property="og:site_name" content="Web Online Tools">
<meta property="og:title" content="{esc(ogtitle or title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#060b18">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="alternate" type="application/rss+xml" title="Web Online Tools AI news" href="{SITE}{BASE}feed.xml">
{FONTS}
<link rel="stylesheet" href="{BASE}assets/ui.css?v={css_version}">
{schema}
</head>
<body class="ui">
{uikit.header(current)}
<main id="content">
{main}
</main>
{uikit.footer(reg, hubs)}
{uikit.UI_SCRIPT}
{extra_script}
</body>
</html>
"""


def hub_lookup(hubs):
    return {h["slug"]: h for h in hubs}


def post_hubs(post, hubs):
    by = hub_lookup(hubs)
    return [by[c] for c in post.get("cats", []) if c in by]


def news_card(post, hubs, delay=0.0):
    ph = post_hubs(post, hubs)
    badge = uikit.hub_badge(ph[0]) if ph else '<span class="badge" style="--badge:#94a3b8">AI news</span>'
    search = esc(f"{post['title']} {post.get('description', '')} {' '.join(h['name'] for h in ph)}".lower())
    return (f'<li class="reveal" style="--d:{delay:.2f}s" data-search="{search}">'
            f'<a class="card news-card" href="{BASE}{post["slug"]}.html">'
            f'<div class="meta">{badge}<span class="meta-item">{uikit.icon("calendar", 14)}'
            f'<time datetime="{post["publishedDt"].date()}">{short_date(post["publishedDt"])}</time></span></div>'
            f'<h3>{esc(post["title"])}</h3><p>{esc(post.get("description", ""))}</p>'
            f'<div class="card-foot"><span class="meta-item">{uikit.icon("clock", 14)}{read_time(post)} min read</span>'
            f'<span class="card-go">Read {uikit.icon("arrow", 16)}</span></div></a></li>')


def featured_card(post, hubs):
    ph = post_hubs(post, hubs)
    hub = ph[0] if ph else None
    badge = uikit.hub_badge(hub) if hub else '<span class="badge" style="--badge:#94a3b8">AI news</span>'
    art_icon = "scale" if hub and hub.get("kind") == "topic" else ("building" if hub else "news")
    art_label = esc(hub["name"]) if hub else "Latest"
    return (f'<a class="card featured reveal" href="{BASE}{post["slug"]}.html">'
            f'<div class="featured-art" aria-hidden="true"><div style="display:grid;justify-items:center;gap:10px;position:relative;z-index:1">'
            f'{uikit.icon(art_icon, 56)}<strong style="font-size:1.4rem;letter-spacing:-0.02em">{art_label}</strong></div></div>'
            f'<div class="featured-body"><div class="news-card"><div class="meta">{badge}'
            f'<span class="badge" style="--badge:#22d3ee">Latest story</span>'
            f'<span class="meta-item">{uikit.icon("calendar", 14)}{short_date(post["publishedDt"])}</span></div></div>'
            f'<h3>{esc(post["title"])}</h3><p>{esc(post.get("description", ""))}</p>'
            f'<div class="card-foot"><span class="meta-item">{uikit.icon("clock", 14)}{read_time(post)} min read</span>'
            f'<span class="card-go">Read the story {uikit.icon("arrow", 16)}</span></div></div></a>')


def hub_chips(hubs, current=None, total=None):
    all_chip = (f'<li><a class="chip" href="{BASE}"' + (' aria-current="page"' if current == "all" else "")
                + f'>{uikit.icon("news", 16)}All stories' + (f' <span class="count">{total}</span>' if total else "") + "</a></li>")
    chips = "".join(
        f'<li><a class="chip" style="--badge:{uikit.hub_color(h["slug"])}" href="{BASE}{h["slug"]}/"'
        + (' aria-current="page"' if h["slug"] == current else "")
        + f'><span class="dot"></span>{esc(h["name"])} <span class="count">{h["count"]}</span></a></li>'
        for h in hubs)
    return f'<ul class="chips" aria-label="Browse by company or topic">{all_chip}{chips}</ul>'


FILTER_SCRIPT = """<script>
(function () {
  var list = document.getElementById("story-list"); if (!list) return;
  var items = Array.prototype.slice.call(list.children), step = 18, shown = step;
  var box = document.getElementById("story-filter"), more = document.getElementById("show-more"), empty = document.getElementById("no-stories");
  function render() {
    var q = box ? box.value.trim().toLowerCase() : "", visible = 0;
    items.forEach(function (li) {
      var match = !q || li.getAttribute("data-search").indexOf(q) > -1;
      var show = match && (q || visible < shown);
      li.classList.toggle("is-hidden", !show);
      if (show) { visible++; li.classList.add("in"); }
    });
    var remaining = q ? 0 : items.length - shown;
    if (more) more.classList.toggle("is-hidden", remaining <= 0);
    if (empty) empty.style.display = q && !visible ? "block" : "none";
  }
  if (box) box.addEventListener("input", render);
  if (more) more.querySelector("button").addEventListener("click", function () { shown += step; render(); });
  render();
})();
</script>"""


def story_grid(posts, hubs, with_filter=True):
    cards = "".join(news_card(p, hubs, delay=min(i % 6, 5) * 0.05) for i, p in enumerate(posts))
    return (f'<ul class="ui-grid ui-grid-3" id="story-list">{cards}</ul>'
            '<p class="empty-state" id="no-stories">No stories match that search.</p>'
            f'<div class="load-more is-hidden" id="show-more"><button class="ui-btn ui-btn-ghost" type="button">Show more stories {uikit.icon("arrow", 16)}</button></div>')


# ── pages ─────────────────────────────────────────────────────────────

def build_post(post, posts, hubs, reg):
    url = f"{SITE}{BASE}{post['slug']}.html"
    ph = post_hubs(post, hubs)
    primary = ph[0] if ph else None
    sources = post.get("sources") or []
    body = re.sub(r'<a\s[^>]*href="https?://vertexaisearch\.cloud\.google\.com[^"]*"[^>]*>(.*?)</a>', r"\1",
                  post["body"], flags=re.S | re.I)
    body = link_citations(body, len(sources))

    badges = "".join(uikit.hub_badge(h) for h in ph) or '<span class="badge" style="--badge:#94a3b8">AI news</span>'
    updated = ""
    if post["updatedDt"].date() != post["publishedDt"].date():
        updated = f'<span class="meta-item">{uikit.icon("check", 15)}Updated {nice_date(post["updatedDt"])}</span>'
    meta = (f'<div class="article-meta"><span class="meta-item">{uikit.icon("calendar", 15)}'
            f'<time datetime="{post["publishedDt"].date()}">{nice_date(post["publishedDt"])}</time></span>{updated}'
            f'<span class="meta-item">{uikit.icon("clock", 15)}{read_time(post)} min read</span>'
            f'<span class="meta-item">{uikit.icon("book", 15)}By <a href="{BASE}editorial-policy.html">Web Online Tools Editorial</a></span></div>')
    correction = ""
    if post.get("correction"):
        c = post["correction"]
        when = nice_date(parse_date(c["date"] + "T00:00:00")) if c.get("date") else ""
        correction = (f'<div class="callout callout-warn" role="note">{uikit.icon("alert", 18)}<div><strong>Correction'
                      f'{", " + when if when else ""}.</strong> {esc(c["text"])}</div></div>')
    trail = [("Home", "/"), ("AI news", BASE)] + ([(primary["name"], f'{BASE}{primary["slug"]}/')] if primary else []) + [(post["title"], None)]

    if sources:
        items = "".join(
            f'<li id="source-{i}"><div><a href="{esc(s["url"])}" rel="noopener" target="_blank">{esc(s.get("title") or s["url"])}</a>'
            f'<span class="src-meta">{esc(", ".join(x for x in (s.get("publisher"), s.get("date")) if x))}</span></div></li>'
            for i, s in enumerate(sources, 1))
        sources_html = f'<section aria-labelledby="sources-title" style="margin-top:48px"><h2 class="block-title" id="sources-title">{uikit.icon("link", 22)}Sources</h2><ol class="sources-list">{items}</ol></section>'
    else:
        sources_html = (f'<div class="callout callout-info" style="margin-top:40px">{uikit.icon("info", 18)}<div>This story was published before we '
                        f'started listing sources and is being re-checked under our <a href="{BASE}editorial-policy.html">editorial policy</a>.</div></div>')

    facts = post.get("facts") or {}
    facts_html = ""
    if any(facts.values()):
        rows = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in facts.items() if v)
        facts_html = f'<section class="ui-panel facts" aria-labelledby="facts-title"><h2 id="facts-title">{uikit.icon("info", 18)}Key facts</h2><dl>{rows}</dl></section>'
    share = (f'<section class="ui-panel" aria-labelledby="share-title"><h2 id="share-title">{uikit.icon("share", 18)}Share</h2><div class="share-row">'
             f'<button class="share-btn" type="button" data-copy="{url}">{uikit.icon("link", 16)}<span>Copy link</span></button>'
             f'<a class="share-btn" href="https://twitter.com/intent/tweet?url={url}&amp;text={esc(post["title"])}" target="_blank" rel="noopener">X</a>'
             f'<a class="share-btn" href="https://www.linkedin.com/sharing/share-offsite/?url={url}" target="_blank" rel="noopener">LinkedIn</a></div></section>')
    more_html = ""
    if primary:
        more = [p for p in posts if primary["slug"] in p.get("cats", []) and p is not post][:4]
        if more:
            links = "".join(f'<li style="padding:10px 0;border-top:1px solid var(--line)"><a href="{BASE}{p["slug"]}.html" style="color:var(--t1);text-decoration:none;font-weight:500">{esc(p["title"])}</a>'
                            f'<div style="font-size:.8rem;color:var(--t3);margin-top:2px">{short_date(p["publishedDt"])}</div></li>' for p in more)
            more_html = (f'<section class="ui-panel" aria-labelledby="more-title"><h2 id="more-title">{uikit.icon("building", 18)}More from {esc(primary["name"])}</h2>'
                         f'<ul style="list-style:none;margin:0;padding:0">{links}</ul>'
                         f'<p style="margin:12px 0 0"><a class="link-arrow" href="{BASE}{primary["slug"]}/">All {esc(primary["name"])} stories {uikit.icon("arrow", 16)}</a></p></section>')
    related = "".join(news_card(p, hubs, delay=i * 0.06) for i, p in enumerate(related_posts(post, posts)))

    main = f"""<div class="container">
{crumbs(trail)}
<header class="article-hero">
  <div class="chips">{badges}</div>
  <h1>{esc(post["title"])}</h1>
  {f'<p class="lead">{esc(post["description"])}</p>' if post.get("description") else ""}
  {meta}
</header>
<div class="article-layout">
  <article>
    {correction}
    <div class="prose">
{body}
    </div>
    {sources_html}
  </article>
  <aside class="side" aria-label="About this story"><div class="side-sticky">{facts_html}{share}{more_html}</div></aside>
</div>
<section class="section" aria-labelledby="related-title" style="padding-top:24px">
  <div class="section-head"><h2 id="related-title">Related stories</h2><a class="link-arrow" href="{BASE}">All AI news {uikit.icon("arrow", 16)}</a></div>
  <ul class="ui-grid ui-grid-4">{related}</ul>
</section>
</div>"""

    article = {
        "@type": "NewsArticle", "headline": post["title"][:110], "description": post.get("description", ""),
        "datePublished": post["publishedDt"].isoformat(), "dateModified": post["updatedDt"].isoformat(),
        "author": AUTHOR, "publisher": ORG, "mainEntityOfPage": url, "inLanguage": "en", "isAccessibleForFree": True,
    }
    if sources:
        article["citation"] = [{"@type": "CreativeWork", "name": s.get("title") or s["url"], "url": s["url"]} for s in sources]
    if post.get("keyword"):
        article["keywords"] = post["keyword"]
    if primary:
        article["articleSection"] = primary["name"]
    schema_trail = [("Home", SITE + "/"), ("AI news", SITE + BASE)]
    if primary:
        schema_trail.append((primary["name"], f"{SITE}{BASE}{primary['slug']}/"))
    schema = json_ld({"@context": "https://schema.org", "@graph": [article, breadcrumb_schema(schema_trail + [(post["title"], url)])]})
    copy_script = """<script>
document.querySelectorAll("[data-copy]").forEach(function (b) {
  b.addEventListener("click", function () {
    navigator.clipboard.writeText(b.getAttribute("data-copy")).then(function () {
      var s = b.querySelector("span"); s.textContent = "Copied"; setTimeout(function () { s.textContent = "Copy link"; }, 1800);
    });
  });
});
</script>"""
    write(f"{post['slug']}.html", render_page(main, title=seo_title(post["title"]), ogtitle=post["title"],
                                              description=post.get("description", ""), canonical=url, schema=schema,
                                              reg=reg, hubs=hubs, extra_script=copy_script))


def build_archive(posts, hubs, reg):
    latest, rest = posts[0], posts[1:]
    main = f"""<section class="hero hero-center">
  <div class="container">
    <span class="pill reveal"><span class="dot">{uikit.icon("news", 13)}</span>Updated every morning</span>
    <h1 class="reveal" style="--d:.05s">AI news, <span class="grad-text">with the sources</span></h1>
    <p class="lead reveal" style="--d:.1s">Short stories on AI models, companies and policy. Every new story links to the announcements and reports it is based on.</p>
    <label class="search reveal" style="--d:.15s">{uikit.icon("search", 20)}<span class="is-hidden">Search stories</span>
      <input type="search" id="story-filter" placeholder="Search {len(posts)} stories, for example: Gemini, export controls" autocomplete="off"></label>
  </div>
</section>
<div class="container">
  <div class="reveal" style="margin-bottom:32px">{hub_chips(hubs, "all", len(posts))}</div>
  {featured_card(latest, hubs)}
  <section class="section" aria-labelledby="all-stories" style="padding-top:44px">
    <div class="section-head"><div><h2 id="all-stories">All stories</h2><p>Newest first. Use the search box or a company above to narrow the list.</p></div></div>
    {story_grid(rest, hubs)}
  </section>
</div>"""
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": "AI news", "url": SITE + BASE, "isPartOf": ORG,
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(posts), "itemListElement": [
             {"@type": "ListItem", "position": i, "url": f"{SITE}{BASE}{p['slug']}.html"} for i, p in enumerate(posts[:50], 1)]}},
        breadcrumb_schema([("Home", SITE + "/"), ("AI news", SITE + BASE)])]})
    write("index.html", render_page(main, title="AI News: Models, Companies and Policy | Web Online Tools", ogtitle="AI news",
                                    description="AI news on models, companies and policy, with the reports and official announcements behind each new story.",
                                    canonical=SITE + BASE, schema=schema, ogtype="website", reg=reg, hubs=hubs,
                                    extra_script=FILTER_SCRIPT))


def build_hub(hub, posts, hubs, reg):
    items = [p for p in posts if hub["slug"] in p.get("cats", [])]
    url = f"{SITE}{BASE}{hub['slug']}/"
    is_topic = hub.get("kind") == "topic"
    heading = hub["name"] if is_topic else f"{hub['name']} news"
    about = hub["about"] if hub["about"][:2].isupper() else hub["about"][0].lower() + hub["about"][1:]
    main = f"""<section class="hero hero-center" style="padding-bottom:28px">
  <div class="container">
    {crumbs([("Home", "/"), ("AI news", BASE), (heading, None)])}
    <div class="reveal" style="margin-top:28px">{uikit.hub_badge(hub)}</div>
    <h1 class="reveal" style="--d:.05s">{esc(heading)}</h1>
    <p class="lead reveal" style="--d:.1s">{len(items)} stories on {esc(about)}, newest first.</p>
    <label class="search reveal" style="--d:.15s">{uikit.icon("search", 20)}<span class="is-hidden">Search stories</span>
      <input type="search" id="story-filter" placeholder="Search {esc(hub['name'])} stories" autocomplete="off"></label>
  </div>
</section>
<div class="container">
  <div class="reveal" style="margin-bottom:32px">{hub_chips(hubs, hub["slug"], len(posts))}</div>
  {story_grid(items, hubs)}
</div>"""
    title = hub.get("title") or heading
    description = (f"{len(items)} stories on {about}, newest first." if is_topic
                   else f"{hub['name']} news: {hub['about']}. {len(items)} stories, newest first.")
    if len(description) > 160:
        description = f"{hub['name']} news: {hub['about']}."[:158]
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": heading, "url": url, "isPartOf": ORG,
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": [
             {"@type": "ListItem", "position": i, "url": f"{SITE}{BASE}{p['slug']}.html"} for i, p in enumerate(items[:50], 1)]}},
        breadcrumb_schema([("Home", SITE + "/"), ("AI news", SITE + BASE), (heading, url)])]})
    os.makedirs(path(hub["slug"]), exist_ok=True)
    write(f"{hub['slug']}/index.html", render_page(main, title=seo_title(title), ogtitle=heading, description=description,
                                                   canonical=url, schema=schema, ogtype="website", reg=reg, hubs=hubs,
                                                   extra_script=FILTER_SCRIPT))


def build_policy(hubs, reg):
    body = read("templates/editorial-policy.html")
    main = f"""<div class="container text-page">
{crumbs([("Home", "/"), ("AI news", BASE), ("Editorial policy", None)])}
<header class="article-hero" style="text-align:center;border:0">
  <span class="pill"><span class="dot">{uikit.icon("shield", 13)}</span>How we work</span>
  <h1 style="margin-left:auto;margin-right:auto">Editorial policy</h1>
</header>
<div class="ui-panel" style="max-width:820px;margin:0 auto;padding:36px">
  <div class="prose">{body}</div>
</div>
</div>"""
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "AboutPage", "name": "Editorial policy", "url": SITE + BASE + "editorial-policy.html", "publisher": ORG},
        breadcrumb_schema([("Home", SITE + "/"), ("AI news", SITE + BASE), ("Editorial policy", SITE + BASE + "editorial-policy.html")])]})
    write("editorial-policy.html", render_page(main, title="Editorial policy | Web Online Tools",
                                               description="How Web Online Tools researches, sources, checks and corrects its AI news stories.",
                                               canonical=SITE + BASE + "editorial-policy.html", schema=schema,
                                               ogtype="website", reg=reg, hubs=hubs))


def build_sitemap(posts, hubs):
    newest = posts[0]["updatedDt"].date() if posts else datetime.now(timezone.utc).date()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             f"  <url><loc>{SITE}{BASE}</loc><lastmod>{newest}</lastmod></url>",
             f"  <url><loc>{SITE}{BASE}editorial-policy.html</loc></url>"]
    for h in hubs:
        newest_in_hub = max((p["updatedDt"] for p in posts if h["slug"] in p.get("cats", [])), default=None)
        lines.append(f"  <url><loc>{SITE}{BASE}{h['slug']}/</loc>"
                     + (f"<lastmod>{newest_in_hub.date()}</lastmod>" if newest_in_hub else "") + "</url>")
    for p in posts:
        lines.append(f"  <url><loc>{esc(SITE + BASE + p['slug'] + '.html')}</loc><lastmod>{p['updatedDt'].date()}</lastmod></url>")
    lines.append("</urlset>")
    write("sitemap.xml", "\n".join(lines) + "\n")


def build_feed(posts):
    items = []
    for p in posts[:30]:
        url = f"{SITE}{BASE}{p['slug']}.html"
        items.append(f"<item><title>{esc(p['title'])}</title><link>{url}</link><guid>{url}</guid>"
                     f"<pubDate>{p['publishedDt'].strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
                     f"<description>{esc(p.get('description', ''))}</description></item>")
    write("feed.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
          f"<title>Web Online Tools: AI news</title><link>{SITE}{BASE}</link>"
          "<description>Sourced AI news on models, companies and policy.</description>"
          + "".join(items) + "</channel></rss>\n")


def build_manifests(posts, hubs):
    by = {h["slug"]: h for h in hubs}
    public = []
    for p in posts:
        hub = next((by[c] for c in p.get("cats", []) if c in by), None)
        public.append({"url": f"{BASE}{p['slug']}.html", "title": p["title"], "excerpt": p.get("description", ""),
                       "date": p["publishedDt"].strftime("%b %d, %Y"), "category": hub["name"] if hub else "AI news",
                       "categorySlug": hub["slug"] if hub else "", "readTime": read_time(p)})
    write("index.json", json.dumps(public, indent=2, ensure_ascii=False) + "\n")
    write("files.json", json.dumps([p["slug"] + ".html" for p in reversed(posts)], indent=2) + "\n")
    registry = [{"slug": p["slug"], "title": p["title"], "keyword": p.get("keyword", ""),
                 "published": p["publishedDt"].date().isoformat()} for p in posts]
    write("data/keywords.json", json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


def build_htaccess(redirects):
    lines = ["# Generated by scripts/build-site.py. Edit that script, not this file.",
             "# Build sources stay private; only generated pages, feeds and assets are public.",
             "RedirectMatch 404 ^/ai-news/(content|data|templates|scripts|root-site)(/.*)?$",
             '<FilesMatch "(\\.py|\\.md|^\\.last-run|^testing\\.hmtl)$">',
             "  <IfModule mod_authz_core.c>", "    Require all denied", "  </IfModule>",
             "  <IfModule !mod_authz_core.c>", "    Order allow,deny", "    Deny from all", "  </IfModule>",
             "</FilesMatch>", "", "# Merged duplicate stories (data/redirects.json)"]
    for old, new in sorted(redirects.items()):
        lines.append(f"Redirect 301 {BASE}{old}.html {SITE}{BASE}{new}.html")
    write(".htaccess", "\n".join(lines) + "\n")


def remove_stale(posts, hubs):
    keep = STATIC_PAGES | {p["slug"] + ".html" for p in posts}
    removed = [fn for fn in os.listdir(ROOT) if fn.endswith(".html") and fn not in keep]
    for fn in removed:
        os.remove(path(fn))
    # hub folders this script created before but that no longer qualify
    previous = json.loads(read("data/hubs.json")) if os.path.exists(path("data/hubs.json")) else []
    current = [h["slug"] for h in hubs]
    for slug in previous:
        if slug not in current and os.path.exists(path(slug, "index.html")):
            os.remove(path(slug, "index.html"))
            if not os.listdir(path(slug)):
                os.rmdir(path(slug))
            removed.append(slug + "/")
    write("data/hubs.json", json.dumps(current, indent=2) + "\n")
    return removed


def main():
    posts, redirects = load_posts()
    hubs = assign_categories(posts, load_companies())
    reg = uikit.load_registry()
    for post in posts:
        build_post(post, posts, hubs, reg)
    for hub in hubs:
        build_hub(hub, posts, hubs, reg)
    build_archive(posts, hubs, reg)
    build_policy(hubs, reg)
    build_sitemap(posts, hubs)
    build_feed(posts)
    build_manifests(posts, hubs)
    build_htaccess(redirects)
    removed = remove_stale(posts, hubs)
    print(f"built {len(posts)} posts, {len(hubs)} hubs ({', '.join(h['name'] + ' ' + str(h['count']) for h in hubs)}), "
          f"{len(redirects)} redirects, removed {len(removed)} stale pages")


if __name__ == "__main__":
    main()
