#!/bin/bash

# Arena Backend Load-Balanced Deployment Script
# This script deploys the Arena Backend with 10 Django containers behind Nginx

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.loadbalanced.yml"
REQUIRED_VOLUMES=("logs_vol" "nginx_conf" "letsencrypt_certs")
WEB_CONTAINERS=("web-1" "web-2" "web-3" "web-4" "web-5" "web-6" "web-7" "web-8" "web-9" "web-10")

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Arena Backend Load-Balanced Deployment${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if Docker is installed
check_docker() {
    print_info "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_success "Docker is installed"
}

# Check if Docker Compose is installed
check_docker_compose() {
    print_info "Checking Docker Compose installation..."
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    print_success "Docker Compose is installed"
}

# Check if required volumes exist
check_volumes() {
    print_info "Checking required Docker volumes..."
    local missing_volumes=()

    for volume in "${REQUIRED_VOLUMES[@]}"; do
        if ! docker volume inspect "$volume" &> /dev/null; then
            missing_volumes+=("$volume")
        fi
    done

    if [ ${#missing_volumes[@]} -gt 0 ]; then
        print_warning "Missing volumes: ${missing_volumes[*]}"
        print_info "Creating missing volumes..."
        for volume in "${missing_volumes[@]}"; do
            docker volume create "$volume"
            print_success "Created volume: $volume"
        done
    else
        print_success "All required volumes exist"
    fi
}

# Check if .env file exists
check_env_file() {
    print_info "Checking environment configuration..."
    if [ ! -f "config.env" ] && [ ! -f ".env" ]; then
        print_error "Neither config.env nor .env file found."
        print_info "Please create config.env with required environment variables:"
        echo ""
        echo "  DB_NAME=arena_db"
        echo "  DB_USER=arena_user"
        echo "  DB_PASSWORD=your_password"
        echo "  DB_HOST=your_db_host"
        echo "  DB_PORT=5432"
        echo "  REDIS_HOST=redis"
        echo "  REDIS_PORT=6379"
        echo "  SECRET_KEY=your_secret_key_here"
        echo "  DEBUG=False"
        echo "  ALLOWED_HOSTS=your-domain.com"
        echo ""
        exit 1
    fi
    print_success "Environment configuration found"
}

# Build Docker images
build_images() {
    print_info "Building Docker images..."
    docker-compose -f "$COMPOSE_FILE" build
    print_success "Docker images built successfully"
}

# Start Redis
start_redis() {
    print_info "Starting Redis..."
    docker-compose -f "$COMPOSE_FILE" up -d redis

    # Wait for Redis to be ready
    print_info "Waiting for Redis to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &> /dev/null; then
            print_success "Redis is ready"
            return 0
        fi
        echo -n "."
        sleep 1
        ((attempt++))
    done

    print_error "Redis failed to start within $max_attempts seconds"
    exit 1
}

# Start web containers
start_web_containers() {
    print_info "Starting Django web containers..."
    docker-compose -f "$COMPOSE_FILE" up -d "${WEB_CONTAINERS[@]}"
    print_success "Django containers started"
}

# Wait for containers to be healthy
wait_for_health() {
    print_info "Waiting for containers to be healthy..."
    local max_attempts=60
    local attempt=1
    local healthy_containers=0

    while [ $attempt -le $max_attempts ]; do
        healthy_containers=0

        for container in "${WEB_CONTAINERS[@]}"; do
            local container_name="arena-$container"
            local health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "starting")

            if [ "$health_status" == "healthy" ]; then
                ((healthy_containers++))
            fi
        done

        echo -ne "\r  Healthy containers: $healthy_containers/${#WEB_CONTAINERS[@]}"

        if [ $healthy_containers -eq ${#WEB_CONTAINERS[@]} ]; then
            echo ""
            print_success "All containers are healthy"
            return 0
        fi

        sleep 2
        ((attempt++))
    done

    echo ""
    print_warning "Not all containers became healthy within $max_attempts attempts"
    print_info "Continuing anyway... Check container health with: docker-compose -f $COMPOSE_FILE ps"
}

# Start Nginx
start_nginx() {
    print_info "Starting Nginx load balancer..."
    docker-compose -f "$COMPOSE_FILE" up -d nginx
    print_success "Nginx started"
}

# Run database migrations
run_migrations() {
    print_info "Running database migrations..."
    if docker-compose -f "$COMPOSE_FILE" exec -T web-1 python manage.py migrate --noinput; then
        print_success "Database migrations completed"
    else
        print_warning "Migration failed or no migrations needed"
    fi
}

# Collect static files
collect_static() {
    print_info "Collecting static files..."
    if docker-compose -f "$COMPOSE_FILE" exec -T web-1 python manage.py collectstatic --noinput; then
        print_success "Static files collected"
    else
        print_warning "Static files collection failed or skipped"
    fi
}

# Test health endpoints
test_health() {
    print_info "Testing health endpoints..."
    local health_url="http://localhost/health/"

    # Wait a bit for nginx to be ready
    sleep 3

    if curl -sf "$health_url" > /dev/null; then
        print_success "Health check passed"
        print_info "Health endpoint response:"
        curl -s "$health_url" | python -m json.tool || curl -s "$health_url"
    else
        print_warning "Health check failed. Nginx might still be starting."
        print_info "Try manually: curl http://localhost/health/"
    fi
}

# Show status
show_status() {
    echo ""
    print_info "Deployment Status:"
    docker-compose -f "$COMPOSE_FILE" ps

    echo ""
    print_info "Quick Commands:"
    echo "  View logs:         docker-compose -f $COMPOSE_FILE logs -f"
    echo "  View web-1 logs:   docker-compose -f $COMPOSE_FILE logs -f web-1"
    echo "  View nginx logs:   docker-compose -f $COMPOSE_FILE logs -f nginx"
    echo "  Stop all:          docker-compose -f $COMPOSE_FILE down"
    echo "  Restart container: docker-compose -f $COMPOSE_FILE restart web-1"
    echo ""
    print_info "Health Check URLs:"
    echo "  http://localhost/health/  - Basic health check"
    echo "  http://localhost/ready/   - Readiness probe"
    echo "  http://localhost/live/    - Liveness probe"
    echo "  http://localhost/status/  - Detailed status"
    echo ""
    print_success "Deployment complete!"
}

# Main deployment flow
main() {
    check_docker
    check_docker_compose
    check_env_file
    check_volumes

    echo ""
    print_info "Starting deployment..."
    echo ""

    build_images
    start_redis
    start_web_containers
    wait_for_health
    start_nginx

    echo ""
    print_info "Running post-deployment tasks..."
    run_migrations
    collect_static

    echo ""
    test_health
    show_status
}

# Handle script arguments
case "${1:-}" in
    start)
        main
        ;;
    stop)
        print_info "Stopping all services..."
        docker-compose -f "$COMPOSE_FILE" down
        print_success "All services stopped"
        ;;
    restart)
        print_info "Restarting services..."
        docker-compose -f "$COMPOSE_FILE" restart
        print_success "Services restarted"
        ;;
    logs)
        docker-compose -f "$COMPOSE_FILE" logs -f
        ;;
    status)
        docker-compose -f "$COMPOSE_FILE" ps
        ;;
    health)
        curl -s http://localhost/health/ | python -m json.tool || curl -s http://localhost/health/
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|status|health}"
        echo ""
        echo "Commands:"
        echo "  start   - Deploy all services"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  logs    - View logs from all services"
        echo "  status  - Show container status"
        echo "  health  - Test health endpoint"
        echo ""
        echo "Example: $0 start"
        exit 1
        ;;
esac
