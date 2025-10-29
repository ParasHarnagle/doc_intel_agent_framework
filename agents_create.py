import asyncio
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from azure.ai.projects.aio import AIProjectClient
from agent_framework import ChatAgent
from tools.di_read import di_prebuilt_read
import os
from dotenv import load_dotenv
from cons
from prompts.prompts import EXTRACTOR_AGENT_PROMPT_20, EXTRACTOR_AGENT_PROMPT

load_dotenv()

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT = os.environ["MODEL_DEPLOYMENT"]
async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(
            project_endpoint=PROJECT_ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT,
            async_credential=credential,
            agent_name="HelperAgent"
        ).create_agent(
            instructions="You are a helpful assistant."
        ) as agent,
    ):
        result = await agent.run("Hello!")
        print(result.text)

asyncio.run(main())

async def probe_pager_agent(PROBE_PAGER_AGENT_ID):
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential
        ) as project_client,
    ):
        try: 
            #PROBE_PAGER_AGENT_ID = os.environ["PROBE_PAGER_AGENT_ID"]
            if PROBE_PAGER_AGENT_ID:
                # Try to get existing agent
                async with ChatAgent(
                    chat_client=AzureAIAgentClient(
                        project_client=project_client,
                        agent_id=PROBE_PAGER_AGENT_ID
                    ),
                    instructions="You are a helpful assistant."
                ) as probe_agent:
                    
                    return probe_agent
            else:
                created_agent = await project_client.agents.create_agent(
                      model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                     name="ProbePagerAgent",
                     instructions="You are a helpful assistant."
                 )
                return created_agent
        except Exception as e:
            print(f"Could not retrieve existing Probe Pager Agent: {e}")
            raise 

async def extractor_agent_20(EXTRACTOR_AGENT_20_ID):
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential
        ) as project_client,
    ):
        try: 
            #EXTRACTOR_AGENT_ID = os.environ["EXTRACTOR_AGENT_ID"]
            if EXTRACTOR_AGENT_20_ID:
                # Try to get existing agent
                async with ChatAgent(
                    chat_client=AzureAIAgentClient(
                        project_client=project_client,
                        agent_id=EXTRACTOR_AGENT_20_ID
                    ),
                    instructions=EXTRACTOR_AGENT_PROMPT_20
                ) as extractor_agent_20:

                    return extractor_agent_20
            else:
                created_agent = await project_client.agents.create_agent(
                      model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                     name="ExtractorAgent20",
                     instructions=EXTRACTOR_AGENT_PROMPT_20,
                     tools=[di_prebuilt_read]
                 )
                return created_agent
        except Exception as e:
            print(f"Could not retrieve existing Extractor Agent 20: {e}")
            raise

async def extractor_agent(EXTRACTOR_AGENT_ID):
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential
        ) as project_client,
    ):
        try: 
            #EXTRACTOR_AGENT_ID = os.environ["EXTRACTOR_AGENT_ID"]
            if EXTRACTOR_AGENT_ID:
                # Try to get existing agent
                async with ChatAgent(
                    chat_client=AzureAIAgentClient(
                        project_client=project_client,
                        agent_id=EXTRACTOR_AGENT_ID
                    ),
                    instructions=EXTRACTOR_AGENT_PROMPT
                ) as extractor_agent_20:

                    return extractor_agent_20
            else:
                created_agent = await project_client.agents.create_agent(
                      model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                     name="ExtractorAgent",
                     instructions=EXTRACTOR_AGENT_PROMPT,
                     tools=[di_prebuilt_read]
                 )
                return created_agent
        except Exception as e:
            print(f"Could not retrieve existing Extractor Agent 20: {e}")
            raise

async def compliance_agent(COMPLIANCE_AGENT_ID,prompt):
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential
        ) as project_client,
    ):
        try: 
            #COMPLIANCE_AGENT_ID = os.environ["COMPLIANCE_AGENT_ID"]
            if COMPLIANCE_AGENT_ID:
                # Try to get existing agent
                async with ChatAgent(
                    chat_client=AzureAIAgentClient(
                        project_client=project_client,
                        agent_id=COMPLIANCE_AGENT_ID
                    ),
                    instructions=prompt
                ) as compliance_agent:
                    return compliance_agent
            else:
                created_agent = await project_client.agents.create_agent(
                      model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                     name="ComplianceAgent",
                     instructions=prompt
                 )
                return created_agent
        except Exception as e:
            print(f"Could not retrieve existing Compliance Agent: {e}")
            raise 
        