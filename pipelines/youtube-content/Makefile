.PHONY: install test lint scout scout-youtube scout-tiktok scout-tags scout-tags-youtube account-list account-add account-fetch account-daily-report db-up db-down

install:
	uv sync --all-extras
	uv run alembic upgrade head

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check .
	uv run ruff format --check .

scout:
	uv run python trending_aggregator/cli.py

scout-youtube:
	uv run python trending_aggregator/cli.py --platform youtube

scout-tiktok:
	uv run python trending_aggregator/cli.py --platform tiktok

scout-tags:
	uv run python trending_aggregator/cli.py tags

scout-tags-youtube:
	uv run python trending_aggregator/cli.py --platform youtube tags

account-list:
	uv run python -m trending_aggregator.account_tracker list

account-add:
	uv run python -m trending_aggregator.account_tracker add

account-fetch:
	uv run python -m trending_aggregator.account_tracker fetch --detailed

account-daily-report:
	uv run python -m trending_aggregator.account_tracker daily-report

db-up:
	docker compose up -d

db-down:
	docker compose down
