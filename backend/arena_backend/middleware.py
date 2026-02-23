from django.middleware.csrf import CsrfViewMiddleware


class ApiCsrfExemptMiddleware(CsrfViewMiddleware):
    """
    CSRF middleware that only enforces CSRF on Django admin.

    All API endpoints use token-based authentication (JWT / Anonymous Token),
    not cookie-based sessions, so CSRF protection is unnecessary for them
    and causes 403 errors for cross-origin SPA clients.
    """

    def process_view(self, request, callback, callback_args, callback_kwargs):
        # Only enforce CSRF on Django admin and accounts (browser form-based)
        if request.path.startswith(('/admin/', '/accounts/')):
            return super().process_view(request, callback, callback_args, callback_kwargs)
        return None
