from django.db import models


class TenantManager(models.Manager):
    """Manager that automatically filters by current tenant/school"""

    def get_queryset(self):
        # Get the current request's tenant
        # Note: This requires middleware to set the tenant
        from threading import local
        _thread_local = local()

        if hasattr(_thread_local, 'tenant') and _thread_local.tenant:
            return super().get_queryset().filter(school=_thread_local.tenant)
        return super().get_queryset()
