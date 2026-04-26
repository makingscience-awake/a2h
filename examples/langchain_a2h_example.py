"""
Example: Using A2H with LangChain Agents.

This script demonstrates how to inject A2H tools into a LangChain AgentExecutor
so the LLM can pause its execution, ask a human for input, and resume when answered.
"""

import asyncio
import sys
import os

# Add the local a2h package to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from a2h import Gateway, Participant
from a2h.testing import AutoResponder

# In a real app, you would import:
# from integrations.langchain.a2h_langchain import build_a2h_tools
# from langchain.agents import AgentExecutor, create_tool_calling_agent
# from langchain_openai import ChatOpenAI

async def main():
    print("=== A2H + LangChain Integration Example ===")
    
    # 1. Initialize the A2H Gateway
    gw = Gateway()
    
    # 2. Register a human participant (e.g., a Sales Director)
    gw.register(Participant(
        name="director", 
        namespace="sales", 
        participant_type="human",
        channels=["dashboard", "email"]
    ))
    
    # 3. Simulate the human's response for this test
    responder = AutoResponder(gw)
    responder.respond_choice("discount_10") # The director chooses a 10% discount
    
    # 4. Build the LangChain tools from the Gateway
    # a2h_tools = build_a2h_tools(gw, from_name="sales-bot", from_namespace="sales")
    print("🛠️  Building LangChain StructuredTools (human_ask, human_check, human_notify)...")
    
    # 5. Setup the LangChain Agent
    print("🤖 Initializing LangChain AgentExecutor...")
    print("🤖 Agent Prompt: 'A client wants to buy 500 licenses. Ask the sales director what discount to offer.'\n")
    
    # Simulate LangChain Agent Execution
    print("LangChain > Invoking tool: human_ask")
    print("LangChain > Tool Input: {'name': 'director', 'namespace': 'sales', 'question': 'What discount should we offer for 500 licenses?', 'response_type': 'choice', 'options': '[{\"label\": \"No Discount\", \"value\": \"none\"}, {\"label\": \"10% Discount\", \"value\": \"discount_10\"}]'}")
    
    # The tool calls Gateway under the hood
    req = await gw.ask(
        "sales/director",
        question="What discount should we offer for 500 licenses?",
        response_type="choice",
        options=[
            {"label": "No Discount", "value": "none"},
            {"label": "10% Discount", "value": "discount_10"}
        ]
    )
    
    # Wait for the human (AutoResponder handles this instantly)
    result = await gw.wait(req.id, timeout=5)
    
    print(f"LangChain > Tool Output: {result.response.to_dict()}")
    print("\nLangChain > Final Answer: The sales director has approved a 10% discount. I will draft the proposal with this pricing.")

if __name__ == "__main__":
    asyncio.run(main())
