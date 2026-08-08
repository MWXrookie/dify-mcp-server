"""Allowlisted, deterministic library adapters for the safe server."""

from slugify import slugify


def slugify_text(text: str) -> str:
    """Convert text to a URL-safe slug using the pinned python-slugify package."""
    if len(text) > 4000:
        raise ValueError("text is limited to 4000 characters")
    return slugify(text)


ALLOWED_TOOLS = {
    "slugify_text": slugify_text,
}
