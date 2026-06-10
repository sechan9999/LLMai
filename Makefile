# llmai — common dev / demo tasks.
# Cross-platform: works in Git-Bash / WSL on Windows and on macOS / Linux.

.PHONY: help install install-all install-telemetry install-memory install-elastic install-mcp \
        test lint demo-up demo-down demo-bootstrap demo-status \
        elastic-up elastic-down elastic-setup elastic-ingest \
        bindplane-up bindplane-down

help:
	@echo "llmai — available targets"
	@echo ""
	@echo "Setup:"
	@echo "  install            Install core deps only"
	@echo "  install-all        Install core + telemetry + memory + elastic"
	@echo "  install-telemetry  Add OpenTelemetry stack"
	@echo "  install-memory     Add MongoDB pymongo"
	@echo "  install-elastic    Add Elasticsearch client"
	@echo "  install-mcp        Add MCP client SDK (partner MCP servers)"
	@echo ""
	@echo "Demo (one command per group):"
	@echo "  demo-up            Start Elastic + Kibana + Bindplane (Docker)"
	@echo "  demo-down          Stop and remove demo containers"
	@echo "  demo-bootstrap     Create Elastic indices, pull embed model"
	@echo "  demo-status        Show health of every demo service"
	@echo ""
	@echo "Targeted:"
	@echo "  elastic-up         Start ES + Kibana only"
	@echo "  elastic-setup      Create the 4 llmai-* indices"
	@echo "  elastic-ingest     Ingest GitLab issues + pipeline logs"
	@echo "  bindplane-up       Start Bindplane OTel collector only"
	@echo ""
	@echo "Quality:"
	@echo "  test               Run pytest"
	@echo "  lint               Run ruff"

# ── Install ──────────────────────────────────────────────────────────────────

install:
	pip install -e .

install-all:
	pip install -e ".[telemetry,memory,elastic,mcp,dev]"

install-telemetry:
	pip install -e ".[telemetry]"

install-memory:
	pip install -e ".[memory]"

install-elastic:
	pip install -e ".[elastic]"

install-mcp:
	pip install -e ".[mcp]"

# ── One-command demo ─────────────────────────────────────────────────────────

demo-up: elastic-up bindplane-up
	@echo ""
	@echo "Demo stack running:"
	@echo "  Elasticsearch   http://localhost:9200"
	@echo "  Kibana          http://localhost:5601"
	@echo "  Bindplane OTLP  http://localhost:4318  (logs -> ES, traces+metrics -> Dynatrace)"
	@echo ""
	@echo "Next:"
	@echo "  1. make demo-bootstrap     (creates indices, pulls embed model)"
	@echo "  2. cp .env.example .env    (fill in Dynatrace + GitLab tokens if you have them)"
	@echo "  3. export LLMAI_ELASTIC_ENABLED=true LLMAI_ELASTIC_URL=http://localhost:9200"
	@echo "  4. llmai-server"

demo-down:
	-docker compose -f docker-compose.elastic.yml down
	-docker compose -f docker-compose.bindplane.yml down

demo-bootstrap:
	@echo "Pulling embedding model..."
	-ollama pull nomic-embed-text
	@echo ""
	@echo "Creating Elastic indices..."
	LLMAI_ELASTIC_URL=$${LLMAI_ELASTIC_URL:-http://localhost:9200} \
	  python scripts/elastic_setup_indexes.py

demo-status:
	@echo "── Elasticsearch ──"
	@curl -s http://localhost:9200/_cluster/health 2>/dev/null | python -m json.tool 2>/dev/null \
	  || echo "  (not running)"
	@echo ""
	@echo "── Ollama ──"
	@curl -s http://localhost:11434/api/tags 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print('  models:', ', '.join(m['name'] for m in d['models']))" 2>/dev/null \
	  || echo "  (not running)"
	@echo ""
	@echo "── Bindplane (OTLP) ──"
	@curl -s -o /dev/null -w "  HTTP %{http_code}\n" http://localhost:4318 \
	  || echo "  (not running)"

# ── Per-service ──────────────────────────────────────────────────────────────

elastic-up:
	docker compose -f docker-compose.elastic.yml up -d

elastic-down:
	docker compose -f docker-compose.elastic.yml down

elastic-setup:
	LLMAI_ELASTIC_URL=$${LLMAI_ELASTIC_URL:-http://localhost:9200} \
	  python scripts/elastic_setup_indexes.py

elastic-ingest:
	@if [ -z "$$GITLAB_TOKEN" ]; then echo "ERROR: set GITLAB_TOKEN first"; exit 1; fi
	python scripts/elastic_ingest_gitlab.py --limit 500
	python scripts/elastic_ingest_logs.py --limit 50

bindplane-up:
	docker compose -f docker-compose.bindplane.yml up -d

bindplane-down:
	docker compose -f docker-compose.bindplane.yml down

# ── Quality ──────────────────────────────────────────────────────────────────

test:
	python -m pytest tests/ -q

lint:
	ruff check .
