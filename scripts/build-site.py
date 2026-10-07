"""
Builds everything served at /ai-news/ from the data files. Safe to run any time;
it regenerates the same output from the same inputs.

Reads:   content/posts/*.json, data/redirects.json, templates/*.html, assets/site.css
Writes:  <slug>.html for each post, index.html, editorial-policy.html, sitemap.xml,
         feed.xml, index.json, files.json, data/keywords.json, .htaccess
"""
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://webonlinetools.com"
BASE = "/ai-news/"
STATIC_PAGES = {"index.html", "editorial-policy.html"}
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


def json_ld(data):
    text = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{text}\n</script>'


def topic_words(post):
    text = f"{post['title']} {post.get('keyword', '')}".lower().replace("'s", "")
    words = re.findall(r"[a-z0-9][a-z0-9.\-]*[a-z0-9]|[a-z0-9]", text)
    return {w for w in words if w not in STOPWORDS and w not in HYPEWORDS and len(w) > 1}


# ── data ──────────────────────────────────────────────────────────────

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


# ── page pieces ───────────────────────────────────────────────────────

def render_page(main, *, title, description, canonical, schema, ogtype="article", ogtitle=None,
                robots="index, follow", nav="news"):
    page = read("templates/page.html")
    css_version = hashlib.md5(read("assets/site.css").encode()).hexdigest()[:8]
    values = {
        "{{TITLE}}": esc(title),
        "{{OGTITLE}}": esc(ogtitle or title),
        "{{DESCRIPTION}}": esc(description),
        "{{CANONICAL}}": canonical,
        "{{ROBOTS}}": robots,
        "{{OGTYPE}}": ogtype,
        "{{SCHEMA}}": schema,
        "{{CSSVERSION}}": css_version,
        "{{NAVNEWS}}": ' aria-current="page"' if nav == "news" else "",
        "{{NAVPOLICY}}": ' aria-current="page"' if nav == "policy" else "",
        "{{YEAR}}": str(datetime.now(timezone.utc).year),
        "{{MAIN}}": main,
    }
    for token, value in values.items():
        page = page.replace(token, value)
    return page


def link_citations(body, source_count):
    """Turns [1], [2] markers into links to the matching source, only when that source exists."""
    def repl(m):
        n = int(m.group(1))
        if 1 <= n <= source_count:
            return f'<sup class="cite"><a href="#source-{n}" aria-label="Source {n}">[{n}]</a></sup>'
        return ""
    return re.sub(r"\[(\d{1,2})\](?![^<]*</a>)", repl, body)


def facts_box(post):
    facts = post.get("facts") or {}
    rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in facts.items() if v)
    if not rows:
        return ""
    return f'<aside class="facts" aria-labelledby="facts-title"><h2 id="facts-title">Key facts</h2><dl>{rows}</dl></aside>'


def sources_block(post):
    sources = post.get("sources") or []
    if not sources:
        return ('<section class="sources" aria-labelledby="sources-title"><h2 id="sources-title">Sources</h2>'
                '<p class="note">This story was published before we started listing sources. '
                'It is being re-checked under our <a href="/ai-news/editorial-policy.html">editorial policy</a>.</p></section>')
    items = []
    for i, s in enumerate(sources, 1):
        meta = ", ".join(x for x in (s.get("publisher"), s.get("date")) if x)
        items.append(f'<li id="source-{i}"><a href="{esc(s["url"])}">{esc(s.get("title") or s["url"])}</a>'
                     + (f' <span class="source-meta">({esc(meta)})</span>' if meta else "") + "</li>")
    return (f'<section class="sources" aria-labelledby="sources-title"><h2 id="sources-title">Sources</h2>'
            f'<ol>{"".join(items)}</ol></section>')


def related_block(picks):
    items = "".join(f'<li><a href="{BASE}{p["slug"]}.html">{esc(p["title"])}</a></li>' for p in picks)
    return f'<nav class="related" aria-labelledby="related-title"><h2 id="related-title">Related stories</h2><ul>{items}</ul></nav>'


