.DEFAULT_GOAL := help

.PHONY: help sync check team test test-all install release

help: ## Show available make targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Synchronize all provider configurations
	python3 sync.py

check: ## Verify provider configurations are in sync
	python3 sync.py --check

team: ## Display active provider and team roster
	python3 sync.py --team

test: ## Run focused unit tests
	python3 -m unittest tests/test_sync.py

test-all: ## Run the entire test discovery suite
	python3 -m unittest discover tests

release: ## Cut and publish a new release
	./release.sh
