import re
from django.http import JsonResponse
from .config import get_tenant_by_slug
from .context import set_current_tenant, clear_current_tenant

# Capture the tenant slug from the URL
# Matches /{tenant}/... where tenant is the first path segment
TENANT_URL_PATTERN = re.compile(r'^/([a-zA-Z0-9_-]+)/')

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):

        # Match the tenant slug from the URL
        match = TENANT_URL_PATTERN.match(request.path)

        if match:
            # URL matches /{something}/... pattern
            potential_tenant_slug = match.group(1)
            tenant = get_tenant_by_slug(potential_tenant_slug)

            if tenant is not None:
                # Valid tenant found - set context
                set_current_tenant(tenant)
                request.tenant = tenant
            else:
                # Not a valid tenant - pass through to normal routing
                # This allows /admin/, /health/, etc. to work normally
                request.tenant = None

        else:
            # No match - pass through to normal routing
            request.tenant = None
        
        try:
            response = self.get_response(request)
        finally:
            # Ensure the tenant is cleared after each request
            clear_current_tenant()
        
        return response