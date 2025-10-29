import asyncio
from dataclasses import dataclass

from agent_framework import (
    AgentExecutor,  # Executor that runs the agent
    AgentExecutorRequest,  # Message bundle sent to an AgentExecutor
    AgentExecutorResponse,  # Result returned by an AgentExecutor
    ChatMessage,  # Chat message structure
    Executor,  # Base class for workflow executors
    RequestInfoEvent,  # Event emitted when human input is requested
    RequestInfoExecutor,  # Special executor that collects human input out of band
    RequestInfoMessage,  # Base class for request payloads sent to RequestInfoExecutor
    RequestResponse,  # Correlates a human response with the original request
    Role,  # Enum of chat roles (user, assistant, system)
    WorkflowBuilder,  # Fluent builder for assembling the graph
    WorkflowContext,  # Per run context and event bus
    WorkflowOutputEvent,  # Event emitted when workflow yields output
    WorkflowRunState,  # Enum of workflow run states
    WorkflowStatusEvent,  # Event emitted on run state changes
    handler,  # Decorator to expose an Executor method as a step
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel

@dataclass
class HumanFeedbackRequest(RequestInfoMessage):
    prompt: str = ""
    guess: int | None = None

class TurnManager(Executor):
    """Coordinates turns between the agent and the human.

    Responsibilities:
    - Kick off the first agent turn.
    - After each agent reply, request human feedback with a HumanFeedbackRequest.
    - After each human reply, either finish the game or prompt the agent again with feedback.
    """

    def __init__(self, id: str | None = None):
        super().__init__(id=id or "turn_manager")

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Start the game by asking the agent for an initial guess.

        Contract:
        - Input is a simple starter token (ignored here).
        - Output is an AgentExecutorRequest that triggers the agent to produce a guess.
        """
        user = ChatMessage(Role.USER, text="Start by making your first guess.")
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext[HumanFeedbackRequest],
    ) -> None:
        """Handle the agent's guess and request human guidance.

        Steps:
        1) Parse the agent's JSON into GuessOutput for robustness.
        2) Send a HumanFeedbackRequest to the RequestInfoExecutor with a clear instruction:
           - higher means the human's secret number is higher than the agent's guess.
           - lower means the human's secret number is lower than the agent's guess.
           - correct confirms the guess is exactly right.
           - exit quits the demo.
        """
        # Parse structured model output (defensive default if the agent did not reply).
        text = result.agent_run_response.text or ""
        last_guess = GuessOutput.model_validate_json(text).guess if text else None

        # Craft a precise human prompt that defines higher and lower relative to the agent's guess.
        prompt = (
            f"The agent guessed: {last_guess if last_guess is not None else text}. "
            "Type one of: higher (your number is higher than this guess), "
            "lower (your number is lower than this guess), correct, or exit."
        )
        await ctx.send_message(HumanFeedbackRequest(prompt=prompt, guess=last_guess))

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[HumanFeedbackRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """Continue the game or finish based on human feedback.

        The RequestResponse contains both the human's string reply and the correlated HumanFeedbackRequest,
        which carries the prior guess for convenience.
        """
        reply = (feedback.data or "").strip().lower()
        # Prefer the correlated request's guess to avoid extra shared state reads.
        last_guess = getattr(feedback.original_request, "guess", None)

        if reply == "correct":
            await ctx.yield_output(f"Guessed correctly: {last_guess}")
            return

        # Provide feedback to the agent to try again.
        # We keep the agent's output strictly JSON to ensure stable parsing on the next turn.
        user_msg = ChatMessage(
            Role.USER,
            text=(f'Feedback: {reply}. Return ONLY a JSON object matching the schema {{"guess": <int 1..10>}}.'),
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))
