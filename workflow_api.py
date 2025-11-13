"""
FastAPI endpoint for streaming workflow events to React frontend via SSE
"""
import asyncio
import json
import uuid
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from workflow_small import workflow_small
from doc_data_models import DocInput, ApprovalRequest, ApprovalResponse
from agent_framework import (
    RequestInfoEvent,
    WorkflowOutputEvent,
    ExecutorCompletedEvent,
    WorkflowEvent,
)

app = FastAPI(title="Document Intelligence Workflow API")

# Enable CORS for React frontend and local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Python http.server
        "null",                    # For file:// protocol (local HTML files)
    ],
    allow_origin_regex="http://localhost:.*",  # Allow any localhost port
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Store active workflow sessions and pending approvals
workflow_sessions = {}
pending_approvals = {}


class WorkflowStartRequest(BaseModel):
    document_uri: str
    document_title: Optional[str] = None
    page_count: Optional[int] = None


class ApprovalDecision(BaseModel):
    request_id: str
    approval_id: str
    approved: bool
    comment: Optional[str] = None


def format_sse(event_type: str, data: dict) -> str:
    """Format data as Server-Sent Event"""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/workflow/start")
async def start_workflow(request: WorkflowStartRequest):
    """Start a new workflow and return session ID"""
    session_id = str(uuid.uuid4())
    
    workflow_sessions[session_id] = {
        "status": "initializing",
        "document_uri": request.document_uri,
        "created_at": datetime.utcnow().isoformat(),
    }
    
    return {
        "session_id": session_id,
        "message": "Workflow session created. Connect to /api/workflow/{session_id}/events for real-time updates."
    }


@app.get("/api/workflow/{session_id}/events")
async def stream_workflow_events(session_id: str):
    """
    Server-Sent Events endpoint for streaming workflow progress to React frontend
    
    React Usage:
    ```javascript
    const eventSource = new EventSource(`/api/workflow/${sessionId}/events`);
    
    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        console.log('Progress:', data.phase, data.status);
    });
    
    eventSource.addEventListener('approval_required', (e) => {
        const data = JSON.parse(e.data);
        // Show approval UI with data.approval_id, data.preview, etc.
    });
    ```
    """
    
    if session_id not in workflow_sessions:
        raise HTTPException(status_code=404, detail="Workflow session not found")
    
    session = workflow_sessions[session_id]
    
    async def event_generator():
        try:
            # Send connection established event
            yield format_sse("connected", {
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Create workflow
            wf = await workflow_small(session["document_uri"])
            doc_input = DocInput(
                document_uri=session["document_uri"],
                document_title=session.get("document_title"),
                page_count=session.get("page_count")
            )
            
            # Notify workflow started
            yield format_sse("workflow_started", {
                "session_id": session_id,
                "document_uri": session["document_uri"]
            })
            
            pending_responses = {}
            
            while True:
                request_info_events = []
                
                # Use send_responses_streaming if we have pending responses
                if pending_responses:
                    stream = wf.send_responses_streaming(pending_responses)
                    pending_responses = {}
                else:
                    stream = wf.run_stream(doc_input)
                
                async for event in stream:
                    if isinstance(event, WorkflowOutputEvent):
                        # Workflow completed
                        yield format_sse("workflow_completed", {
                            "session_id": session_id,
                            "result": str(event.data),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        return
                    
                    elif isinstance(event, RequestInfoEvent):
                        # Human approval required
                        request_info_events.append(event)
                        req: ApprovalRequest = event.data
                        
                        approval_data = {
                            "request_id": event.request_id,
                            "approval_id": req.approval_id,
                            "title": req.title,
                            "message": req.message,
                            "source_uri": req.source_uri,
                            "preview": req.preview,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        
                        # Store for approval endpoint
                        pending_approvals[event.request_id] = {
                            "session_id": session_id,
                            "approval_data": approval_data
                        }
                        
                        yield format_sse("approval_required", approval_data)
                    
                    elif isinstance(event, WorkflowEvent):
                        # Custom progress events
                        event_data = event.data
                        if isinstance(event_data, dict):
                            event_type = event_data.get("type")
                            
                            if event_type == "progress":
                                yield format_sse("progress", {
                                    "phase": event_data.get("phase"),
                                    "status": event_data.get("status"),
                                    "timestamp": datetime.utcnow().isoformat()
                                })
                            
                            elif event_type == "hitl":
                                yield format_sse("hitl_status", {
                                    "status": event_data.get("status"),
                                    "approval_id": event_data.get("approval_id"),
                                    "timestamp": datetime.utcnow().isoformat()
                                })
                    
                    elif isinstance(event, ExecutorCompletedEvent):
                        yield format_sse("executor_completed", {
                            "executor_id": event.executor_id,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                
                # If we have requests, wait for approval via POST endpoint
                if request_info_events:
                    yield format_sse("waiting_for_approval", {
                        "count": len(request_info_events),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    # Wait for approval responses (polling with timeout)
                    max_wait = 300  # 5 minutes timeout
                    waited = 0
                    while waited < max_wait:
                        # Check if approvals have been submitted via POST endpoint
                        all_responses_ready = True
                        for req_event in request_info_events:
                            if req_event.request_id not in pending_responses:
                                all_responses_ready = False
                                break
                        
                        if all_responses_ready:
                            break
                        
                        await asyncio.sleep(1)
                        waited += 1
                    
                    if not all_responses_ready:
                        yield format_sse("error", {
                            "message": "Approval timeout - no response received",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        return
                else:
                    # No more requests - workflow complete
                    break
        
        except Exception as e:
            yield format_sse("error", {
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.post("/api/workflow/approval")
async def submit_approval(decision: ApprovalDecision):
    """
    Submit approval decision from React frontend
    
    React Usage:
    ```javascript
    await fetch('/api/workflow/approval', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            request_id: requestId,
            approval_id: approvalId,
            approved: true,
            comment: 'Looks good'
        })
    });
    ```
    """
    if decision.request_id not in pending_approvals:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    # Get the session for this approval
    approval_info = pending_approvals[decision.request_id]
    session_id = approval_info["session_id"]
    
    if session_id not in workflow_sessions:
        raise HTTPException(status_code=404, detail="Workflow session not found")
    
    # Create approval response
    resp = ApprovalResponse(
        approval_id=decision.approval_id,
        approved=decision.approved,
        comment=decision.comment
    )
    
    # Store response for workflow to consume
    # (In production, use Redis or message queue for multi-instance support)
    if "pending_responses" not in workflow_sessions[session_id]:
        workflow_sessions[session_id]["pending_responses"] = {}
    
    workflow_sessions[session_id]["pending_responses"][decision.request_id] = resp
    
    # Clean up
    del pending_approvals[decision.request_id]
    
    return {
        "status": "success",
        "message": f"Approval {'granted' if decision.approved else 'rejected'}",
        "approval_id": decision.approval_id
    }


@app.get("/api/workflow/{session_id}/status")
async def get_workflow_status(session_id: str):
    """Get current workflow status"""
    if session_id not in workflow_sessions:
        raise HTTPException(status_code=404, detail="Workflow session not found")
    
    return workflow_sessions[session_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
