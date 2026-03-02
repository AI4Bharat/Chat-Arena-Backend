# Uvicorn Configuration for ASGI
# File: config/uvicorn.conf.py

import os

# Server socket
host = '0.0.0.0'
port = 8001

# Worker processes
workers = int(os.getenv('UVICORN_WORKERS', 2))

# Event loop
loop = 'uvloop'  # uvloop for better performance (Linux only)
# loop = 'asyncio'  # Fallback for Windows

# HTTP
http = 'httptools'  # Faster HTTP parsing

# Timeouts
timeout_keep_alive = 5
timeout_notify = 30

# Limits
limit_concurrency = 200
limit_max_requests = None
backlog = 2048

# Logging
log_level = os.getenv('LOG_LEVEL', 'info').lower()
access_log = True
log_config = None  # Use default logging config

# Reload on code changes (development only)
reload = os.getenv('DEBUG', 'False').lower() == 'true'
reload_dirs = ['./'] if reload else None

# SSL (if needed)
ssl_keyfile = os.getenv('SSL_KEYFILE', None)
ssl_certfile = os.getenv('SSL_CERTFILE', None)

# Headers
server_header = True
date_header = True

# Process
use_colors = True
