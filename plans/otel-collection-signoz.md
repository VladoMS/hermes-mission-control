# SigNoz on Prod — OTel Collection Pipeline

> Phase 1 of 2. This plan covers deploying SigNoz on prod and verifying telemetry flows.
> Phase 2 (separate plan): Mission Control dashboard integration.

## Architecture

```
Claude Code (PC) ──OTLP/HTTP──────────────────┐
  (X-Collector-Token: sk-claude-1)            │
                                              ├──► CloudFlare ──► Tunnel ──► Caddy (:8081, HTTP)
OpenRouter Broadcast ─────────────────────────┘        │
  (X-Collector-Token: sk-openrouter-1)                 │
                                                       ▼
                                                Caddy validates X-Collector-Token
                                                 │              │
                                    /v1/* (valid token)    /api/* + everything else
                                                 │              │
                                                 ▼              ▼
                                    signoz-otel-collector:4318  signoz:8080 (UI + API)
                                                 │
                                            ClickHouse (traces/metrics/logs)
                                                 │
                                            SigNoz UI at https://collect.vladislavstoyanov.com
```

- CloudFlare terminates public TLS. Caddy runs plain HTTP on `:8081` internally.
- Caddy is the single entry point. Validates `X-Collector-Token` on OTLP ingestion routes.
- All SigNoz services are Docker-internal. Only `signoz` (:8080) and `otel-collector` (:4317/:4318) bind host ports.
- No public ports open — CloudFlare Tunnel is outbound-only.

---

## Prerequisites

### 0.1 Verify Claude Code telemetry support (on your PC)

These env vars are undocumented. Verify they work *before* deploying anything:

```bash
# Check if Claude Code recognizes these
claude --help 2>&1 | grep -i telemetry
claude --help 2>&1 | grep -i otel

# Check for any existing telemetry config
ls ~/.claude/ 2>/dev/null
cat ~/.claude/config.json 2>/dev/null | grep -i telemetry
```

If Claude Code does NOT support these env vars, we pivot — OTel SDK wrapper, or scrape Claude Code session logs. Either way, find out before deploying.

### 0.2 Verify OpenRouter observability → OTLP

1. Log into https://openrouter.ai/settings/observability
2. Confirm "Destination: OpenTelemetry Collector" exists as an option
3. Note any required headers/auth format

If OTLP export doesn't exist yet, OpenRouter data comes through their API instead.

### 0.3 Ensure cloudflared is installed on prod

```bash
ssh prod 'which cloudflared || curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared'
```

---

## Part 1 — Deploy SigNoz Stack

### 1.1 Clone and prepare files

```bash
ssh prod

mkdir -p ~/signoz && cd ~/signoz

# Clone upstream
git clone --depth=1 https://github.com/SigNoz/signoz.git /tmp/signoz-repo

# Copy compose + collector config to ~/signoz/
cp /tmp/signoz-repo/deploy/docker/docker-compose.yaml ./
cp /tmp/signoz-repo/deploy/docker/otel-collector-config.yaml ./
cp /tmp/signoz-repo/deploy/docker/.env ./

# Copy common/ ONE LEVEL UP so ../common/ resolves correctly from the compose
cp -r /tmp/signoz-repo/deploy/common ~/common/

# Clean up
rm -rf /tmp/signoz-repo
```

Resulting layout:

```
~/
  signoz/
    docker-compose.yaml
    otel-collector-config.yaml
    .env
  common/
    clickhouse/
      config.xml
      users.xml
      custom-function.xml
      user_scripts/
      cluster.xml
    signoz/
      otel-collector-opamp-config.yaml
    dashboards/
    locust-scripts/
```

The `docker-compose.yaml` references `../common/clickhouse/...` and `../common/signoz/...`. From `~/signoz/docker-compose.yaml`, `../common/` resolves to `~/common/` — correct.

### 1.2 Start SigNoz

```bash
cd ~/signoz
docker compose up -d --remove-orphans
```

Wait for health checks:

