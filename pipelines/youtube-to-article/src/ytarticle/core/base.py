"""Component base class — every component must implement this."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from ytarticle.core.schema import ContentItem


class ComponentError(Exception):
    """Raised when a component encounters a non-recoverable error."""


class BaseComponent(ABC):
    """Base class for pipeline components.

    Subclass and implement:
        name: str
        version: str
        run(item, config) -> ContentItem
    """

    name: str = "unnamed"
    version: str = "1.0.0"
    required_fields: list[str] = []
    output_fields: list[str] = []

    @abstractmethod
    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        ...

    def validate_input(self, item: ContentItem) -> list[str]:
        """Return list of missing required fields."""
        return [f for f in self.required_fields
                if not getattr(item, f, None)]

    def validate_output(self, item: ContentItem) -> list[str]:
        """Return list of missing output fields."""
        return [f for f in self.output_fields
                if not getattr(item, f, None)]
