FROM edoburu/pgbouncer:latest

# Copy PgBouncer configuration
COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini.template
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD psql "postgresql://${DB_USER}:${DB_PASSWORD}@localhost:6432/${DB_NAME}?sslmode=disable" -c "SELECT 1" || exit 1

EXPOSE 6432

ENTRYPOINT ["/entrypoint.sh"]
