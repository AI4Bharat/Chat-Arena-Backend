import contextvars
import functools
import logging

logger = logging.getLogger(__name__)

# create context variable
_tenant_context = contextvars.ContextVar('current_tenant', default=None)


# SET the tenant
def set_current_tenant(tenant):
    """
    Sets the current tenant for the current context.
    """
    _tenant_context.set(tenant)


# GET the tenant
def get_current_tenant():
    """
    Returns the current tenant for the current context.
    """
    return _tenant_context.get()


# CLEAR the tenant
def clear_current_tenant():
    """
    Clears the current tenant for the current context.
    """
    _tenant_context.set(None)


def tenant_aware_task(func):
    """
    Decorator for Celery tasks that should run across all tenants
    including the default database.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from tenants.config import TENANT_REGISTRY

        # 1. Run on default database
        clear_current_tenant()
        try:
            logger.info(f"Running task {func.__name__} on default database")
            func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error executing task {func.__name__} on default database: {e}")
        finally:
            clear_current_tenant()

        # 2. Run on all configured tenants
        for tenant in TENANT_REGISTRY.values():
            set_current_tenant(tenant)
            try:
                logger.info(f"Running task {func.__name__} on tenant: {tenant['slug']}")
                func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error executing task {func.__name__} on tenant {tenant['slug']}: {e}")
            finally:
                clear_current_tenant()

    return wrapper
