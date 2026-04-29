#!/usr/bin/env python3
"""Convert WordPress WXR export to Astro-compatible markdown blog posts.

Usage: python convert.py <project_name>

Reads from projects/<project_name>/source (WXR files + media folder),
writes to projects/<project_name>/output (posts/ + images/).
Per-project config (authors, overrides, etc.) lives in projects/<project_name>/config.py.
"""

import argparse
import importlib.util
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

from rename_images import rename_images

BASE_DIR = Path(__file__).parent

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "wp": "http://wordpress.org/export/1.2/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def xml_text(el, path, default=""):
    """Find a child element and return its text, or default if missing/empty."""
    if el is None:
        return default
    found = el.find(path, NS)
    if found is None or found.text is None:
        return default
    return found.text


def load_project(name):
    project_dir = BASE_DIR / "projects" / name
    if not project_dir.is_dir():
        sys.exit(f"Project not found: {project_dir}")

    source = project_dir / "source"
    if not source.is_dir():
        sys.exit(f"Missing source/ in {project_dir}")

    wxr_files = sorted(source.glob("*.xml"))
    if not wxr_files:
        sys.exit(f"No WXR (.xml) files in {source}")

    subdirs = [p for p in source.iterdir() if p.is_dir()]
    if len(subdirs) != 1:
        sys.exit(
            f"Expected exactly one media subfolder in {source}, found {len(subdirs)}"
        )
    media_dir = subdirs[0]

    config_path = project_dir / "config.py"
    if not config_path.exists():
        sys.exit(f"Missing config.py in {project_dir}")
    spec = importlib.util.spec_from_file_location(f"_project_{name}", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

    return project_dir, wxr_files, media_dir, config


def build_media_index(media_dir):
    """Build a dict of lowercase filename -> actual filename for local media files."""
    index = {}
    for f in media_dir.iterdir():
        if f.is_file():
            index[f.name.lower()] = f.name
    return index


def resolve_image_url(url, media_index):
    """Resolve a WP image URL to a local media filename (original, no size variants).

    Returns the local filename or None if not found. Only matches exact filenames
    (after stripping -NNNxNNN size suffixes and trying a -scaled variant); never
    falls back across extensions, since two unrelated files can share a base name.
    """
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if not filename:
        return None

    base, ext = os.path.splitext(filename)
    original_base = re.sub(r"-\d+x\d+$", "", base)

    for candidate in (original_base + ext, original_base + "-scaled" + ext):
        hit = media_index.get(candidate.lower())
        if hit:
            return hit

    return None


class WPMarkdownConverter(MarkdownConverter):
    """Custom markdownify converter for WordPress content."""

    def __init__(self, media_index, referenced_images, unresolved, **kwargs):
        self.media_index = media_index
        self.referenced_images = referenced_images
        self.unresolved = unresolved
        super().__init__(**kwargs)

    def _render_image(self, src, alt):
        local_file = resolve_image_url(src, self.media_index)
        if local_file:
            self.referenced_images.add(local_file)
            return f"![{alt}](/images/blog/{local_file})"
        if src:
            self.unresolved.append(src)
        return f"![{alt}]({src})"

    def convert_figure(self, el, text, parent_tags):
        classes = el.get("class", [])

        # Galleries wrap multiple inner figures; keep the children's markdown
        # instead of collapsing to the first <img> descendant.
        if "wp-block-gallery" in classes:
            return f"\n\n{text}\n\n"

        # Handle pullquotes
        blockquote = el.find("blockquote")
        if blockquote and "wp-block-pullquote" in classes:
            inner = blockquote.get_text(separator="\n", strip=True)
            lines = inner.strip().splitlines()
            quoted = "\n".join(f"> {line}" for line in lines if line.strip())
            return f"\n\n{quoted}\n\n"

        # Handle embeds (Vimeo etc.)
        embed_wrapper = el.find("div", class_="wp-block-embed__wrapper")
        if embed_wrapper:
            url = embed_wrapper.get_text(strip=True)
            if url:
                return f"\n\n{url}\n\n"

        # Handle images
        img = el.find("img")
        if img:
            return f"\n\n{self._render_image(img.get('src', ''), img.get('alt', ''))}\n\n"

        # Handle figcaption or other figure content
        return f"\n\n{text}\n\n"

    def convert_img(self, el, text, parent_tags):
        return self._render_image(el.get("src", ""), el.get("alt", ""))


def preprocess_html(html, drop_href_patterns=(), drop_class_patterns=()):
    """Strip WordPress block comments and project-configured junk HTML before conversion.

    `drop_href_patterns` removes any <a> (and its enclosing <figure>) whose href
    matches the regex; `drop_class_patterns` removes any <div> whose class string
    matches. Both default to empty — they are project-specific filters.
    """
    # Strip WP block comments
    html = re.sub(r"<!--\s*/?wp:\S+.*?-->\s*", "", html, flags=re.DOTALL)
    # Strip <!--more--> tags
    html = re.sub(r"<!--more-->\s*", "", html)

    soup = BeautifulSoup(html, "html.parser")

    for pattern in drop_href_patterns:
        rx = re.compile(pattern)
        for a_tag in soup.find_all("a", href=rx):
            figure = a_tag.find_parent("figure")
            if figure:
                figure.decompose()
            else:
                a_tag.decompose()

    # Strip inline style spans (copy-paste artifacts)
    for span in soup.find_all("span", style=True):
        span.unwrap()

    for pattern in drop_class_patterns:
        rx = re.compile(pattern)
        for div in soup.find_all("div", class_=rx):
            div.decompose()

    return str(soup)


def convert_html_to_markdown(
    html, media_index, referenced_images, unresolved, config
):
    """Convert WordPress HTML content to clean markdown."""
    html = preprocess_html(
        html,
        drop_href_patterns=getattr(config, "PREPROCESS_DROP_HREFS", ()),
        drop_class_patterns=getattr(config, "PREPROCESS_DROP_CLASSES", ()),
    )
    converter = WPMarkdownConverter(
        media_index=media_index,
        referenced_images=referenced_images,
        unresolved=unresolved,
        heading_style="atx",
        bullets="-",
        strong_em_symbol="*",
    )
    md = converter.convert(html)

    # Post-process
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    md = md.strip()

    return md


_SKIP_BLOCK_PREFIXES = ("#", "!", ">", "-", "*", "1.", "```", "<", "|")


def _strip_markdown_formatting(text):
    """Best-effort strip of inline markdown formatting for description previews."""
    # Inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Links / images: keep the visible text
    text = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Bold+italic / bold / italic with asterisks (paired, non-greedy)
    text = re.sub(r"\*{1,3}([^*\n]+?)\*{1,3}", r"\1", text)
    # Underscore emphasis only when not adjacent to word chars on both sides
    # (so `some_var` is left alone but `_word_` becomes `word`).
    text = re.sub(r"(?<!\w)_{1,2}([^_\n]+?)_{1,2}(?!\w)", r"\1", text)
    return text


def generate_description(markdown_content):
    """Generate a description from the first prose paragraph of markdown content."""
    in_fence = False
    for block in markdown_content.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            # Toggle fence state; skip the fenced block itself.
            in_fence = not in_fence
            if stripped.count("```") >= 2:
                in_fence = False
            continue
        if in_fence:
            continue
        if stripped.startswith(_SKIP_BLOCK_PREFIXES):
            continue
        desc = _strip_markdown_formatting(stripped).replace("\n", " ").strip()
        desc = re.sub(r"\s+", " ", desc)
        if not desc:
            continue
        if len(desc) > 160:
            desc = desc[:157].rsplit(" ", 1)[0] + "..."
        return desc
    return ""


def escape_yaml(s):
    """Escape a string for use in a single-line, double-quoted YAML value.

    Collapses any internal newline/tab/etc. to a single space, then strips other
    C0 control characters, then escapes backslash and double-quote.
    """
    if s is None:
        return ""
    s = re.sub(r"[\r\n\t\v\f]+", " ", s)
    s = re.sub(r"[\x00-\x1f\x7f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace("\\", "\\\\").replace('"', '\\"')


def parse_wxr(wxr_files, media_index, config, post_types=("post",)):
    """Parse all WXR files in a single pass.

    Returns (items, attachment_map). `items` is filtered to the requested
    post_types; `attachment_map` is a dict of attachment post_id -> URL across
    all files (built in the same pass so we don't parse the XML twice).
    """
    fallback_category = getattr(config, "CATEGORY_FALLBACK", "General")

    raw_items = []
    attachment_map = {}

    for xml_path in wxr_files:
        tree = ET.parse(str(xml_path))
        channel = tree.getroot().find("channel")
        if channel is None:
            continue

        for item in channel.findall("item"):
            post_type = xml_text(item, "wp:post_type")

            if post_type == "attachment":
                pid = xml_text(item, "wp:post_id")
                url = xml_text(item, "wp:attachment_url")
                if pid and url:
                    attachment_map[pid] = url
                continue

            if post_type not in post_types:
                continue

            raw_items.append(item)

    items = []
    for item in raw_items:
        post_type = xml_text(item, "wp:post_type")
        status = xml_text(item, "wp:status")
        if status in ("trash", "auto-draft"):
            continue

        post_date = xml_text(item, "wp:post_date")
        excerpt = xml_text(item, "excerpt:encoded")

        categories = [
            (c.text or "").strip()
            for c in item.findall('category[@domain="category"]')
            if c.text and c.text.strip()
        ]
        if not categories:
            categories = [fallback_category]

        thumbnail_id = None
        for meta in item.findall("wp:postmeta", NS):
            if xml_text(meta, "wp:meta_key") == "_thumbnail_id":
                thumbnail_id = xml_text(meta, "wp:meta_value") or None
                break

        featured_image = None
        if thumbnail_id and thumbnail_id in attachment_map:
            featured_image = resolve_image_url(
                attachment_map[thumbnail_id], media_index
            )

        items.append({
            "type": post_type,
            "title": xml_text(item, "title"),
            "slug": xml_text(item, "wp:post_name"),
            "date": post_date[:10] if post_date else "",
            "creator": xml_text(item, "dc:creator"),
            "status": status,
            "content": xml_text(item, "content:encoded"),
            "excerpt": excerpt.strip(),
            "categories": categories,
            "featured_image": featured_image,
            "featured_thumbnail_id": thumbnail_id,
        })

    return items, attachment_map


def get_author(post, config):
    """Get author info for a post from project config.

    Lookup order: per-slug override -> WP creator login -> default.
    """
    slug = post["slug"]
    creator = post.get("creator", "")
    by_login = getattr(config, "AUTHOR_BY_LOGIN", {})
    author_key = (
        config.AUTHOR_OVERRIDES.get(slug)
        or by_login.get(creator)
        or config.DEFAULT_AUTHOR
    )
    return config.AUTHORS[author_key]


def _yaml_list(values):
    """Render a list of strings as an inline YAML flow sequence."""
    quoted = ", ".join(f'"{escape_yaml(v)}"' for v in values)
    return f"[{quoted}]"


def write_post(post, markdown_content, output_dir, config):
    """Write a single post as an Astro-compatible markdown file."""
    author = get_author(post, config)
    description = (
        post["excerpt"] if post["excerpt"] else generate_description(markdown_content)
    )
    draft = "true" if post["status"] != "publish" else "false"

    featured = post.get("featured_image", "")
    featured_line = (
        f'\nfeaturedImage: "/images/blog/{featured}"' if featured else ""
    )

    categories = post.get("categories") or [getattr(config, "CATEGORY_FALLBACK", "General")]

    frontmatter = f"""---
title: "{escape_yaml(post['title'])}"
slug: "{post['slug']}"
date: "{post['date']}"
author: "{author['name']}"
authorEmail: "{author['email']}"
authorBio: "{escape_yaml(author['bio'])}"
category: "{escape_yaml(categories[0])}"
categories: {_yaml_list(categories)}
description: "{escape_yaml(description)}"{featured_line}
draft: {draft}
---"""

    filepath = output_dir / f"{post['slug']}.md"
    filepath.write_text(frontmatter + "\n\n" + markdown_content + "\n", encoding="utf-8")
    return filepath


def write_page(page, markdown_content, output_dir):
    """Write a single page as an Astro-compatible markdown file (no author/category/date)."""
    description = (
        page["excerpt"] if page["excerpt"] else generate_description(markdown_content)
    )
    draft = "true" if page["status"] != "publish" else "false"

    frontmatter = f"""---
title: "{escape_yaml(page['title'])}"
slug: "{page['slug']}"
description: "{escape_yaml(description)}"
draft: {draft}
---"""

    filepath = output_dir / f"{page['slug']}.md"
    filepath.write_text(frontmatter + "\n\n" + markdown_content + "\n", encoding="utf-8")
    return filepath


def main(project_name):
    project_dir, wxr_files, media_dir, config = load_project(project_name)
    output_posts = project_dir / "output" / "posts"
    output_pages = project_dir / "output" / "pages"
    output_images = project_dir / "output" / "images"
    output_posts.mkdir(parents=True, exist_ok=True)
    output_pages.mkdir(parents=True, exist_ok=True)
    output_images.mkdir(parents=True, exist_ok=True)

    media_index = build_media_index(media_dir)
    print(f"Media index: {len(media_index)} files in {media_dir.name}")

    items, attachment_map = parse_wxr(
        wxr_files, media_index, config, post_types=("post", "page")
    )
    print(
        f"Attachment map: {len(attachment_map)} attachments across {len(wxr_files)} WXR file(s)"
    )

    posts = [i for i in items if i["type"] == "post"]
    pages = [i for i in items if i["type"] == "page"]
    print(f"Parsed: {len(posts)} posts, {len(pages)} pages from WXR")

    referenced_images = set()
    warnings = []
    author_counts = {}

    source_url_pattern = getattr(config, "SOURCE_URL_PATTERN", None)

    def scan_unresolved(item):
        if not source_url_pattern:
            return
        for match in re.finditer(source_url_pattern, item["content"], re.IGNORECASE):
            url = match.group(0)
            if resolve_image_url(url, media_index) is None:
                warnings.append(f"  Unresolved image in '{item['slug']}': {url}")

    def convert_one(item):
        unresolved = []
        markdown_content = convert_html_to_markdown(
            item["content"], media_index, referenced_images, unresolved, config
        )
        for url in unresolved:
            warnings.append(f"  Unresolved image in '{item['slug']}': {url}")
        if item.get("featured_image"):
            referenced_images.add(item["featured_image"])
        elif item.get("featured_thumbnail_id"):
            warnings.append(
                f"  Featured image for '{item['slug']}' "
                f"(thumbnail id {item['featured_thumbnail_id']}) could not be resolved"
            )
        return markdown_content

    for post in posts:
        markdown_content = convert_one(post)
        write_post(post, markdown_content, output_posts, config)

        author = get_author(post, config)
        author_counts[author["name"]] = author_counts.get(author["name"], 0) + 1

        scan_unresolved(post)

        draft_marker = " [DRAFT]" if post["status"] != "publish" else ""
        print(f"  Converted post: {post['slug']}{draft_marker}")

    for page in pages:
        markdown_content = convert_one(page)
        write_page(page, markdown_content, output_pages)
        scan_unresolved(page)

        draft_marker = " [DRAFT]" if page["status"] != "publish" else ""
        print(f"  Converted page: {page['slug']}{draft_marker}")

    copied = 0
    for img_name in sorted(referenced_images):
        src = media_dir / img_name
        dst = output_images / img_name
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1
        else:
            warnings.append(f"  Referenced image not found on disk: {img_name}")

    print("\n--- Summary ---")
    draft_posts = sum(1 for p in posts if p["status"] != "publish")
    draft_pages = sum(1 for p in pages if p["status"] != "publish")
    print(f"Posts converted: {len(posts)} ({draft_posts} drafts)")
    print(f"Pages converted: {len(pages)} ({draft_pages} drafts)")
    print(f"Images copied: {copied} / {len(media_index)} available")
    print("\nPosts per author:")
    for name, count in sorted(author_counts.items()):
        print(f"  {name}: {count}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(w)
    else:
        print("\nNo warnings.")

    print("\n--- Renaming images ---")
    rename_images(project_dir, config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a WordPress WXR export to Astro markdown."
    )
    parser.add_argument("project", help="Project name (folder under projects/)")
    args = parser.parse_args()
    main(args.project)
