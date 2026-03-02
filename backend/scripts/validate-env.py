#!/usr/bin/env python3
# Environment Validation Script
# File: scripts/validate-env.py

import os
import sys

REQUIRED_VARS = {
    'common': [
        'SECRET_KEY',
        'DB_NAME',
        'DB_USER',
        'DB_PASSWORD',
        'DB_HOST',
        'REDIS_HOST',
    ],
    'wsgi': [
        'CONTAINER_TYPE',
        'GUNICORN_WORKERS',
    ],
    'asgi': [
        'CONTAINER_TYPE',
        'UVICORN_WORKERS',
    ]
}

def validate_env(env_type='common'):
    """Validate environment variables"""
    missing = []
    
    for var in REQUIRED_VARS.get(env_type, []):
        if not os.getenv(var):
            missing.append(var)
    
    return missing

def main():
    env_type = sys.argv[1] if len(sys.argv) > 1 else 'common'
    
    print(f"Validating {env_type} environment...")
    
    missing = validate_env(env_type)
    
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        sys.exit(1)
    else:
        print("✅ All required environment variables are set")
        
        # Additional checks
        if os.getenv('DEBUG', 'False').lower() == 'true':
            print("⚠️  WARNING: DEBUG is enabled")
        
        if os.getenv('SECRET_KEY') == 'your-super-secret-key-change-this-in-production':
            print("❌ ERROR: SECRET_KEY is still using default value!")
            sys.exit(1)
        
        print("✅ Environment validation passed")

if __name__ == '__main__':
    main()
