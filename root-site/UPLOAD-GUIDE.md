# Uploading the updated site files to Hostinger

These files replace everything in `public_html` **except the `ai-news` folder**, which GitHub updates on its own.

## 1. Upload and replace

1. In Hostinger, open **File Manager** and go to `public_html`.
2. Upload `webonlinetools-root-files.zip` and choose **Extract** into `public_html`.
3. Choose **Replace** when asked about existing files.
4. If an earlier upload created `assets/tools.css`, delete it; it is no longer used.

The ZIP contains:

| Path | What it is |
| --- | --- |
| `index.html` | New homepage, with every tool linked in plain HTML |
| `tools/index.html` | New tools directory, grouped by task |
| `tools/<tool>/index.html` | All 17 tool pages, fixed and with new titles, descriptions and schema |
| `tools/tools.json` | Tools list (now includes PDF to JPG) |
| `assets/ui.css` | The site's design: header, footer, cards, fonts and animation (new folder) |
| `sitemap.xml` | Sitemap index that covers the tools and the AI news |
| `sitemap-pages.xml` | Homepage, tools directory and all tool pages |
| `robots.txt` | New: allows crawling and points to the sitemap |
| `favicon.svg` | Unchanged |

## 2. Delete these files

They are Hostinger placeholder pages titled "Default page" and should not exist on a live site:

- `keep.txt`
- `tools/<every tool folder>/default.php` (16 files, one in each tool folder)

## 3. Search Console

1. **Sitemaps:** submit `sitemap.xml`. It is now an index that includes the AI news sitemap, so this one submission covers the whole site. You can leave the `ai-news/sitemap.xml` submission in place.
2. **URL Inspection:** request indexing for the homepage, `/tools/`, `/tools/password-rule-generator/` and `/tools/webp-converter/`.

## Do not upload into `ai-news`

That folder is deployed from GitHub. Anything uploaded there by hand is overwritten.
