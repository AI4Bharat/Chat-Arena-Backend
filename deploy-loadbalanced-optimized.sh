```bash
#!/bin/bash

# =============================================================================
# Arena Backend Load-Balanced Deployment Script (OPTIMIZED)
# Supports docker-compose.loadbalanced.optimized.yml
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
COMPOSE_FILE="docker-compose.loadbalanced.optimized.yml"
REQUIRED_VOLUMES=("logs_vol" "nginx_conf" "letsencrypt_certs" "certbot_acme_challenge" "static_volume" "redis_data")
WEB_CONTAINERS=("web-1" "web-2" "web-3" "web-4" "web-5" "web-6")

# Logging helpers
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Arena Backend Optimized Deployment${NC}"
echo -e "${BLUE}========================================${NC}\n"

# -----------------------------------------------------------------------------
# Check Docker
# -----------------------------------------------------------------------------
check_docker() {
    print_info "Checking Docker..."

    if ! command -v docker &> /dev/null; then
        print_warning "Docker not found. Installing..."
        sudo apt update
        sudo apt install -y docker.io
        sudo systemctl enable docker
        sudo systemctl start docker
        print_success "Docker installed"
    else
        print_success "Docker is installed"
    fi
}

# -----------------------------------------------------------------------------
# Check Docker Compose plugin
# -----------------------------------------------------------------------------
check_docker_compose() {
    print_info "Checking Docker Compose plugin..."

    if ! docker compose version &> /dev/null; then
        print_warning "Docker Compose plugin missing. Installing..."
        sudo apt update
        sudo apt install -y docker-compose-plugin
        print_success "Docker Compose plugin installed"
    else
        print_success "Docker Compose is available"
    fi
}

# -----------------------------------------------------------------------------
# Cleanup Docker (prevents disk + corruption issues)
# -----------------------------------------------------------------------------
cleanup_docker() {
    print_info "Cleaning Docker (safe cleanup)..."
    docker system prune -a -f || true
    docker builder prune -a -f || true
}

# -----------------------------------------------------------------------------
# Volumes
# -----------------------------------------------------------------------------
check_volumes() {
    print_info "Checking Docker volumes..."

    for volume in "${REQUIRED_VOLUMES[@]}"; do
        if ! docker volume inspect "$volume" &> /dev/null; then
            docker volume create "$volume"
            print_success "Created volume: $volume"
        fi
    done

    print_success "All volumes ready"
}

# -----------------------------------------------------------------------------
# Env
# -----------------------------------------------------------------------------
check_env_file() {
    print_info "Checking environment file..."

    if [ ! -f "config.env" ] && [ ! -f ".env" ]; then
        print_error "Missing config.env or .env file"
        exit 1
    fi

    print_success "Environment file found"
}

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------
build_images() {
    print_info "Building images..."
    docker compose -f "$COMPOSE_FILE" build
    print_success "Images built"
}

# -----------------------------------------------------------------------------
# Redis
# -----------------------------------------------------------------------------
start_redis() {
    print_info "Starting Redis..."
    docker compose -f "$COMPOSE_FILE" up -d redis

    print_info "Waiting for Redis..."
    for i in {1..30}; do
        if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &> /dev/null; then
            print_success "Redis is ready"
            return
        fi
        sleep 1
    done

    print_error "Redis failed to start"
    exit 1
}

# -----------------------------------------------------------------------------
# Web + Workers
# -----------------------------------------------------------------------------
start_services() {
    print_info "Starting web + workers..."

    docker compose -f "$COMPOSE_FILE" up -d \
        "${WEB_CONTAINERS[@]}" \
        celery-default celery-beat cron certbot

    print_success "All services started"
}

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------
wait_for_health() {
    print_info "Waiting for containers..."

    for i in {1..60}; do
        healthy=0

        for c in "${WEB_CONTAINERS[@]}"; do
            status=$(docker inspect --format='{{.State.Health.Status}}' "arena-$c" 2>/dev/null || echo "starting")
            [ "$status" == "healthy" ] && ((healthy++))
        done

        echo -ne "\rHealthy: $healthy/${#WEB_CONTAINERS[@]}"

        if [ "$healthy" -eq "${#WEB_CONTAINERS[@]}" ]; then
            echo ""
            print_success "All containers healthy"
            return
        fi

        sleep 2
    done

    echo ""
    print_warning "Some containers not healthy"
}

# -----------------------------------------------------------------------------
# Nginx
# -----------------------------------------------------------------------------
start_nginx() {
    print_info "Starting Nginx..."
    docker compose -f "$COMPOSE_FILE" up -d nginx
    print_success "Nginx started"
}

# -----------------------------------------------------------------------------
# Django tasks
# -----------------------------------------------------------------------------
run_migrations() {
    print_info "Running migrations..."
    docker compose -f "$COMPOSE_FILE" exec -T web-1 python manage.py migrate --noinput || true
}

collect_static() {
    print_info "Collecting static..."
    docker compose -f "$COMPOSE_FILE" exec -T web-1 python manage.py collectstatic --noinput || true
}

# -----------------------------------------------------------------------------
# Health endpoint
# -----------------------------------------------------------------------------
test_health() {
    print_info "Testing health endpoint..."
    sleep 5

    if curl -sf http://localhost/health/ > /dev/null; then
        print_success "Health check passed"
    else
        print_warning "Health check failed"
    fi
}

# -----------------------------------------------------------------------------
# Status
# -----------------------------------------------------------------------------
show_status() {
    echo ""
    docker compose -f "$COMPOSE_FILE" ps

    echo ""
    print_info "Endpoints:"
    echo "http://localhost/health/"
    echo "http://localhost/status/"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    check_docker
    check_docker_compose
    check_env_file
    check_volumes

    echo ""
    cleanup_docker

    build_images
    start_redis
    start_services
    wait_for_health
    start_nginx

    run_migrations
    collect_static

    test_health
    show_status

    print_success "Deployment complete 🚀"
}

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
case "${1:-}" in
    start) main ;;
    stop)
        docker compose -f "$COMPOSE_FILE" down
        ;;
    restart)
        docker compose -f "$COMPOSE_FILE" restart
        ;;
    logs)
        docker compose -f "$COMPOSE_FILE" logs -f
        ;;
    status)
        docker compose -f "$COMPOSE_FILE" ps
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|status}"
        exit 1
        ;;
esac
```
