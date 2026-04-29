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

    Returns the local filename or None if not found.
    """
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if not filename:
        return None

    # Strip size variant suffix: -NNNxNNN before extension
    base, ext = os.path.splitext(filename)
    original_base = re.sub(r"-\d+x\d+$", "", base)
    original_filename = original_base + ext

    # Try direct match
    key = original_filename.lower()
    if key in media_index:
        return media_index[key]

    # Try with -scaled suffix
    scaled_filename = original_base + "-scaled" + ext
    key = scaled_filename.lower()
    if key in media_index:
        return media_index[key]

    # Try alternative extensions
    alt_exts = [".jpg", ".jpeg", ".png", ".avif", ".webp"]
    for alt_ext in alt_exts:
        if alt_ext == ext.lower():
            continue
        key = (original_base + alt_ext).lower()
        if key in media_index:
            return media_index[key]
        key = (original_base + "-scaled" + alt_ext).lower()
        if key in media_index:
            return media_index[key]

    return None


class WPMarkdownConverter(MarkdownConverter):
    """Custom markdownify converter for WordPress content."""

    def __init__(self, media_index, referenced_images, **kwargs):
        self.media_index = media_index
        self.referenced_images = referenced_images
        super().__init__(**kwargs)

    def convert_figure(self, el, text, parent_tags):
        classes = el.get("class", [])

        # Galleries wrap multiple inner figures; keep the children's markdown
        # instead of collapsing to the first <img> descendant.
        if "wp-block-gallery" in classes:
            return f"\n\n{text}\n\n"

        # Handle pullquotes
        blockquote = el.find("blockquote")
        if blockquote and "wp-block-pullquote" in el.get("class", []):
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
            src = img.get("src", "")
            alt = img.get("alt", "")
            local_file = resolve_image_url(src, self.media_index)
            if local_file:
                self.referenced_images.add(local_file)
                return f"\n\n![{alt}](/images/blog/{local_file})\n\n"
            else:
                return f"\n\n![{alt}]({src})\n\n"

        # Handle figcaption or other figure content
        return f"\n\n{text}\n\n"

    def convert_img(self, el, text, parent_tags):
        src = el.get("src", "")
        alt = el.get("alt", "")
        local_file = resolve_image_url(src, self.media_index)
        if local_file:
            self.referenced_images.add(local_file)
            return f"![{alt}](/images/blog/{local_file})"
        return f"![{alt}]({src})"


def preprocess_html(html):
    """Strip WordPress block comments, CTA banners, and junk HTML before conversion."""
    # Strip WP block comments
    html = re.sub(r"<!--\s*/?wp:\S+.*?-->\s*", "", html, flags=re.DOTALL)
    # Strip <!--more--> tags
    html = re.sub(r"<!--more-->\s*", "", html)

    # Strip CTA banner figures (images linking to subscribe-modal)
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=re.compile(r"subscribe-modal")):
        figure = a_tag.find_parent("figure")
        if figure:
            figure.decompose()
        else:
            a_tag.decompose()

    # Strip inline style spans (copy-paste artifacts)
    for span in soup.find_all("span", style=True):
        span.unwrap()

    # Strip ChatGPT UI junk (divs with tailwind classes pasted in)
    for div in soup.find_all("div", class_=re.compile(r"mt-\d|flex|gap-\d")):
        div.decompose()

    return str(soup)


def convert_html_to_markdown(html, media_index, referenced_images):
    """Convert WordPress HTML content to clean markdown."""
    html = preprocess_html(html)
    converter = WPMarkdownConverter(
        media_index=media_index,
        referenced_images=referenced_images,
        heading_style="atx",
        bullets="-",
        strong_em_symbol="*",
        strip=["span"],
    )
    md = converter.convert(html)

    # Post-process
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    md = md.strip()

    return md


def generate_description(markdown_content):
    """Generate a description from the first paragraph of markdown content."""
    for block in markdown_content.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith(("#", "!", ">", "-", "1.")):
            continue
        desc = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", block)
        desc = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", desc)
        desc = desc.replace("\n", " ")
        if len(desc) > 160:
            desc = desc[:157].rsplit(" ", 1)[0] + "..."
        return desc
    return ""


def escape_yaml(s):
    """Escape a string for use in double-quoted YAML values."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_attachment_map(wxr_files):
    """Build a map of attachment post ID -> URL across all WXR files."""
    attachments = {}
    for xml_path in wxr_files:
        tree = ET.parse(str(xml_path))
        channel = tree.getroot().find("channel")
        for item in channel.findall("item"):
            pt = item.find("wp:post_type", NS)
            if pt is not None and pt.text == "attachment":
                pid = item.find("wp:post_id", NS).text
                url = item.find("wp:attachment_url", NS)
                if url is not None:
                    attachments[pid] = url.text
    return attachments


