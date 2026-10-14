"""Acces au Data Lake (Managed Identity ou connection string locale) et a PostgreSQL."""
from __future__ import annotations

from .config import Settings

# Chaine de connexion publique et documentee d'Azurite (emulateur local), identique pour tous.
AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)


def resolve_connection_string(value: str) -> str:
    """Etend le raccourci UseDevelopmentStorage=true utilise dans les TP (non gere par le SDK v12)."""
    if value.strip().lower() == "usedevelopmentstorage=true":
        return AZURITE_CONNECTION_STRING
    return value


def blob_service(settings: Settings):
    from azure.storage.blob import BlobServiceClient

    if settings.storage_connection_string:
        return BlobServiceClient.from_connection_string(
            resolve_connection_string(settings.storage_connection_string)
        )

    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    if settings.azure_client_id:
        credential = ManagedIdentityCredential(client_id=settings.azure_client_id)
    else:
        credential = DefaultAzureCredential()
    return BlobServiceClient(settings.storage_url, credential=credential)


def put_blob(settings: Settings, container: str, path: str, data: bytes) -> None:
    """Depose un blob. En local (Azurite), cree le container s'il n'existe pas."""
    from azure.core.exceptions import ResourceNotFoundError

    service = blob_service(settings)
    client = service.get_blob_client(container, path)
    try:
        client.upload_blob(data, overwrite=True)
    except ResourceNotFoundError:
        if not settings.storage_connection_string:
            raise
        service.create_container(container)
        client.upload_blob(data, overwrite=True)


def get_blob(settings: Settings, container: str, path: str) -> bytes:
    return blob_service(settings).get_blob_client(container, path).download_blob().readall()


def pg_connect(settings: Settings):
    import psycopg2

    return psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_db,
        user=settings.pg_user,
        password=settings.pg_password,
    )
