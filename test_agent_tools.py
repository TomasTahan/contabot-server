"""Test of Claude Agent SDK with MCP tools."""
import asyncio
from typing import Any, AsyncIterator
from claude_agent_sdk import query, ClaudeAgentOptions, tool, create_sdk_mcp_server

@tool(
    "saludar",
    "Saluda a una persona por su nombre",
    {"nombre": str}
)
async def saludar(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{
            "type": "text",
            "text": f"¡Hola {args.get('nombre', 'amigo')}!"
        }]
    }

# Create MCP server
test_server = create_sdk_mcp_server(
    name="test_tools",
    version="1.0.0",
    tools=[saludar]
)

async def create_message_stream(text: str) -> AsyncIterator[dict]:
    """Create async generator for streaming input (required for MCP tools)."""
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": text
        }
    }

async def main():
    print("Testing Claude Agent SDK with MCP tools...")

    options = ClaudeAgentOptions(
        system_prompt="Eres un asistente. Usa la herramienta saludar cuando te pidan saludar a alguien.",
        mcp_servers={"test": test_server},
        allowed_tools=["mcp__test__saludar"],
        max_turns=3,
    )

    try:
        response_text = ""
        # Use async generator for prompt (required for MCP servers)
        async for message in query(prompt=create_message_stream("Saluda a Juan"), options=options):
            print(f"Message type: {type(message).__name__}")
            if hasattr(message, "type"):
                print(f"  type: {message.type}")
            if hasattr(message, "content"):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text
                        print(f"  text: {block.text}")
        print(f"\nFinal response: {response_text}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
