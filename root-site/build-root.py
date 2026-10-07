"""
Builds the files that live at the root of webonlinetools.com (everything outside /ai-news/).

Reads:   root-site/tools.json            the tools registry (names, titles, descriptions, categories, icons)
         root-site/src/tools/<slug>/      each tool's page (its own UI and script)
         assets/ui.css, scripts/uikit.py  the shared design, header, footer and icons (same as the blog)
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
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uikit  # noqa: E402  (shared with the blog build)

DIST = os.path.join(HERE, "dist")
SITE = "https://webonlinetools.com"
BRAND = " | Web Online Tools"
VERIFY = '<meta name="google-site-verification" content="2yOkCxBls80UcV_za_vpGqbxg_nIOjhLNQqcEFoGEZc">'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800'
         '&family=JetBrains+Mono:wght@400;500&display=swap">')
TODAY = datetime.now(timezone.utc).date().isoformat()
icon = uikit.icon


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

def head_block(*, title, description, canonical, schema, css_version, ogtype="website", verify=False):
    return "\n".join(filter(None, [
        uikit.JS_FLAG,
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
        '<meta name="theme-color" content="#060b18">',
        VERIFY if verify else "",
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        FONTS,
        f'<link rel="stylesheet" href="/assets/ui.css?v={css_version}">',
        schema,
    ]))


def crumbs(items):
    parts = [f'<a href="{href}">{esc(name)}</a>' if i < len(items) - 1 else f'<span aria-current="page">{esc(name)}</span>'
             for i, (name, href) in enumerate(items)]
    return '<nav class="crumbs" aria-label="Breadcrumb">' + '<span class="sep">/</span>'.join(parts) + "</nav>"


def breadcrumb_schema(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": SITE + h} for i, (n, h) in enumerate(items, 1)]}


def tool_card(t, cats, delay=0.0):
    cat = cats[t["category"]]
    search = esc(f'{t["name"]} {t["card"]} {cat["name"]}'.lower())
    return (f'<li class="reveal" style="--d:{delay:.2f}s" data-search="{search}">'
            f'<a class="card" href="/tools/{t["slug"]}/"><span class="tool-icon">{icon(t["icon"], 24)}</span>'
            f'<h3>{esc(t["name"])}</h3><p>{esc(t["card"])}</p>'
            f'<div class="card-foot"><span>{esc(cat["name"])}</span><span class="card-go">Open {icon("arrow", 16)}</span></div>'
            f"</a></li>")


def news_card(p, delay=0.0):
    color = uikit.hub_color(p.get("categorySlug", ""))
    return (f'<li class="reveal" style="--d:{delay:.2f}s"><a class="card news-card" href="{esc(p["url"])}">'
            f'<div class="meta"><span class="badge" style="--badge:{color}">{esc(p.get("category", "AI news"))}</span>'
            f'<span class="meta-item">{icon("calendar", 14)}{esc(p["date"])}</span></div>'
            f'<h3>{esc(p["title"])}</h3><p>{esc(p.get("excerpt", ""))}</p>'
            f'<div class="card-foot"><span class="meta-item">{icon("clock", 14)}{p.get("readTime", 4)} min read</span>'
            f'<span class="card-go">Read {icon("arrow", 16)}</span></div></a></li>')


# ── tool pages ────────────────────────────────────────────────────────

APP_CATEGORY = {"developer": "DeveloperApplication", "design": "DesignApplication",
                "text": "UtilitiesApplication", "files": "MultimediaApplication", "calculators": "FinanceApplication"}

STRIP_HEAD = [
    r"<title>.*?</title>",
    r'<meta\s+name="(?:description|keywords|robots|google-site-verification|theme-color|twitter:[^"]*)"[^>]*>',
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
    cats = {c["slug"]: c for c in reg["categories"]}
    cat = cats[t["category"]]
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
    seo = head_block(title=t["title"], description=t["description"], canonical=url, schema=schema, css_version=css_version)
    head = re.sub(r'(<meta\s+name="viewport"[^>]*>)', lambda m: m.group(1) + "\n" + seo, head, count=1)

    body = re.sub(r'<header class="site-header".*?</header>', uikit.header("tools"), body, count=1, flags=re.S)
    body = re.sub(r'<footer class="site-footer".*?</footer>', uikit.footer(reg, hubs), body, count=1, flags=re.S)
    body = re.sub(r"(<h1[^>]*>).*?(</h1>)", lambda m: m.group(1) + esc(t["h1"]) + m.group(2), body, count=1, flags=re.S)
    body = re.sub(r"(<main[^>]*>)", lambda m: m.group(1) + "\n  " + crumbs(trail), body, count=1)
    body = re.sub(r'<div class="flex flex-wrap gap-3 mt-10[^"]*">\s*(?:<a [^>]*class="tag-link"[^>]*>.*?</a>\s*)+</div>',
                  "", body, flags=re.S)
    by_slug = {x["slug"]: x for x in reg["tools"]}
    related = [by_slug[s] for s in t.get("related", []) if s in by_slug]
    block = (f'<section class="related-tools" aria-labelledby="related-tools-title">'
             f'<div class="section-head"><h2 class="block-title" id="related-tools-title">{icon(cat["icon"], 22)}Related tools</h2>'
             f'<a class="link-arrow" href="/tools/#{cat["slug"]}">More {esc(cat["name"].lower())} {icon("arrow", 16)}</a></div>'
             f'<ul class="ui-grid ui-grid-3">{"".join(tool_card(r, cats, i * 0.06) for i, r in enumerate(related))}</ul></section>')
    body = body.replace("</main>", block + "\n</main>", 1)
    body = body.replace("</body>", uikit.UI_SCRIPT + "\n</body>", 1)
    write(f"tools/{t['slug']}/index.html", head + body)


# ── homepage and tools index ─────────────────────────────────────────

def page(*, title, description, canonical, schema, main, current, reg, hubs, css_version, verify=False, script=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{head_block(title=title, description=description, canonical=canonical, schema=schema, css_version=css_version, verify=verify)}
</head>
<body class="ui">
{uikit.header(current)}
<main id="content">
{main}
</main>
{uikit.footer(reg, hubs)}
{uikit.UI_SCRIPT}
{script}
</body>
</html>
"""


