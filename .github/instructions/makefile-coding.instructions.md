---
applyTo: "**/makefile"
---

# Makefile Coding Standards

## Purpose
- In this project, makefiles are workflow orchestrators, not build systems
- actual software builds happen inside dockerfiles
- make provides convenient shortcuts for docker commands, which is better than writing a bunch of shell-scripts

## Core Principles
- lowercase everything: variables, targets, filenames, except where required by the software being invoked
- no comments unless absolutely necessary
- minimal abstraction, each target should be obvious
- `.phony` for all targets (nothing produces files)

## Syntax Style
- variables in lowercase: `image_name := website`
- targets in lowercase: `build:`, `run:`, `push:`
- use `:=` for immediate assignment, `=` only when lazy evaluation needed
- indent recipes with tabs (required by make)

## Variables
```makefile
image_name := website
registry := docker.io/laya-kenya
tag := latest
port := 80
```

## Common Targets
```makefile
.PHONY: build run stop clean push pull logs shell

build:
	docker build -t $(image_name):$(tag) .

run:
	docker run -d --name $(image_name) -p $(port):80 $(image_name):$(tag)

stop:
	docker stop $(image_name) && docker rm $(image_name)

clean:
	docker rmi $(image_name):$(tag)

push:
	docker push $(registry)/$(image_name):$(tag)

pull:
	docker pull $(registry)/$(image_name):$(tag)

logs:
	docker logs -f $(image_name)

shell:
	docker exec -it $(image_name) /bin/sh
```

## Target Naming
- single-word lowercase: `build`, `run`, `push`
- hyphenated for multi-word: `build-dev`, `run-watch`
- group related targets with prefixes: `db-start`, `db-stop`, `db-migrate`

## Dependencies
- chain targets when order matters: `deploy: build push`
- keep chains short and obvious

## Patterns
- `@` prefix suppresses command echo: `@echo "done"`
- use `$(MAKE)` for recursive make calls
- `||` for fallback commands: `docker stop x || true`

## Environment
- read from environment with defaults: `tag ?= latest`
- pass build args: `--build-arg version=$(version)`

## Avoid
- uppercase anything
- complex shell scripting in recipes, use a script file instead (in a script folder)
- file-based targets (everything is .PHONY)
- tab/space mixing (use tabs, not spaces, for recipe indentation)
- deeply nested variable references
