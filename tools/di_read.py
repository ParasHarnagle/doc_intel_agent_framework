# tools/di_read.py
import os
from typing import Dict, Any

import numpy as np
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest


def _format_bounding_box(bounding_box) -> str:
    if not bounding_box:
        return "N/A"
    pts = np.array(bounding_box).reshape(-1, 2)
    return ", ".join([f"[{x}, {y}]" for x, y in pts])


def di_prebuilt_read(document_uri: str) -> Dict[str, Any]:
    """
    Runs Azure Document Intelligence 'prebuilt-read' on the given URI or local path.
    Returns: { ok, document_uri, content, meta }

    Env required:
      DI_ENDPOINT, DI_KEY
    """
    di_endpoint = os.environ.get("DI_ENDPOINT", "").strip()
    di_key = os.environ.get("DI_KEY", "").strip()
    if not di_endpoint or not di_key:
        return {"ok": False, "error": "Missing DI_ENDPOINT or DI_KEY in environment.", "document_uri": document_uri}

    client = DocumentIntelligenceClient(
        endpoint=di_endpoint, credential=AzureKeyCredential(di_key)
    )

    try:
        if document_uri.startswith(("http://", "https://")):
            poller = client.begin_analyze_document(
                model_id="prebuilt-read",
                analyze_request=AnalyzeDocumentRequest(url_source=document_uri),
            )
        else:
            with open(document_uri, "rb") as f:
                poller = client.begin_analyze_document(
                    model_id="prebuilt-read",
                    body=f,
                )
        result = poller.result()
    except Exception as e:
        return {"ok": False, "error": f"Document Intelligence call failed: {e}", "document_uri": document_uri}

    content = getattr(result, "content", "") or ""
    meta = {
        "uri": document_uri,
        "pages": len(result.pages or []),
        "styles_handwritten_flags": [
            bool(getattr(s, "is_handwritten", False)) for s in (result.styles or [])
        ],
        "first_page": None,
    }

    if result.pages:
        p = result.pages[0]
        first_page = {
            "page_number": p.page_number,
            "size": {"width": p.width, "height": p.height, "unit": p.unit},
            "line_samples": [],
            "word_samples": [],
        }
        for i, line in enumerate(p.lines[:3] if p.lines else []):
            first_page["line_samples"].append(
                {"index": i, "text": line.content, "bbox": _format_bounding_box(line.polygon)}
            )
        for i, w in enumerate(p.words[:5] if p.words else []):
            first_page["word_samples"].append(
                {"index": i, "text": w.content, "confidence": getattr(w, "confidence", None)}
            )
        meta["first_page"] = first_page

    return {"ok": True, "document_uri": document_uri, "content": content, "meta": meta}