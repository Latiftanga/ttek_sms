from django.core.files.storage import FileSystemStorage
from django.db import connection
from django_tenants.files.storage import TenantFileSystemStorage


class CustomSchemaStorage(FileSystemStorage):
    """
    Custom storage backend that uses FileSystemStorage for public schema
    and TenantFileSystemStorage for tenant schemas.

    Inherits from FileSystemStorage to ensure all required methods are available.
    """

    def _get_storage_backend(self):
        schema_name = connection.schema_name
        if schema_name == 'public':
            return FileSystemStorage()
        else:
            return TenantFileSystemStorage()

    def save(self, name, content, max_length=None):
        storage_backend = self._get_storage_backend()
        return storage_backend.save(name, content, max_length)

    def url(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.url(name)

    def path(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.path(name)

    def exists(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.exists(name)

    def open(self, name, mode='rb'):
        storage_backend = self._get_storage_backend()
        return storage_backend.open(name, mode)

    def size(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.size(name)

    def listdir(self, path):
        storage_backend = self._get_storage_backend()
        return storage_backend.listdir(path)

    def generate_filename(self, filename):
        storage_backend = self._get_storage_backend()
        return storage_backend.generate_filename(filename)

    def delete(self, name):
        storage_backend = self._get_storage_backend()
        storage_backend.delete(name)

    def get_accessed_time(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.get_accessed_time(name)

    def get_created_time(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.get_created_time(name)

    def get_modified_time(self, name):
        storage_backend = self._get_storage_backend()
        return storage_backend.get_modified_time(name)