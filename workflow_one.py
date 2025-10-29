import asyncio
import json
import os
from agent_framework import WorkflowExecutor,AgentExecutor,AgentExecutorResponse,WorkflowExecutor,handler,ChatMessage,Role,Executor,WorkflowContext
from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowOutputEvent,RequestInfoMessage,AgentExecutorRequest
from azure.identity.aio import AzureCliCredential
from azure.ai.projects.aio import AIProjectClient
from agent_framework.azure import AzureAIAgentClient
from dataclasses import dataclass
from agents_create import extractor_agent_20,compliance_agent
from contextlib import AsyncExitStack
from typing import Any, Awaitable, Callable, Dict, Optional
from agent_framework import ChatAgent

@dataclass
class HumanReviewPacket:
    document_uri: str
    summary: str
    compliance_notes: str
    prompt: str = "Approve or Reject? (type 'approve' / 'reject')"
    
# ---------- Small helper to parse compliance agent JSON ----------
def _parse_compliance_json(text: str) -> Dict[str, Any]:
    try:
        obj = json.loads(text or "{}")
        # expected shape: { "compliance": { "is_compliant": bool, "notes": [...] }, "needs_human_review": bool }
        if "compliance" not in obj:
            obj["compliance"] = {}
        obj.setdefault("needs_human_review", False)
        return obj
    except Exception:
        # if non-JSON, force human review and carry the raw text as a note
        return {"compliance": {"is_compliant": False, "notes": [text]}, "needs_human_review": True}


# ---------- Start adapter: turns document_uri -> AgentExecutorRequest for extractor ----------
class StartAdapter(Executor):
    def __init__(self, document_uri: str):
        super().__init__(id="start_adapter")
        self.document_uri = document_uri

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        user = ChatMessage(
            Role.USER,
            text=json.dumps({
                "op": "extract",
                "document": {"uri": self.document_uri}
            }),
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

# ---------- Compliance adapter: routes to HITL or save ----------
class ComplianceAdapter(Executor):
    def __init__(self):
        super().__init__(id="compliance_exec")

    @handler
    async def on_compliance(self, result: AgentExecutorResponse, ctx: WorkflowContext[HumanReviewPacket, Dict[str, Any]]) -> None:
        # stash raw for audit
        comp_text = result.agent_run_response.text or ""
        ctx.state["compliance_text"] = comp_text

        comp = _parse_compliance_json(comp_text)
        is_ok = bool(comp.get("compliance", {}).get("is_compliant", False))
        needs_human = bool(comp.get("needs_human_review", False))

        # if auto-pass → go to save_results
        if is_ok and not needs_human:
            await ctx.send_message("save_results", {"approved": True, "auto": True, "compliance": comp})
            return

        # else → HITL terminal node
        extracted_text = str(ctx.state.get("extractor_text", ""))  # set by post-extractor adapter below
        notes = comp.get("compliance", {}).get("notes", [])
        notes_text = "; ".join(map(str, notes)) if isinstance(notes, list) else str(notes)
        packet = HumanReviewPacket(
            document_uri=str(ctx.state.get("document_uri", "")),
            summary=extracted_text[:1000],
            compliance_notes=notes_text or "(no notes)"
        )
        await ctx.send_message("human_review_exec", packet)

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT = os.environ["MODEL_DEPLOYMENT"]

async def create_agent_factory() -> tuple[
    Callable[..., Awaitable[ChatAgent]],  # factory(**kwargs) -> ChatAgent (open, managed by stack)
    Callable[[], Awaitable[None]]         # close()
]:
    """
    Returns (factory, close). The factory creates ChatAgent instances tied to this stack.
    Call close() once you're done to dispose all contexts.
    """
    stack = AsyncExitStack()

    cred = await stack.enter_async_context(AzureCliCredential())
    project_client = await stack.enter_async_context(AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=cred))
    # AzureAIAgentClient can take project_client; do not pass endpoint again
    client = AzureAIAgentClient(project_client=project_client)

    async def factory(
        *,
        agent_id: Optional[str] = None,
        instructions: Optional[str] = None,
        name: Optional[str] = None,
        model: Optional[str] = MODEL_DEPLOYMENT,
        tools: Optional[list] = None,
    ) -> ChatAgent:
        """
        - If agent_id is provided → bind ChatAgent to that agent.
        - Else create a new agent (one-off) and return a ChatAgent bound to it.
        Returned ChatAgent is kept open by the AsyncExitStack.
        """
        if agent_id:
            # Bind to existing agent by id
            chat_client = AzureAIAgentClient(project_client=project_client, agent_id=agent_id)
            agent = ChatAgent(chat_client=chat_client, instructions=instructions)
            # Keep it open on the shared stack
            return await stack.enter_async_context(agent)

        # Create a new agent in the project then bind
        created = await project_client.agents.create_agent(
            model=model, name=name or "AdhocAgent", instructions=instructions or "You are a helpful assistant.", tools=tools
        )
        chat_client = AzureAIAgentClient(project_client=project_client, agent_id=created.id)
        agent = ChatAgent(chat_client=chat_client, instructions=instructions)
        return await stack.enter_async_context(agent)

    async def close() -> None:
        await stack.aclose()

    return factory, close

