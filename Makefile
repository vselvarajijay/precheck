# Everything runs in containers; the host needs only Docker + .env.
COMPOSE ?= docker compose
RUN_API  = $(COMPOSE) --profile test run --rm --no-deps api-test
RUN_WEB  = $(COMPOSE) --profile test run --rm --no-deps web-test
ARGS ?=

.PHONY: up dev down logs build ps test test-backend test-frontend test-live pytest lint typecheck \
        fmt gen-types e2e sh-api sh-web

up:            ## Start the stack in the background
	$(COMPOSE) up -d --build --wait

dev:           ## Start the stack in the foreground (hot reload)
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

build:
	$(COMPOSE) --profile test --profile e2e build

ps:
	$(COMPOSE) ps

test: test-backend test-frontend   ## Unit + integration tests, offline (network_mode: none)

test-backend:
	$(RUN_API) pytest $(ARGS)

test-frontend:
	$(RUN_WEB) pnpm test

test-live:     ## Tests that call real Jev / Anthropic (needs .env keys; costs money)
	$(COMPOSE) run --rm --no-deps --entrypoint "" api pytest -m live $(ARGS)

pytest:        ## make pytest ARGS='-k health -v'
	$(RUN_API) pytest $(ARGS)

lint:
	$(RUN_API) sh -c "ruff check . && ruff format --check ."
	$(RUN_WEB) pnpm lint

fmt:
	$(RUN_API) sh -c "ruff check --fix . && ruff format ."

typecheck:
	$(RUN_API) mypy
	$(RUN_WEB) pnpm typecheck

gen-types:     ## Backend OpenAPI -> frontend/src/api/schema.d.ts
	$(RUN_API) python -m precheck.api.openapi > frontend/src/api/openapi.json
	$(RUN_WEB) pnpm gen-types
	rm -f frontend/src/api/openapi.json

e2e:           ## Playwright against the running stack (starts it if needed)
	$(COMPOSE) --profile e2e run --rm e2e

sh-api:
	$(COMPOSE) exec api sh

sh-web:
	$(COMPOSE) exec web sh
