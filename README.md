# wordpress-to-markdown

Convert a WordPress WXR export into clean, Astro-ready Markdown blog posts and pages — with author frontmatter, resolved local images, and human-readable filenames.

This is the script [Niteo](https://niteo.co) used to migrate every one of its blogs off WordPress and onto [Hakuto](https://github.com/teamniteo/hakuto), our free and open source Astro site builder framework for Claude Code. We figured we may as well share it.

## What it does

- Reads a WordPress WXR (`.xml`) export plus the matching media folder.
- Strips WordPress block comments, CTA banners, inline-style spans, and copy-paste junk.
- Converts each `<item>` to a `.md` file with YAML frontmatter (title, slug, date, author, description, category, draft, optional `featuredImage`).
- Resolves every `<img>` and `<figure>` to a local file in the media folder, copying only the images each post actually uses.
- Renames images from `IMG_2034-scaled.jpg` to `your-post-slug-cover.jpg` (or `your-post-slug-<description>.jpg`) so the content folder stays readable.
- Handles posts and pages, drafts, multiple authors, and per-slug author overrides.

The output is opinionated for [Hakuto](https://github.com/teamniteo/hakuto) but the frontmatter is plain enough to drop into any Astro content collection — adjust schemas to taste.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
- A WordPress WXR export and the matching `wp-content/uploads` media folder
- _(Recommended)_ [Claude Code](https://claude.com/claude-code) — see [Working with Claude Code](#working-with-claude-code) below

The Python scripts run standalone. Claude Code is not a hard dependency — it just makes the human-judgment parts (author bios, mapping logins, picking image descriptions, post-conversion cleanup) hours faster.

## Run it with Claude Code (no terminal required)

If you don't live in a terminal, this is the easy path. You'll need [Claude Code](https://claude.com/claude-code) installed and your WordPress export ready to drop on disk.

1. Download this repo as a zip from GitHub (green **Code** button → **Download ZIP**) and unzip it somewhere — Desktop is fine.
2. Export your WordPress site (**Tools → Export → All content** in WP admin) and save the `.xml` file. For the media, install the [Export Media Library](https://wordpress.org/plugins/export-media-library/) plugin and use **Media → Export → Single folder with all files** to grab everything as a flat zip.
3. Make a new folder inside `projects/` named after your site (e.g. `projects/my-site`). Inside it, create a folder called `source/` and put both the `.xml` file and your uploads folder there.
4. Open the unzipped folder in Claude Code (`claude` in the folder, or open it via the Claude Code app).
5. Paste this prompt:

   > Set up a new conversion project called `my-site`. Copy `projects/example/config.py` into it, then look at the WXR in `projects/my-site/source/` and help me fill in the authors and `AUTHOR_BY_LOGIN` map by reading the `<dc:creator>` values. Set `SOURCE_URL_PATTERN` to match my old WordPress domain. Then install the Python dependencies (`pip install -r requirements.txt`) and run `python convert.py my-site`. Show me any warnings about unresolved images at the end.

6. Claude Code will ask you a couple of questions (your old domain, who each author is), then run the conversion. The output lands in `projects/my-site/output/`.
7. _(Optional, but worth it)_ After the first run, paste:

   > Look at the warnings about missing image descriptions. For each one, read the post it appears in and suggest a short, descriptive filename slug. Add them to `CONTENT_DESCRIPTIONS` in `projects/my-site/config.py`, then re-run `python rename_images.py my-site`.

That's the whole loop. The CLI quick-start below is the same thing, just typed out by hand.

## Quick start

```bash
git clone https://github.com/teamniteo/wordpress-to-markdown
cd wordpress-to-markdown
pip install -r requirements.txt

# Set up a project
cp -r projects/example projects/my-site
# Drop your WXR + media folder into projects/my-site/source/
# Edit projects/my-site/config.py with your authors and SOURCE_URL_PATTERN

python convert.py my-site
```

Converted files land in `projects/my-site/output/`:

```
output/
├── posts/      # .md per post, ready for Astro
├── pages/      # .md per page
└── images/     # only the images actually referenced, renamed for readability
```

## Exporting from WordPress

In WP admin: **Tools → Export → All content → Download Export File**.

You also need the matching media. The easiest way is the [Export Media Library](https://wordpress.org/plugins/export-media-library/) plugin — install it, then **Media → Export** and choose "Single folder with all files" to get a flat zip you can drop straight into `source/`. If you'd rather not install a plugin, download `wp-content/uploads/` over SFTP and flatten it into a single folder (the script doesn't care about year/month subfolders — it indexes by filename).

Drop both into `projects/<your-site>/source/`:

```
projects/my-site/source/
├── wordpress-export.xml      # one or more WXR files
└── uploads/                  # any single subfolder name; must contain images
```

The script expects exactly one subfolder under `source/` for media.

## Project layout

```
projects/<name>/
├── config.py        # authors, login map, image rename hints (you edit this)
├── source/          # your WXR + media (gitignored)
└── output/          # generated — posts/, pages/, images/ (gitignored)
```

Each project is fully self-contained, so you can run several migrations side by side.

## `config.py` reference

See [`projects/example/config.py`](projects/example/config.py) for a fully-commented template. The fields:

| Key | Purpose |
| --- | --- |
| `AUTHORS` | Dict of `key -> {name, email, bio}`. Bios end up in the `authorBio` frontmatter field. |
| `DEFAULT_AUTHOR` | Author key used when no other lookup matches. |
| `AUTHOR_BY_LOGIN` | Map `<dc:creator>` value (the WP login) to an author key. Find these by grepping the WXR. |
| `AUTHOR_OVERRIDES` | Per-slug overrides — wins over login map. Useful for guest posts. |
| `SOURCE_URL_PATTERN` | Regex matching your old domain's image URLs. Used to warn about images present in HTML but missing from the media folder. Set to `None` to disable. |
| `CONTENT_DESCRIPTIONS` | `(old_filename, slug) -> description` map. Drives the readable-filename rename pass. Optional — unmapped images fall back to `<slug>-image-N`. |

## How images work

1. Every `<img>` and `<figure>` in the WXR HTML gets resolved against the media folder. Size variants like `-300x200` and `-scaled` are stripped before lookup, and alternative extensions (`.jpg`/`.jpeg`/`.png`/`.webp`/`.avif`) are tried.
2. Only images referenced by surviving posts/pages get copied into `output/images/` — orphans are left behind.
3. After conversion, `rename_images.py` runs automatically. It:
   - Renames featured images to `<slug>-cover.<ext>`.
   - Renames content images using `CONTENT_DESCRIPTIONS` if you provided hints, or `<slug>-image-1`, `<slug>-image-2`, … as a fallback (with a warning so you can fill them in later).
   - Updates every Markdown file to point at the new names.

If you re-run after editing `CONTENT_DESCRIPTIONS`, `rename_images.py` is idempotent — wipe `output/` first to start clean.

## Output frontmatter

Each post gets:

```yaml
---
title: "Post title"
slug: "post-slug"
date: "2024-08-12"
author: "Jane Doe"
authorEmail: "jane@example.com"
authorBio: "Jane writes about web performance and developer tooling."
category: "Engineering"
description: "Either the WP excerpt, or the first non-trivial paragraph trimmed to ~160 chars."
featuredImage: "/images/blog/post-slug-cover.jpg"   # only if a thumbnail was set
draft: false
---
```

Pages get a slimmer frontmatter (no author, category, or date). Drafts (`status != publish`) come through with `draft: true` so you can review before shipping.

## Working with Claude Code

This script handles the mechanical 90%. The remaining 10% is judgment work that's much faster with [Claude Code](https://claude.com/claude-code) sitting in the same repo:

- **Author bios.** Point Claude Code at the company about page or LinkedIn and have it draft 1–2 sentence bios per author.
- **Login → author key map.** `grep '<dc:creator>' projects/my-site/source/*.xml | sort -u` and ask Claude Code to fill in `AUTHOR_BY_LOGIN` from the result.
- **Image descriptions.** After a first run, the script logs `WARNING: no description for content image …`. Have Claude Code skim each post's Markdown and propose `CONTENT_DESCRIPTIONS` entries — it sees both the surrounding prose and the image position, so it picks much better names than you'd grind out by hand.
- **Post-conversion cleanup.** WordPress accumulates exotic markup over the years (custom shortcodes, embedded PDFs, weird gallery plugins). Skim the output, paste any oddities into Claude Code, and let it patch `preprocess_html` in `convert.py`.

We use Claude Code with [Hakuto's skills](https://github.com/teamniteo/hakuto) so the prompts already understand Astro content collections — but vanilla Claude Code works fine.

## Credits

Built by [Niteo](https://niteo.co), the team behind [Hakuto](https://github.com/teamniteo/hakuto) — our free and open source Astro site builder framework for Claude Code. We wrote this to migrate our own blogs (and a handful of personal ones) off WordPress when we moved to Hakuto.

If you build something with it, [say hi](https://niteo.co).

## License

MIT — see [LICENSE](LICENSE).