def breadcrumbs(extra=None):
    trail = '<nav class="crumbs" aria-label="Breadcrumb"><a href="https://webonlinetools.com/">Home</a>'
    if extra:
        trail += f'<span aria-hidden="true">/</span><a href="{BASE}">AI news</a>'
    return trail + "</nav>"


def breadcrumb_schema(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": url} for i, (name, url) in enumerate(items, 1)]}


ORG = {"@type": "Organization", "name": "Web Online Tools", "url": SITE + "/"}
AUTHOR = {"@type": "Organization", "name": "Web Online Tools Editorial", "url": SITE + BASE + "editorial-policy.html"}


# ── pages ─────────────────────────────────────────────────────────────

def build_post(post, posts):
    url = f"{SITE}{BASE}{post['slug']}.html"
    sources = post.get("sources") or []
    # Google's temporary grounding-redirect links expire; keep the words, drop the link.
    body = re.sub(r'<a\s[^>]*href="https?://vertexaisearch\.cloud\.google\.com[^"]*"[^>]*>(.*?)</a>', r"\1",
                  post["body"], flags=re.S | re.I)
    body = link_citations(body, len(sources))
    dateline = f'Published <time datetime="{post["publishedDt"].date()}">{nice_date(post["publishedDt"])}</time>'
    if post["updatedDt"].date() != post["publishedDt"].date():
        dateline += f', updated <time datetime="{post["updatedDt"].date()}">{nice_date(post["updatedDt"])}</time>'
    dateline += ' by <a href="/ai-news/editorial-policy.html">Web Online Tools Editorial</a>'
    facts = facts_box(post)
    main = "\n".join([
        breadcrumbs(extra=True),
        f'<article class="story{" story-wide" if facts else ""}">',
        f'<header><h1>{esc(post["title"])}</h1><p class="dateline">{dateline}</p>'
        + (f'<p class="lead">{esc(post["description"])}</p>' if post.get("description") else "") + "</header>",
        facts,
        f'<div class="story-body">\n{body}\n</div>',
        sources_block(post),
        related_block(related_posts(post, posts)),
        "</article>",
    ])
    article = {
        "@type": "NewsArticle",
        "headline": post["title"][:110],
        "description": post.get("description", ""),
        "datePublished": post["publishedDt"].isoformat(),
        "dateModified": post["updatedDt"].isoformat(),
        "author": AUTHOR,
        "publisher": ORG,
        "mainEntityOfPage": url,
        "inLanguage": "en",
        "isAccessibleForFree": True,
    }
    if sources:
        article["citation"] = [{"@type": "CreativeWork", "name": s.get("title") or s["url"], "url": s["url"]} for s in sources]
    if post.get("keyword"):
        article["keywords"] = post["keyword"]
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        article, breadcrumb_schema([("Home", SITE + "/"), ("AI news", SITE + BASE), (post["title"], url)])]})
    page = render_page(main, title=f"{post['title']} | Web Online Tools", ogtitle=post["title"],
                       description=post.get("description", ""), canonical=url, schema=schema)
    write(f"{post['slug']}.html", page)


def build_archive(posts):
    sourced = sum(1 for p in posts if p.get("sources"))
    groups, order = {}, []
    for p in posts:
        key = p["publishedDt"].strftime("%B %Y")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)
    sections = []
    for key in order:
        items = "".join(
            f'<li><a href="{BASE}{p["slug"]}.html">{esc(p["title"])}</a>'
            f'<time datetime="{p["publishedDt"].date()}">{nice_date(p["publishedDt"])}</time></li>' for p in groups[key])
        sections.append(f"<h2>{key}</h2><ul>{items}</ul>")
    main = "\n".join([
        breadcrumbs(),
        '<section class="archive">',
        "<h1>AI news</h1>",
        f'<p class="intro">{len(posts)} stories on AI models, companies and policy, newest first. '
        + ('Each one lists the sources it is based on; ' if sourced == len(posts)
           else f'{sourced} list their sources so far, and every new story does; ' if sourced
           else 'Every new story lists the sources it is based on; ')
        + 'see <a href="/ai-news/editorial-policy.html">how we check them</a>.</p>',
        "\n".join(sections),
        "</section>",
    ])
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": "AI news", "url": SITE + BASE, "isPartOf": ORG,
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(posts), "itemListElement": [
             {"@type": "ListItem", "position": i, "url": f"{SITE}{BASE}{p['slug']}.html"} for i, p in enumerate(posts[:50], 1)]}},
        breadcrumb_schema([("Home", SITE + "/"), ("AI news", SITE + BASE)])]})
    write("index.html", render_page(main, title="AI news: sourced stories on models, companies and policy | Web Online Tools",
                                    ogtitle="AI news", description="AI news on models, companies and policy, with the reports and official announcements behind each new story.",
                                    canonical=SITE + BASE, schema=schema, ogtype="website"))