```bash
docker compose ps
# All services should show "healthy" or "running"
# signoz-telemetrystore-migrator exits 0 (one-shot)
```

Services running:

| Container | Ports (host) | Purpose |
|---|---|---|
| `signoz-otel-collector` | :4317 gRPC, :4318 HTTP | OTLP ingestion |
| `signoz-clickhouse` | none (internal :8123, :9000) | Telemetry storage |
| `signoz-zookeeper-1` | none | ClickHouse coordination |
| `signoz` | :8080 | UI + query API |
| `signoz-telemetrystore-migrator` | none | One-shot migrations |

### 1.3 First login — create admin account and PAT

1. Visit `http://<prod-ip>:8080` (temporarily, before tunnel is up)
2. Register your account (first user = admin)
3. Go to Settings → Access Tokens
4. Create a PAT with read access for mission-control (Phase 2 will need this)
5. Save the token securely (e.g., `~/signoz/.env.pat` — not committed)

---

## Part 2 — CloudFlare Tunnel

### 2.1 Create tunnel

```bash
ssh prod

cloudflared tunnel login   # if not already authenticated
cloudflared tunnel create signoz-collector
# Note the tunnel ID from output

cloudflared tunnel route dns signoz-collector collect.vladislavstoyanov.com
```

This creates:
- `~/.cloudflared/<tunnel-id>.json` — credentials
- DNS CNAME record: `collect.vladislavstoyanov.com` → tunnel

### 2.2 Tunnel config

`~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: collect.vladislavstoyanov.com
    service: http://localhost:8081
  - service: http_status:404
```

All traffic for `collect.vladislavstoyanov.com` goes to Caddy on `localhost:8081`. Everything else gets 404.

### 2.3 Run tunnel as systemd service

```bash
cloudflared --config ~/.cloudflared/config.yml service install
systemctl enable cloudflared --now
systemctl status cloudflared
```

---

## Part 3 — Caddy Reverse Proxy (HTTP, no TLS)

CloudFlare terminates TLS at the edge. Caddy runs plain HTTP on `:8081` internally.

### 3.1 Caddy compose

`~/signoz/caddy-compose.yaml`:

```yaml
services:
  caddy:
    image: caddy:2
    container_name: signoz-caddy
    ports:
      - "8081:8081"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
    networks:
      - signoz-net
    restart: unless-stopped

networks:
  signoz-net:
    external: true
    name: signoz-net
```

### 3.2 Caddyfile

`~/signoz/Caddyfile`:

```caddy
:8081 {
    # OTLP ingestion — requires valid token
    handle /v1/* {
        @valid {
            header_regexp X-Collector-Token "^(sk-claude-1|sk-openrouter-1)$"
        }
        handle @valid {
            reverse_proxy signoz-otel-collector:4318
        }
        handle {
            respond "Unauthorized — invalid or missing X-Collector-Token" 401
        }
    }

    # SigNoz API — proxied as-is
    # (PUT YOUR PAT in the X-SIGNOZ-API-Token header, or use PAT as query param)
    handle /api/* {
        reverse_proxy signoz:8080
    }

    # SigNoz UI — everything else
    handle {
        reverse_proxy signoz:8080
    }
}
```

**Important**: No TLS config. No LetsEncrypt. `:8081` is plain HTTP. CloudFlare handles the secure edge.

### 3.3 Start Caddy

```bash
cd ~/signoz
docker compose -f caddy-compose.yaml up -d

# Verify
curl -s http://localhost:8081/api/v1/health
# Should return SigNoz health response
```

---

## Part 4 — Configure Telemetry Sources

### 4.1 Claude Code (your PC)

Only configure this if Step 0.1 confirmed the env vars work:

```env
CLAUDE_CODE_ENABLE_TELEMETRY=1
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://collect.vladislavstoyanov.com
OTEL_EXPORTER_OTLP_HEADERS=X-Collector-Token=sk-claude-1
OTEL_METRIC_EXPORT_INTERVAL=1000
OTEL_LOGS_EXPORT_INTERVAL=1000
OTEL_TRACES_EXPORT_INTERVAL=1000
```

