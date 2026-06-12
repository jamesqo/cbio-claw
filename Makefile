# ============================================================
#  Hermes Agent — Makefile
#  Usage: make <target>
# ============================================================

DOCKER_DIR := docker
ENV_FILE := docker-compose.env

# All docker compose commands pick up the env file
COMPOSE := docker compose --env-file $(ENV_FILE) -f docker-compose.yml
COMPOSE_TEST := docker compose --env-file $(ENV_FILE) -f docker-compose.yml -f docker-compose.test.yml

# Resolve the data dir from the env file at make-parse time so targets can
# reference it (e.g. for the sync target).
HERMES_DATA := $(shell grep -E '^HERMES_DATA=' $(ENV_FILE) | cut -d= -f2-)

# Dashboard port (for the helpful URL echo)
DASHBOARD_PORT := $(shell grep -E '^HERMES_DASHBOARD_PORT=' $(ENV_FILE) | cut -d= -f2-)

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "  Hermes Agent — available targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Build ─────────────────────────────────────────────────────────────────────

.PHONY: build
build: ## Build the Docker image
	docker build \
		-t $(shell grep -E '^HERMES_IMAGE=' $(ENV_FILE) | cut -d= -f2-) \
		-f $(DOCKER_DIR)/Dockerfile \
		$(DOCKER_DIR)

# ── Gateway ───────────────────────────────────────────────────────────────────

.PHONY: gateway
gateway: ## (Re)start the gateway in the background
	$(COMPOSE) down hermes-cbio-gateway || true
	$(COMPOSE) up -d hermes-cbio-gateway

.PHONY: gateway-logs
gateway-logs: ## Tail gateway logs
	$(COMPOSE) logs -f hermes-cbio-gateway

.PHONY: gateway-stop
gateway-stop: ## Stop the gateway
	$(COMPOSE) stop hermes-cbio-gateway

# ── Dashboard ─────────────────────────────────────────────────────────────────

.PHONY: dashboard
dashboard: ## (Re)start the dashboard in the background
	$(COMPOSE) --profile dashboard down hermes-cbio-dashboard || true
	$(COMPOSE) --profile dashboard up -d hermes-cbio-dashboard
	@echo "Dashboard running at http://localhost:$(DASHBOARD_PORT)"

.PHONY: dashboard-logs
dashboard-logs: ## Tail dashboard logs
	$(COMPOSE) --profile dashboard logs -f hermes-cbio-dashboard

.PHONY: dashboard-stop
dashboard-stop: ## Stop the dashboard
	$(COMPOSE) --profile dashboard stop hermes-cbio-dashboard

# ── Shell / CLI ───────────────────────────────────────────────────────────────

.PHONY: cli
cli: ## Open an interactive chat session (exec into running gateway)
	docker exec -it hermes-cbio-gateway hermes chat

.PHONY: shell
shell: ## Open a bash shell in the running gateway container
	docker exec -it hermes-cbio-gateway /bin/bash

# ── Init ──────────────────────────────────────────────────────────────────────

.PHONY: init
init: ## Run the one-time init container
	$(COMPOSE) run --rm hermes-init


# ── oMLX (local Apple Silicon inference) ──────────────────────────────────────

.PHONY: setup-omlx
setup-omlx: ## Install & start oMLX on this Mac (requires macOS 15+ and Apple Silicon)
	PORT=$(PORT) bash scripts/setup-omlx.sh

.PHONY: use-omlx
use-omlx: ## Switch agent to oMLX  →  make use-omlx MODEL=<model-id> [PORT=8000]  then  make restart
	@test -n "$(MODEL)" || (echo "Usage: make use-omlx MODEL=<model-id> [PORT=8000]"; exit 1)
	bash scripts/use-omlx.sh "$(MODEL)" "$(or $(PORT),8000)"

.PHONY: use-copilot
use-copilot: ## Switch agent back to GitHub Copilot  →  make use-copilot [MODEL=claude-sonnet-4.6]  then  make restart
	bash scripts/use-copilot.sh "$(or $(MODEL),claude-sonnet-4.6)"

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run the full test suite (pass ARGS="..." to forward pytest args)
	$(COMPOSE_TEST) down -v --remove-orphans || true
	$(COMPOSE_TEST) up -d hermes-cbio-gateway
	$(COMPOSE_TEST) run --rm hermes-test $(if $(ARGS),pytest -vv -s $(ARGS),) ; \
		EXIT=$$? ; \
		$(COMPOSE_TEST) down -v --remove-orphans ; \
		exit $$EXIT

# ── Lifecycle helpers ─────────────────────────────────────────────────────────

.PHONY: up
up: gateway dashboard ## Start gateway + dashboard

.PHONY: down
down: ## Tear down all containers
	$(COMPOSE) --profile dashboard down

.PHONY: restart
restart: down up ## Full restart (gateway + dashboard)

.PHONY: ps
ps: ## Show running containers
	$(COMPOSE) --profile dashboard ps

.PHONY: logs
logs: ## Tail logs for all running services
	$(COMPOSE) --profile dashboard logs -f
