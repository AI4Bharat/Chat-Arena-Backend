# Rollback Scripts

## For Windows Development
These scripts are designed for Linux production. 
For Windows development rollback, use:

\\\powershell
# Stop containers
docker-compose down

# Checkout previous commit
git log --oneline -5
git checkout <previous-commit-hash>

# Restart
docker-compose up -d
\\\

## For Linux Production
See the bash scripts in docs/migration/rollback-plan.md

The actual rollback scripts will be created during Phase 4 (Docker setup).
