import os
from pydantic import BaseModel

class Settings(BaseModel):
    # scheduler
    poll_interval_hours: int = int(os.getenv("POLL_INTERVAL_HOURS", "3"))

    # sharepoint
    sp_tenant_id: str = os.getenv("SP_TENANT_ID", "")
    sp_client_id: str = os.getenv("SP_CLIENT_ID", "")
    sp_client_secret: str = os.getenv("SP_CLIENT_SECRET", "")
    sp_site_id: str = os.getenv("SP_SITE_ID", "")
    sp_drive_id: str = os.getenv("SP_DRIVE_ID", "")
    sp_folder_path: str = os.getenv("SP_FOLDER_PATH", "/Documents/Incoming")

    # azure agents
    az_project_endpoint: str = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
    az_model_deployment: str = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")

    # agent ids
    extractor_agent_id: str = os.getenv("EXTRACTOR_AGENT_ID", "")
    extractor_agent_20_id: str = os.getenv("EXTRACTOR_AGENT_20_ID", "")  # optional
    compliance_agent_id: str = os.getenv("COMPLIANCE_AGENT_ID", "")

settings = Settings()
