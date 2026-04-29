# wordpress-to-markdown

Convert a WordPress export into clean, Astro-ready Markdown blog posts and pages — with author frontmatter, resolved local images, and human-readable filenames.

This is the script [Niteo](https://niteo.co) used to migrate every one of its blogs off WordPress and onto [Hakuto](https://github.com/teamniteo/hakuto), our free and open source Astro site builder framework for [Claude Code](https://claude.com/claude-code).

## What you need

- [Claude Code](https://claude.com/claude-code) installed
- A WordPress site you can log into as admin
- Python 3.10+ on your machine (Claude Code will install dependencies for you)

## Step 1 — Get your WordPress content

In WP admin:

- **Tools → Export → All content** → download the `.xml` file.
- Install the [Export Media Library](https://wordpress.org/plugins/export-media-library/) plugin, then **Media → Export → Single folder with all files** to download all your images as a flat zip.

## Step 2 — Set up the folder

1. Download this repo (green **Code** button → **Download ZIP**) and unzip it.
2. Inside `projects/`, create a folder named after your site, e.g. `projects/my-site/`.
3. Inside that, create a `source/` folder and drop in your `.xml` export and your unzipped uploads folder.

```
projects/my-site/source/
├── wordpress-export.xml
└── uploads/                  # all your images, flat
```

## Step 3 — Hand off to Claude Code

Open the unzipped folder in Claude Code (`claude` in the folder, or via the Claude Code app) and paste this:

```
Set up a new conversion project called my-site. Copy projects/example/config.py into it, then look at the WXR in projects/my-site/source/ and help me fill in the authors and AUTHOR_BY_LOGIN map by reading the <dc:creator> values. Set SOURCE_URL_PATTERN to match my old WordPress domain. Then install the Python dependencies (pip install -r requirements.txt) and run python convert.py my-site. Show me any warnings about unresolved images at the end.
```

Claude Code will ask you a few questions (your old domain, who each author is), fill in the config, and run the conversion. Output lands in `projects/my-site/output/`:

```
output/
├── posts/      # .md per post, ready for Astro
├── pages/      # .md per page
└── images/     # only the images actually referenced, renamed for readability
```

## Step 4 — Tidy image filenames (optional, recommended)

After the first run, the script logs warnings for images it couldn't auto-name. Paste:

```
Look at the warnings about missing image descriptions. For each one, read the post it appears in and suggest a short, descriptive filename slug. Add them to CONTENT_DESCRIPTIONS in projects/my-site/config.py, then re-run python rename_images.py my-site.
```

## Output format

Each post gets Astro-ready frontmatter:

```yaml
---
title: "Post title"
slug: "post-slug"
date: "2024-08-12"
author: "Jane Doe"
authorEmail: "jane@example.com"
authorBio: "Jane writes about web performance and developer tooling."
category: "Engineering"
description: "Excerpt or first paragraph, trimmed to ~160 chars."
featuredImage: "/images/blog/post-slug-cover.jpg"
draft: false
---
```

Drafts come through with `draft: true` so you can review before shipping.

## Credits

Built by [Niteo](https://niteo.co), the team behind [Hakuto](https://github.com/teamniteo/hakuto). MIT licensed — see [LICENSE](LICENSE).
