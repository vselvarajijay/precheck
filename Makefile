# Everything runs in containers; the host needs only Docker + .env.
COMPOSE ?= docker compose
RUN_API  = $(COMPOSE) --profile test run --rm --no-deps --build api-test
RUN_WEB  = $(COMPOSE) --profile test run --rm --no-deps --build web-test
ARGS ?=

.PHONY: up dev down logs build ps test test-backend test-frontend test-live pytest lint typecheck \
        fmt gen-types e2e e2e-live e2e-live-llm e2e-record eval-translator translator-roundtrip sh-api sh-web

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

e2e:           ## Playwright against an isolated stack (fresh DB, Jev replay); ARGS passed to playwright
	$(COMPOSE) --profile e2e rm -sf api-e2e web-e2e >/dev/null 2>&1 || true
	$(COMPOSE) --profile e2e run --rm --build e2e pnpm exec playwright test $(ARGS); \
	  status=$$?; $(COMPOSE) --profile e2e rm -sf api-e2e web-e2e >/dev/null 2>&1; exit $$status

e2e-live:      ## e2e with real Jev calls (uses TYPESAFE_API_KEY from .env; costs a little)
	E2E_JEV_MODE=live E2E_JEV_KEY="$$(grep '^TYPESAFE_API_KEY=' .env | cut -d= -f2-)" $(MAKE) e2e

e2e-live-llm:  ## e2e with real Jev AND real Claude translations (costs more; ~$0.08 per translation)
	E2E_JEV_MODE=live E2E_JEV_KEY="$$(grep '^TYPESAFE_API_KEY=' .env | cut -d= -f2-)" \
	  E2E_LLM_MODE=live E2E_LLM_KEY="$$(grep '^ANTHROPIC_API_KEY=' .env | cut -d= -f2-)" $(MAKE) e2e

e2e-record:    ## e2e with real Jev calls, saving fixtures under backend/tests/fixtures/jev
	E2E_JEV_MODE=record E2E_JEV_KEY="$$(grep '^TYPESAFE_API_KEY=' .env | cut -d= -f2-)" $(MAKE) e2e

eval-translator: ## Score the translator on the eval corpus (live Claude; LLM_MODE=cache reuses recordings)
	$(COMPOSE) run --rm --no-deps --entrypoint "" -e LLM_MODE=$${LLM_MODE:-cache} api python -m precheck.translator.eval $(ARGS)

translator-roundtrip: ## Translate with tests, then run the generated tests through the engine (live Jev)
	$(COMPOSE) run --rm --no-deps --entrypoint "" -e LLM_MODE=$${LLM_MODE:-cache} api python -m precheck.translator.roundtrip $(ARGS)

sh-api:
	$(COMPOSE) exec api sh

sh-web:
	$(COMPOSE) exec web sh
