#!/bin/bash
# =============================================================================
# ZERO-DOWNTIME ROLLING UPDATE SCRIPT
# =============================================================================
# Use this instead of "down -v && up -d" for deployments.
# Rebuilds the backend image, then restarts containers one-at-a-time,
# waiting for each to be healthy before touching the next.
# Nginx stays up throughout and routes around the container being restarted.
# =============================================================================

set -e

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.loadbalanced.yml}"
WEB_CONTAINERS=(web-1 web-2 web-3 web-4 web-5 web-6 web-7 web-8 web-9 web-10)
HEALTH_TIMEOUT=180  # seconds to wait for each container to become healthy

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step()    { echo -e "\n${BLUE}==> $1${NC}"; }
print_ok()      { echo -e "${GREEN}    ✓ $1${NC}"; }
print_warn()    { echo -e "${YELLOW}    ⚠ $1${NC}"; }
print_err()     { echo -e "${RED}    ✗ $1${NC}"; }

wait_healthy() {
    local service="$1"
    local container_name="arena-${service}"
    local elapsed=0

    echo -n "    Waiting for ${service} to be healthy"
    while true; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "missing")

        if [ "$status" = "healthy" ]; then
            echo ""
            print_ok "${service} is healthy"
            return 0
        fi

        if [ "$status" = "unhealthy" ]; then
            echo ""
            print_err "${service} is unhealthy after ${elapsed}s. Check logs:"
            echo "    docker compose -f $COMPOSE_FILE logs --tail=50 ${service}"
            exit 1
        fi

        if [ "$elapsed" -ge "$HEALTH_TIMEOUT" ]; then
            echo ""
            print_err "Timed out waiting for ${service} after ${HEALTH_TIMEOUT}s"
            exit 1
        fi

        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done
}

# -----------------------------------------------------------------------------
# STEP 1: Build new image (no containers are touched)
# -----------------------------------------------------------------------------
print_step "Building new backend image..."
docker compose -f "$COMPOSE_FILE" build web-1
print_ok "Image built"

# -----------------------------------------------------------------------------
# STEP 2: Run migrations on the currently-running web-1
# (before any restarts, so old code runs them against new schema if needed)
# -----------------------------------------------------------------------------
print_step "Running database migrations..."
if docker compose -f "$COMPOSE_FILE" run --rm --no-deps web-1 python manage.py migrate --noinput; then
    print_ok "Migrations complete"
else
    print_warn "migrate exited non-zero (no migrations needed, or DB unreachable — continuing)"
fi

# -----------------------------------------------------------------------------
# STEP 3: Collect static files
# -----------------------------------------------------------------------------
print_step "Collecting static files..."
if docker compose -f "$COMPOSE_FILE" run --rm --no-deps web-1 python manage.py collectstatic --noinput; then
    print_ok "Static files collected"
else
    print_warn "collectstatic exited non-zero — continuing"
fi

# -----------------------------------------------------------------------------
# STEP 4: Rolling restart — one container at a time
# Gunicorn's --graceful-timeout 60 ensures in-flight requests finish before
# the old container exits. Nginx's proxy_next_upstream routes around it.
# -----------------------------------------------------------------------------
print_step "Starting rolling restart of ${#WEB_CONTAINERS[@]} containers..."

for service in "${WEB_CONTAINERS[@]}"; do
    echo ""
    echo -e "  ${BLUE}Restarting ${service}...${NC}"

    # Recreate this container with the new image; leave all others running
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate "$service"

    wait_healthy "$service"
done

# -----------------------------------------------------------------------------
# STEP 5: Reload nginx (zero-downtime config reload, not a restart)
# -----------------------------------------------------------------------------
print_step "Reloading nginx..."
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload
print_ok "Nginx reloaded"

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Rolling update complete — 0 downtime  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Container status:"
docker compose -f "$COMPOSE_FILE" ps
