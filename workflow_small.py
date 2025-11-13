import asyncio
from datetime import datetime
import json
from dataclasses import dataclass, field
import os
from typing import Annotated, Any, Dict
from tools.utils import _name_from_uri, _stable_id
from doc_data_models import ApprovalResponse, DocInput, PromptOutput
from agent_framework import (
    AgentExecutorRequest,
    RequestInfoExecutor,
    RequestResponse,
    AgentExecutorResponse,
    RequestInfoMessage,
    WorkflowContext,
    WorkflowEvent,
    AgentRunUpdateEvent,
    ChatMessage,
    FunctionExecutor,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    RequestInfoEvent,
    WorkflowViz,
    ToolMode,
    WorkflowBuilder,
    handler
)
#from agent_framework.functionexecutor import FunctionExecutor
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field
from typing_extensions import Never
from run_extractor_agent import run_extractor_20_agent
from run_compliance_agent import run_compliance_20_agent
from doc_data_models import ExtractorOutput, PostprocessOutput, ApprovalRequest, ProgressPayload
import uuid
from azure.identity import DefaultAzureCredential, AzureCliCredential
from azure.storage.blob import BlobServiceClient


APPROVAL_CONTEXT: Dict[str, Dict[str, Any]] = {}

class HitlCoordinator(Executor):
    """Coordinates HITL using the pattern from hitl.py - sends request then receives response"""
    
    def __init__(self, id: str = "hitl_coordinator"):
        super().__init__(id=id)
    
    @handler
    async def prepare_request(self, prev: str, ctx: WorkflowContext[ApprovalRequest]):
        """Prepare and send ApprovalRequest message to RequestInfoExecutor ONLY"""
        print(f"🔧 prepare_request called with input type: {type(prev)}")
        rid = str(uuid.uuid4())

        # Parse input
        try:
            data = json.loads(prev)
            uri = data.get("document_details", {}).get("source_uri") or data.get("source_doc_uri") or "n/a"
            summary_text = data.get("document_summary", {}).get("text") or ""
            preview = (summary_text[:240] + "…") if len(summary_text) > 240 else (summary_text or "No preview")
        except (json.JSONDecodeError, TypeError):
            uri = prev
            preview = f"Testing HITL for document: {prev[-60:]}"

        # Cache payload
        APPROVAL_CONTEXT[rid] = {
            "payload": prev,
            "source_uri": uri,
            "preview": preview,
        }

        print(f"📨 Sending ApprovalRequest with approval_id: {rid}")
        # Send ApprovalRequest - will be routed to RequestInfoExecutor based on message type
        # Use target_id to ensure it only goes to the RequestInfoExecutor
        await ctx.send_message(
            ApprovalRequest(
                approval_id=rid,
                title="Manual approval required",
                message="Please review the extracted result.",
                source_uri=uri,
                preview=preview,
            ),
            target_id="human_review_exec"  # Send only to RequestInfoExecutor
        )
    
    @handler
    async def handle_response(
        self,
        feedback: RequestResponse[ApprovalRequest, ApprovalResponse],
        ctx: WorkflowContext[str],
    ):
        """Handle approval response - receives RequestResponse wrapper from RequestInfoExecutor"""
        response = feedback.data
        
        info = APPROVAL_CONTEXT.pop(response.approval_id, {})
        payload = info.get("payload")
        
        print(f"🔍 handle_response called with approval_id: {response.approval_id}, approved: {response.approved}")
        
        await ctx.add_event(WorkflowEvent({
            "type": "hitl",
            "status": "approved" if response.approved else "rejected",
            "approval_id": response.approval_id,
        }))

        if response.approved and payload:
            print(f"✅ Approved: {info.get('source_uri')}")
            # Send the payload to the next executor in chain (final_res)
            await ctx.send_message(payload)
        else:
            print(f"❌ Rejected: {info.get('source_uri')}")
            # Send rejection message to final_res
            await ctx.send_message(json.dumps({
                "overall_status": "rejected_by_human",
                "remarks": response.comment or "Rejected"
            }))

async def build_prompt(doc: DocInput, ctx: WorkflowContext[str])-> None:
    """Build prompt - accepts either string URI or DocInput for flexibility"""
    # For HITL testing, just pass through the URI
    # if isinstance(doc, str):
    #     print(f"📄 Processing document: {doc}")
    #     await ctx.send_message(doc)
    # else:
        # Full DocInput processing
    prompt = f"""
        Document Details:
        - Document URI: {doc.document_uri}
        - Document Title: {doc.document_title or 'N/A'}
        - Page Count: {doc.page_count}
        """
    await ctx.send_message(prompt)
    # output = PromptOutput(
    #     prompt=prompt,
    #     meta={
    #         "source_uri": str(doc.document_uri),
    #         "stage": "prompt_initialized",
    #         "version": "v1",
    #     },
    # )
    #await ctx.send_message(prompt)
    #return output


async def extractor_node(msg: str, ctx: WorkflowContext[str])-> None:
    print("In extractor_node")
    print(f"Document URI received: {msg}")
    result = await run_extractor_20_agent(msg)
    await ctx.add_event(WorkflowEvent({"type": "progress", "phase": "extraction", "status": "running"}))
    await ctx.send_message(result)
    #return result

