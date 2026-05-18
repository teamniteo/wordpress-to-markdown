#!/usr/bin/env python3
"""Rename blog images to standardized {slug}-{description}.{ext} format.

Usage: python rename_images.py <project_name>

Operates on projects/<project_name>/output/posts and .../output/images.
Per-project rename map (CONTENT_DESCRIPTIONS) lives in projects/<project_name>/config.py.

Re-runnable: a sidecar `output/.rename_map.json` records each renamed file's
*original* filename, so subsequent runs can resolve current markdown filenames
back to their CONTENT_DESCRIPTIONS keys after the user adds entries.
"""

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

RENAME_MAP_FILE = ".rename_map.json"


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


def _load_rename_map(output_dir):
    """Load `current_filename -> original_filename` from sidecar, if any."""
    path = output_dir / RENAME_MAP_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_rename_map(output_dir, mapping):
    path = output_dir / RENAME_MAP_FILE
    path.write_text(
        json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8"
    )


def rename_images(project_dir, config):
    output_dir = project_dir / "output"
    posts_dir = output_dir / "posts"
    images_dir = output_dir / "images"

    if not posts_dir.is_dir():
        sys.exit(f"Missing posts dir: {posts_dir}. Run convert.py first.")
    if not images_dir.is_dir():
        sys.exit(f"Missing images dir: {images_dir}. Run convert.py first.")

    content_descriptions = config.CONTENT_DESCRIPTIONS

    # current_filename_in_md -> original_filename (from previous run)
    existing = _load_rename_map(output_dir)

    def to_original(current):
        return existing.get(current, current)

    md_files = sorted(posts_dir.glob("*.md"))

    # Pass 1: scan every post and group references by current filename so we
    # can detect images shared across multiple posts.
    # current -> list of (slug, kind) where kind is "featured" | "content"
    usage = {}
    for filepath in md_files:
        slug = filepath.stem
        text = filepath.read_text(encoding="utf-8")

        m = re.search(r'featuredImage: "/images/blog/(.+?)"', text)
        if m:
            usage.setdefault(m.group(1), []).append((slug, "featured"))

        for m in re.finditer(r"!\[([^\]]*)\]\(/images/blog/(.+?)\)", text):
            usage.setdefault(m.group(2), []).append((slug, "content"))

    # Pass 2: pick the new filename for each source.
    #   - Shared (used by 2+ distinct posts): keep the original WP filename so
    #     every post references a single physical file. Saves disk and avoids
    #     stale copies when posts evolve independently.
    #   - Single-owner: slug-prefixed (`<slug>-cover.ext` or
    #     `<slug>-<description>.ext` / `<slug>-image-N.ext`).
    post_renames = {}  # (slug, current) -> new
    file_renames = {}  # current -> new
    unmapped_counter = {}

    for current, refs in usage.items():
        original = to_original(current)
        ext = Path(current).suffix
        unique_slugs = {s for s, _ in refs}

        if len(unique_slugs) > 1:
            new = original
            file_renames[current] = new
            for slug, _kind in refs:
                post_renames[(slug, current)] = new
            continue

        for slug, kind in refs:
            key = (slug, current)
            if key in post_renames:
                continue
            if kind == "featured":
                new = f"{slug}-cover{ext}"
            else:
                desc = content_descriptions.get((original, slug))
                if desc:
                    new = f"{slug}-{desc}{ext}"
                else:
                    print(
                        f"WARNING: no description for content image {original} in {slug}"
                    )
                    unmapped_counter[slug] = unmapped_counter.get(slug, 0) + 1
                    new = f"{slug}-image-{unmapped_counter[slug]}{ext}"
            post_renames[key] = new
            file_renames.setdefault(current, new)

    moved = 0
    for current, new in sorted(file_renames.items()):
        if current == new:
            continue
        src = images_dir / current
        dst = images_dir / new
        if not src.exists():
            continue
        if dst.exists():
            src.unlink()
            continue
        shutil.move(str(src), str(dst))
        moved += 1
        print(f"  {current} -> {new}")

    # Update markdown files
    for filepath in md_files:
        slug = filepath.stem
        text = filepath.read_text(encoding="utf-8")
        original_text = text

        for (s, current), new in post_renames.items():
            if s != slug or current == new:
                continue
            text = text.replace(f"/images/blog/{current}", f"/images/blog/{new}")

        if text != original_text:
            filepath.write_text(text, encoding="utf-8")

    # Persist new -> original mapping so future runs can resolve back.
    new_map = {}
    for current, new in file_renames.items():
        original = existing.get(current, current)
        new_map[new] = original
    # Preserve entries for files that weren't touched this run.
    referenced_now = set(file_renames.values()) | set(file_renames.keys())
    for current, original in existing.items():
        if current not in referenced_now:
            new_map.setdefault(current, original)
    _save_rename_map(output_dir, new_map)

    print(
        f"\nDone. {moved} files renamed; "
        f"{len(file_renames)} total references mapped."
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
