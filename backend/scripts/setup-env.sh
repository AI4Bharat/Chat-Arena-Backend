#!/bin/bash
# Environment Setup Script
# File: scripts/setup-env.sh

set -e

ENV_TYPE=\

echo "Setting up environment for: \"

case \ in
  development)
    if [ ! -f .env ]; then
      echo "Creating development .env from template..."
      cp .env.example .env
      echo "✅ .env created. Please update with your local settings."
    else
      echo "⚠️  .env already exists. Skipping."
    fi
    ;;
    
  production)
    echo "Setting up production environment files..."
    
    # Check if production env exists
    if [ ! -f .env.production ]; then
      echo "Creating .env.production from template..."
      cp .env.production.example .env.production
      echo "⚠️  IMPORTANT: Update .env.production with actual values!"
    fi
    
    # Create WSGI env
    if [ ! -f .env.wsgi ]; then
      cat .env.production > .env.wsgi
      cat .env.wsgi.example >> .env.wsgi
      echo "✅ .env.wsgi created"
    fi
    
    # Create ASGI env
    if [ ! -f .env.asgi ]; then
      cat .env.production > .env.asgi
      cat .env.asgi.example >> .env.asgi
      echo "✅ .env.asgi created"
    fi
    
    echo ""
    echo "📝 Next steps:"
    echo "  1. Edit .env.production with production values"
    echo "  2. Update SECRET_KEY, DB_PASSWORD, API keys"
    echo "  3. Set ALLOWED_HOSTS to your domain"
    echo "  4. Review and update .env.wsgi and .env.asgi"
    ;;
    
  *)
    echo "Usage: ./scripts/setup-env.sh [development|production]"
    exit 1
    ;;
esac

echo ""
echo "✅ Environment setup complete!"