def parse_items(wxr_files, attachment_map, media_index, post_types=("post",)):
    """Parse all WXR files and return a list of item dicts for the given post_types."""
    items = []
    for xml_path in wxr_files:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        channel = root.find("channel")

        for item in channel.findall("item"):
            post_type_el = item.find("wp:post_type", NS)
            if post_type_el is None or post_type_el.text not in post_types:
                continue

            title = item.find("title").text or ""
            slug = item.find("wp:post_name", NS).text or ""
            post_date = item.find("wp:post_date", NS).text or ""
            date = post_date[:10] if post_date else ""
            creator = item.find("dc:creator", NS).text or ""
            status = item.find("wp:status", NS).text or ""
            content = item.find("content:encoded", NS).text or ""
            excerpt = item.find("excerpt:encoded", NS).text or ""

            # Skip trashed items
            if status == "trash":
                continue

            cat_el = item.find('category[@domain="category"]')
            category = cat_el.text if cat_el is not None else "General"

            thumbnail_id = None
            featured_image = None
            for meta in item.findall("wp:postmeta", NS):
                key = meta.find("wp:meta_key", NS)
                if key is not None and key.text == "_thumbnail_id":
                    val = meta.find("wp:meta_value", NS)
                    if val is not None:
                        thumbnail_id = val.text

            if thumbnail_id and thumbnail_id in attachment_map:
                featured_image = resolve_image_url(
                    attachment_map[thumbnail_id], media_index
                )

            items.append({
                "type": post_type_el.text,
                "title": title,
                "slug": slug,
                "date": date,
                "creator": creator,
                "status": status,
                "content": content,
                "excerpt": excerpt.strip() if excerpt else "",
                "category": category,
                "featured_image": featured_image,
            })

    return items


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

    frontmatter = f"""---
title: "{escape_yaml(post['title'])}"
slug: "{post['slug']}"
date: "{post['date']}"
author: "{author['name']}"
authorEmail: "{author['email']}"
authorBio: "{escape_yaml(author['bio'])}"
category: "{escape_yaml(post['category'])}"
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
    attachment_map = build_attachment_map(wxr_files)
    print(
        f"Attachment map: {len(attachment_map)} attachments across {len(wxr_files)} WXR file(s)"
    )

    items = parse_items(wxr_files, attachment_map, media_index, post_types=("post", "page"))
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
            url = re.sub(r'["\'>].*$', "", url)
            if resolve_image_url(url, media_index) is None:
                warnings.append(f"  Unresolved image in '{item['slug']}': {url}")

    for post in posts:
        markdown_content = convert_html_to_markdown(
            post["content"], media_index, referenced_images
        )

        if post.get("featured_image"):
            referenced_images.add(post["featured_image"])

        write_post(post, markdown_content, output_posts, config)

        author = get_author(post, config)
        author_counts[author["name"]] = author_counts.get(author["name"], 0) + 1

        scan_unresolved(post)

        draft_marker = " [DRAFT]" if post["status"] != "publish" else ""
        print(f"  Converted post: {post['slug']}{draft_marker}")

    for page in pages:
        markdown_content = convert_html_to_markdown(
            page["content"], media_index, referenced_images
        )

        if page.get("featured_image"):
            referenced_images.add(page["featured_image"])

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
