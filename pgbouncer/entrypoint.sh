#!/bin/sh
set -e

# Generate userlist.txt from environment variables
# Format: "username" "md5password"

if [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: DB_USER and DB_PASSWORD environment variables are required"
    exit 1
fi

# Generate MD5 password hash for PgBouncer
# Format: md5 + md5(password + username)
PASSWORD_HASH=$(echo -n "${DB_PASSWORD}${DB_USER}" | md5sum | awk '{print $1}')
MD5_PASSWORD="md5${PASSWORD_HASH}"

# Create userlist.txt
echo "\"${DB_USER}\" \"${MD5_PASSWORD}\"" > /etc/pgbouncer/userlist.txt

echo "Generated PgBouncer userlist for user: ${DB_USER}"

# Replace environment variables in pgbouncer.ini
envsubst < /etc/pgbouncer/pgbouncer.ini.template > /etc/pgbouncer/pgbouncer.ini

# Verify configuration
if [ ! -f /etc/pgbouncer/pgbouncer.ini ]; then
    echo "ERROR: pgbouncer.ini was not created"
    exit 1
fi

if [ ! -f /etc/pgbouncer/userlist.txt ]; then
    echo "ERROR: userlist.txt was not created"
    exit 1
fi

echo "PgBouncer configuration:"
echo "  Listen: 0.0.0.0:6432"
echo "  Database: ${DB_NAME}"
echo "  Backend: ${DB_HOST}:${DB_PORT}"
echo "  Pool mode: transaction"
echo "  Default pool size: 25"
echo "  Max client connections: 1000"

# Start PgBouncer
echo "Starting PgBouncer..."
exec pgbouncer /etc/pgbouncer/pgbouncer.ini
