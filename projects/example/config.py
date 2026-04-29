"""Example project config.

Copy this folder to `projects/<your-site>/`, drop your WXR export and media
folder into `source/`, then edit the values below to match your site.

Run with:  python convert.py <your-site>
"""

# Map of author key -> {name, email, bio}. Reference these keys from
# AUTHOR_BY_LOGIN, AUTHOR_OVERRIDES, and DEFAULT_AUTHOR below.
AUTHORS = {
    "jane": {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "bio": "Jane writes about web performance and developer tooling.",
    },
    "john": {
        "name": "John Smith",
        "email": "john@example.com",
        "bio": "John leads engineering at Example Co.",
    },
}

# Used when no override or login match is found.
DEFAULT_AUTHOR = "jane"

# Map WP login (the value in <dc:creator>) -> author key.
# Find these by grepping `<dc:creator>` inside your WXR file.
AUTHOR_BY_LOGIN = {
    "janedoe": "jane",
    "jsmith": "john",
}

# Per-slug overrides. Win over AUTHOR_BY_LOGIN when set.
# Useful for guest posts where the WP author isn't the real author.
AUTHOR_OVERRIDES = {
    # "guest-post-slug": "jane",
}

# Regex used to flag image URLs in the source HTML that didn't resolve to a
# local file. Set to your old WP domain so you can spot images that need
# manual download. Set to None to disable the warning.
SOURCE_URL_PATTERN = (
    r"https?://[^\"'>\s]*example\.com[^\"'>\s]*\.(?:jpe?g|png|gif|webp|avif)"
)

# Fallback category for posts that have no <category domain="category"> entries.
CATEGORY_FALLBACK = "General"

# Per-project HTML preprocessing filters. Each entry is a regex.
#
# PREPROCESS_DROP_HREFS: any <a> whose href matches is removed (along with its
#   enclosing <figure>, if any). Useful for stripping CTA banners.
# PREPROCESS_DROP_CLASSES: any <div> whose class string matches is removed.
#   Useful for stripping accidentally-pasted UI fragments.
#
# Both default to empty. Be careful with class regexes — `flex` will match
# `inline-flex`, `flex-row`, etc.
PREPROCESS_DROP_HREFS = (
    # r"subscribe-modal",
)
PREPROCESS_DROP_CLASSES = (
    # r"^(mt-\d+|gap-\d+)$",
)

# Per-image rename hints used by rename_images.py.
# Keys are (original_filename, post_slug). Values become the descriptive
# suffix in the renamed file: <slug>-<description>.<ext>
#
# Example: ("DSC_1234.jpg", "my-post") -> "my-post-team-photo.jpg"
#
# Generating these by hand is tedious — we let Claude Code skim each post and
# suggest descriptions. See the README for the prompt we use.
CONTENT_DESCRIPTIONS = {
    # ("DSC_1234.jpg", "my-post"): "team-photo",
}
