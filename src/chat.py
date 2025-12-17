"""Chat interface for interacting with LLMs via LiteLLM proxy."""

from typing import List, Optional

from colorama import Fore, Style, init

from src.client import APIError, GuardrailViolationError, ProxyClient

# Initialize colorama for cross-platform colored output
init(autoreset=True)


class ChatSession:
    """Manages a chat session with conversation history."""

    def __init__(
        self,
        client: ProxyClient,
        model: str = "gpt-3.5-turbo",
        guardrails: Optional[List[str]] = None,
    ):
        """Initialize a chat session.

        Args:
            client: ProxyClient instance for making API calls
            model: Model name to use
            guardrails: Optional list of guardrail names to apply
        """
        self.client = client
        self.model = model
        self.guardrails = guardrails or ["lakera-guard"]
        self.messages: List[dict] = []

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history.

        Args:
            role: Message role ('user', 'assistant', or 'system')
            content: Message content
        """
        self.messages.append({"role": role, "content": content})

    def chat(self, user_message: str, system_message: Optional[str] = None) -> str:
        """Send a chat message and get a response.

        Args:
            user_message: The user's message
            system_message: Optional system message (only added once at start)

        Returns:
            The assistant's response

        Raises:
            GuardrailViolationError: If content violates guardrails
            APIError: If the API request fails
        """
        # Add system message if provided and not already in history
        if system_message and not any(m.get("role") == "system" for m in self.messages):
            self.add_message("system", system_message)

        # Add user message
        self.add_message("user", user_message)

        try:
            response = self.client.chat_completion(
                model=self.model,
                messages=self.messages,
                guardrails=self.guardrails,
            )

            # Extract assistant response
            choices = response.get("choices", [])
            if not choices:
                raise APIError("No response choices in API response")

            assistant_message = choices[0].get("message", {}).get("content", "")
            if not assistant_message:
                raise APIError("Empty response from assistant")

            # Add assistant response to history
            self.add_message("assistant", assistant_message)

            return assistant_message

        except GuardrailViolationError as e:
            # Remove the user message from history since it was blocked
            if self.messages and self.messages[-1].get("role") == "user":
                self.messages.pop()
            raise

    def reset(self) -> None:
        """Reset the conversation history."""
        self.messages = []

    def print_response(self, response: str) -> None:
        """Pretty print the assistant's response.

        Args:
            response: The response text to print
        """
        print(f"\n{Fore.GREEN}{Style.BRIGHT}Assistant:{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{response}{Style.RESET_ALL}\n")

    def print_error(self, error: Exception) -> None:
        """Pretty print an error message.

        Args:
            error: The error to print
        """
        if isinstance(error, GuardrailViolationError):
            print(f"\n{Fore.RED}{Style.BRIGHT}⚠ Content Safety Policy Violation:{Style.RESET_ALL}")
            # Split the error message into lines and format nicely
            error_lines = str(error).split("\n")
            for line in error_lines:
                if line.strip():
                    if line.startswith("Detected policy violations:"):
                        print(f"{Fore.YELLOW}{line}{Style.RESET_ALL}")
                    elif line.startswith("  •"):
                        print(f"{Fore.YELLOW}{line}{Style.RESET_ALL}")
                    elif line.startswith("Please revise"):
                        print(f"{Fore.CYAN}{line}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}{line}{Style.RESET_ALL}")
            print()  # Extra newline at end
        elif isinstance(error, APIError):
            print(f"\n{Fore.RED}{Style.BRIGHT}✗ API Error:{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{str(error)}{Style.RESET_ALL}\n")
        else:
            print(f"\n{Fore.RED}{Style.BRIGHT}✗ Error:{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{str(error)}{Style.RESET_ALL}\n")

