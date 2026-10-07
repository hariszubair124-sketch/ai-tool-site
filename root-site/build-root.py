"""
Builds the files that live at the root of webonlinetools.com (everything outside /ai-news/).

Reads:   root-site/tools.json            the tools registry (names, titles, descriptions, categories)
         root-site/src/tools/<slug>/      each tool's page (its own UI and script)
         root-site/src/assets/tools.css   shared header, footer and font styles
         data/companies.json, data/hubs.json, index.json   AI news hubs and latest stories (from the blog)
Writes:  root-site/dist/                  upload this folder's contents to Hostinger public_html
         root-site/lastmod.json           remembers when each page last changed, for the sitemap

Run:     python root-site/build-root.py
"""
import hashlib
import html
import json
import os
import re
import shutil
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")
SITE = "https://webonlinetools.com"
BRAND = " | Web Online Tools"
VERIFY = '<meta name="google-site-verification" content="2yOkCxBls80UcV_za_vpGqbxg_nIOjhLNQqcEFoGEZc">'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
         '&family=JetBrains+Mono:wght@400;500&display=swap">')
TODAY = datetime.now(timezone.utc).date().isoformat()


def esc(text):
    return html.escape(text or "", quote=True)


def seo_title(title):
    return title + BRAND if len(title + BRAND) <= 60 else title


