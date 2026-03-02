import os
import django
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arena_backend.settings')
django.setup()

from django.urls import get_resolver
from django.conf import settings
import re

def extract_endpoints():
    """Extract all URL patterns from Django"""
    url_patterns = get_resolver().url_patterns
    endpoints = []
    
    def extract_pattern(pattern, prefix=''):
        try:
            if hasattr(pattern, 'url_patterns'):
                # It's an include(), recurse into it
                new_prefix = prefix + str(pattern.pattern)
                for p in pattern.url_patterns:
                    extract_pattern(p, new_prefix)
            else:
                # It's an endpoint
                path = prefix + str(pattern.pattern)
                name = pattern.name if hasattr(pattern, 'name') else 'unnamed'
                
                # Try to get the view
                if hasattr(pattern, 'callback'):
                    view = pattern.callback
                    view_name = f"{view.__module__}.{view.__name__}"
                else:
                    view_name = "Unknown"
                
                endpoints.append({
                    'path': path.replace('^', '').replace('$', ''),
                    'name': name,
                    'view': view_name
                })
        except Exception as e:
            pass
    
    for pattern in url_patterns:
        extract_pattern(pattern)
    
    return endpoints

def classify_endpoint(path, view):
    """Classify endpoint as WSGI or ASGI based on characteristics"""
    
    # ASGI indicators (streaming/long-lived/async-heavy)
    asgi_keywords = [
        'stream', 'websocket', 'ws/', 'compare', 'tts', 
        'asr', 'audio', 'generate', 'chat'
    ]
    
    # WSGI indicators (CRUD/admin/auth/sync)
    wsgi_keywords = [
        'admin', 'auth', 'login', 'logout', 'register',
        'list', 'create', 'update', 'delete', 'retrieve',
        'leaderboard', 'health', 'metrics', 'feedback'
    ]
    
    path_lower = path.lower()
    view_lower = view.lower()
    
    # Check for ASGI patterns
    for keyword in asgi_keywords:
        if keyword in path_lower or keyword in view_lower:
            return 'ASGI', keyword
    
    # Check for WSGI patterns
    for keyword in wsgi_keywords:
        if keyword in path_lower or keyword in view_lower:
            return 'WSGI', keyword
    
    # Default to WSGI for safety
    return 'WSGI', 'default'

def generate_classification_doc():
    """Generate markdown documentation"""
    print("Extracting endpoints...")
    endpoints = extract_endpoints()
    
    # Classify endpoints
    classified = {
        'ASGI': [],
        'WSGI': [],
        'WEBSOCKET': []
    }
    
    for ep in endpoints:
        if 'ws/' in ep['path'] or 'websocket' in ep['path'].lower():
            classified['WEBSOCKET'].append(ep)
        else:
            category, reason = classify_endpoint(ep['path'], ep['view'])
            ep['reason'] = reason
            classified[category].append(ep)
    
    # Generate markdown
    doc = []
    doc.append("# Endpoint Classification Document")
    doc.append(f"\n**Generated:** {os.popen('date /t').read().strip()}")
    doc.append(f"\n**Project:** Chat-Arena-Backend Hybrid WSGI+ASGI Migration")
    doc.append("\n---\n")
    
    doc.append("## Overview\n")
    doc.append("This document classifies all endpoints in the Chat-Arena-Backend ")
    doc.append("for the hybrid WSGI+ASGI migration.\n")
    
    doc.append(f"\n**Total Endpoints:** {len(endpoints)}")
    doc.append(f"\n- **ASGI Targets:** {len(classified['ASGI'])}")
    doc.append(f"\n- **WebSocket Targets:** {len(classified['WEBSOCKET'])}")
    doc.append(f"\n- **WSGI Targets:** {len(classified['WSGI'])}\n")
    
    doc.append("\n---\n")
    
    # ASGI Section
    doc.append("## ASGI Endpoints (Async/Streaming)\n")
    doc.append("These endpoints handle streaming responses, long-lived connections, ")
    doc.append("or external API-heavy operations.\n")
    doc.append("\n| Path | View | Rationale |\n")
    doc.append("|------|------|----------|\n")
    
    for ep in sorted(classified['ASGI'], key=lambda x: x['path']):
        path = ep['path'][:60]
        view = ep['view'].split('.')[-1][:40]
        reason = ep.get('reason', 'streaming')
        doc.append(f"| `{path}` | {view} | {reason} |\n")
    
    # WebSocket Section
    doc.append("\n## WebSocket Endpoints\n")
    doc.append("These endpoints require ASGI for WebSocket protocol support.\n")
    doc.append("\n| Path | View | Type |\n")
    doc.append("|------|------|------|\n")
    
    for ep in sorted(classified['WEBSOCKET'], key=lambda x: x['path']):
        path = ep['path'][:60]
        view = ep['view'].split('.')[-1][:40]
        doc.append(f"| `{path}` | {view} | WebSocket |\n")
    
    # WSGI Section
    doc.append("\n## WSGI Endpoints (Sync/CRUD)\n")
    doc.append("These endpoints handle short-lived, database/CPU-bound operations.\n")
    doc.append("\n| Path | View | Category |\n")
    doc.append("|------|------|----------|\n")
    
    for ep in sorted(classified['WSGI'], key=lambda x: x['path'])[:50]:  # Limit to 50 for brevity
        path = ep['path'][:60]
        view = ep['view'].split('.')[-1][:40]
        reason = ep.get('reason', 'crud')
        doc.append(f"| `{path}` | {view} | {reason} |\n")
    
    if len(classified['WSGI']) > 50:
        doc.append(f"\n*... and {len(classified['WSGI']) - 50} more WSGI endpoints*\n")
    
    # Routing Rules
    doc.append("\n---\n")
    doc.append("## Nginx Routing Rules\n")
    doc.append("\nBased on this classification, configure Nginx as follows:\n")
    doc.append("\n```nginx\n")
    doc.append("# Route to ASGI upstream\n")
    doc.append("location ~ ^/api/(chat|stream|tts|asr|compare) {\n")
    doc.append("    proxy_pass http://asgi_upstream;\n")
    doc.append("}\n\n")
    doc.append("# Route WebSockets to ASGI\n")
    doc.append("location /ws/ {\n")
    doc.append("    proxy_pass http://asgi_upstream;\n")
    doc.append("    proxy_http_version 1.1;\n")
    doc.append("    proxy_set_header Upgrade $http_upgrade;\n")
    doc.append("    proxy_set_header Connection \"upgrade\";\n")
    doc.append("}\n\n")
    doc.append("# Route everything else to WSGI\n")
    doc.append("location / {\n")
    doc.append("    proxy_pass http://wsgi_upstream;\n")
    doc.append("}\n")
    doc.append("```\n")
    
    return ''.join(doc)

if __name__ == "__main__":
    doc_content = generate_classification_doc()
    print(doc_content)
    print("\n" + "="*80)
    print("Documentation generated successfully!")
