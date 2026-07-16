"""跑全部平台采集 — cli.py 的轻量替代。"""
import logging

from trending_aggregator.orchestrator import run_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

results = run_all()
for platform, count in results.items():
    print(f"  {platform}: {count} 条入库")
