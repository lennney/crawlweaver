"""Pipeline engine — config-driven step orchestrator."""
from __future__ import annotations
import logging
import json
import time
from pathlib import Path
from typing import Any

import yaml

from ytarticle.core.schema import ContentItem
from ytarticle.core.base import ComponentError
from ytarticle.core.registry import Registry

logger = logging.getLogger("ytarticle.pipeline")


class Pipeline:
    """Config-driven content pipeline."""

    def __init__(self, config: dict[str, Any] | str | Path):
        if isinstance(config, (str, Path)):
            config = self._load_config(config)
        self.config = config
        self.steps = config.get("steps", [])
        self.max_retries = config.get("max_retries", 2)
        self.registry = Registry()
        self.registry.discover()

    @staticmethod
    def _load_config(path: str | Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run(self, item: ContentItem) -> ContentItem:
        """Run all configured steps."""
        item.mark_running()
        task_id = item.task_id()

        for step_idx, step_conf in enumerate(self.steps):
            comp_name = step_conf.get("component", "")
            comp_config = step_conf.get("config", {})
            step_name = step_conf.get("id", comp_name)

            if not self.registry.has(comp_name):
                item.mark_failed(f"Component '{comp_name}' not found")
                return item

            comp = self.registry.get(comp_name)

            missing = comp.validate_input(item)
            if missing:
                item.mark_failed(f"{comp_name}: missing {missing}")
                return item

            success = False
            last_error = ""
            for attempt in range(self.max_retries + 1):
                try:
                    logger.info(f"[pipeline] Running: {comp_name}"
                                + (f" (attempt {attempt+1})" if attempt > 0 else ""))
                    item = comp.run(item, comp_config)
                    success = True
                    break
                except ComponentError as e:
                    last_error = str(e)
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                except Exception as e:
                    last_error = f"{type(e).__name__}: {e}"
                    logger.warning(f"[pipeline] {comp_name} error: {e}")
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)

            if not success:
                item.mark_failed(f"{comp_name}: {last_error}")
                self._save_state(item)
                return item

            logger.info(f"[pipeline] {comp_name} done")

        item.mark_done()
        self._save_state(item)
        logger.info(f"[pipeline] Done: {task_id}")
        return item

    def _save_state(self, item: ContentItem) -> None:
        """Save pipeline state JSON for export command."""
        output_dir = self.config.get("steps", [{}])[0].get("config", {}).get("output_dir", "output")
        state_dir = Path(output_dir).parent / "state" if "/" in output_dir else Path("output") / "state"
        # ponytail: resolve state dir from first step's output_dir
        for step in self.config.get("steps", []):
            cfg = step.get("config", {})
            if "output_dir" in cfg:
                state_dir = Path(cfg["output_dir"]).parent / "state"
                break
        state_dir.mkdir(parents=True, exist_ok=True)

        state = {
            "title": item.title,
            "source": item.source.value,
            "source_id": item.source_id,
            "source_url": item.source_url,
            "status": item.status,
            "category": item.category,
            "keyword": item.keyword,
            "difficulty": item.difficulty,
            "estimated_time": item.estimated_time,
            "estimated_cost": item.estimated_cost,
            "materials": item.materials,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "seo": {
                "title_tag": item.seo.title_tag,
                "meta_description": item.seo.meta_description,
                "url_slug": item.seo.url_slug,
                "h1": item.seo.h1,
            },
            "artifacts": {
                "html_path": item.artifacts.html_path,
                "article_md": item.artifacts.article_md,
                "images_dir": item.artifacts.images_dir,
                "cover_img": item.artifacts.cover_img,
            },
            "tags": item.tags,
            "error": item.error,
        }
        state_file = state_dir / f"{item.task_id()}.json"
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_from_config(config_path: str, item: ContentItem) -> ContentItem:
    """Convenience: one-liner to run a pipeline."""
    pipe = Pipeline(config_path)
    return pipe.run(item)
