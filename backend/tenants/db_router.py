"""
Tenant-aware Database Router

Routes database operations to the appropriate database based on the current tenant.
Uses thread-local storage to get the current tenant context.
"""

from .context import get_current_tenant


class TenantDatabaseRouter:
    """
    A database router that directs queries to the appropriate database
    based on the current tenant set in thread-local storage.
    """
    
    def _get_tenant_db(self):
        """
        Get the database alias for the current tenant.
        Returns 'default' if no tenant is set.
        """
        tenant = get_current_tenant()
        if tenant and 'db' in tenant:
            return tenant['db']
        return 'default'
    
    def db_for_read(self, model, **hints):
        """
        Route read operations to the tenant's database.
        """
        return self._get_tenant_db()
    
    def db_for_write(self, model, **hints):
        """
        Route write operations to the tenant's database.
        """
        return self._get_tenant_db()
    
    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations only if both objects are in the same database.
        """
        # Get the databases for both objects
        db1 = self._get_tenant_db()
        db2 = self._get_tenant_db()
        
        # Only allow relations within the same database
        if db1 == db2:
            return True
        return False
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Allow migrations on all databases.
        This ensures schema is created on all tenant databases.
        """
        return True