async def small_workflow(document_uri: str):
    
    try:
        factory, close = await create_agent_factory()
        compliance_agent = await factory(agent_id=os.environ["COMPLIANCE_AGENT_ID"], instructions="<<compliance prompt>>")
        extractor_agent_20 = await factory(
            agent_id=os.environ["EXTRACTOR_AGENT_20_ID"],
            instructions="<<extractor prompt 20>>",
        )

        extractor_agent_20 = AgentExecutor(agent=extractor_agent_20, id="extractor_agent_20")
        compliance_agent_exec = AgentExecutor(agent=compliance_agent, id="compliance_agent")


        start = StartAdapter(document_uri)
        post_extractor = ExtractorToCompliance(document_uri)
        compliance_exec = ComplianceAdapter()
        human_review_exec = HumanReviewTerminal()   # terminal
        save_results = SaveResults()  

        small_wb = (
            WorkflowBuilder()
            .set_start_executor(start)                         # start → extractor
            .add_edge(start, extractor_agent_20)
            .add_edge(extractor_agent_20, post_extractor)      # extractor → adapter
            .add_edge(post_extractor, compliance_agent_exec)   # adapter → compliance agent

            # === keep HITL edges exactly as you wrote ===
            .add_edge(compliance_agent_exec, compliance_exec)  # compliance agent → adapter
            .add_edge("compliance_exec", "human_review_exec")  # HITL branch (terminal)
            .add_edge("compliance_exec", "save_results")  
                 # auto-pass branch (terminal) ##add delete openai calls
        )

        wf = small_wb.build()
        runner = WorkflowExecutor(wf, id="small_flow")

        events = runner.run_stream("start")
        async for ev in events:
            if isinstance(ev, AgentExecutorResponse):
                # optional: live logs for agent tokens/messages
                pass
            if hasattr(ev, "data"):
                # will see WorkflowOutputEvent data from terminal nodes
                if ev.__class__.__name__ == "WorkflowOutputEvent":
                    print("\n===== Final output =====")
                    print(ev.data)

        # last_executor_id: str | None = None
        # input_message_small_workflow = f"""
        #     Document URI:{document_uri}
        #     """
        # events = small_flow_exec.run_stream(input_message_small_workflow)
        # async for event in events:
        #             if isinstance(event, AgentRunUpdateEvent):
        #             # Handle streaming updates from agents
        #                 eid = event.executor_id
        #                 if eid != last_executor_id:
        #                     if last_executor_id is not None:
        #                         print()
        #                     print(f"{eid}:", end=" ", flush=True)
        #                     last_executor_id = eid
        #                 print(event.data, end="", flush=True)
        #             elif isinstance(event, WorkflowOutputEvent):
        #                 print("\n===== Final output =====")
        #                 print(event.data)
    except Exception as e:
        print(f"Error in small_workflow: {e}")
        raise RuntimeError(f"Error in small_workflow: {e}") from e    
    finally:
        await close()