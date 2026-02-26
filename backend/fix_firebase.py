import os

# Read the file
with open("user/services.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the line with "cred = credentials.Certificate(cred_path)"
new_lines = []
skip_next = False

for i, line in enumerate(lines):
    if "cred = credentials.Certificate(cred_path)" in line:
        # Insert the check before this line
        indent = len(line) - len(line.lstrip())
        new_lines.append(" " * indent + "# Check if Firebase credentials exist\n")
        new_lines.append(" " * indent + "if os.path.exists(cred_path):\n")
        new_lines.append(" " * (indent + 4) + "cred = credentials.Certificate(cred_path)\n")
        skip_next = True
    elif skip_next and "firebase_admin.initialize_app" in line:
        # This is the initialize_app line
        indent = len(line) - len(line.lstrip())
        new_lines.append(" " * (indent + 4) + "firebase_admin.initialize_app(cred)\n")
        new_lines.append(" " * indent + "else:\n")
        new_lines.append(" " * (indent + 4) + "import logging\n")
        new_lines.append(" " * (indent + 4) + "logger = logging.getLogger(__name__)\n")
        new_lines.append(" " * (indent + 4) + 'logger.warning("Firebase disabled for local dev")\n')
        skip_next = False
    elif not ("cred = credentials.Certificate" in line or (skip_next and "firebase_admin.initialize_app" in line)):
        new_lines.append(line)

# Write back
with open("user/services.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("✅ Fixed user/services.py")
