"""
Demo: CrewAI agent using A2H protocol to interact with a human.

A research agent investigates a topic and asks a human manager for
approval before publishing its findings.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from crewai import Agent, Task, Crew, LLM
from integrations.crewai.a2h_crewai import build_a2h_tools
from a2h import Gateway, Participant, DelegationRule
from a2h.testing import MockChannel


def main():
    # -- A2H setup --
    channel = MockChannel()
    gw = Gateway(channels=[channel])

    gw.register(Participant(
        name="manager",
        namespace="company",
        participant_type="human",
        role="Engineering Manager",
        channels=["dashboard", "slack"],
        delegation_rules=[
            DelegationRule(
                name="auto-approve-research",
                response_type="approval",
                auto_response={"approved": True, "text": "Looks good, go ahead and publish."},
            )
        ],
    ))

    # Register the agent participant so sender identity is verified
    gw.register(Participant(
        name="research-agent",
        namespace="company",
        participant_type="agent",
        role="Research Analyst",
    ))

    # -- Build A2H tools for CrewAI --
    a2h_tools = build_a2h_tools(gw, from_participant="company/research-agent")
    print(f"A2H tools available: {[t.name for t in a2h_tools]}\n")

    # -- CrewAI agent --
    llm = LLM(model="claude-sonnet", temperature=0)

    researcher = Agent(
        role="Research Analyst",
        goal="Research topics and get human approval before publishing findings",
        backstory=(
            "You are a diligent research analyst. You always validate your work "
            "with your human manager before publishing. You use the human_ask tool "
            "to request approval and human_notify to send status updates."
        ),
        tools=a2h_tools,
        llm=llm,
        verbose=True,
    )

    research_task = Task(
        description=(
            "Research the benefits of using AI agents in customer support workflows. "
            "Write a brief 3-bullet summary of your findings. "
            "Then use the human_ask tool to ask 'manager' in namespace 'company' "
            "for approval (response_type='approval') to publish these findings. "
            "Include your summary in the context parameter as JSON: "
            '{\"summary\": \"your 3-bullet summary here\"}. '
            "After getting the approval response, use human_notify to notify "
            "'manager' in namespace 'company' that the report has been published. "
            "Return the final summary along with the approval status."
        ),
        expected_output="A 3-bullet research summary with the human manager's approval status.",
        agent=researcher,
    )

    crew = Crew(
        agents=[researcher],
        tasks=[research_task],
        verbose=True,
    )

    # -- Run --
    print("=" * 60)
    print("Starting CrewAI + A2H demo...")
    print("=" * 60 + "\n")

    result = crew.kickoff()

    print("\n" + "=" * 60)
    print("CREW RESULT")
    print("=" * 60)
    print(result)

    # -- Show A2H activity --
    print("\n" + "=" * 60)
    print("A2H PROTOCOL ACTIVITY")
    print("=" * 60)
    print(f"Requests delivered via channels: {len(channel.requests)}")
    for r in channel.requests:
        print(f"  - [{r.response_type.value}] {r.question[:80]}")
    print(f"Notifications delivered: {len(channel.notifications)}")
    for n in channel.notifications:
        print(f"  - [{n.severity}] {n.message[:80]}")


if __name__ == "__main__":
    main()
