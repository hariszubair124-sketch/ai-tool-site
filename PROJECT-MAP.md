# Project map

This repo is the AI news section of webonlinetools.com. Hostinger deploys the repo root to `/ai-news/`
on every push to `main`. Pages are generated; never edit a generated file by hand.

## Where to change what

| To change | Edit | Then |
| --- | --- | --- |
| Look of every page (colors, fonts, spacing) | `assets/site.css` | push; the workflow rebuilds |
| Header, footer, meta tags shared by all pages | `templates/page.html` | push |
| Post layout, schema, related links, archive, sitemap, feed, redirects, access rules | `scripts/build-site.py` | push |
| Editorial policy text | `templates/editorial-policy.html` | push |
| What the daily writer asks Gemini, and its publishing checks | `scripts/write-post.py` | runs next morning |
| A post's text, title, sources or facts | `content/posts/<slug>.json` | push |
| Merge a duplicate story | add `"old-slug": "kept-slug"` to `data/redirects.json` | push |
| Schedule and steps of the automation | `.github/workflows/daily-news.yml` | push |

## Folders

```
content/posts/<slug>.json   one file per post (source of truth)
data/redirects.json         merged duplicates, old slug -> kept slug (hand-maintained)
data/keywords.json          keyword registry, generated; the writer reads it to avoid duplicates
templates/                  page shell and the editorial policy body
assets/site.css             the only stylesheet
scripts/build-site.py       renders everything below from the data
scripts/write-post.py       daily Gemini writer with source, freshness and duplicate checks
```

## Generated (do not edit)

`<slug>.html`, `index.html`, `editorial-policy.html`, `sitemap.xml`, `feed.xml`, `index.json`,
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
  "status": "verified or legacy",
  "body": "<p>HTML with [1] citation markers</p>"
}
```

## Rules

- One H1 per page (the title); the body starts at H2.
- Hyphens, never underscores, in URLs, file names, CSS classes and IDs.
- One primary keyword per URL. A story that repeats an existing one is skipped or redirected, never published twice.
- Legacy posts (`"status": "legacy"`) predate sourcing and show a note instead of a Sources list.
