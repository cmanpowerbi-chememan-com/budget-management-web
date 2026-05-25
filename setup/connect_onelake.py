"""
Connect to OneLake (Microsoft Fabric) and list available paths.

Workspace: budget_management_web
Lakehouse:  lakehouse

Usage:
    python setup/connect_onelake.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import msal
from azure.storage.filedatalake import DataLakeServiceClient
from azure.core.credentials import AccessToken
import time

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

TENANT_ID = os.environ["ENTRA_TENANT_ID"]
CLIENT_ID = os.environ["ENTRA_CLIENT_ID"]
CLIENT_SECRET = os.environ["ENTRA_CLIENT_SECRET"]
WORKSPACE_ID = os.environ["FABRIC_WORKSPACE_ID"]
LAKEHOUSE_ID = os.environ["FABRIC_LAKEHOUSE_ID"]

ONELAKE_ENDPOINT = "https://onelake.dfs.fabric.microsoft.com"
SCOPE = ["https://storage.azure.com/.default"]


def get_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )
    result = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Token acquisition failed: {result.get('error_description')}")
    return result["access_token"]


class _StaticTokenCredential:
    """Wraps a plain token string into the azure-sdk credential interface."""

    def __init__(self, token: str):
        self._token = token

    def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self._token, int(time.time()) + 3600)


def get_client(token: str) -> DataLakeServiceClient:
    return DataLakeServiceClient(
        account_url=ONELAKE_ENDPOINT,
        credential=_StaticTokenCredential(token),
    )


def main():
    print("Acquiring token via service principal...")
    token = get_token()
    print("Token acquired OK")

    client = get_client(token)
    fs_client = client.get_file_system_client(file_system=WORKSPACE_ID)

    # OneLake paths use Lakehouse GUID (not friendly name) when workspace uses GUID filesystem
    lakehouse_root = LAKEHOUSE_ID

    # List Tables
    print(f"\n[Tables] {lakehouse_root}/Tables/")
    try:
        paths = list(fs_client.get_paths(path=f"{lakehouse_root}/Tables", recursive=False))
        if paths:
            for p in paths:
                print(f"  {'DIR ' if p.is_directory else 'FILE'} {p.name}")
        else:
            print("  (empty)")
    except Exception as e:
        print(f"  ERROR: {e}")

    # List Files
    print(f"\n[Files] {lakehouse_root}/Files/")
    try:
        paths = list(fs_client.get_paths(path=f"{lakehouse_root}/Files", recursive=False))
        if paths:
            for p in paths:
                print(f"  {'DIR ' if p.is_directory else 'FILE'} {p.name}")
        else:
            print("  (empty)")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