def json_ld(data):
    return ('<script type="application/ld+json">\n'
            + json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/") + "\n</script>")


def load_json(*parts, default=None):
    p = os.path.join(*parts)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write(rel, text):
    p = os.path.join(DIST, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


# ── shared pieces ─────────────────────────────────────────────────────

def head_block(*, title, description, canonical, schema, ogtype="website", css_version="", verify=False):
    return "\n".join(filter(None, [
        f"<title>{esc(seo_title(title))}</title>",
        f'<meta name="description" content="{esc(description)}">',
        '<meta name="robots" content="index, follow">',
        f'<link rel="canonical" href="{canonical}">',
        f'<meta property="og:type" content="{ogtype}">',
        '<meta property="og:site_name" content="Web Online Tools">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{canonical}">',
        '<meta name="twitter:card" content="summary">',
        VERIFY if verify else "",
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        FONTS,
        f'<link rel="stylesheet" href="/assets/tools.css?v={css_version}">',
        schema,
    ]))


def header(current=None):
    def link(href, label, key):
        return f'<a href="{href}"' + (' aria-current="page"' if key == current else "") + f">{label}</a>"
    return ('<header class="wot-header"><div class="wot-header-inner">'
            '<a class="wot-brand" href="/">Web Online Tools</a>'
            '<nav class="wot-nav" aria-label="Main">'
            + link("/tools/", "All tools", "tools") + link("/ai-news/", "AI news", "news")
            + "</nav></div></header>")


def footer(reg, hubs):
    cols = []
    for cat in reg["categories"]:
        items = [t for t in reg["tools"] if t["category"] == cat["slug"]]
        links = "".join(f'<li><a href="/tools/{t["slug"]}/">{esc(t["name"])}</a></li>' for t in items)
        cols.append(f'<div><h2>{esc(cat["name"])}</h2><ul>{links}</ul></div>')
    if hubs:
        links = "".join(f'<li><a href="/ai-news/{h["slug"]}/">{esc(h["name"])}</a></li>' for h in hubs)
        cols.append(f'<div><h2>AI news</h2><ul><li><a href="/ai-news/">All stories</a></li>{links}</ul></div>')
    return ('<footer class="wot-footer"><div class="wot-footer-inner">'
            f'<div class="wot-footer-cols">{"".join(cols)}</div>'
            '<p class="wot-footer-note">© <span id="year">' + TODAY[:4] + '</span> Web Online Tools. '
            'Every tool runs in your browser; your files and text are not uploaded. '
            '<a href="/ai-news/editorial-policy.html">Editorial policy</a></p>'
            "</div></footer>")


def crumbs(items):
    parts = []
    for i, (name, href) in enumerate(items):
        parts.append(f'<a href="{href}">{esc(name)}</a>' if i < len(items) - 1 else f'<span aria-current="page">{esc(name)}</span>')
    return '<nav class="wot-crumbs" aria-label="Breadcrumb">' + '<span aria-hidden="true"> / </span>'.join(parts) + "</nav>"


def breadcrumb_schema(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": SITE + h} for i, (n, h) in enumerate(items, 1)]}


def tool_card(t, heading="h3"):
    return (f'<li class="wot-card"><a href="/tools/{t["slug"]}/"><{heading}>{esc(t["name"])}</{heading}>'
            f'<p>{esc(t["card"])}</p></a></li>')


# ── tool pages ────────────────────────────────────────────────────────

APP_CATEGORY = {"developer": "DeveloperApplication", "design": "DesignApplication",
                "text": "UtilitiesApplication", "files": "MultimediaApplication", "calculators": "FinanceApplication"}

STRIP_HEAD = [
    r"<title>.*?</title>",
    r'<meta\s+name="(?:description|keywords|robots|google-site-verification|twitter:[^"]*)"[^>]*>',
    r'<meta\s+property="og:[^"]*"[^>]*>',
    r'<link\s+rel="canonical"[^>]*>',
    r'<link\s+rel="icon"[^>]*>',
    r'<link\s+rel="preconnect"[^>]*>',
    r'<link\s+href="https://fonts\.googleapis\.com[^"]*"[^>]*>',
    r'<link\s+rel="stylesheet"\s+href="https://fonts\.googleapis\.com[^"]*"[^>]*>',
    r'<script\s+type="application/ld\+json">.*?</script>',
    r"<!--\s*══[^>]*-->",
]


def build_tool(t, reg, hubs, css_version):
    src = open(os.path.join(HERE, "src", "tools", t["slug"], "index.html"), encoding="utf-8").read()
    url = f"{SITE}/tools/{t['slug']}/"
    cat = next(c for c in reg["categories"] if c["slug"] == t["category"])
    trail = [("Home", "/"), ("Tools", "/tools/"), (t["name"], f"/tools/{t['slug']}/")]

    head_end = src.index("</head>")
    head, body = src[:head_end], src[head_end:]
    for pat in STRIP_HEAD:
        head = re.sub(pat, "", head, flags=re.S | re.I)
    head = re.sub(r"\n\s*\n+", "\n", head)
    head = head.replace("'Syne'", "'Inter'").replace("'Plus Jakarta Sans'", "'Inter'")
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "WebApplication", "name": t["name"], "url": url, "description": t["description"],
         "applicationCategory": APP_CATEGORY[t["category"]], "operatingSystem": "Any (runs in a web browser)",
         "browserRequirements": "Requires JavaScript", "isAccessibleForFree": True,
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
         "publisher": {"@type": "Organization", "name": "Web Online Tools", "url": SITE + "/"}},
        breadcrumb_schema(trail)]})
    seo = head_block(title=t["title"], description=t["description"], canonical=url, schema=schema,
                     ogtype="website", css_version=css_version)
    head = re.sub(r'(<meta\s+name="viewport"[^>]*>)', lambda m: m.group(1) + "\n" + seo, head, count=1)

    # one shared header and footer on every page
    body = re.sub(r'<header class="site-header".*?</header>', header("tools"), body, count=1, flags=re.S)
    body = re.sub(r'<footer class="site-footer".*?</footer>', footer(reg, hubs), body, count=1, flags=re.S)
    # the H1 says what the page is for, in the words people search
    body = re.sub(r"(<h1[^>]*>).*?(</h1>)", lambda m: m.group(1) + esc(t["h1"]) + m.group(2), body, count=1, flags=re.S)
    # breadcrumb at the top of main
    body = re.sub(r"(<main[^>]*>)", lambda m: m.group(1) + "\n  " + crumbs(trail), body, count=1)
    # replace the old hand-made link chips with related tools from the registry
    body = re.sub(r'<div class="flex flex-wrap gap-3 mt-10[^"]*">\s*(?:<a [^>]*class="tag-link"[^>]*>.*?</a>\s*)+</div>',
                  "", body, flags=re.S)
    by_slug = {x["slug"]: x for x in reg["tools"]}
    related = [by_slug[s] for s in t.get("related", []) if s in by_slug]
    block = ('<section class="wot-related" aria-labelledby="related-tools"><h2 id="related-tools">Related tools</h2>'
             '<ul class="wot-grid">' + "".join(tool_card(r) for r in related) + "</ul>"
             f'<p class="wot-more"><a href="/tools/#{cat["slug"]}">More {esc(cat["name"].lower())}</a> · '
             '<a href="/tools/">All tools</a></p></section>')
    body = body.replace("</main>", block + "\n</main>", 1)
    write(f"tools/{t['slug']}/index.html", head + body)


# ── homepage and tools index ─────────────────────────────────────────

