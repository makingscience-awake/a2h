"""
Example: Advanced Routing, Escalation Chains, and Auto-Delegation.

This script demonstrates the core power of the A2H protocol:
1. State-aware routing (if someone is away, route to their delegate).
2. Auto-delegation (if a request matches a rule, auto-approve it).
3. Escalation chains (if someone doesn't answer in time, escalate to their boss).
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from a2h import Gateway, Participant, DelegationRule, EscalationChain, EscalationLevel

async def main():
    print("=== A2H Advanced Routing & Escalation Example ===\n")
    
    gw = Gateway()
    
    # 1. Setup Participants
    # Junior Support Agent (Currently Away)
    junior = Participant(
        name="junior", 
        namespace="support",
        current_state="away", # They are away!
        delegate="senior"     # Route to senior if away
    )
    
    # Senior Support Agent (Available)
    senior = Participant(
        name="senior", 
        namespace="support",
        current_state="available",
        # Rule: Auto-approve any refund under $50
        delegation_rules=[
            DelegationRule(
                name="auto_approve_small_refunds",
                response_type="approval",
                context_conditions={"amount": {"lt": 50}},
                auto_response={"approved": True, "text": "Auto-approved by rule (under $50)"}
            )
        ]
    )
    
    # Support Manager (Available)
    manager = Participant(
        name="manager", 
        namespace="support",
        current_state="available"
    )
    
    gw.register(junior)
    gw.register(senior)
    gw.register(manager)
    
    print("👥 Team Status:")
    print(f"  - Junior: {junior.current_state} (Delegate: {junior.delegate})")
    print(f"  - Senior: {senior.current_state} (Has auto-delegation rule for <$50)")
    print(f"  - Manager: {manager.current_state}\n")
    
    # --- SCENARIO 1: State-Aware Routing ---
    print("▶️ SCENARIO 1: Agent asks Junior for help, but Junior is away.")
    req1 = await gw.ask(
        "support/junior",
        question="Can you review this ticket?",
        response_type="text"
    )
    print(f"   Original Target: support/junior")
    print(f"   Actual Target:   {req1.to_namespace}/{req1.to_name} (Rerouted!)")
    print(f"   Status:          {req1.status.value}\n")
    
    # --- SCENARIO 2: Auto-Delegation ---
    print("▶️ SCENARIO 2: Agent asks Senior to approve a $25 refund.")
    req2 = await gw.ask(
        "support/senior",
        question="Approve $25 refund?",
        response_type="approval",
        context={"amount": 25} # This triggers the rule!
    )
    print(f"   Target: support/senior")
    print(f"   Status: {req2.status.value} (Instantly approved without bothering the human!)")
    print(f"   Reason: {req2.response.text}\n")
    
    # --- SCENARIO 3: Escalation Chain ---
    print("▶️ SCENARIO 3: Agent asks Senior for a $500 refund, but they don't answer in time.")
    
    # Create an escalation chain: If no answer in 10 mins, escalate to manager
    chain = EscalationChain(levels=[
        EscalationLevel(target="support/senior", timeout_minutes=10), # Level 0
        EscalationLevel(target="support/manager", timeout_minutes=10, priority_override="high") # Level 1
    ])
    
    req3 = await gw.ask(
        "support/senior",
        question="Approve $500 refund?",
        response_type="approval",
        context={"amount": 500}, # Doesn't trigger rule
        escalation=chain
    )
    print(f"   Target: support/senior")
    print(f"   Status: {req3.status.value}")
    
    # Simulate a timeout (in a real app, a background worker handles this)
    print("   ... 10 minutes pass ...")
    next_level = req3.escalation.promote()
    
    if next_level:
        print(f"   Escalating to: {next_level.target} with priority {next_level.priority_override}")
    
    # The manager finally answers
    gw.respond(req3.id, {"approved": False, "text": "Too high, reject it."})
    
    result = gw.get(req3.id)
    print(f"   Final Status:  {result.status.value}")
    print(f"   Final Answer:  Approved={result.response.approved} ({result.response.text})")

if __name__ == "__main__":
    asyncio.run(main())
