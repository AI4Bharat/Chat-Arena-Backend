#!/usr/bin/env python3
"""
Automatically add ulimits to all containers in docker-compose.loadbalanced.yml
This fixes "Too many open files" errors during load testing
"""

import re
import sys
from datetime import datetime

def add_ulimits_to_compose(filename='docker-compose.loadbalanced.yml'):
    """
    Add ulimits section to all web containers, nginx, redis, and pgbouncer
    """
    print("=" * 50)
    print("Adding ulimits to docker-compose.yml")
    print("=" * 50)
    print("")

    # Read the file
    try:
        with open(filename, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: {filename} not found!")
        print(f"   Make sure you're in the Chat-Arena-Backend directory")
        return False

    # Backup the original file
    backup_filename = f"{filename}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(backup_filename, 'w') as f:
        f.write(content)
    print(f"✓ Backup created: {backup_filename}")
    print("")

    # Check if ulimits already exist
    if 'ulimits:' in content and 'nofile:' in content:
        print("⚠ Warning: ulimits already exist in the file")
        response = input("Do you want to continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return False
        print("")

    # Define the ulimits block to add
    ulimits_block = """    ulimits:
      nofile:
        soft: 65535
        hard: 65535"""

    containers_updated = 0

    # Pattern 1: Add ulimits to web containers (before 'deploy:')
    # Matches: web-1 through web-10 (and any additional web-N)
    pattern_web = re.compile(
        r'(  web-\d+:.*?)(    deploy:)',
        re.DOTALL
    )

    def replace_web(match):
        nonlocal containers_updated
        service_block = match.group(1)
        deploy_line = match.group(2)

        # Check if ulimits already exists in this service
        if 'ulimits:' in service_block:
            return match.group(0)  # No change

        # Add ulimits before deploy
        containers_updated += 1
        return f"{service_block}{ulimits_block}\n{deploy_line}"

    content = pattern_web.sub(replace_web, content)

    # Pattern 2: Add ulimits to nginx (before 'ports:')
    pattern_nginx = re.compile(
        r'(  nginx:.*?)(    ports:)',
        re.DOTALL
    )

    def replace_nginx(match):
        nonlocal containers_updated
        service_block = match.group(1)
        ports_line = match.group(2)

        if 'ulimits:' in service_block:
            return match.group(0)

        containers_updated += 1
        return f"{service_block}{ulimits_block}\n{ports_line}"

    content = pattern_nginx.sub(replace_nginx, content)

    # Pattern 3: Add ulimits to redis (before 'deploy:' or 'healthcheck:')
    pattern_redis = re.compile(
        r'(  redis:.*?)(    (?:deploy|healthcheck):)',
        re.DOTALL
    )

    def replace_redis(match):
        nonlocal containers_updated
        service_block = match.group(1)
        next_section = match.group(2)

        if 'ulimits:' in service_block:
            return match.group(0)

        containers_updated += 1
        return f"{service_block}{ulimits_block}\n{next_section}"

    content = pattern_redis.sub(replace_redis, content)

    # Pattern 4: Add ulimits to pgbouncer (before 'deploy:')
    pattern_pgbouncer = re.compile(
        r'(  pgbouncer:.*?)(    deploy:)',
        re.DOTALL
    )

    def replace_pgbouncer(match):
        nonlocal containers_updated
        service_block = match.group(1)
        deploy_line = match.group(2)

        if 'ulimits:' in service_block:
            return match.group(0)

        containers_updated += 1
        return f"{service_block}{ulimits_block}\n{deploy_line}"

    content = pattern_pgbouncer.sub(replace_pgbouncer, content)

    # Write the updated content
    with open(filename, 'w') as f:
        f.write(content)

    print(f"✓ Updated {containers_updated} containers with ulimits")
    print("")
    print("Containers updated:")
    print("  - All web-* containers (web-1 through web-10)")
    print("  - nginx")
    print("  - redis")
    print("  - pgbouncer")
    print("")
    print("=" * 50)
    print("Update Complete!")
    print("=" * 50)
    print("")
    print("Next steps:")
    print("1. Review changes: diff docker-compose.loadbalanced.yml.backup.* docker-compose.loadbalanced.yml")
    print("2. Rebuild containers: docker compose -f docker-compose.loadbalanced.yml build")
    print("3. Restart: docker compose -f docker-compose.loadbalanced.yml down && docker compose -f docker-compose.loadbalanced.yml up -d")
    print("4. Verify: docker compose -f docker-compose.loadbalanced.yml exec web-1 ulimit -n")
    print("   (Should output: 65535)")
    print("")

    return True


if __name__ == "__main__":
    import os

    # Check if file exists
    if not os.path.exists('docker-compose.loadbalanced.yml'):
        print("❌ Error: docker-compose.loadbalanced.yml not found!")
        print("")
        print("Please run this script from the Chat-Arena-Backend directory:")
        print("  cd Chat-Arena-Backend")
        print("  python3 add-ulimits-to-compose.py")
        sys.exit(1)

    success = add_ulimits_to_compose()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
