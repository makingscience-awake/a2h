"""
Example: Running the A2H Server and using Webhooks.

This script demonstrates how to start the A2H HTTP transport server
and register a webhook callback so external systems (like Slack or a custom dashboard)
can be notified when a human responds.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from a2h import Gateway, Participant
from a2h.server import create_app
from a2h.callbacks import CallbackRegistry, WebhookTarget

def main():
    print("=== A2H Server & Webhook Example ===\n")
    
    # 1. Initialize the A2H Gateway
    gw = Gateway()
    
    # 2. Register a human participant
    gw.register(Participant(
        name="ops_team", 
        namespace="infrastructure", 
        participant_type="human",
        channels=["dashboard"]
    ))
    
    # 3. Setup Callbacks and Webhooks
    callbacks = CallbackRegistry(gw)
    
    # Example A: A simple Python callback function
    async def on_response(interaction):
        print(f"\n🔔 [Python Callback] Human responded to {interaction.id}!")
        print(f"   Answer: {interaction.response.to_dict()}")
    
    callbacks.on_all_responses(on_response)
    
    # Example B: A Webhook Target (HTTP POST to an external URL)
    # In a real app, this URL would be your backend server or a Slack webhook
    webhook = WebhookTarget(
        url="https://httpbin.org/post", # A public echo server for testing
        events=["response", "expired"],
        secret="my-super-secret-key"    # Used to sign the payload (HMAC-SHA256)
    )
    callbacks.on_all_responses(webhook.fire)
    
    # 4. Create the FastAPI app
    app = create_app(gw)
    
    print("🚀 A2H Server is ready!")
    print("To run this server, use:")
    print("  uvicorn examples.server_webhook_example:app --reload")
    print("\nOnce running, you can test it with:")
    print("  1. Create a request:")
    print("     curl -X POST http://127.0.0.1:8000/a2h/v1/requests \\")
    print("          -H 'Content-Type: application/json' \\")
    print("          -d '{\"to\": \"infrastructure/ops_team\", \"question\": \"Restart DB?\", \"response_type\": \"confirm\"}'")
    print("\n  2. Respond to the request (this will trigger the callbacks and webhook!):")
    print("     curl -X POST http://127.0.0.1:8000/a2h/v1/requests/<REQUEST_ID>/respond \\")
    print("          -H 'Content-Type: application/json' \\")
    print("          -d '{\"response\": {\"confirmed\": true}}'")

# This allows uvicorn to import 'app' directly
gw = Gateway()
gw.register(Participant(name="ops_team", namespace="infrastructure"))
app = create_app(gw)

if __name__ == "__main__":
    main()
