# Read settings.py
with open("arena_backend/settings.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the DATABASES section and replace it
old_databases = '''DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT"),
    },
    "aquarium": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("AQUARIUM_DB_NAME"),
        "USER": os.getenv("AQUARIUM_DB_USER"),
        "PASSWORD": os.getenv("AQUARIUM_DB_PASSWORD"),
        "HOST": os.getenv("AQUARIUM_DB_HOST"),
        "PORT": os.getenv("AQUARIUM_DB_PORT"),
    },
}'''

new_databases = '''# Database Configuration - Use SQLite for local dev
USE_SQLITE = os.getenv('USE_SQLITE', 'False') == 'True'

if USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT"),
        },
        "aquarium": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("AQUARIUM_DB_NAME"),
            "USER": os.getenv("AQUARIUM_DB_USER"),
            "PASSWORD": os.getenv("AQUARIUM_DB_PASSWORD"),
            "HOST": os.getenv("AQUARIUM_DB_HOST"),
            "PORT": os.getenv("AQUARIUM_DB_PORT"),
        },
    }'''

content = content.replace(old_databases, new_databases)

# Also need to comment out django.contrib.postgres for SQLite
content = content.replace(
    '    "django.contrib.postgres",',
    '    # "django.contrib.postgres",  # Disabled for SQLite compatibility'
)

# Write back
with open("arena_backend/settings.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Patched settings.py for SQLite support")
