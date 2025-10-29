###Creating and Managing Persistent Agents
```python
import asyncio
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential

async def main():
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], 
            credential=credential
        ) as project_client,
    ):
        # Create a persistent agent
        created_agent = await project_client.agents.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            name="PersistentAgent",
            instructions="You are a helpful assistant."
        )

        try:
            # Use the agent
            async with ChatAgent(
                chat_client=AzureAIAgentClient(
                    project_client=project_client,
                    agent_id=created_agent.id
                ),
                instructions="You are a helpful assistant."
            ) as agent:
                result = await agent.run("Hello!")
                print(result.text)
        finally:
            # Clean up the agent
            await project_client.agents.delete_agent(created_agent.id)

asyncio.run(main())
```
### Function Tools
```python
import asyncio
from typing import Annotated
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."

async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather
        ) as agent,
    ):
        result = await agent.run("What's the weather like in Seattle?")
        print(result.text)

asyncio.run(main())

```
###Streaming Responses

For non-streaming, use the run method.
```python
result = await agent.run("What is the weather like in Amsterdam?")
print(result.text)
```

####Example
```python
import asyncio
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="StreamingAgent",
            instructions="You are a helpful assistant."
        ) as agent,
    ):
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream("Tell me a short story"):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print()

asyncio.run(main())
```

###Response types

For the non-streaming case, everything is returned in one AgentRunResponse object. AgentRunResponse allows access to the produced messages via the messages property.
To extract the text result from a response, all TextContent items from all ChatMessage items need to be aggregated. To simplify this, we provide a text property on all response types that aggregates all TextContent.

```python
response = await agent.run("What is the weather like in Amsterdam?")
print(response.text)
print(len(response.messages))

# Access individual messages
for message in response.messages:
    print(f"Role: {message.role}, Text: {message.text}")

```

For the streaming case, AgentRunResponseUpdate objects are streamed as they are produced. Each update may contain a part of the result from the agent, and also various other content items. Similar to the non-streaming case, it is possible to use the text property to get the portion of the result contained in the update, and drill into the detail via the contents property.

```python
async for update in agent.run_stream("What is the weather like in Amsterdam?"):
    print(f"Update text: {update.text}")
    print(f"Content count: {len(update.contents)}")

    # Access individual content items
    for content in update.contents:
        if hasattr(content, 'text'):
            print(f"Content: {content.text}")

```