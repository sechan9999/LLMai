"""
Skill helpers — derived from frequently-recalled knowledge facts.

A "skill" in llmai is a stable piece of reusable context that gets
auto-injected into every new session in the same workspace. Skills are
created automatically when a knowledge fact crosses a recall-count
threshold (see ``MemoryStore.recall`` and ``_promote_if_eligible``).

This module provides:
  - ``slugify_skill_name``  derive a short slug from the first words of
                            a fact text
  - ``format_skills_message`` build the system message that's injected
                              into the agent at session start
"""
from __future__ import annotations

import re
from typing import Iterable

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "for", "in", "on",
    "at", "by", "is", "are", "was", "were", "be", "been", "being",
    "with", "as", "this", "that", "these", "those", "it", "its", "we",
    "our", "you", "your", "they", "them", "their",
})

_NAME_MAX = 32


def slugify_skill_name(text: str, *, max_len: int = _NAME_MAX) -> str:
    """Build a short, kebab-case slug from the first meaningful words.

    Drops stopwords, keeps alphanumerics and dashes, caps at ``max_len``.
    Falls back to ``"skill"`` for empty / all-stopword input.
    """
    if not text:
        return "skill"
    # Lowercase, split into alphanumeric runs
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    keep = [w for w in words if w not in _STOPWORDS] or words
    slug = "-".join(keep[:5])
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "skill"


def format_skills_message(skills: Iterable[dict]) -> str:
    """Render a system-message block listing active skills.

    Returns an empty string if ``skills`` is empty so callers can skip
    insertion. Each skill rendered as ``• name: content``.
    """
    lines: list[str] = []
    for s in skills:
        name = (s.get("name") or "").strip() or "skill"
        content = (s.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"• {name}: {content}")
    if not lines:
        return ""
    return "[Active skills for this workspace]\n" + "\n".join(lines)
