import os

def load_tenant_registry():
    """
    Loads the tenant registry from the ACTIVE_TENANTS environment variable.
    Parses the comma-separated string of IDs into a dictionary structure.
    Returns a mapping of active tenant identifiers to their configurations.
    """

    registry = {}

    active_tenants = os.getenv("ACTIVE_TENANTS", "")
    if not active_tenants:
        return registry

    tenant_ids = active_tenants.split(",")

    for tenant_id in tenant_ids:
        tenant_id = tenant_id.strip()

        slug = os.getenv(f"TENANT_{tenant_id}_SLUG")
        name = os.getenv(f"TENANT_{tenant_id}_NAME", tenant_id)

        if slug:
            registry[slug] = {
                "id": tenant_id,
                "name": name,
                "slug": slug,
                "db": os.getenv(f"TENANT_{tenant_id}_DB", "default")
            }
    return registry


#Load the registry once when the module is imported
TENANT_REGISTRY = load_tenant_registry()

def get_tenant_by_slug(slug):
    """
    Retrieves a tenant configuration by its slug.
    Returns the tenant configuration if found, otherwise None.
    """
    return TENANT_REGISTRY.get(slug)
