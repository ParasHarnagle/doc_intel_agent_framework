import base64
import os
import requests
from msal import ConfidentialClientApplication
from typing import Tuple, Optional, IO

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

TENANT_ID = os.environ["TENANT_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]

def _token() -> str:
    app = ConfidentialClientApplication(
        CLIENT_ID, authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Graph token error: {result}")
    return result["access_token"]

def _encode_share_url(sharing_url: str) -> str:
    # Per Graph: /shares/{shareId}/driveItem where shareId = base64url("u!" + base64url(sharing_url))
    # Simplify: base64url the full URL and prefix "u!"
    b = sharing_url.encode("utf-8")
    b64 = base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")
    inner = "u!" + b64
    outer = base64.urlsafe_b64encode(inner.encode("utf-8")).decode("utf-8").rstrip("=")
    return outer

def resolve_drive_item(sharing_url: str) -> dict:
    token = _token()
    share_id = _encode_share_url(sharing_url)
    url = f"{GRAPH_BASE}/shares/{share_id}/driveItem"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()

def open_download_stream(drive_item: dict) -> Tuple[IO[bytes], Optional[str]]:
    """
    Returns (stream, file_name). Uses the pre-authenticated temporary
    @microsoft.graph.downloadUrl provided by Graph.
    """
    download_url = drive_item.get("@microsoft.graph.downloadUrl")
    name = drive_item.get("name")
    if not download_url:
        # fallback to /drive/items/{id}/content
        token = _token()
        item_id = drive_item["id"]
        url = f"{GRAPH_BASE}/drives/{drive_item['parentReference']['driveId']}/items/{item_id}/content"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, stream=True)
        r.raise_for_status()
        return r.raw, name
    r = requests.get(download_url, stream=True)
    r.raise_for_status()
    return r.raw, name
