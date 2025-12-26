import threading

# create thread local storage object
_thread_locals = threading.local()

# SET the tenant
def set_current_tenant(tenant):
    """
    Sets the current tenant for the current thread.
    """
    _thread_locals.tenant = tenant


# GET the tenant
def get_current_tenant():
    """
    Returns the current tenant for the current thread.
    """
    return getattr(_thread_locals, "tenant", None)

# CLEAR the tenant
def clear_current_tenant():
    """
    Clears the current tenant for the current thread.
    """
    if hasattr(_thread_locals, "tenant"):
        del _thread_locals.tenant