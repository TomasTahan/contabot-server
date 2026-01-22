"""Simple test of Claude Agent SDK."""
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    print("Testing Claude Agent SDK...")

    options = ClaudeAgentOptions(
        system_prompt="Eres un asistente amigable. Responde brevemente.",
        max_turns=1,
    )

    try:
        async for message in query(prompt="Hola, di solo 'Funciona!'", options=options):
            print(f"Message type: {type(message)}")
            if hasattr(message, "type"):
                print(f"  type: {message.type}")
            if hasattr(message, "content"):
                print(f"  content: {message.content}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
