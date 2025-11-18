import asyncio
from typing import List
from workflow_small import workflow_small
from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    FunctionExecutor,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    RequestInfoEvent,
    Workflow,
    WorkflowViz,
    ToolMode,
    ExecutorCompletedEvent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowEvent)
from doc_data_models import DocInput, ApprovalRequest, ApprovalResponse

async def run_once(input_data: DocInput | str, workflow: Workflow):
    """Run workflow with HITL support - handles RequestInfoEvent for human approval
    
    Pattern from Microsoft docs:
    1. Collect all RequestInfoEvents during stream
    2. Exit stream completely (no break)
    3. Process collected events and gather responses
    4. Loop back with pending_responses for send_responses_streaming()
    """
    
    pending_responses = {}
    
    if isinstance(input_data, str):
        print(f"🚀 Running workflow for URI: {input_data}\n")
    else:
        print(f"🚀 Running workflow for URI: {input_data.document_uri}\n")
    
    while True:
        # Collect request events from this iteration
        request_info_events: list[RequestInfoEvent] = []
        
        # Use send_responses_streaming if we have pending responses, otherwise run_stream
        if pending_responses:
            print(f"📤 Resuming workflow with {len(pending_responses)} response(s)")
            stream = workflow.send_responses_streaming(pending_responses)
            pending_responses = {}  # Clear after using
        else:
            stream = workflow.run_stream(input_data)
        
        async for event in stream:
            if isinstance(event, WorkflowOutputEvent):
                print("\n✅ Workflow completed successfully")
                return event.data
                
            elif isinstance(event, RequestInfoEvent):
                # Collect request - don't break the stream!
                print(f"   📩 Received RequestInfoEvent: {event.request_id}")
                request_info_events.append(event)
            
            elif isinstance(event, WorkflowEvent):
                # Custom progress events
                event_data = event.data
                if isinstance(event_data, dict):
                    event_type = event_data.get("type")
                    if event_type == "progress":
                        phase = event_data.get("phase", "unknown")
                        status = event_data.get("status", "unknown")
                        # Use emoji indicators for progress
                        status_icon = "🔄" if status == "running" else "✅" if status == "completed" else "⚠️"
                        print(f"   {status_icon} Progress: {phase.upper()} - {status}")
                    elif event_type == "hitl":
                        hitl_status = event_data.get("status", "unknown")
                        approval_id = event_data.get("approval_id", "N/A")
                        icon = "✅" if hitl_status == "approved" else "❌"
                        print(f"   {icon} HITL: {hitl_status} (ID: {approval_id[:8]}...)")
                    else:
                        print(f"   📌 Custom event: {event_data}")
                else:
                    print(f"   📌 WorkflowEvent: {event_data}")
                    
            elif isinstance(event, ExecutorCompletedEvent):
                print(f"   ✓ {event.executor_id} completed")
            else:
                # Show event type and executor/node name if available
                event_name = type(event).__name__
                executor_info = ""
                if hasattr(event, 'executor_id'):
                    executor_info = f" [{event.executor_id}]"
                elif hasattr(event, 'target_executor_id'):
                    executor_info = f" [→ {event.target_executor_id}]"
                print(f"   ℹ️  Other event: {event_name}{executor_info}")
        
        # Stream is now complete - process any collected requests
        print(f"📊 Stream completed. Collected {len(request_info_events)} request(s)")
        
        if not request_info_events:
            # No requests means workflow is done
            print("🏁 No more requests - workflow complete")
            break
        
        # Process each request and collect responses
        for request_event in request_info_events:
            req: ApprovalRequest = request_event.data
            print(f"\n{'='*70}")
            print(f"⏸️  HUMAN REVIEW REQUIRED")
            print(f"{'='*70}")
            print(f"Title:    {req.title}")
            print(f"Message:  {req.message}")
            print(f"Source:   {req.source_uri}")
            print(f"Preview:  {req.preview}")
            print(f"{'='*70}\n")
            
            # Get human decision (replace with UI/API integration in production)
            decision = input("Approve this document? (y/n): ").strip().lower() == 'y'
            comment = input("Add comment (optional): ").strip() or None
            
            # Create response
            resp = ApprovalResponse(
                approval_id=req.approval_id,
                approved=decision,
                comment=comment
            )
            
            # Store response for next iteration
            pending_responses[request_event.request_id] = resp
            
            status = "✅ APPROVED" if decision else "❌ REJECTED"
            print(f"\n{status} - Response will be sent to workflow")
            if comment:
                print(f"Comment: {comment}\n")

async def main():
    """Main entry point for workflow execution with HITL"""
    test_uri = "/Users/parasharnagle/Documents/LLMsprojs/Doc_Intel/docIntel/docintel/1040 - Individual Tax Return - Example 3.pdf"
    
    print("="*70)
    print("🚀 Starting Document Intelligence Workflow with HITL")
    print("="*70)
    print(f"Document: {test_uri.split('/')[-1]}")
    print("="*70 + "\n")
    
    # Create workflow
    wf = await workflow_small(test_uri)
    doc_input = DocInput(
        document_uri=test_uri,
        document_title="1040 Tax Return Example",
        page_count=20  # or None if unknown
    )
    
    # Run workflow with HITL support
    final_result = await run_once(doc_input, wf)
    
    # Display final results
    print("\n" + "="*70)
    print("📊 WORKFLOW RESULTS")
    print("="*70)
    if final_result:
        print(f"Final output: {final_result}")
    else:
        print("Workflow completed with no output (possibly rejected)")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())

# ============================================================================
# USAGE EXAMPLES
# ============================================================================

# Example 1: HITL Testing (current mode)
# - Tests HITL flow with simple document URI
# - Workflow: build_prompt → hitl_prepare → RequestInfoExecutor → hitl_finalize → final_result
# - Human approval required before completion

# Example 2: Full workflow with HITL (uncomment in workflow_small.py)
# - Full chain: extractor → compliance → HITL → final_result
# - Workflow pauses after compliance check for human review
# - To enable: uncomment extractor/compliance chains in workflow_small.py

# Example 3: Batch processing with HITL
# async def run_batch_with_hitl():
#     uris = [
#         "/path/to/doc1.pdf",
#         "/path/to/doc2.pdf",
#         "/path/to/doc3.pdf",
#     ]
#     wf = await workflow_small(uris[0])
#     results = []
#     for uri in uris:
#         result = await run_once(uri, wf)
#         results.append(result)
#     return results

# Example 4: Programmatic approval (for automation)
# async def run_with_auto_approval(uri: str, auto_approve: bool = True):
#     wf = await workflow_small(uri)
#     events = wf.run_stream(uri)
#     
#     async for event in events:
#         if isinstance(event, RequestInfoEvent):
#             req: ApprovalRequest = event.data
#             # Auto-approve based on criteria
#             resp = ApprovalResponse(
#                 approval_id=req.approval_id,
#                 approved=auto_approve,
#                 comment="Auto-approved by system"
#             )
#             await wf.send_response(event.request_id, resp)
#         elif isinstance(event, WorkflowOutputEvent):
#             return event.data
# ============================================================================