async def extractor_result(extractor_output: str,ctx: WorkflowContext[str]):
    print("In extractor_result node")
    print(f"Extractor output: {extractor_output}")
    # The extractor already emits a 'running' progress event in `extractor_node`.
    # To avoid duplicate 'running' messages in the frontend, only emit completion
    # here and let the initial 'running' event signal phase start.

    await ctx.send_message(extractor_output)
    await ctx.add_event(WorkflowEvent({"type": "progress", "phase": "extraction", "status": "completed"}))

    #return output

async def compliance_node(prompt: str,ctx: WorkflowContext[str]):
    # Consume output of first node; take the URI from its meta
    await ctx.add_event(WorkflowEvent({"type": "progress", "phase": "compliance", "status": "running"}))
    result =  await run_compliance_20_agent(prompt)
    await ctx.send_message(result)
    #return result

async def compliance_result(compliance_output: str,ctx: WorkflowContext[str]):
    await ctx.add_event(WorkflowEvent({"type": "progress", "phase": "compliance", "status": "completed"}))
    # Just a pass-through for now; could do additional processing here
    await ctx.send_message(compliance_output)
    #return await ctx.send_message(compliance_output)

async def final_result_placeholder(prev: Any, ctx: WorkflowContext[Never]):
    """Final executor - yields workflow output"""
    print(f"🏁 Final result placeholder reached with input type: {type(prev)}")
    print(f"📦 Output preview: {str(prev)[:200]}")
    await ctx.yield_output(prev)

async def save_result_to_blob(prev: Dict[str, Any], ctx: WorkflowContext[Never]) -> None:
    """
    Expected input (from hitl_finalize):
      {
        status, comment, approval_id, source_uri, preview, timestamp_utc
      }
    Writes a JSON record to Azure Blob Storage and yields {blob_url, ...}.
    """
    account_url = os.environ["AZURE_STORAGE_ACCOUNT_URL"]  # e.g. https://myacct.blob.core.windows.net
    container = os.environ["AZURE_STORAGE_CONTAINER"]      # e.g. doc-workflow-results

    # auth (prefers MSI/Workload ID; falls back to Azure CLI if local)
    try:
        credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)
    except Exception:
        credential = AzureCliCredential()

    bsc = BlobServiceClient(account_url=account_url, credential=credential)
    cc = bsc.get_container_client(container)
    # ensure container exists (idempotent)
    try:
        cc.create_container()
    except Exception:
        pass

    # build blob name
    src = str(prev.get("source_uri", "n/a"))
    fname = _name_from_uri(src)
    rid = _stable_id(src + "|" + str(prev.get("approval_id", "")))
    day = datetime.datetime.utcnow().strftime("%Y/%m/%d")
    blob_name = f"runs/{day}/{fname}-{rid}.json"

    payload = {
        "source_uri": src,
        "status": prev.get("status"),
        "comment": prev.get("comment"),
        "approval_id": prev.get("approval_id"),
        "preview": prev.get("preview"),
        "timestamp_utc": prev.get("timestamp_utc"),
        "workflow": {
            "name": "doc_20_page_workflow",
            "node": "save_results",
            "version": "v1",
        },
    }

    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cc.upload_blob(name=blob_name, data=data, overwrite=True, content_type="application/json")

    blob_url = f"{account_url.rstrip('/')}/{container}/{blob_name}"
    # return downstream-friendly object
    result = {
        **payload,
        "blob_url": blob_url,
        "blob_name": blob_name,
        "container": container,
    }
    await ctx.yield_output(result)

async def workflow_small(document_uri: str):

    print(f"Starting workflow for document URI: {document_uri}")
    builder = WorkflowBuilder(name="doc_20_page_workflow", max_iterations=80)
    
    # Define all executors
    input = FunctionExecutor(build_prompt, id="doc_prompt")
    extractor = FunctionExecutor(extractor_node, id="extractor_node")
    extractor_result_node = FunctionExecutor(extractor_result, id="extractor_result_node")
    compliance = FunctionExecutor(compliance_node, id="compliance_node")
    compliance_result_node = FunctionExecutor(compliance_result, id="compliance_result_node")
    
    # HITL setup
    hitl_coordinator = HitlCoordinator(id="hitl_coordinator")
    hitl_gate = RequestInfoExecutor(id="human_review_exec")
    final_res = FunctionExecutor(final_result_placeholder, id="final_result_placeholder")

    # Build workflow: input → extractor → extractor_result → compliance → compliance_result → HITL → final
    builder.set_start_executor(input)
    
    # Extractor chain
    builder.add_edge(input, extractor)
    builder.add_edge(extractor, extractor_result_node)
    
    # Compliance chain
    builder.add_edge(extractor_result_node, compliance)
    builder.add_edge(compliance, compliance_result_node)
    
    # HITL chain: compliance_result → coordinator → gate → coordinator (loop) → final
    builder.add_edge(compliance_result_node, hitl_coordinator)
    builder.add_edge(hitl_coordinator, hitl_gate)
    builder.add_edge(hitl_gate, hitl_coordinator)  # Response goes back to coordinator
    builder.add_edge(hitl_coordinator, final_res)  # After handling response, go to final    #builder.set_start_executor(extractor_chain[0])

    wf = builder.build()

    viz = WorkflowViz(wf)
        # Generate Mermaid flowchart
    mermaid_content = viz.to_mermaid()
    with open("workflow_diagram.mmd", "w", encoding="utf-8") as f:
        f.write(mermaid_content)

    print("Workflow created successfully")
    return wf