def build_home(reg, hubs, news, css_version):
    cats = {c["slug"]: c for c in reg["categories"]}
    n = len(reg["tools"])
    featured = [t for t in reg["tools"] if t.get("featured")]
    cat_tiles = "".join(
        f'<li class="reveal" style="--d:{i * 0.05:.2f}s"><a class="card cat-tile" href="/tools/#{c["slug"]}">'
        f'<span class="tool-icon">{icon(c["icon"], 24)}</span><span><h3>{esc(c["name"])}</h3>'
        f'<p>{sum(1 for t in reg["tools"] if t["category"] == c["slug"])} tools</p></span></a></li>'
        for i, c in enumerate(reg["categories"]))
    counts = {}
    for p in news:
        counts[p.get("categorySlug", "")] = counts.get(p.get("categorySlug", ""), 0) + 1
    chips = "".join(
        f'<li><a class="chip" style="--badge:{uikit.hub_color(h["slug"])}" href="/ai-news/{h["slug"]}/"><span class="dot"></span>{esc(h["name"])}</a></li>'
        for h in hubs)
    features = [
        ("shield", "Private by design", "Everything runs in your browser. Text, images and PDFs are processed on your device and never uploaded."),
        ("zap", "Instant results", "No waiting for a server. Tools respond as you type, even on a slow connection."),
        ("gift", "Free, no sign-up", "No account, no trial and no paywall. Open a tool and use it."),
        ("book", "Sourced AI news", "Daily AI stories that link to the announcements and reports they are based on."),
    ]
    feature_cards = "".join(
        f'<li class="reveal" style="--d:{i * 0.06:.2f}s"><div class="card feature"><span class="tool-icon">{icon(ic, 24)}</span>'
        f'<h3>{esc(h)}</h3><p>{esc(d)}</p></div></li>' for i, (ic, h, d) in enumerate(features))
    main = f"""<section class="hero hero-center">
  <div class="container">
    <span class="pill reveal"><span class="dot">{icon("sparkles", 13)}</span>{n} free tools, no sign-up</span>
    <h1 class="reveal" style="--d:.05s">Free online tools for<br><span class="grad-text">developers, designers and writers</span></h1>
    <p class="lead reveal" style="--d:.1s">Format JSON, build CSS, convert images and PDFs, clean up text and more. Everything runs in your browser, so nothing you paste or upload leaves your device.</p>
    <form class="search reveal" style="--d:.15s" action="/tools/" method="get" role="search">
      {icon("search", 20)}<label class="is-hidden" for="home-search">Search tools</label>
      <input type="search" id="home-search" name="q" placeholder="Search tools, for example: json, webp, password regex" autocomplete="off">
    </form>
    <div class="hero-actions reveal" style="--d:.2s;margin-top:22px">
      <a class="ui-btn ui-btn-primary" href="/tools/">Browse all {n} tools {icon("arrow", 16)}</a>
      <a class="ui-btn ui-btn-ghost" href="/ai-news/">{icon("news", 16)} Latest AI news</a>
    </div>
  </div>
</section>

<div class="container">
  <section class="section" aria-labelledby="by-task" style="padding-top:20px">
    <div class="section-head"><div><h2 id="by-task">Find a tool by task</h2><p>Five groups, each one a click away.</p></div></div>
    <ul class="ui-grid ui-grid-4" style="grid-template-columns:repeat(auto-fill,minmax(210px,1fr))">{cat_tiles}</ul>
  </section>

  <section class="section" aria-labelledby="popular">
    <div class="section-head"><div><h2 id="popular">Popular tools</h2><p>The tools people open most often.</p></div>
      <a class="link-arrow" href="/tools/">All {n} tools {icon("arrow", 16)}</a></div>
    <ul class="ui-grid ui-grid-4">{"".join(tool_card(t, cats, (i % 4) * 0.05) for i, t in enumerate(featured))}</ul>
    <h3 style="font-size:1rem;color:var(--t2);margin:32px 0 14px">More tools</h3>
    <ul class="chips reveal">{"".join(f'<li><a class="chip" href="/tools/{t["slug"]}/">{icon(t["icon"], 16)}{esc(t["name"])}</a></li>' for t in reg["tools"] if not t.get("featured"))}</ul>
  </section>

  <section class="section" aria-labelledby="latest-news">
    <div class="section-head"><div><h2 id="latest-news">Latest AI news</h2><p>Short, sourced stories about AI models, companies and policy.</p></div>
      <a class="link-arrow" href="/ai-news/">All stories {icon("arrow", 16)}</a></div>
    <ul class="chips reveal" style="margin-bottom:22px">{chips}</ul>
    <ul class="ui-grid ui-grid-3" id="news-list">{"".join(news_card(p, i * 0.06) for i, p in enumerate(news[:3]))}</ul>
  </section>

  <section class="section" id="about" aria-labelledby="about-title">
    <div class="section-head"><div><h2 id="about-title">Why Web Online Tools</h2>
      <p>A free collection of small, focused utilities, plus an AI news section checked against its sources. Read the <a href="/ai-news/editorial-policy.html">editorial policy</a>.</p></div></div>
    <ul class="ui-grid ui-grid-4">{feature_cards}</ul>
  </section>
</div>"""
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/", "name": "Web Online Tools",
         "description": "Free browser-based tools for developers, designers and writers, plus sourced AI news.",
         "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": SITE + "/tools/?q={search_term_string}"},
                             "query-input": "required name=search_term_string"}},
        {"@type": "Organization", "@id": SITE + "/#org", "name": "Web Online Tools", "url": SITE + "/", "logo": SITE + "/favicon.svg"}]})
    write("index.html", page(
        title="Web Online Tools: Free Developer, Design and Text Tools",
        description=f"{n} free tools that run in your browser: format JSON, build CSS gradients and shadows, "
                    "convert images and PDFs, clean lists and more. No sign-up, no uploads.",
        canonical=SITE + "/", schema=schema, main=main, current=None, reg=reg, hubs=hubs,
        css_version=css_version, verify=True))