**If these don't work**, the fallback is to wrap Claude Code invocations with a local OTel SDK shim that captures token counts from Claude Code's own logs and exports them as custom spans. That's a separate mini-project (likely a Python script using `opentelemetry-api` + `opentelemetry-exporter-otlp`).

### 4.2 OpenRouter

Only configure if Step 0.2 confirmed the option exists:

- Log into https://openrouter.ai/settings/observability
- Destination: OpenTelemetry Collector
- Endpoint: `https://collect.vladislavstoyanov.com/v1/traces`
- Headers: `{"X-Collector-Token": "sk-openrouter-1"}`
- Click Test Connection, then Save

---

## Part 5 — Verification

### 5.1 Tunnel + Caddy + SigNoz chain

```bash
# From hermes (external — goes through CF → Tunnel → Caddy → SigNoz)
curl -s https://collect.vladislavstoyanov.com/api/v1/health

# OTLP auth test — should 401 without token
curl -s -o /dev/null -w "%{http_code}" https://collect.vladislavstoyanov.com/v1/traces
# Expected: 401

# OTLP auth test — should pass with token (will 200 even if empty body)
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Collector-Token: sk-claude-1" \
  https://collect.vladislavstoyanov.com/v1/traces
# Expected: 200 or 202
```

### 5.2 SigNoz UI accessible

Visit `https://collect.vladislavstoyanov.com` — should show the SigNoz login/UI.

### 5.3 Telemetry flowing

1. Run a Claude Code session on your PC with the telemetry env vars
2. Open SigNoz UI → Services — should see a service appear
3. Check Traces tab for spans from Claude Code

### 5.4 OpenRouter test

1. Enable OpenRouter observability
2. Run a query through OpenRouter
3. Check SigNoz → Services for OpenRouter traces

---

## Security Notes

| Risk | Mitigation |
|---|---|
| Unauthenticated OTLP ingestion | Caddy validates `X-Collector-Token` header on `/v1/*` routes |
| SigNoz API exposed | Behind CloudFlare Tunnel + CF WAF if needed |
| No port exposure | CloudFlare Tunnel is outbound-only. Docker ports are localhost-only except where bound to host |
| Token compromise | Rotate token in Caddyfile + env vars; `docker compose -f caddy-compose.yaml restart` |
| CF Tunnel compromise | CloudFlare Zero Trust policies can add additional auth layers |

---

## Files Created on Prod

| Path | Source |
|---|---|
| `~/signoz/docker-compose.yaml` | Copied from upstream `deploy/docker/` |
| `~/signoz/otel-collector-config.yaml` | Copied from upstream `deploy/docker/` |
| `~/signoz/.env` | Copied from upstream `deploy/docker/` |
| `~/signoz/caddy-compose.yaml` | Custom (this plan) |
| `~/signoz/Caddyfile` | Custom (this plan) |
| `~/common/clickhouse/*.xml` | Copied from upstream `deploy/common/` |
| `~/common/signoz/*.yaml` | Copied from upstream `deploy/common/` |
| `~/.cloudflared/config.yml` | Custom (this plan) |
| `~/.cloudflared/<tunnel-id>.json` | Auto-generated by `cloudflared tunnel create` |

---

## What This Plan Does NOT Cover

- Mission Control dashboard integration (Phase 2)
- Cost calculation (Phase 2)
- Claude Code telemetry fallback if env vars don't work (TBD after 0.1 check)
- Alerting rules in SigNoz
- Retention policies for ClickHouse data
- Backups for ClickHouse volumes

---

## Decision Gate

Before proceeding to Phase 2 (Mission Control dashboard), you need:

- [ ] SigNoz UI accessible at `https://collect.vladislavstoyanov.com`
- [ ] At least one telemetry source flowing (Claude Code OR OpenRouter)
- [ ] SigNoz PAT created and tested (for API access)
- [ ] Confident the data pipeline is stable (running for 24h+)