def page(*, title, description, canonical, schema, main, current, reg, hubs, css_version, verify=False):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{head_block(title=title, description=description, canonical=canonical, schema=schema, css_version=css_version, verify=verify)}
</head>
<body class="wot-page">
{header(current)}
<main class="wot-main" id="content">
{main}
</main>
{footer(reg, hubs)}
</body>
</html>
"""


def build_home(reg, hubs, news, css_version):
    featured = [t for t in reg["tools"] if t.get("featured")]
    sections = []
    for cat in reg["categories"]:
        items = [t for t in reg["tools"] if t["category"] == cat["slug"]]
        links = "".join(f'<li><a href="/tools/{t["slug"]}/">{esc(t["name"])}</a></li>' for t in items)
        sections.append(f'<div><h3><a href="/tools/#{cat["slug"]}">{esc(cat["name"])}</a></h3><ul>{links}</ul></div>')
    stories = "".join(
        f'<li><a href="{esc(p["url"])}">{esc(p["title"])}</a><span>{esc(p["date"])}</span></li>' for p in news[:5])
    hub_links = " ".join(f'<a href="/ai-news/{h["slug"]}/">{esc(h["name"])}</a>' for h in hubs)
    main = f"""
<section class="wot-hero">
  <h1>Free online tools for developers, designers and writers</h1>
  <p class="wot-lead">{len(reg["tools"])} small tools that do one job well: format JSON, build CSS, convert images and PDFs, clean up text and more. Everything runs in your browser, so nothing you paste or upload leaves your device.</p>
  <p><a class="wot-button" href="/tools/">Browse all {len(reg["tools"])} tools</a></p>
</section>

<section aria-labelledby="popular">
  <h2 id="popular">Popular tools</h2>
  <ul class="wot-grid">{"".join(tool_card(t) for t in featured)}</ul>
</section>

<section aria-labelledby="by-task">
  <h2 id="by-task">Tools by task</h2>
  <div class="wot-columns">{"".join(sections)}</div>
</section>

<section aria-labelledby="latest-news">
  <h2 id="latest-news">Latest AI news</h2>
  <p class="wot-muted">Short, sourced stories about AI models, companies and policy. Browse by company: {hub_links}</p>
  <ul class="wot-news" id="news-list">{stories}</ul>
  <p><a href="/ai-news/">All AI news</a></p>
</section>

<section aria-labelledby="about">
  <h2 id="about">About Web Online Tools</h2>
  <p>Web Online Tools is a free collection of browser-based utilities. Each tool processes your data with JavaScript on your own device: there is no account, no upload and no tracking of what you type. The AI news section is researched and drafted with AI assistance and checked against its sources before it is published; read the <a href="/ai-news/editorial-policy.html">editorial policy</a> for details.</p>
</section>

<script>
// Refresh the news list with the newest stories; the list above already works without JavaScript.
fetch("/ai-news/index.json").then(r => r.ok ? r.json() : []).then(posts => {{
  if (!posts.length) return;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
  document.getElementById("news-list").innerHTML = posts.slice(0, 5)
    .map(p => `<li><a href="${{esc(p.url)}}">${{esc(p.title)}}</a><span>${{esc(p.date)}}</span></li>`).join("");
}}).catch(() => {{}});
</script>"""
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/", "name": "Web Online Tools",
         "description": "Free browser-based tools for developers, designers and writers, plus sourced AI news."},
        {"@type": "Organization", "@id": SITE + "/#org", "name": "Web Online Tools", "url": SITE + "/",
         "logo": SITE + "/favicon.svg"}]})
    write("index.html", page(
        title="Web Online Tools: Free Developer, Design and Text Tools",
        description=f"{len(reg['tools'])} free tools that run in your browser: format JSON, build CSS gradients and shadows, "
                    "convert images and PDFs, clean lists and more. No sign-up, no uploads.",
        canonical=SITE + "/", schema=schema, main=main, current=None, reg=reg, hubs=hubs,
        css_version=css_version, verify=True))


def build_tools_index(reg, hubs, css_version):
    blocks = []
    for cat in reg["categories"]:
        items = [t for t in reg["tools"] if t["category"] == cat["slug"]]
        blocks.append(f'<section id="{cat["slug"]}" class="wot-cat" aria-labelledby="h-{cat["slug"]}">'
                      f'<h2 id="h-{cat["slug"]}">{esc(cat["name"])}</h2><p class="wot-muted">{esc(cat["about"])}</p>'
                      f'<ul class="wot-grid">{"".join(tool_card(t) for t in items)}</ul></section>')
    trail = [("Home", "/"), ("Tools", "/tools/")]
    main = f"""{crumbs(trail)}
<section class="wot-hero wot-hero-small">
  <h1>All free online tools</h1>
  <p class="wot-lead">{len(reg["tools"])} browser-based tools, grouped by task. Nothing to install, and your files stay on your device.</p>
  <label class="wot-search"><span class="wot-visually-hidden">Filter tools</span>
    <input type="search" id="tool-filter" placeholder="Filter tools, for example: json, color, pdf" autocomplete="off"></label>
  <p id="no-match" class="wot-muted" hidden>No tools match that search.</p>
