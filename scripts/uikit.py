"""
Shared interface pieces for the whole site: icons, header, footer and the scroll-animation script.
Used by scripts/build-site.py (AI news) and root-site/build-root.py (homepage and tools),
so every page on webonlinetools.com has the same header and footer.
"""
import html
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Icon paths in the 24x24 stroke style (Lucide-like), drawn with stroke="currentColor".
ICONS = {
    "logo": '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "news": '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "zap": '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    "gift": '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5A4.8 8 0 0 1 12 8a4.8 8 0 0 1 4.5-5 2.5 2.5 0 0 1 0 5"/>',
    "book": '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "share": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.59 13.51 6.83 3.98"/><path d="m15.41 6.51-6.82 3.98"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "scale": '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    "building": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
    # tools
    "braces": '<path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1"/><path d="M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1"/>',
    "binary": '<rect x="14" y="14" width="4" height="6" rx="2"/><rect x="6" y="4" width="4" height="6" rx="2"/><path d="M6 20h4"/><path d="M14 10h4"/><path d="M6 14h2v6"/><path d="M14 4h2v6"/>',
    "key": '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/>',
    "dice": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M16 8h.01"/><path d="M8 8h.01"/><path d="M8 16h.01"/><path d="M16 16h.01"/><path d="M12 12h.01"/>',
    "blend": '<circle cx="9" cy="9" r="7"/><circle cx="15" cy="15" r="7"/>',
    "layers": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "pointer": '<path d="M14 4.1 12 6"/><path d="m5.1 8-2.9-.8"/><path d="m6 12-1.9 2"/><path d="M7.2 2.2 8 5.1"/><path d="M9.04 9.68a.5.5 0 0 1 .64-.64l11 4.5a.5.5 0 0 1-.06.94l-4.43 1.18a2 2 0 0 0-1.42 1.42l-1.18 4.43a.5.5 0 0 1-.94.06z"/>',
    "palette": '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.65-.75 1.65-1.69 0-.44-.18-.84-.44-1.13-.29-.29-.44-.65-.44-1.13a1.64 1.64 0 0 1 1.67-1.67h2c3.05 0 5.56-2.5 5.56-5.55C21.97 6.01 17.46 2 12 2z"/>',
    "pipette": '<path d="m2 22 1-1h3l9-9"/><path d="M3 21v-3l9-9"/><path d="m15 6 3.4-3.4a2.1 2.1 0 1 1 3 3L18 9l.4.4a2.1 2.1 0 1 1-3 3l-3.8-3.8a2.1 2.1 0 1 1 3-3l.4.4Z"/>',
    "text": '<path d="M17 6.1H3"/><path d="M21 12.1H3"/><path d="M15.1 18H3"/>',
    "type": '<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>',
    "list": '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    "sparkles": '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.13-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.13a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.13 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.13a.5.5 0 0 1-.96 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    "file-image": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><circle cx="10" cy="12" r="2"/><path d="m20 17-1.3-1.3a2.4 2.4 0 0 0-3.4 0L9 22"/>',
    "cart": '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>',
    "code": '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    "pen": '<path d="M15.71 2.29a1 1 0 0 1 1.42 0l4.58 4.58a1 1 0 0 1 0 1.42l-2.3 2.3a1 1 0 0 1-1.42 0l-4.58-4.58a1 1 0 0 1 0-1.42Z"/><path d="m14 7-9.54 9.54a2 2 0 0 0-.46.83L3 21l3.63-1a2 2 0 0 0 .83-.46L17 10"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "calculator": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8"/><path d="M16 14v4"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/>',
    "x-logo": '<path d="M4 4l16 16"/><path d="M20 4 4 20"/>',
}

# Brand colour for each AI news hub badge; companies not listed get a neutral colour.
HUB_COLORS = {
    "openai": "#10b981", "google": "#3b82f6", "anthropic": "#f59e0b", "microsoft": "#06b6d4",
    "nvidia": "#84cc16", "apple": "#a1a1aa", "meta": "#6366f1", "amazon": "#f97316", "policy": "#e879f9",
}

PRIMARY_NAV = [("Tools", "/tools/", "grid", "tools"), ("AI news", "/ai-news/", "news", "news")]


def esc(text):
    return html.escape(text or "", quote=True)


def icon(name, size=20, cls="ico"):
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, "")}</svg>')


