"""
Example: Using A2H with CrewAI.

This script demonstrates how to inject A2H tools into a CrewAI Agent
so it can pause its task, ask a human for input, and resume when answered.
"""

import asyncio
import sys
import os

# Add the local a2h package to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from a2h import Gateway, Participant
from a2h.testing import AutoResponder

# In a real app, you would import:
# from integrations.crewai.a2h_crewai import HumanAskTool, HumanNotifyTool
# from crewai import Agent, Task, Crew

async def main():
    print("=== A2H + CrewAI Integration Example ===")
    
    # 1. Initialize the A2H Gateway
    gw = Gateway()
    
    # 2. Register a human participant (e.g., a Senior Developer)
    gw.register(Participant(
        name="senior_dev", 
        namespace="engineering", 
        participant_type="human",
        channels=["slack", "dashboard"]
    ))
    
    # 3. Simulate the human's response for this test
    responder = AutoResponder(gw)
    responder.respond_text("The issue is a race condition in the database connection pool. Add a lock.")
    
    print("🛠️  Building CrewAI BaseTools (HumanAskTool, HumanNotifyTool, HumanCheckTool)...")
    
    # 4. Setup the CrewAI Agent
    print("🤖 Initializing CrewAI Agent (Role: Junior Developer)...")
    print("🤖 Task: 'Debug the production outage. If you get stuck, ask the senior_dev for help.'\n")
    
    # Simulate CrewAI Agent Execution
    print("CrewAI > Junior Developer is analyzing logs...")
    print("CrewAI > Junior Developer is stuck. Deciding to use HumanAskTool.")
    print("CrewAI > Action: HumanAskTool")
    print("CrewAI > Action Input: {'name': 'senior_dev', 'namespace': 'engineering', 'question': 'I am seeing 500 errors on the /checkout endpoint. The logs show a timeout. What should I check next?', 'response_type': 'text'}")
    
    # The tool calls Gateway under the hood
    req = await gw.ask(
        "engineering/senior_dev",
        question="I am seeing 500 errors on the /checkout endpoint. The logs show a timeout. What should I check next?",
        response_type="text"
    )
    
    # Wait for the human (AutoResponder handles this instantly)
    result = await gw.wait(req.id, timeout=5)
    
    print(f"CrewAI > Tool Output: {result.response.to_dict()}")
    print("\nCrewAI > Junior Developer Final Answer: Based on the senior developer's advice, I will add a lock to the database connection pool to fix the race condition.")

if __name__ == "__main__":
    asyncio.run(main())
