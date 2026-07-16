"""Component registry — auto-discover and manage components."""
from __future__ import annotations
import importlib
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent


class Registry:
    """Component registry with auto-discovery."""

    def __init__(self):
        self._components: dict[str, BaseComponent] = {}
        self._components_dir = Path(__file__).resolve().parent.parent / "components"

    def register(self, component: BaseComponent) -> None:
        self._components[component.name] = component

    def get(self, name: str) -> BaseComponent:
        if name not in self._components:
            raise KeyError(
                f"Component '{name}' not found. "
                f"Available: {list(self._components.keys())}"
            )
        return self._components[name]

    def has(self, name: str) -> bool:
        return name in self._components

    def list_all(self) -> list[str]:
        return list(self._components.keys())

    def discover(self) -> int:
        """Auto-scan component subdirectories and register."""
        subdirs = ["sources", "processors", "checkers"]
        count = 0
        for subdir in subdirs:
            pkg_dir = self._components_dir / subdir
            if not pkg_dir.is_dir():
                continue
            for py_file in sorted(pkg_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module_name = f"ytarticle.components.{subdir}.{py_file.stem}"
                try:
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, "create"):
                        comp = mod.create()
                        if isinstance(comp, BaseComponent):
                            self.register(comp)
                            count += 1
                except Exception as e:
                    print(f"[registry] Warn: failed to load {module_name}: {e}")
        return count
