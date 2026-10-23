# Hostinger public_html backup

This folder is a byte-for-byte copy of the webonlinetools.com `public_html` folder on Hostinger,
**except the `ai-news` folder**. On the server the layout was:

```
public_html/
  ai-news/          <- this whole repository (deployed from GitHub)
  index.html        <- these files: the homepage,
  favicon.svg          favicon,
  sitemap.xml          root sitemap,
  keep.txt             Hostinger placeholder,
  tools/               tools directory and the 17 tool pages
```

So the files here sat **next to** `ai-news`, not inside it. Taken from the export of 7 October 2026,
before the domain expired on 21 October 2026. Checked against the export: 39 files, all identical.

## Two versions of the root site in this repo

| Folder | What it is |
| --- | --- |
| `public-html/` (this folder) | The original files exactly as they were on Hostinger. Keep as an untouched backup. |
| `root-site/dist/` | The redesigned and fixed version (new design, tool bug fixes, SEO, sitemap index, robots.txt). Ready to upload. |
| `root-site/src/` + `root-site/tools.json` | The source the redesigned version is built from (`python root-site/build-root.py`). |

## Putting the site back online

To restore the whole site on any static host (Hostinger, Netlify, GitHub Pages, Cloudflare Pages):

1. Copy the contents of `root-site/dist/` (or this folder, for the original version) to the web root.
2. Put the generated blog files from this repository in an `ai-news/` folder next to them.
3. If the domain changes, update the domain in `SITE` in `scripts/build-site.py` and `root-site/build-root.py`
   and rebuild, so canonical links and sitemaps point to the new address.

The `tools/*/default.php` files are Hostinger "Default page" placeholders and are not needed on a new host.
