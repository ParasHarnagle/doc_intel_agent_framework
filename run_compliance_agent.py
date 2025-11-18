import asyncio
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
load_dotenv()
from prompts.prompt import PTR_CP
from tools.di_read import di_read_tool

async def create_compliance_agent():
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
            name="ComplianceAgent",
            instructions=PTR_CP,
            #tools=[di_prebuilt_read],
        )

        print(f"Created compliance agent: {created_agent.id}")

#asyncio.run(create_agent())     
compliance_input = {
    "source_uri": "/Users/parasharnagle/Documents/LLMsprojs/Doc_Intel/docIntel/docintel/1040 - Individual Tax Return - Example 3.pdf",
    "title": "Form 1040 (2024) U.S. Individual Income Tax Return",
    "document description": "U.S. Individual Income Tax Return with attachments Schedule 1, Schedule C, Schedule 4562",
    "language": "English",
    "created_date": "",
    "statement_date": "",
    "period": { "start": "2024-01-01", "end": "2024-12-31" },
    "parties": {
      "primary_subject": { "name": "Matthew A Morgan", "role": "Taxpayer", "id": "501-19-4455" },
      "counterparties": [
        { "name": "Tess M Morgan", "role": "Spouse", "id": "501-19-9466" }
      ]
    },
    "addresses": [
      { "label": "Home", "address_full": "208 4th St So, New Salem, ND 58563" }
    ]

  }

async def run_compliance_20_agent(doc_uri):
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
                agent_id=os.environ["COMPLIANCE_AGENT_ID"],
                async_credential=credential
            ),
            #tools=[di_read_tool],
            #instructions=EXTRACTOR_AGENT_PROMPT_20,
        ) as compliance_agent:
            result = await compliance_agent.run(doc_uri)
            print(result.text)
            return result.text
        
async def run_compliance_agent():
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
                agent_id=os.environ["COMPLIANCE_AGENT_ID"],
                async_credential=credential
            ),
            #tools=[di_read_tool],
            #instructions=EXTRACTOR_AGENT_PROMPT_20,
        ) as compliance_agent:
            return compliance_agent
            # result = await compliance_agent.run(doc_uri)
            # print(result.text)
            # return result.text
            
if __name__ == "__main__":
    asyncio.run(create_compliance_agent())
    #asyncio.run(run_compliance_agent(compliance_input))
