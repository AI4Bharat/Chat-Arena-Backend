# Check and install async dependencies
# File: scripts/check_async_deps.py

import subprocess
import sys

required_packages = {
    'httpx': 'httpx',  # For async HTTP requests
    'anthropic': 'anthropic',  # Anthropic async client
    'openai': 'openai>=1.0.0',  # OpenAI async client
    'aiohttp': 'aiohttp',  # Already have, but verify
    'uvicorn[standard]': 'uvicorn',  # ASGI server
    'channels': 'channels',  # Already have
    'channels-redis': 'channels_redis',  # For Channels layer
}

def check_package(package_name):
    """Check if package is installed"""
    try:
        __import__(package_name.replace('-', '_'))
        return True
    except ImportError:
        return False

def main():
    print("Checking async dependencies...")
    print("=" * 60)
    
    missing = []
    installed = []
    
    for pip_name, import_name in required_packages.items():
        if check_package(import_name):
            print(f"✅ {pip_name} - installed")
            installed.append(pip_name)
        else:
            print(f"❌ {pip_name} - MISSING")
            missing.append(pip_name)
    
    print("=" * 60)
    print(f"Installed: {len(installed)}/{len(required_packages)}")
    
    if missing:
        print(f"\n⚠️  Missing {len(missing)} packages")
        print("\nInstall command:")
        print(f"pip install {' '.join(missing)}")
        return 1
    else:
        print("\n✅ All async dependencies installed!")
        return 0

if __name__ == '__main__':
    sys.exit(main())
