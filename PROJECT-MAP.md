# Project map

This repo is the AI news section of webonlinetools.com. Hostinger deploys the repo root to `/ai-news/`
on every push to `main`. Pages are generated; never edit a generated file by hand.

## Where to change what

| To change | Edit | Then |
| --- | --- | --- |
| Look of every page on the whole site (colors, fonts, cards, animation) | `assets/ui.css` (also copied to the root site) | push; rebuild root and upload |
| Header, footer and icons on every page (blog and tools) | `scripts/uikit.py` | push; rebuild root and upload |
| Blog page head and meta tags | `render_page` in `scripts/build-site.py` | push |
| Post layout, schema, related links, archive, sitemap, feed, redirects, access rules | `scripts/build-site.py` | push |
| Editorial policy text | `templates/editorial-policy.html` | push |
| What the daily writer asks Gemini, and its publishing checks | `scripts/write-post.py` | runs next morning |
| A post's text, title, sources or facts | `content/posts/<slug>.json` | push |
| Merge a duplicate story | add `"old-slug": "kept-slug"` to `data/redirects.json` | push |
| Company and topic hubs, menu order | `data/companies.json` (name, slug, match words, about, title) | push |
| How many stories a hub needs | `HUB_MIN` in `scripts/build-site.py` (now 4) | push |
| Schedule and steps of the automation | `.github/workflows/daily-news.yml` | push |

## Folders

```
content/posts/<slug>.json   one file per post (source of truth)
data/redirects.json         merged duplicates, old slug -> kept slug (hand-maintained)
data/companies.json         companies and topics; the writer adds new companies automatically
data/hubs.json              hubs built last time, generated; used to remove hubs that no longer qualify
data/keywords.json          keyword registry, generated; the writer reads it to avoid duplicates
templates/                  editorial policy body
assets/ui.css               the one stylesheet for the whole site
scripts/uikit.py            shared header, footer, icons and scroll animation
scripts/build-site.py       renders everything below from the data
scripts/write-post.py       daily Gemini writer with source, freshness and duplicate checks
```

## Generated (do not edit)

`<slug>.html`, `<hub>/index.html` (e.g. `openai/`), `index.html`, `editorial-policy.html`, `sitemap.xml`, `feed.xml`, `index.json`,
`files.json`, `data/keywords.json`, `.htaccess`

## Post file format

```json
{
  "slug": "url-name-with-hyphens",
  "title": "Plain headline people would search",
  "description": "Meta description, about 150 characters",
  "keyword": "the one long-tail query this page targets",
  "published": "2026-10-07T03:00:00+00:00",
  "updated": "",
  "facts": {"Who": "", "What": "", "When": "", "Status": ""},
  "sources": [{"title": "", "publisher": "", "date": "YYYY-MM-DD", "url": ""}],
  "related": [],
  "company": "OpenAI",
  "correction": {"date": "YYYY-MM-DD", "text": "shown above the story when present"},
  "status": "verified or legacy",
  "body": "<p>HTML with [1] citation markers</p>"
}
```

## Rules

- One H1 per page (the title); the body starts at H2.
- Hyphens, never underscores, in URLs, file names, CSS classes and IDs.
- One primary keyword per URL. A story that repeats an existing one is skipped or redirected, never published twice.
- A hub page and menu link appear automatically once a company has HUB_MIN stories.
- New stories are rejected if any 2-3 word phrase makes up more than 2.5% of the text (keyword stuffing).
- Legacy posts (`"status": "legacy"`) predate sourcing and show a note instead of a Sources list.

## Root site (everything outside /ai-news/)

The homepage, `/tools/` and the tool pages are hosted directly on Hostinger, not deployed from this repo.
Their source lives in `root-site/` (blocked from public access) so changes are made here and uploaded.

| To change | Edit | Then |
| --- | --- | --- |
| A tool's name, title tag, meta description, H1, card text, category, related tools | `root-site/tools.json` | build and upload |
| A tool's interface or logic | `root-site/src/tools/<slug>/index.html` | build and upload |
| Homepage and tools-index layout | `root-site/build-root.py` (header, footer and styles come from `scripts/uikit.py` and `assets/ui.css`) | build and upload |
| Add a new tool | add its page under `root-site/src/tools/<slug>/` and an entry in `root-site/tools.json` | build and upload |

Build: `python root-site/build-root.py` writes `root-site/dist/`, then upload its contents to `public_html`
(see `root-site/UPLOAD-GUIDE.md`). The build regenerates the homepage tool grid, tools index, footer menus,
`sitemap.xml` (an index that includes `/ai-news/sitemap.xml`), `sitemap-pages.xml` and `robots.txt`.
`root-site/lastmod.json` records when each page last changed so sitemap dates stay honest.