def build_policy():
    main = breadcrumbs(extra=True) + "\n" + read("templates/editorial-policy.html")
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "AboutPage", "name": "Editorial policy", "url": SITE + BASE + "editorial-policy.html", "publisher": ORG},
        breadcrumb_schema([("Home", SITE + "/"), ("AI news", SITE + BASE), ("Editorial policy", SITE + BASE + "editorial-policy.html")])]})
    write("editorial-policy.html", render_page(main, title="Editorial policy | Web Online Tools",
                                               description="How Web Online Tools researches, sources, checks and corrects its AI news stories.",
                                               canonical=SITE + BASE + "editorial-policy.html", schema=schema,
                                               ogtype="website", nav="policy"))


def build_sitemap(posts):
    newest = posts[0]["updatedDt"].date() if posts else datetime.now(timezone.utc).date()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             f"  <url><loc>{SITE}{BASE}</loc><lastmod>{newest}</lastmod></url>",
             f"  <url><loc>{SITE}{BASE}editorial-policy.html</loc></url>"]
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


def build_manifests(posts):
    public = [{"url": f"{BASE}{p['slug']}.html", "title": p["title"], "excerpt": p.get("description", ""),
               "date": p["publishedDt"].strftime("%b %d, %Y")} for p in posts]
    write("index.json", json.dumps(public, indent=2, ensure_ascii=False) + "\n")
    write("files.json", json.dumps([p["slug"] + ".html" for p in reversed(posts)], indent=2) + "\n")
    registry = [{"slug": p["slug"], "title": p["title"], "keyword": p.get("keyword", ""),
                 "published": p["publishedDt"].date().isoformat()} for p in posts]
    write("data/keywords.json", json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


def build_htaccess(redirects):
    lines = ["# Generated by scripts/build-site.py. Edit that script, not this file.",
             "# Build sources stay private; only generated pages, feeds and assets are public.",
             "RedirectMatch 404 ^/ai-news/(content|data|templates|scripts)(/.*)?$",
             '<FilesMatch "(\\.py|\\.md|^\\.last-run|^testing\\.hmtl)$">',
             "  <IfModule mod_authz_core.c>", "    Require all denied", "  </IfModule>",
             "  <IfModule !mod_authz_core.c>", "    Order allow,deny", "    Deny from all", "  </IfModule>",
             "</FilesMatch>", "", "# Merged duplicate stories (data/redirects.json)"]
    for old, new in sorted(redirects.items()):
        lines.append(f"Redirect 301 {BASE}{old}.html {SITE}{BASE}{new}.html")
    write(".htaccess", "\n".join(lines) + "\n")


def remove_stale(posts):
    keep = STATIC_PAGES | {p["slug"] + ".html" for p in posts}
    removed = [fn for fn in os.listdir(ROOT) if fn.endswith(".html") and fn not in keep]
    for fn in removed:
        os.remove(path(fn))
    return removed


def main():
    posts, redirects = load_posts()
    for post in posts:
        build_post(post, posts)
    build_archive(posts)
    build_policy()
    build_sitemap(posts)
    build_feed(posts)
    build_manifests(posts)
    build_htaccess(redirects)
    removed = remove_stale(posts)
    print(f"built {len(posts)} posts, {len(redirects)} redirects, removed {len(removed)} stale pages")


if __name__ == "__main__":
    main()
