"""Localized route notes, with source-checked translations kept across rescans."""
from __future__ import annotations

from hashlib import sha256

from .quest_engine import local_text


def source_key(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def tip_text(tip, translations=None, locale="zh") -> str:
    if not isinstance(tip, dict):
        return ""
    texts = tip.get("texts") or {}
    if isinstance(texts, dict) and texts.get(locale):
        return str(texts[locale])
    original = tip.get("text") or ""
    if isinstance(original, dict):
        return local_text(original, locale)
    translated = (translations or {}).get(source_key(str(original)), {})
    if isinstance(translated, dict) and translated.get(locale):
        return str(translated[locale])
    return str(original)
