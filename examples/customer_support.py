#!/usr/bin/env python3
"""
A2H Example: Customer Support Complaint Handling

A support agent receives a complaint ticket, investigates it,
and asks humans for decisions at key points. Shows every A2H
feature in a realistic workflow.

Run:
    python examples/customer_support.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from a2h import (
    DelegationRule,
    EscalationChain,
    EscalationLevel,
    Gateway,
    Participant,
)

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
B = "\033[1m"; M = "\033[95m"; D = "\033[90m"; RS = "\033[0m"

def step(n, title):
    print(f"\n{B}{C}Step {n}: {title}{RS}")

def agent(t):  print(f"  {G}[agent]{RS} {t}")
def human(t):  print(f"  {M}[human]{RS} {t}")
def proto(t):  print(f"  {Y}[a2h]{RS}   {t}")
def info(t):   print(f"  {D}        {t}{RS}")


async def main():
    print(f"\n{B}{'='*60}{RS}")
    print(f"{B} Customer Support: Complaint Ticket #4521{RS}")
    print(f"{B}{'='*60}{RS}")
    print(f"{D} Customer: Jane Smith (Premium tier, 3-year account)")
    print(f" Issue: Charged twice for annual subscription ($499 each)")
    print(f" Mood: Angry — third time contacting support{RS}")

    # ─── Setup ───────────────────────────────────────────────
    gw = Gateway()

    # Register humans
    gw.register(Participant(
        name="maria", namespace="support",
        role="Senior Support Agent",
        channels=["dashboard"],
    ))
    gw.register(Participant(
        name="rachel", namespace="support",
        role="Support Team Lead",
        channels=["dashboard", "slack"],
        delegation_rules=[
            DelegationRule(
                name="auto_approve_small_refunds",
                from_name_pattern="support-*",
                response_type="approval",
                context_conditions={"refund_amount": {"lt": 100}},
                auto_response={
                    "approved": True,
                    "reason": "Auto-approved: refund under $100",
                },
            ),
        ],
    ))
    gw.register(Participant(
        name="david", namespace="finance",
        role="Finance Manager",
        channels=["dashboard", "slack", "email"],
    ))

    # ─── Step 1: Agent triages the complaint ─────────────────
    step(1, "Support agent triages complaint")
    agent("Analyzing ticket #4521...")
    agent("Customer: Jane Smith (Premium, $14K lifetime value)")
    agent("Issue: duplicate charge of $499")
    agent("Sentiment: angry (3rd contact about this issue)")
    agent("Decision: refund is warranted, needs approval")

    # ─── Step 2: Agent asks Maria (support agent) to confirm ─
    step(2, "Agent asks Maria to confirm the refund details")
    proto("human__ask → support/maria (response_type: confirm)")

    req1 = await gw.ask("support/maria",
        question=(
            "Ticket #4521: Jane Smith was charged twice for annual subscription "
            "($499 each). She's a Premium customer with $14K lifetime value and "
            "this is her 3rd contact about this issue. "
            "Confirm I should proceed with a $499 refund?"
        ),
        response_type="confirm",
        priority="high",
        context={
            "ticket_id": "4521",
            "customer": "Jane Smith",
            "tier": "Premium",
            "lifetime_value": 14000,
            "charge_amount": 499,
            "duplicate": True,
            "contact_count": 3,
            "sentiment": "angry",
        },
        from_name="support-bot",
        from_namespace="support",
    )
    info(f"Request ID: {req1.id}")
    info(f"Status: {req1.status.value}")
    info(f"Deadline: {req1.deadline}")

    # Maria confirms
    human("Maria reviews the ticket details...")
    human("Maria clicks: Confirmed")
    gw.respond(req1.id, {"confirmed": True, "text": "Yes, proceed with refund. Clear duplicate."}, channel="dashboard")

    result1 = gw.get(req1.id)
    proto(f"Response: confirmed={result1.response.confirmed}")
    proto(f"Channel: {result1.response.channel}")
    agent("Confirmed. Proceeding to refund approval.")

    # ─── Step 3: Agent asks Rachel (team lead) for approval ──
    step(3, "Agent asks Rachel for refund approval ($499)")
    proto("human__ask → support/rachel (response_type: approval)")
    info("Rachel has auto-approve rule for refunds < $100")
    info("$499 > $100 → auto-delegation does NOT apply")

    req2 = await gw.ask("support/rachel",
        question=(
            "Approve refund of $499 for ticket #4521? "
            "Jane Smith (Premium) was charged twice for annual subscription. "
            "Maria has confirmed the duplicate charge."
        ),
        response_type="approval",
        priority="high",
        deadline="2h",
        escalation=EscalationChain(levels=[
            EscalationLevel(target="support/rachel", timeout_minutes=30),
            EscalationLevel(target="finance/david", timeout_minutes=60,
                            priority_override="critical"),
        ]),
        context={
            "ticket_id": "4521",
            "refund_amount": 499,
            "customer": "Jane Smith",
            "tier": "Premium",
            "lifetime_value": 14000,
            "confirmed_by": "maria",
            "reason": "duplicate_charge",
        },
        from_name="support-bot",
        from_namespace="support",
    )
    info(f"Request ID: {req2.id}")
    info(f"Status: {req2.status.value} (auto-delegation did not match: $499 > $100)")
    info(f"Escalation: rachel(30min) → david(60min)")

    # Rachel approves
    human("Rachel reviews in Slack...")
    human("Rachel clicks: Approve")
    gw.respond(req2.id, {
        "approved": True,
        "reason": "Clear duplicate. Premium customer, high LTV. Approve immediately.",
    }, channel="slack")

    result2 = gw.get(req2.id)
    proto(f"Response: approved={result2.response.approved}")
    proto(f"Reason: {result2.response.text or result2.response.metadata.get('reason', '')}")
    agent("Refund approved by Rachel. Processing...")

    # ─── Step 4: Agent asks Rachel about compensation ────────
    step(4, "Agent recommends additional compensation")
    agent("3rd contact, angry customer, Premium tier → recommend goodwill credit")
    proto("human__ask → support/rachel (response_type: choice)")

    req3 = await gw.ask("support/rachel",
        question=(
            "Jane Smith has contacted us 3 times about this issue. "
            "She's a Premium customer ($14K LTV). I recommend a goodwill "
            "credit to retain her. How much?"
        ),
        response_type="choice",
        options=[
            {"label": "1 month free", "value": "1_month", "description": "Credit $41.58 (1/12 of annual)"},
            {"label": "2 months free", "value": "2_months", "description": "Credit $83.17 (2/12 of annual)"},
            {"label": "No credit", "value": "none", "description": "Refund only, no additional compensation"},
            {"label": "Custom amount", "value": "custom", "description": "Enter a specific amount"},
        ],
        priority="medium",
        context={
            "ticket_id": "4521",
            "customer": "Jane Smith",
            "contact_count": 3,
            "lifetime_value": 14000,
            "annual_subscription": 499,
            "agent_recommendation": "2_months",
        },
        from_name="support-bot",
        from_namespace="support",
    )

    human("Rachel reviews compensation options...")
    human("Rachel selects: 2 months free")
    gw.respond(req3.id, {
        "value": "2_months",
        "text": "Give her 2 months. She's been very patient.",
    }, channel="slack")

    result3 = gw.get(req3.id)
    proto(f"Response: {result3.response.value}")
    agent("Applying 2-month credit ($83.17) to Jane's account.")

    # ─── Step 5: Auto-delegation example ─────────────────────
    step(5, "Agent processes a small courtesy refund (auto-delegated)")
    agent("Jane also had a $15 late fee from the billing confusion")
    proto("human__ask → support/rachel (response_type: approval)")
    info("Rachel's rule: auto-approve refunds < $100 from support-*")
    info("$15 < $100 → AUTO-DELEGATED (no human action needed)")

    req4 = await gw.ask("support/rachel",
        question="Waive $15 late fee for Jane Smith (caused by billing confusion)?",
        response_type="approval",
        context={
            "ticket_id": "4521",
            "refund_amount": 15,
            "reason": "late_fee_waiver",
        },
        from_name="support-bot",
        from_namespace="support",
    )

    proto(f"Status: {req4.status.value}")
    proto(f"Auto-response: approved={req4.response.approved}")
    proto(f"Reason: {req4.response.metadata.get('reason', '')}")
    agent("Late fee waived automatically. No human action needed.")

    # ─── Step 6: Agent notifies Maria of resolution ──────────
    step(6, "Agent notifies Maria that the ticket is resolved")
    proto("notification → support/maria (no response needed)")

    notif = await gw.notify("support/maria",
        message=(
            "Ticket #4521 resolved. "
            "Actions taken: $499 refund (approved by Rachel), "
            "2-month credit ($83.17), $15 late fee waived (auto-approved). "
            "Total compensation: $597.17. "
            "Please call Jane to confirm and close the ticket."
        ),
        severity="success",
        priority="medium",
        context={
            "ticket_id": "4521",
            "refund": 499,
            "credit": 83.17,
            "late_fee_waiver": 15,
            "total": 597.17,
            "next_action": "Call customer to confirm",
        },
        from_name="support-bot",
    )
    info(f"Notification ID: {notif.id}")
    human("Maria sees notification in dashboard")
    human("Maria calls Jane to confirm resolution")

    # ─── Step 7: Agent notifies David (finance) ──────────────
    step(7, "Agent notifies Finance of the total adjustment")
    proto("notification → finance/david")

    await gw.notify("finance/david",
        message=(
            "Customer refund processed: Jane Smith (Premium). "
            "Refund: $499 (duplicate charge). Credit: $83.17 (goodwill, 2 months). "
            "Late fee waiver: $15. Total: $597.17. "
            "Approved by Rachel Torres (Support Lead)."
        ),
        severity="info",
        priority="low",
        context={"ticket_id": "4521", "total_adjustment": 597.17,
                 "approved_by": "rachel"},
        from_name="support-bot",
        from_namespace="support",
    )
    human("David sees notification in dashboard (end of day)")

    # ─── Summary ─────────────────────────────────────────────
    print(f"\n{B}{'='*60}{RS}")
    print(f"{B} Ticket #4521 — Resolution Summary{RS}")
    print(f"{B}{'='*60}{RS}")
    print(f"""
  Customer:       Jane Smith (Premium, $14K LTV)
  Issue:          Duplicate charge ($499)
  Resolution:     $499 refund + $83.17 credit + $15 fee waiver

  A2H interactions:
    1. {G}confirm{RS}    Maria confirmed duplicate charge       (dashboard)
    2. {G}approval{RS}   Rachel approved $499 refund             (slack)
    3. {G}choice{RS}     Rachel chose 2-month goodwill credit   (slack)
    4. {G}auto{RS}       Rachel's rule auto-approved $15 waiver (no action)
    5. {G}notify{RS}     Maria notified of resolution           (dashboard)
    6. {G}notify{RS}     David notified of financial adjustment (dashboard)

  Protocols used:
    A2H requests:     4 (1 confirm, 1 approval, 1 choice, 1 auto-delegated)
    A2H notifications: 2
    Human actions:     3 (1 auto-delegated, 2 notifications = no action)

  Time:  Agent handled the investigation and routing.
         Humans only made the decisions they needed to make.
""")


if __name__ == "__main__":
    asyncio.run(main())
