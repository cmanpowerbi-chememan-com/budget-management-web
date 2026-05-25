"""
Ingest SAP flat files from local path → Fabric Lakehouse Files/00landing

Source:  data_pipeline_onelake/source/   (or --source-dir <path>)
Target:  Lakehouse Files/00landing/<filename>
Mode:    Overwrite (replace existing file with same name)

Usage:
    # upload all files in source/ folder
    python data_pipeline_onelake/ingest_to_landing.py

    # upload a specific file
    python data_pipeline_onelake/ingest_to_landing.py --file "D:/SAPDW/PRD/SAP_T_GL_TRANS_1000_RATIMA_TEST1"

    # upload all files from a custom directory
    python data_pipeline_onelake/ingest_to_landing.py --source-dir "D:/SAPDW/PRD"
"""

import os
import sys
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv
import msal
from azure.storage.filedatalake import DataLakeServiceClient
from azure.core.credentials import AccessToken

load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE_ID = os.environ["FABRIC_WORKSPACE_ID"]
LAKEHOUSE_ID = os.environ["FABRIC_LAKEHOUSE_ID"]
LANDING_PATH = f"{LAKEHOUSE_ID}/Files/00landing"
DEFAULT_SOURCE = Path(__file__).parent / "source"


def get_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=os.environ["ENTRA_CLIENT_ID"],
        client_credential=os.environ["ENTRA_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{os.environ['ENTRA_TENANT_ID']}",
    )
    result = app.acquire_token_for_client(scopes=["https://storage.azure.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Token error: {result.get('error_description')}")
    return result["access_token"]


class _StaticTokenCredential:
    def __init__(self, token: str):
        self._token = token

    def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self._token, int(time.time()) + 3600)


def get_fs_client(token: str):
    svc = DataLakeServiceClient(
        account_url="https://onelake.dfs.fabric.microsoft.com",
        credential=_StaticTokenCredential(token),
    )
    return svc.get_file_system_client(WORKSPACE_ID)


def upload_file(fs_client, local_path: Path) -> None:
    dest = f"{LANDING_PATH}/{local_path.name}"
    file_client = fs_client.get_file_client(dest)

    data = local_path.read_bytes()
    file_size = len(data)

    # overwrite=True replaces existing file
    file_client.upload_data(data, overwrite=True, length=file_size)
    print(f"  UPLOADED  {local_path.name}  ({file_size:,} bytes)  → 00landing/")


def main():
    parser = argparse.ArgumentParser(description="Ingest SAP files to OneLake 00landing")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", type=Path, help="Upload a single file")
    group.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE,
                       help=f"Upload all files in directory (default: {DEFAULT_SOURCE})")
    args = parser.parse_args()

    # collect files to upload
    if args.file:
        if not args.file.exists():
            print(f"ERROR: file not found: {args.file}")
            sys.exit(1)
        files = [args.file]
    else:
        src = args.source_dir
        if not src.exists():
            print(f"ERROR: source directory not found: {src}")
            sys.exit(1)
        files = [f for f in src.iterdir() if f.is_file()]
        if not files:
            print(f"No files found in {src}")
            sys.exit(0)

    print(f"Acquiring token...")
    token = get_token()
    fs_client = get_fs_client(token)

    print(f"Uploading {len(files)} file(s) to Files/00landing  [overwrite mode]\n")
    for f in files:
        upload_file(fs_client, f)

    print(f"\nDone — {len(files)} file(s) uploaded.")


if __name__ == "__main__":
    main()
