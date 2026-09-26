---
applyTo: "**/dockerfile,**/*.dockerfile"
---

# Dockerfile Coding Standards

## Core Principles
- lowercase everything: commands, variables, labels, stage names
- no comments, dockerfiles are self-documenting
- minimal layers, maximum clarity
- multi-stage builds for images

## Syntax Style
- commands in lowercase: `from`, `run`, `copy`, `workdir`, `env`, `arg`, `expose`, `cmd`, `entrypoint`, etc.
- variables in lowercase: `arg version=1.0`, etc. Except where uppercase is required by the software being installed (e.g. NODE_ENV=production is acceptable, as are the typical bash conventions of uppercase environment variables, but anything you create should be lowercase).
- stage names in lowercase: `from oven/bun:alpine as builder`
- labels in lowercase: `label maintainer="team@ops.site"`

## Structure
- group related `run` commands with `&&` and `\` for continuation
- order instructions from least to most frequently changing (cache optimisation)
- place `copy package.json bun.lock` before `copy . .` for dependency caching
- use `.dockerignore` to exclude unnecessary files

## Base Images
- use specific tags, but avoid patch versions where possible: `oven/bun:alpine:3.23` is preferred over `oven/bun:alpine:3.23.1`
- only using `latest` for local development images in development environments
- prefer alpine or distroless images, or arch-linux based images if we cannot work with alpine or distroless
- pin versions for reproducibility
- Production images that are pushed to a public repo (docker hub, ghcr, etc.) should always use semantic versioning tags, as well as maintain latest and stable tags as well as a linux timestamp tag.

## Build Arguments & Environment
- `arg` for build-time variables
- `env` for runtime variables
- One env or arg per line - do not combine multiple in a single instruction

## Layers
- combine commands to reduce layers:
```dockerfile
run apk add --no-cache curl && \
    bun install --production
```
- clean up in the same layer that creates files

## Networking
- When we're building our own code, always use port 80
- When packaging third-party software that defaults to another port, use that port (e.g., Postgres uses 5432, Redis uses 6379, etc.)

## Multi-stage Builds
e.g:

```dockerfile
from oven/bun:alpine as builder
workdir /app
copy package.json bun.lock ./
run bun install --frozen-lockfile
copy . .
run bun run build

from nginx:alpine as runtime
copy --from=builder /app/dist /usr/share/nginx/html
expose 80
cmd ["nginx", "-g", "daemon off;"]
```

## Security
- run as non-root user when possible
- avoid secrets in build args or env
- use `copy` over `add` unless extracting archives
- remove unnecessary packages after installation and purge caches, all in a single layer

## Final Instructions
- `expose` documents ports but doesn't publish them
- Understand the difference between `cmd` and `entrypoint` and use appropriately
- Always use exec form for `cmd`: `cmd ["bun", "run", "server.ts"]`
- `healthcheck` for container health monitoring

## Avoid
- `latest` tags
- running as root unless necessary
- `add` when `copy` suffices
- multiple `run` commands that could be combined
- uppercase anything unless absolutely necessary
