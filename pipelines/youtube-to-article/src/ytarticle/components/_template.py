"""Template for new components."""
from __future__ import annotations
from typing import Any
from ytarticle.core.base import BaseComponent, ComponentError
from ytarticle.core.schema import ContentItem


class TemplateComponent(BaseComponent):
    name = "template"
    version = "1.0.0"
    required_fields: list[str] = []
    output_fields: list[str] = []

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        return item


def create():
    return TemplateComponent()
