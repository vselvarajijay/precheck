# precheck

A fast, rule-driven **pre-check decision layer for AI agents**. Before an agent does
something consequential — calls a tool, sends data out, or takes in untrusted content —
precheck answers *"may this proceed?"* with a typed verdict: **allow**, **deny**, or
**escalate**.

- **Deterministic checks** (amounts, dates, allowlists, exact matches) run in plain code.
- **Judgment checks** ("does the stated reason justify this refund?") are answered by
  [Jev](https://docs.typesafe.ai/api) (TypeSafe AI) as typed questions with calibrated
  probabilities, mapped to verdicts through per-rule thresholds.
- **Authoring**: describe rules in plain language ("refunds over $500 need a manager");
  the translator turns them into structured, tested rules you can review and publish.

> Status: early MVP, under active development. No authentication yet — bind to localhost only.

## Run locally

Requirements: Docker (with Compose v2). Nothing else is needed on the host.

```sh
cp .env.example .env        # add TYPESAFE_API_KEY (and ANTHROPIC_API_KEY for the translator)
docker compose up           # or: make up  (detached, waits for healthy)
```

| Service | URL |
|---------|-----|
| Web UI  | http://127.0.0.1:5173 |
| API     | http://127.0.0.1:8000/api/health · docs at http://127.0.0.1:8000/docs |

All ports are published on `127.0.0.1` only. SQLite data lives in `./data/`.

## Development

```sh
make test        # backend + frontend unit tests, in containers, no network
make lint        # ruff + oxlint
make typecheck   # mypy (strict) + tsc
make e2e         # Playwright against the running stack
make gen-types   # regenerate frontend API types from the backend OpenAPI schema
make test-live   # tests that call real Jev / Anthropic (uses your keys; costs money)
make pytest PKG=server ARGS='-k health -v'
```

### Layout

A uv workspace of Python packages sharing the `precheck` namespace, plus the web app:

| Path | Package | What it is | May import |
|------|---------|------------|------------|
| `packages/core` | `precheck-core` | `precheck.core`: rule schema, Jev client, decision engine | — |
| `packages/translator` | `precheck-translator` | `precheck.translator`: business case → rules (Claude) | core |
| `packages/server` | `precheck-server` | `precheck.server`: authoring API, rule store, authoring MCP | core, translator |
| `packages/mcp-proxy` | `precheck-mcp-proxy` | `precheck.mcp_proxy`: enforcement proxy in front of MCP tools | core |
| `packages/lab` | `precheck-lab` | `precheck.lab`: mock tools + test agent (dev only) | core |
| `apps/web` | — | React UI, grouped by feature (`src/features/*`, `src/shared/*`) | — |

Adapters and the lab talk to the server over HTTP only; `tests/test_layering.py` enforces
the import rules. Shared data lives at the root: `examples/` (rule packs, scenarios,
playground requests) and `fixtures/` (recorded Jev/Claude responses for replay mode).
Dockerfiles are in `deploy/`. Each package keeps its tests in `packages/<pkg>/tests`;
`make pytest PKG=server ARGS='-k health'` runs one package.

## Privacy

Judgment checks send the parts of a request selected by each rule's state template to
TypeSafe's Jev API (directly or via a gateway you configure). Deterministic-only rules
never leave your machine.

## License

Apache-2.0 — see [LICENSE](LICENSE).
