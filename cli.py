#!/usr/bin/env python3
"""CLI tool for interacting with LLMs via LiteLLM proxy with Lakera security."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.chat import ChatSession
from src.client import ProxyClient
from src.proxy_manager import ProxyManager

# Load environment variables from .env file
load_dotenv()


def check_env_vars() -> bool:
    """Check if required environment variables are set.

    Returns:
        True if all required vars are set, False otherwise
    """
    required_vars = ["OPENAI_API_KEY", "LAKERA_API_KEY"]
    missing = []

    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        print("Error: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease set these in your .env file or environment.")
        print("See .env.example for reference.")
        return False

    return True


def proxy_command(args: argparse.Namespace) -> int:
    """Handle proxy management commands.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Get config path from restart subcommand or use default
    config_path = getattr(args, "config", None) or "config.yaml"
    litellm_path = Path("litellm") if Path("litellm").exists() else None

    proxy_manager = ProxyManager(
        config_path=config_path,
        litellm_path=str(litellm_path) if litellm_path else None,
    )

    if args.proxy_action == "restart":
        print("Restarting LiteLLM proxy server...")
        # Always stop first, even if not running (to catch any orphaned processes)
        proxy_manager.stop()
        # Wait a moment for port to be released
        import time
        time.sleep(1)
        if proxy_manager.start():
            print("✓ Proxy restarted successfully")
            print(f"  Using config: {proxy_manager.config_path}")
            return 0
        else:
            print("✗ Failed to restart proxy")
            return 1
    elif args.proxy_action == "stop":
        if proxy_manager.is_running():
            proxy_manager.stop()
            return 0
        else:
            print("Proxy is not running")
            return 0
    elif args.proxy_action == "status":
        if proxy_manager.is_running():
            print(f"✓ Proxy is running at {proxy_manager.PROXY_URL}")
            return 0
        else:
            print("✗ Proxy is not running")
            return 1
    else:
        print("Unknown proxy action. Use: restart, stop, or status")
        return 1


def chat_command(args: argparse.Namespace) -> int:
    """Handle the chat command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    if not check_env_vars():
        return 1

    # Initialize proxy manager
    config_path = args.config or "config.yaml"
    litellm_path = Path("litellm") if Path("litellm").exists() else None

    proxy_manager = ProxyManager(
        config_path=config_path,
        litellm_path=str(litellm_path) if litellm_path else None,
    )

    # Ensure proxy is running
    if not proxy_manager.ensure_running():
        print("Failed to start LiteLLM proxy server.")
        return 1

    # Initialize client and chat session
    client = ProxyClient()
    session = ChatSession(
        client=client,
        model=args.model or "gpt-3.5-turbo",
        # Use empty list to disable guardrails; None would default back to Lakera
        guardrails=["lakera-guard"] if not args.no_guardrails else [],
    )

    # Handle single message or interactive mode
    if args.message:
        # Single message mode
        try:
            response = session.chat(args.message, system_message=args.system)
            session.print_response(response)
            return 0
        except Exception as e:
            session.print_error(e)
            return 1
    else:
        # Interactive mode
        print("\n" + "=" * 60)
        print("LiteLLM Chat with Lakera Security")
        print("=" * 60)
        print("Type your messages (or 'quit'/'exit' to end, 'reset' to clear history)\n")

        try:
            while True:
                try:
                    user_input = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n\nGoodbye!")
                    break

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    print("\nGoodbye!")
                    break

                if user_input.lower() == "reset":
                    session.reset()
                    print("Conversation history cleared.\n")
                    continue

                try:
                    response = session.chat(user_input, system_message=args.system)
                    session.print_response(response)
                except Exception as e:
                    session.print_error(e)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            return 0
        # Normal interactive exit
        return 0


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="CLI tool for interacting with LLMs via LiteLLM proxy with Lakera security",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Chat with an LLM")
    chat_parser.add_argument(
        "message",
        nargs="?",
        help="Message to send (if omitted, starts interactive mode)",
    )
    chat_parser.add_argument(
        "--model",
        "-m",
        default="gpt-3.5-turbo",
        help="Model to use (default: gpt-3.5-turbo)",
    )
    chat_parser.add_argument(
        "--config",
        "-c",
        help="Path to LiteLLM config.yaml file (default: config.yaml)",
    )
    chat_parser.add_argument(
        "--system",
        "-s",
        help="System message to set context",
    )
    chat_parser.add_argument(
        "--no-guardrails",
        action="store_true",
        dest="no_guardrails",
        help="Disable Lakera guardrails (not recommended)",
    )

    # Proxy management commands
    proxy_parser = subparsers.add_parser("proxy", help="Manage LiteLLM proxy server")
    proxy_subparsers = proxy_parser.add_subparsers(dest="proxy_action", help="Proxy action")
    
    restart_parser = proxy_subparsers.add_parser("restart", help="Restart the proxy server")
    restart_parser.add_argument(
        "--config",
        "-c",
        help="Path to LiteLLM config.yaml file (default: config.yaml)",
    )
    
    stop_parser = proxy_subparsers.add_parser("stop", help="Stop the proxy server")
    
    status_parser = proxy_subparsers.add_parser("status", help="Check proxy server status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "chat":
        return chat_command(args)
    elif args.command == "proxy":
        return proxy_command(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

