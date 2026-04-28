# Instructions for AI Coding Assistants

You are working on the A2H (Agent-to-Human) protocol.
- Always respect the formal spec in docs/a2h-spec.md
- Use Python dataclasses (or Pydantic models if migrating) for all messages
- Prefer async/await for gateway operations
- Keep responses structured and never use free-text unless explicitly allowed
- Add detailed docstrings (Google style) to all functions and classes
- Keep functions under 50 lines where possible
- Ensure strict type hinting (`typing`) everywhere
