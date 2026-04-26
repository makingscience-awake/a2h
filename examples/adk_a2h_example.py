import asyncio
import sys
import os

# Add the local a2h package to the path so we can import it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from a2h import Gateway, Participant
from a2h.testing import AutoResponder

# We need to mock the ADK Agent for this example since we don't have the real ADK installed
# but we want to show how the code would look.
class MockADKAgent:
    def __init__(self, name, model, instruction, tools):
        self.name = name
        self.model = model
        self.instruction = instruction
        self.tools = tools
        
    async def run(self, prompt):
        print(f"\n🤖 Agent '{self.name}' received prompt: {prompt}")
        print("🤖 Agent is thinking...")
        
        # Simulate the agent deciding to use the human_ask tool
        print("🤖 Agent decided to use tool: human_ask")
        
        # Find the human_ask tool
        ask_tool = next(t for t in self.tools if t.__name__ == "human_ask")
        
        # Execute the tool
        print(f"🤖 Agent calling human_ask(name='sarah', question='Approve $500 refund for ticket #1234?', response_type='approval', namespace='support')")
        
        result = await ask_tool(
            name="sarah",
            question="Approve $500 refund for ticket #1234?",
            response_type="approval",
            namespace="support"
        )
        
        print(f"🤖 Agent received tool result: {result}")
        
        if result.get("status") == "answered" and result.get("response", {}).get("approved"):
            print("🤖 Agent final response: The refund of $500 has been approved by Sarah. I will process it now.")
        else:
            print("🤖 Agent final response: The refund was not approved or timed out.")

async def main():
    print("=== A2H + Google ADK Integration Example ===")
    
    # 1. Initialize the A2H Gateway
    gw = Gateway()
    
    # 2. Register a human participant (Sarah from Support)
    gw.register(Participant(
        name="sarah", 
        namespace="support", 
        participant_type="human",
        channels=["dashboard", "slack"]
    ))
    
    # 3. For this example, we'll use the AutoResponder to simulate Sarah clicking "Approve"
    # In a real app, the Gateway would send a Slack message and wait for her real click.
    responder = AutoResponder(gw)
    responder.approve_all(reason="Looks good, customer is a VIP.")
    
    # 4. Build the ADK tools from the Gateway
    # Since we don't have ADK installed, we'll manually create the tool function
    # In a real app, you would just do:
    # from integrations.adk.a2h_adk import build_a2h_tools
    # a2h_tools = build_a2h_tools(gw, from_name="refund-bot", from_namespace="billing")
    
    async def human_ask(name, question, response_type="approval", namespace="default"):
        req = await gw.ask(f"{namespace}/{name}", question=question, response_type=response_type)
        result = await gw.wait(req.id, timeout=2)
        return {"status": result.status.value, "response": result.response.to_dict()}
    human_ask.__name__ = "human_ask"
    
    a2h_tools = [human_ask]
    
    # In a real ADK app, you would import Agent from google.adk.agents
    # from google.adk.agents import Agent
    Agent = MockADKAgent
    
    # 5. Create the ADK Agent and give it the A2H tools
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
    
    # 6. Run the agent
    await agent.run("A customer requested a $500 refund for ticket #1234. Please process it.")

if __name__ == "__main__":
    asyncio.run(main())
