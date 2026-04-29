#!/usr/bin/env python3
"""Rename blog images to standardized {slug}-{description}.{ext} format.

Usage: python rename_images.py <project_name>

Operates on projects/<project_name>/output/posts and .../output/images.
Per-project rename map (CONTENT_DESCRIPTIONS) lives in projects/<project_name>/config.py.
"""

import argparse
import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def load_project(name):
    project_dir = BASE_DIR / "projects" / name
    if not project_dir.is_dir():
        sys.exit(f"Project not found: {project_dir}")

    config_path = project_dir / "config.py"
    if not config_path.exists():
        sys.exit(f"Missing config.py in {project_dir}")
    spec = importlib.util.spec_from_file_location(f"_project_{name}", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

    return project_dir, config


def rename_images(project_dir, config):
    posts_dir = project_dir / "output" / "posts"
    images_dir = project_dir / "output" / "images"

    if not posts_dir.is_dir():
        sys.exit(f"Missing posts dir: {posts_dir}. Run convert.py first.")
    if not images_dir.is_dir():
        sys.exit(f"Missing images dir: {images_dir}. Run convert.py first.")

    content_descriptions = config.CONTENT_DESCRIPTIONS

    post_renames = {}  # (slug, old_filename) -> new_filename
    unmapped_counter = {}  # slug -> running int for `-image-N` suffix

    for fname in sorted(os.listdir(posts_dir)):
        if not fname.endswith(".md"):
            continue
        slug = fname[:-3]
        filepath = posts_dir / fname
        text = filepath.read_text()

        # Featured image
        m = re.search(r'featuredImage: "/images/blog/(.+?)"', text)
        if m:
            old = m.group(1)
            ext = os.path.splitext(old)[1]
            new = f"{slug}-cover{ext}"
            post_renames[(slug, old)] = new

        # Content images
        for m in re.finditer(r"!\[([^\]]*)\]\(/images/blog/(.+?)\)", text):
            old = m.group(2)
            ext = os.path.splitext(old)[1]
            key = (slug, old)
            if key in post_renames:
                continue  # same file referenced multiple times in one post
            desc = content_descriptions.get((old, slug))
            if desc:
                new = f"{slug}-{desc}{ext}"
            else:
                print(f"WARNING: no description for content image {old} in {slug}")
                unmapped_counter[slug] = unmapped_counter.get(slug, 0) + 1
                new = f"{slug}-image-{unmapped_counter[slug]}{ext}"
            post_renames[key] = new

    # Copy files with new names
    copied = set()
    for (slug, old), new in sorted(post_renames.items()):
        src = images_dir / old
        dst = images_dir / new
        if src.exists() and new not in copied:
            shutil.copy2(src, dst)
            copied.add(new)
            print(f"  {old} -> {new}")

    # Update markdown files
    for fname in sorted(os.listdir(posts_dir)):
        if not fname.endswith(".md"):
            continue
        slug = fname[:-3]
        filepath = posts_dir / fname
        text = filepath.read_text()
        original = text

        for (s, old), new in post_renames.items():
            if s != slug:
                continue
            text = text.replace(f"/images/blog/{old}", f"/images/blog/{new}")

        if text != original:
            filepath.write_text(text)

    # Remove old files that have been renamed
    old_files = set()
    new_files = set()
    for (slug, old), new in post_renames.items():
        old_files.add(old)
        new_files.add(new)

    for old in old_files - new_files:
        path = images_dir / old
        if path.exists():
            path.unlink()
            print(f"  Removed: {old}")

    print(
        f"\nDone. {len(copied)} images renamed, "
        f"{len(old_files - new_files)} old files removed."
    )
    print(f"Total images now: {len(list(images_dir.iterdir()))}")


def main(project_name):
    project_dir, config = load_project(project_name)
    rename_images(project_dir, config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Standardize image filenames for an Astro project."
    )
    parser.add_argument("project", help="Project name (folder under projects/)")
    args = parser.parse_args()
    main(args.project)