</section>
{"".join(blocks)}
<script>
// Optional filter; every tool link is already in the page for search engines and keyboard users.
const box = document.getElementById("tool-filter");
box.addEventListener("input", () => {{
  const q = box.value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll(".wot-cat").forEach(sec => {{
    let any = false;
    sec.querySelectorAll(".wot-card").forEach(card => {{
      const hit = !q || card.textContent.toLowerCase().includes(q);
      card.hidden = !hit; any = any || hit; if (hit) shown++;
    }});
    sec.hidden = !any;
  }});
  document.getElementById("no-match").hidden = shown > 0;
}});
</script>"""
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": "All free online tools", "url": SITE + "/tools/",
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(reg["tools"]), "itemListElement": [
             {"@type": "ListItem", "position": i, "name": t["name"], "url": f"{SITE}/tools/{t['slug']}/"}
             for i, t in enumerate(reg["tools"], 1)]}},
        breadcrumb_schema(trail)]})
    write("tools/index.html", page(
        title="All Free Online Tools",
        description=f"Browse all {len(reg['tools'])} free browser-based tools for developers, designers and writers, "
                    "grouped by task. Nothing to install, and your files never leave your device.",
        canonical=SITE + "/tools/", schema=schema, main=main, current="tools", reg=reg, hubs=hubs, css_version=css_version))


def build_registry_json(reg):
    """Public copy of the registry, in the same shape the old pages used."""
    cats = {c["slug"]: c["name"] for c in reg["categories"]}
    out = [{"name": t["name"], "url": f"/tools/{t['slug']}/", "category": cats[t["category"]],
            "description": t["card"], "featured": t.get("featured", False)} for t in reg["tools"]]
    write("tools/tools.json", json.dumps(out, indent=2, ensure_ascii=False) + "\n")


# ── sitemap, robots, lastmod tracking ────────────────────────────────

def track_lastmod(pages):
    """Updates root-site/lastmod.json: a page's date changes only when its built content changes."""
    path = os.path.join(HERE, "lastmod.json")
    known = load_json(path, default={})
    for url, rel in pages:
        digest = hashlib.sha256(open(os.path.join(DIST, rel), "rb").read()).hexdigest()[:16]
        if known.get(url, {}).get("hash") != digest:
            known[url] = {"hash": digest, "lastmod": TODAY}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(known, f, indent=2, sort_keys=True)
        f.write("\n")
    return known


def build_sitemaps(reg):
    pages = [("/", "index.html"), ("/tools/", "tools/index.html")] + \
            [(f"/tools/{t['slug']}/", f"tools/{t['slug']}/index.html") for t in reg["tools"]]
    known = track_lastmod(pages)
    urls = "\n".join(f"  <url><loc>{SITE}{u}</loc><lastmod>{known[u]['lastmod']}</lastmod></url>" for u, _ in pages)
    write("sitemap-pages.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "\n</urlset>\n")
    # /sitemap.xml is an index of the two sitemaps, so one submission in Search Console covers the whole site
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"  <sitemap><loc>{SITE}/sitemap-pages.xml</loc><lastmod>{max(v['lastmod'] for v in known.values())}</lastmod></sitemap>\n"
          f"  <sitemap><loc>{SITE}/ai-news/sitemap.xml</loc></sitemap>\n"
          "</sitemapindex>\n")
    write("robots.txt", "User-agent: *\nAllow: /\nDisallow: /tools/*/default.php\n\n"
          f"Sitemap: {SITE}/sitemap.xml\n")


def main():
    reg = load_json(HERE, "tools.json")
    companies = {c["slug"]: c for c in load_json(REPO, "data", "companies.json", default=[])}
    hubs = [companies[s] for s in load_json(REPO, "data", "hubs.json", default=[]) if s in companies]
    news = load_json(REPO, "index.json", default=[])
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    css = open(os.path.join(HERE, "src", "assets", "tools.css"), encoding="utf-8").read()
    css_version = hashlib.md5(css.encode()).hexdigest()[:8]
    write("assets/tools.css", css)
    shutil.copy(os.path.join(HERE, "src", "favicon.svg"), os.path.join(DIST, "favicon.svg"))
    for t in reg["tools"]:
        build_tool(t, reg, hubs, css_version)
    build_home(reg, hubs, news, css_version)
    build_tools_index(reg, hubs, css_version)
    build_registry_json(reg)
    build_sitemaps(reg)
    print(f"built {len(reg['tools'])} tool pages, homepage, tools index, sitemaps and robots.txt into {DIST}")


if __name__ == "__main__":
    main()
