"""Template loader — find and load the right template."""
from __future__ import annotations
from pathlib import Path
from typing import Optional


BUILTIN_TEMPLATES = {
    "default": "default/article.html",
    "diyhub": "diyhub/article.html",
}


def resolve_template(name: str = "default",
                     custom_dirs: Optional[list[str]] = None) -> tuple[Path, str]:
    """Resolve template path and name. Returns (template_dir, template_name)."""
    template_name = BUILTIN_TEMPLATES.get(name, name)

    if custom_dirs:
        for d in custom_dirs:
            p = Path(d)
            if (p / template_name).exists():
                return p, template_name

    pkg_dir = Path(__file__).resolve().parent
    return pkg_dir, template_name


def list_templates() -> list[str]:
    return list(BUILTIN_TEMPLATES.keys())
