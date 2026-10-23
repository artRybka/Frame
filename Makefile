.PHONY: setup test lint serve addon ios

setup:
	cd server && uv sync

test:
	cd server && uv run pytest -q

lint:
	cd server && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src

serve:
	cd server && uv run frame serve

addon:
	scripts/bundle-addon.sh

ios:
	cd ios && xcodegen generate && open Frame.xcodeproj
