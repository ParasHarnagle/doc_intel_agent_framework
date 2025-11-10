import os, json, fitz
from datetime import datetime, timedelta, timezone
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
load_dotenv()

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
CONN_STR = os.getenv("CONN_STRING")
CONTAINER = "docs"
BASE_TRACK_DIR = "File_tracker_dir"
CRON_WINDOW_HOURS = 12  # 12-hour processing window

# Connect to Azure Blob
blob_service = BlobServiceClient.from_connection_string(CONN_STR)
container_client = blob_service.get_container_client(CONTAINER)

# ------------------------------------------------------------------
# PATH UTILITIES
# ------------------------------------------------------------------
def make_tracker_path() -> str:
    """Create directory structure: File_tracker_dir/<date>/run_N/tmp_recent_files.json"""
    today = datetime.now().strftime("%Y-%m-%d")
    date_dir = os.path.join(BASE_TRACK_DIR, today)
    os.makedirs(date_dir, exist_ok=True)

    # Find highest existing run number in today's directory
    runs = [d for d in os.listdir(date_dir) if d.startswith("run_") and os.path.isdir(os.path.join(date_dir, d))]
    if runs:
        last_run = max(int(d.split("_")[1]) for d in runs)
        next_run = f"run_{last_run + 1:02d}"
    else:
        next_run = "run_01"

    run_dir = os.path.join(date_dir, next_run)
    os.makedirs(run_dir, exist_ok=True)
    tracker_path = os.path.join(run_dir, "tmp_recent_files.json")

    print(f"Creating tracker for {today}/{next_run}")
    return tracker_path

def load_tracker(file_path: str):
    """Load prior tracker if exists."""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return {}

def save_tracker(file_path: str, data):
    """Save tracker JSON with indentation."""
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

# ------------------------------------------------------------------
# PDF PAGE COUNT
# ------------------------------------------------------------------
def get_pdf_page_count(blob_client):
    """Accurate page count using PyMuPDF (in-memory)."""
    pdf_bytes = blob_client.download_blob().readall()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count

# ------------------------------------------------------------------
# RECENT BLOBS FETCH
# ------------------------------------------------------------------
def list_recent_blobs(hours=12):
    """Return list of blobs modified in the last N hours."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    return [
        b for b in container_client.list_blobs()
        if b.name.endswith(".pdf") and b.last_modified > cutoff
    ]

# ------------------------------------------------------------------
# MAIN CRON WORKFLOW
# ------------------------------------------------------------------
def process_recent_blobs():
    tracker_path = make_tracker_path()
    tracker = load_tracker(tracker_path)
    new_tracker = {}
    recent_blobs = list_recent_blobs(CRON_WINDOW_HOURS)

    print(f"Tracker file: {tracker_path}")
    print(f"Found {len(recent_blobs)} PDF(s) modified in last {CRON_WINDOW_HOURS} hours")

    for blob in recent_blobs:
        blob_client = container_client.get_blob_client(blob.name)
        blob_key = blob.name
        etag = blob.etag

        # Skip duplicates within same run
        if tracker.get(blob_key, {}).get("etag") == etag:
            print(f" Skipping unchanged: {blob_key}")
            new_tracker[blob_key] = tracker[blob_key]
            continue

        try:
            count = get_pdf_page_count(blob_client)
            uri = blob_client.url
            print(f"{blob_key}: {count} pages")

            new_tracker[blob_key] = {
                "etag": etag,
                "last_modified": blob.last_modified.isoformat(),
                "page_count": count,
                "uri": uri,
                "processed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"Error processing {blob_key}: {e}")

    save_tracker(tracker_path, new_tracker)
    print(f"Tracker saved at {tracker_path} with {len(new_tracker)} entries.")


if __name__ == "__main__":
    process_recent_blobs()