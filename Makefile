bun := $(shell command -v bun 2>/dev/null || echo $(HOME)/.bun/bin/bun)
base_repo := receptron/laya-onnx
fallacy_repo := BryanSnappCTO/laya-fallacies-onnx

.PHONY: all install-bun install build typecheck lint test check format format-check download-base download-fallacy download-models run-basic run-debate run-examples clean clean-cache

all: install build check

install-bun:
	@test -x "$(bun)" || curl -fsSL https://bun.sh/install | bash

install: install-bun
	$(bun) install

build:
	$(bun) run build

typecheck:
	$(bun) run typecheck

lint:
	$(bun) run lint

test:
	$(bun) run test

check: typecheck lint test

format:
	$(bun) run format

format-check:
	$(bun) run format:check

download-base:
	$(bun) examples/download-models.ts base

download-fallacy:
	$(bun) examples/download-models.ts fallacy

download-models: download-base download-fallacy

run-basic: download-base
	LAYA_REPO=$(base_repo) $(bun) examples/basic.ts

run-debate: download-fallacy
	LAYA_REPO=$(fallacy_repo) $(bun) examples/debate.ts

run-examples: run-basic run-debate

clean:
	rm -rf dist

clean-cache:
	rm -rf "$${XDG_CACHE_HOME:-$${HOME}/.cache}/receptron-laya"