TOOLS_SCRIPT = """<script>
(function () {
  var box = document.getElementById("tool-filter"), empty = document.getElementById("no-match");
  function run() {
    var q = box.value.trim().toLowerCase(), shown = 0;
    document.querySelectorAll(".tool-section").forEach(function (sec) {
      var any = false;
      sec.querySelectorAll("li[data-search]").forEach(function (li) {
        var hit = !q || li.getAttribute("data-search").indexOf(q) > -1;
        li.classList.toggle("is-hidden", !hit); if (hit) { any = true; shown++; li.classList.add("in"); }
      });
      sec.classList.toggle("is-hidden", !any);
    });
    empty.style.display = shown ? "none" : "block";
  }
  var q = new URLSearchParams(location.search).get("q");
  if (q) { box.value = q; }
  box.addEventListener("input", run);
  run();
})();
</script>"""


def build_tools_index(reg, hubs, css_version):
    cats = {c["slug"]: c for c in reg["categories"]}
    n = len(reg["tools"])
    chips = "".join(f'<li><a class="chip" href="#{c["slug"]}">{icon(c["icon"], 16)}{esc(c["name"])}</a></li>' for c in reg["categories"])
    sections = []
    for c in reg["categories"]:
        items = [t for t in reg["tools"] if t["category"] == c["slug"]]
        sections.append(
            f'<section class="section tool-section" id="{c["slug"]}" aria-labelledby="h-{c["slug"]}" style="scroll-margin-top:80px;padding:36px 0">'
            f'<div class="section-head"><div><h2 id="h-{c["slug"]}" style="display:flex;align-items:center;gap:12px">'
            f'<span class="tool-icon" style="margin:0;width:40px;height:40px">{icon(c["icon"], 20)}</span>{esc(c["name"])}</h2>'
            f'<p>{esc(c["about"])}</p></div></div>'
            f'<ul class="ui-grid ui-grid-4">{"".join(tool_card(t, cats, (i % 4) * 0.05) for i, t in enumerate(items))}</ul></section>')
    trail = [("Home", "/"), ("Tools", "/tools/")]
    main = f"""<section class="hero hero-center" style="padding-bottom:20px">
  <div class="container">
    {crumbs(trail)}
    <span class="pill reveal" style="margin-top:28px"><span class="dot">{icon("grid", 13)}</span>{n} tools in 5 groups</span>
    <h1 class="reveal" style="--d:.05s">All free <span class="grad-text">online tools</span></h1>
    <p class="lead reveal" style="--d:.1s">Browser-based tools for developers, designers and writers. Nothing to install, and your files stay on your device.</p>
    <label class="search reveal" style="--d:.15s">{icon("search", 20)}<span class="is-hidden">Filter tools</span>
      <input type="search" id="tool-filter" placeholder="Filter tools, for example: json, color, pdf" autocomplete="off"></label>
    <ul class="chips reveal" style="--d:.2s;justify-content:center;margin-top:24px">{chips}</ul>
  </div>
</section>
<div class="container">
  {"".join(sections)}
  <p class="empty-state" id="no-match">No tools match that search. Try another word, or <a href="/tools/">see all tools</a>.</p>
</div>"""
    schema = json_ld({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": "All free online tools", "url": SITE + "/tools/",
         "mainEntity": {"@type": "ItemList", "numberOfItems": n, "itemListElement": [
             {"@type": "ListItem", "position": i, "name": t["name"], "url": f"{SITE}/tools/{t['slug']}/"}
             for i, t in enumerate(reg["tools"], 1)]}},
        breadcrumb_schema(trail)]})
    write("tools/index.html", page(
        title="All Free Online Tools",
        description=f"Browse all {n} free browser-based tools for developers, designers and writers, "
                    "grouped by task. Nothing to install, and your files never leave your device.",
        canonical=SITE + "/tools/", schema=schema, main=main, current="tools", reg=reg, hubs=hubs,
        css_version=css_version, script=TOOLS_SCRIPT))


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
    css = open(os.path.join(REPO, "assets", "ui.css"), encoding="utf-8").read()
    css_version = hashlib.md5(css.encode()).hexdigest()[:8]
    write("assets/ui.css", css)
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
