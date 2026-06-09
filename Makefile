# ============================================================
#  Hermes Agent — Makefile
#  Usage: make <target>
# ============================================================

HERMES_PROFILE ?= work
-include local.mk

DOCKER_DIR := docker
ENV_FILE := $(DOCKER_DIR)/.env.$(HERMES_PROFILE)

# All docker compose commands pick up the env file
COMPOSE := docker compose --env-file $(ENV_FILE) -f $(DOCKER_DIR)/docker-compose.yml -f $(DOCKER_DIR)/docker-compose.work.yml
COMPOSE_TEST := docker compose --env-file $(ENV_FILE) -f $(DOCKER_DIR)/docker-compose.yml -f $(DOCKER_DIR)/docker-compose.test.yml

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

	@echo ""

# ── Build ─────────────────────────────────────────────────────────────────────

.PHONY: build
build: ## Build the Docker image for the current profile
	docker build --build-arg HERMES_PROFILE=$(HERMES_PROFILE) \
		-t $(shell grep -E '^HERMES_IMAGE=' $(ENV_FILE) | cut -d= -f2-) \
		-f $(DOCKER_DIR)/Dockerfile \
		$(DOCKER_DIR)

# ── Gateway ───────────────────────────────────────────────────────────────────

.PHONY: gateway
gateway: ## (Re)start the gateway in the background
	$(COMPOSE) down hermes-gateway || true
	$(COMPOSE) up -d hermes-gateway

.PHONY: gateway-logs
gateway-logs: ## Tail gateway logs
	$(COMPOSE) logs -f hermes-gateway

.PHONY: gateway-stop
gateway-stop: ## Stop the gateway
	$(COMPOSE) stop hermes-gateway

# ── Dashboard ─────────────────────────────────────────────────────────────────

.PHONY: dashboard
dashboard: ## (Re)start the dashboard in the background
	$(COMPOSE) --profile dashboard down hermes-dashboard || true
	$(COMPOSE) --profile dashboard up -d hermes-dashboard
	@echo "Dashboard running at http://localhost:$(DASHBOARD_PORT)"

.PHONY: dashboard-logs
dashboard-logs: ## Tail dashboard logs
	$(COMPOSE) --profile dashboard logs -f hermes-dashboard

.PHONY: dashboard-stop
dashboard-stop: ## Stop the dashboard
	$(COMPOSE) --profile dashboard stop hermes-dashboard

# ── CLI ───────────────────────────────────────────────────────────────────────

.PHONY: cli
cli: ## Open an interactive chat session (--rm; ephemeral)
	$(COMPOSE) --profile cli run --rm hermes-cli

# ── Init ──────────────────────────────────────────────────────────────────────

.PHONY: init
init: ## Run the one-time init container
	$(COMPOSE) run --rm hermes-init


# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run the full test suite (pass ARGS="..." to forward pytest args)
	$(COMPOSE_TEST) down -v --remove-orphans || true
	$(COMPOSE_TEST) up -d hermes-gateway
	$(COMPOSE_TEST) run --rm hermes-test $(if $(ARGS),pytest -vv -s $(ARGS),) ; \
		EXIT=$$? ; \
		$(COMPOSE_TEST) down -v --remove-orphans ; \
		exit $$EXIT

# ── Lifecycle helpers ─────────────────────────────────────────────────────────

.PHONY: up
up: gateway dashboard ## Start gateway + dashboard

.PHONY: down
down: ## Tear down all containers for the current profile
	$(COMPOSE) --profile dashboard --profile cli down

.PHONY: restart
restart: down up ## Full restart (gateway + dashboard)

.PHONY: ps
ps: ## Show running containers for the current profile
	$(COMPOSE) --profile dashboard --profile cli ps

.PHONY: logs
logs: ## Tail logs for all running services
	$(COMPOSE) --profile dashboard logs -f