def hub_color(slug):
    return HUB_COLORS.get(slug, "#94a3b8")


def hub_badge(hub, small=False):
    """Coloured company or topic badge, e.g. on news cards."""
    label = esc(hub["name"])
    return (f'<span class="badge{" badge-sm" if small else ""}" style="--badge:{hub_color(hub["slug"])}">'
            f'{icon("scale", 12) if hub.get("kind") == "topic" else ""}{label}</span>')


def load_registry():
    with open(os.path.join(REPO, "root-site", "tools.json"), encoding="utf-8") as f:
        return json.load(f)


def header(current=None):
    links = "".join(
        f'<a href="{href}" class="nav-link"' + (' aria-current="page"' if key == current else "") + f">{icon(ic, 18)}<span>{label}</span></a>"
        for label, href, ic, key in PRIMARY_NAV)
    return f"""<header class="site-head" id="top">
  <div class="site-head-inner">
    <a class="ui-logo" href="/" aria-label="Web Online Tools home">
      <span class="ui-logo-mark">{icon("logo", 18)}</span><span class="ui-logo-text">Web Online Tools</span>
    </a>
    <nav class="main-nav" id="main-nav" aria-label="Main">{links}
      <a href="/tools/" class="nav-cta">Browse tools {icon("arrow", 16)}</a>
    </nav>
    <button class="menu-btn" type="button" aria-controls="main-nav" aria-expanded="false" aria-label="Open menu">{icon("menu", 22)}</button>
  </div>
</header>"""


def footer(reg, hubs):
    cats = {c["slug"]: c for c in reg["categories"]}
    popular = [t for t in reg["tools"] if t.get("featured")][:7]
    tool_links = "".join(f'<li><a href="/tools/{t["slug"]}/">{esc(t["name"])}</a></li>' for t in popular)
    cat_links = "".join(f'<li><a href="/tools/#{c["slug"]}">{esc(c["name"])}</a></li>' for c in reg["categories"])
    hub_links = "".join(f'<li><a href="/ai-news/{h["slug"]}/">{esc(h["name"])}</a></li>' for h in hubs)
    return f"""<footer class="site-foot">
  <div class="site-foot-inner">
    <div class="foot-brand">
      <a class="ui-logo" href="/"><span class="ui-logo-mark">{icon("logo", 18)}</span><span class="ui-logo-text">Web Online Tools</span></a>
      <p>Free tools that run in your browser, plus sourced news on AI models, companies and policy.</p>
      <ul class="foot-points">
        <li>{icon("shield", 16)} Your files and text never leave your device</li>
        <li>{icon("gift", 16)} Free, no sign-up</li>
      </ul>
    </div>
    <nav class="foot-col" aria-label="Popular tools"><h2>Popular tools</h2><ul>{tool_links}<li><a href="/tools/">All {len(reg["tools"])} tools</a></li></ul></nav>
    <nav class="foot-col" aria-label="Tool categories"><h2>Categories</h2><ul>{cat_links}</ul></nav>
    <nav class="foot-col" aria-label="AI news"><h2>AI news</h2><ul><li><a href="/ai-news/">Latest stories</a></li>{hub_links}</ul></nav>
  </div>
  <div class="foot-bottom">
    <p>© <span id="year">2026</span> Web Online Tools</p>
    <p class="foot-links"><a href="/ai-news/editorial-policy.html">Editorial policy</a><a href="/#about">About</a></p>
  </div>
</footer>"""


# Mobile menu toggle, scroll-in animation and footer year. Respects reduced-motion settings.
UI_SCRIPT = """<script>
(function () {
  var btn = document.querySelector(".menu-btn"), nav = document.getElementById("main-nav");
  if (btn && nav) btn.addEventListener("click", function () {
    var open = nav.classList.toggle("open");
    btn.setAttribute("aria-expanded", open);
    btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });
  var y = document.getElementById("year"); if (y) y.textContent = new Date().getFullYear();
  var items = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    items.forEach(function (el) { el.classList.add("in"); }); return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { rootMargin: "0px 0px -8% 0px" });
  items.forEach(function (el) { io.observe(el); });
})();
</script>"""

# Runs before paint: marks that JavaScript is on, so content only starts hidden when it can be revealed.
JS_FLAG = '<script>document.documentElement.classList.add("js")</script>'
