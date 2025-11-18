import asyncio
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
load_dotenv()
from prompts.prompt import EXTRACTOR_AGENT_PROMPT_20
from tools.di_read import di_read_tool
from doc_data_models import ExtractorOutput

async def create_agent():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], 
            credential=credential
        ) as project_client,
    ):
        # Create a persistent agent
        created_agent = await project_client.agents.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            name="ExtractorAgent20",
            instructions=EXTRACTOR_AGENT_PROMPT_20,
            #tools=[di_prebuilt_read],
        )

        print(f"Created agent: {created_agent.id}")

#asyncio.run(create_agent())     
doc_uri = f"""
DOcument URI: "/Users/parasharnagle/Documents/LLMsprojs/Doc_Intel/docIntel/docintel/1040 - Individual Tax Return - Example 3.pdf"
"""
async def run_extractor_20_agent(doc_uri):
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], 
            credential=credential
        ) as project_client,
    ):
        async with ChatAgent(
            chat_client=AzureAIAgentClient(
                project_client=project_client,
                agent_id=os.environ["EXTRACTOR_AGENT_ID"],
                async_credential=credential
            ),
            tools=[di_read_tool],
            #instructions=EXTRACTOR_AGENT_PROMPT_20,
        ) as extractor_agent:
            result = await extractor_agent.run(doc_uri)
            print(result.text)
            return result.text
            #async for update in extractor_agent.run_stream(doc_uri):
            #    if update.text:
            #        print(update.text, end="", flush=True)

async def run_extractor_agent():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], 
            credential=credential
        ) as project_client,
    ):
        async with ChatAgent(
            chat_client=AzureAIAgentClient(
                project_client=project_client,
                agent_id=os.environ["EXTRACTOR_AGENT_ID"],
                async_credential=credential
            ),
            tools=[di_read_tool],
            #instructions=EXTRACTOR_AGENT_PROMPT_20,
        ) as extractor_agent:
            return extractor_agent
            # result = await extractor_agent.run(doc_uri)
            # print(result.text)
            # return result.text
            #async for update in extractor_agent.run_stream(doc_uri):
            #    if update.text:
            #        print(update.text, end="", flush=True)

if __name__ == "__main__":
    #asyncio.run(create_agent())
    #r = di_read_tool("/Users/parasharnagle/Documents/LLMsprojs/Doc_Intel/docIntel/docintel/1040 - Individual Tax Return - Example 3.pdf")
    #print("pages:", r.get("pages"))
    #print("per_page_len:", len(r.get("per_page", [])))
    #print("first_pages:", [pp["page_number"] for pp in r.get("per_page", [])[:5]])
    asyncio.run(run_extractor_agent(doc_uri))
