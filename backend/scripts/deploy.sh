#!/bin/bash
# Main Deployment Script
# File: scripts/deploy.sh

set -e

ENVIRONMENT=\
ACTION=\

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         Chat-Arena-Backend Hybrid Deployment                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Environment: \"
echo "Action: \"
echo ""

# Color codes
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

# Functions
log_info() {
    echo -e "\[INFO]\ \"
}

log_warn() {
    echo -e "\[WARN]\ \"
}

log_error() {
    echo -e "\[ERROR]\ \"
}

# Pre-deployment checks
pre_deploy_checks() {
    log_info "Running pre-deployment checks..."
    
    # Check if docker is running
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running"
        exit 1
    fi
    
    # Check if environment file exists
    if [ ! -f .env.production ]; then
        log_error ".env.production not found"
        log_info "Run: ./scripts/setup-env.sh production"
        exit 1
    fi
    
    # Validate environment
    python3 scripts/validate-env.py common || exit 1
    
    log_info "Pre-deployment checks passed ✓"
}

# Backup database
backup_database() {
    log_info "Creating database backup..."
    
    BACKUP_DIR="./backups"
    BACKUP_FILE="backup_\.sql"
    
    mkdir -p \
    
    docker-compose -f docker-compose.hybrid.yml exec -T postgres \
        pg_dump -U \ \ > "\/\"
    
    log_info "Backup created: \ ✓"
}

# Build containers
build_containers() {
    log_info "Building Docker containers..."
    
    docker-compose -f docker-compose.hybrid.yml build \
        --no-cache \
        --parallel
    
    log_info "Containers built ✓"
}

# Deploy
deploy() {
    log_info "Deploying application..."
    
    # Stop old containers (if any)
    docker-compose -f docker-compose.hybrid.yml down
    
    # Start services
    docker-compose -f docker-compose.hybrid.yml up -d
    
    log_info "Waiting for services to start..."
    sleep 10
    
    # Run migrations
    log_info "Running database migrations..."
    docker-compose -f docker-compose.hybrid.yml exec -T backend-wsgi \
        python manage.py migrate --noinput
    
    # Collect static files
    log_info "Collecting static files..."
    docker-compose -f docker-compose.hybrid.yml exec -T backend-wsgi \
        python manage.py collectstatic --noinput --clear
    
    log_info "Deployment complete ✓"
}

# Health check
health_check() {
    log_info "Running health checks..."
    
    # Check WSGI
    if curl -f http://localhost/health/ > /dev/null 2>&1; then
        log_info "WSGI health check passed ✓"
    else
        log_error "WSGI health check failed ✗"
        return 1
    fi
    
    # Check ASGI
    if docker-compose -f docker-compose.hybrid.yml exec -T backend-asgi \
        curl -f http://localhost:8001/health/ > /dev/null 2>&1; then
        log_info "ASGI health check passed ✓"
    else
        log_error "ASGI health check failed ✗"
        return 1
    fi
    
    log_info "All health checks passed ✓"
}

# Rollback
rollback() {
    log_warn "Rolling back deployment..."
    
    # Stop current containers
    docker-compose -f docker-compose.hybrid.yml down
    
    # Restore previous version (you'll need to tag images)
    docker-compose -f docker-compose.hybrid.yml pull
    docker-compose -f docker-compose.hybrid.yml up -d
    
    log_info "Rollback complete ✓"
}

# Show logs
show_logs() {
    SERVICE=\
    
    if [ -z "\" ]; then
        docker-compose -f docker-compose.hybrid.yml logs -f --tail=100
    else
        docker-compose -f docker-compose.hybrid.yml logs -f --tail=100 \
    fi
}

# Main execution
case \ in
    deploy)
        pre_deploy_checks
        backup_database
        build_containers
        deploy
        health_check
        
        echo ""
        log_info "═══════════════════════════════════════════════════════"
        log_info "  Deployment successful! 🎉"
        log_info "═══════════════════════════════════════════════════════"
        log_info "Services:"
        log_info "  • Nginx: http://localhost"
        log_info "  • WSGI: backend-wsgi:8000"
        log_info "  • ASGI: backend-asgi:8001"
        log_info "  • PostgreSQL: postgres:5432"
        log_info "  • Redis: redis:6379"
        log_info ""
        log_info "Useful commands:"
        log_info "  • View logs: ./scripts/deploy.sh production logs"
        log_info "  • Restart: docker-compose -f docker-compose.hybrid.yml restart"
        log_info "  • Scale WSGI: docker-compose -f docker-compose.hybrid.yml up -d --scale backend-wsgi=3"
        ;;
        
    rollback)
        rollback
        health_check
        ;;
        
    logs)
        show_logs \
        ;;
        
    status)
        docker-compose -f docker-compose.hybrid.yml ps
        ;;
        
    restart)
        log_info "Restarting services..."
        docker-compose -f docker-compose.hybrid.yml restart
        ;;
        
    stop)
        log_info "Stopping services..."
        docker-compose -f docker-compose.hybrid.yml down
        ;;
        
    *)
        echo "Usage: ./scripts/deploy.sh [environment] [action]"
        echo ""
        echo "Actions:"
        echo "  deploy   - Deploy application (default)"
        echo "  rollback - Rollback to previous version"
        echo "  logs     - View logs"
        echo "  status   - Show service status"
        echo "  restart  - Restart services"
        echo "  stop     - Stop all services"
        exit 1
        ;;
esac
