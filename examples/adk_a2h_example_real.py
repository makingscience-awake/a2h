"""
This is how the code looks when using the REAL Google ADK library.
(This script won't run unless `pip install google-adk` is executed)
"""

import asyncio
from a2h import Gateway, Participant
from integrations.adk.a2h_adk import build_a2h_tools

# Import the real ADK Agent
from google.adk.agents import Agent

async def main():
    # 1. Initialize the A2H Gateway
    gw = Gateway()
    
    # 2. Register a human participant (Sarah from Support)
    gw.register(Participant(
        name="sarah", 
        namespace="support", 
        participant_type="human",
        channels=["dashboard", "slack"]
    ))
    
    # 3. Build the ADK tools from the Gateway
    # This automatically creates 'human_ask', 'human_check', and 'human_notify'
    # wrapped in ADK's FunctionTool class.
    a2h_tools = build_a2h_tools(gw, from_name="refund-bot", from_namespace="billing")
    
    # 4. Create the ADK Agent and give it the A2H tools
    agent = Agent(
        name="refund-bot",
        model="gemini-2.5-flash",
        instruction=(
            "You are a billing assistant. You can process refunds, but any refund "
            "over $100 MUST be approved by a human manager using the human_ask tool. "
            "Always ask 'sarah' in the 'support' namespace."
        ),
        tools=a2h_tools
    )
    
    # 5. Run the agent
    # The agent will automatically pause, call the human_ask tool, and wait for
    # Sarah to approve the request via the A2H Gateway before continuing.
    response = await agent.run("A customer requested a $500 refund for ticket #1234. Please process it.")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
