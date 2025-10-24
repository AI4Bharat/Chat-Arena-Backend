"""
Database Router for Read/Write Splitting

This router automatically directs:
- Read operations (SELECT) to read replicas
- Write operations (INSERT, UPDATE, DELETE) to the primary database

Usage:
1. Set DB_READ_HOST environment variable with replica hostname
2. Django will automatically use read_replica database for read operations
3. All writes go to the default (primary) database

Benefits:
- Reduces load on primary database
- Improves read performance with dedicated replicas
- Transparent to application code
"""

import random


class ReadReplicaRouter:
    """
    A router to control database operations for read/write splitting.

    Routes read queries to read replicas and write queries to the primary database.
    """

    def db_for_read(self, model, **hints):
        """
        Route read operations to read replica if available.

        If read_replica is not configured, falls back to default.
        """
        # Check if model explicitly requires primary database
        if hints.get('require_primary', False):
            return 'default'

        # Check if read_replica database exists in settings
        from django.conf import settings
        if 'read_replica' in settings.DATABASES:
            # You can add multiple read replicas and randomly select one
            # For now, just use the single read_replica
            return 'read_replica'

        # Fallback to default database
        return 'default'

    def db_for_write(self, model, **hints):
        """
        All write operations go to the primary (default) database.
        """
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations between objects if they're in the same database.
        """
        # Get databases for both objects
        db1 = obj1._state.db or 'default'
        db2 = obj2._state.db or 'default'

        # Allow if both use default or both use replicas
        if db1 in ('default', 'read_replica') and db2 in ('default', 'read_replica'):
            return True

        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure migrations only run on the primary database.

        Read replicas should be synchronized from the primary.
        """
        # Only allow migrations on the default (primary) database
        return db == 'default'


class MultiReadReplicaRouter(ReadReplicaRouter):
    """
    Enhanced router that supports multiple read replicas with random selection.

    Usage:
    Set multiple read replicas in settings:
    - DB_READ_HOST_1, DB_READ_HOST_2, etc.

    This router will randomly distribute reads across available replicas.
    """

    def db_for_read(self, model, **hints):
        """
        Route read operations to a randomly selected read replica.
        """
        # Check if model explicitly requires primary database
        if hints.get('require_primary', False):
            return 'default'

        # Get all read replica databases from settings
        from django.conf import settings
        read_dbs = [
            db_name for db_name in settings.DATABASES.keys()
            if db_name.startswith('read_replica')
        ]

        if read_dbs:
            # Randomly select a read replica for load distribution
            return random.choice(read_dbs)

        # Fallback to default database
        return 'default'


# Utility function to force using primary database
def use_primary_db():
    """
    Context manager to force database queries to use the primary database.

    Usage:
        with use_primary_db():
            # These queries will use the primary database
            User.objects.get(id=1)
    """
    from django.db import router

    class ForcePrimaryRouter:
        def db_for_read(self, model, **hints):
            return 'default'

        def db_for_write(self, model, **hints):
            return 'default'

    # This is a simplified version. For production, you might want to use
    # django.db.router.use_db('default') if using Django 4.2+
    return router.override(ForcePrimaryRouter())
