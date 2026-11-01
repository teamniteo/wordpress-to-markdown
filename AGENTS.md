# Instructions for Claude Code

This repo converts a WordPress WXR export into Astro-ready Markdown via two scripts: `convert.py` and `rename_images.py`. Each conversion lives under `projects/<name>/`.

## Workflow: `New conversion - <name>`

When the user says `New conversion - <name>`:

1. Verify `projects/<name>/source/` exists and contains:
   - At least one `.xml` file (the WXR export)
   - Exactly one subfolder containing the media (any name)

   If either is missing, stop and tell the user what to drop in.

2. If `projects/<name>/config.py` doesn't exist, copy `projects/example/config.py` to it.

3. Fill in `config.py` by reading the WXR:
   - Run `grep -h '<dc:creator>' projects/<name>/source/*.xml | sort -u` to list all WP login names. Ask the user who each one is (real name, email, short bio) and populate `AUTHORS`, `AUTHOR_BY_LOGIN`, and `DEFAULT_AUTHOR`. If a login looks like a generic team account (`info@…`, `admin`), suggest it as the team/default author.
   - Ask the user for their old WordPress domain and update `SOURCE_URL_PATTERN` to match it.
   - Leave `CONTENT_DESCRIPTIONS = {}` for now — Step 4 (`Tidy image filenames`) fills that in after the first run.

4. Install Python dependencies if not already installed: `pip install -r requirements.txt`.

5. Run `python convert.py <name>`. Surface the final summary verbatim, especially:
   - The "Posts converted" / "Pages converted" counts and draft counts
   - The "Posts per author" breakdown — flag if any author has zero posts (likely a missing login mapping)
   - Any `Warnings` block (unresolved image URLs)

6. Tell the user the output is in `projects/<name>/output/` and offer Step 4.

## Workflow: `Tidy image filenames - <name>`

When the user says `Tidy image filenames - <name>`:

1. Re-run `python convert.py <name>` with stderr captured if no recent run is on disk; otherwise skip and read the existing posts directly.

2. Find every `WARNING: no description for content image …` from the rename pass. For each:
   - Read `projects/<name>/output/posts/<slug>.md` and locate the image reference.
   - Look at the surrounding 1–2 paragraphs and the alt text. Propose a short, descriptive slug fragment (lowercase, hyphens, no extension). Examples: `team-photo`, `dashboard-screenshot`, `pricing-table`.
   - If the image looks generic (a stock illustration, decorative spacer), use `illustration-1`, `illustration-2`, etc.

3. Add each `(filename, slug) -> description` entry to `CONTENT_DESCRIPTIONS` in `projects/<name>/config.py`. Group entries by post slug with a comment header for readability.

4. Re-run `python rename_images.py <name>` and report how many images were renamed and how many warnings remain.

## Things to remember

- Never commit anything under `projects/<name>/source/` or `projects/<name>/output/` — both are gitignored, but don't `git add -A`.
- The `projects/example/` folder is the template only. Don't run conversions there.
- If the user's `.xml` file is huge (>50 MB), warn them but proceed — `convert.py` streams it via `xml.etree`.
- If a post import fails because of malformed HTML, patch `preprocess_html` in `convert.py` rather than hand-editing the post output (so re-runs stay clean).
