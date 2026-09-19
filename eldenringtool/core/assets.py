from __future__ import annotations

from pathlib import Path


def marker_icon_name(assets_root: Path, icon: object) -> str:
    """Return a QML-relative path below ``assets/icons`` for a marker icon.

    Game-extracted icons use numeric IDs and live directly under ``icons/``.
    Built-in category icons use filenames and live under ``icons/categories/``.
    Older/generated corpora may already contain a relative subpath; preserve it
    after normalising separators and rejecting traversal/absolute paths.
    """
    if icon is None or isinstance(icon, bool):
        return ""

    if isinstance(icon, int):
        name = f"{icon}.png"
    elif isinstance(icon, float):
        if not icon.is_integer():
            return ""
        name = f"{int(icon)}.png"
    else:
        name = str(icon).strip().replace("\\", "/")
        if not name:
            return ""
        if not name.lower().endswith(".png"):
            name += ".png"

    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        return ""
    name = rel.as_posix().lstrip("/")

    icons = Path(assets_root) / "icons"
    if "/" in name:
        return name if (icons / name).is_file() else ""
    if (icons / name).is_file():
        return name
    category = icons / "categories" / name
    if category.is_file():
        return f"categories/{name}"
    return ""
