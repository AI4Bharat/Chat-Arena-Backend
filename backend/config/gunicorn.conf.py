# Gunicorn Configuration for WSGI
# File: config/gunicorn.conf.py

import multiprocessing
import os

# Server socket
bind = '0.0.0.0:8000'
backlog = 2048

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2))
worker_class = 'sync'
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 5

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# Process naming
proc_name = 'arena-wsgi'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Reload on code changes (development only)
reload = os.getenv('DEBUG', 'False').lower() == 'true'
reload_engine = 'auto'

# Server hooks
def on_starting(server):
    server.log.info('Starting Arena Backend WSGI server')

def on_reload(server):
    server.log.info('Reloading Arena Backend WSGI server')

def when_ready(server):
    server.log.info('Arena Backend WSGI server is ready. Spawning workers')

def pre_fork(server, worker):
    server.log.info(f'Worker spawned (pid: {worker.pid})')

def post_fork(server, worker):
    server.log.info(f'Worker spawned (pid: {worker.pid})')

def worker_int(worker):
    worker.log.info('Worker received INT or QUIT signal')

def worker_abort(worker):
    worker.log.info('Worker received SIGABRT signal')
