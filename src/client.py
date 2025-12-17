"""HTTP client for communicating with LiteLLM proxy server."""

import ast
import json
from typing import Any, Dict, List, Optional

import requests


class ProxyClient:
    """Client for making requests to the LiteLLM proxy server."""

    def __init__(self, base_url: str = "http://localhost:4000", api_key: str = "dummy-key"):
        """Initialize the proxy client.

        Args:
            base_url: Base URL of the LiteLLM proxy server
            api_key: API key for authentication (can be dummy for local proxy)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_endpoint = f"{self.base_url}/v1/chat/completions"

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        guardrails: Optional[List[str]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Make a chat completion request to the proxy.

        Args:
            model: Model name to use
            messages: List of message dictionaries with 'role' and 'content'
            guardrails: Optional list of guardrail names to apply
            stream: Whether to stream the response
            **kwargs: Additional parameters to pass to the API

        Returns:
            Response dictionary from the API

        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs,
        }

        if guardrails:
            payload["guardrails"] = guardrails

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.post(
            self.chat_endpoint,
            json=payload,
            headers=headers,
            timeout=60,
        )

        # Handle errors
        if response.status_code != 200:
            try:
                error_data = response.json()
                
                # Check for Lakera guardrail violation - multiple possible formats
                lakera_response = None
                violations = []
                
                # Format 1: Direct lakera_guardrail_response in error_data (top level)
                if "lakera_guardrail_response" in error_data:
                    lakera_response = error_data.get("lakera_guardrail_response", {})
                    breakdown = lakera_response.get("breakdown", [])
                    for detector in breakdown:
                        if detector.get("detected", False):
                            detector_type = detector.get("detector_type", "unknown")
                            violations.append(detector_type)
                
                # Format 2: Nested in error.message (may be JSON string or Python dict string)
                elif "error" in error_data:
                    error_obj = error_data.get("error", {})
                    error_msg = error_obj.get("message", "") if isinstance(error_obj, dict) else str(error_obj)
                    
                    # Try to parse error_msg - could be JSON or Python dict string
                    if isinstance(error_msg, str):
                        parsed_error = None
                        # Try JSON first
                        try:
                            parsed_error = json.loads(error_msg)
                        except (json.JSONDecodeError, TypeError):
                            # Try Python literal eval (safer than eval)
                            try:
                                parsed_error = ast.literal_eval(error_msg)
                            except (ValueError, SyntaxError):
                                pass
                        
                        if parsed_error and isinstance(parsed_error, dict):
                            if "lakera_guardrail_response" in parsed_error:
                                lakera_response = parsed_error.get("lakera_guardrail_response", {})
                                breakdown = lakera_response.get("breakdown", [])
                                for detector in breakdown:
                                    if detector.get("detected", False):
                                        detector_type = detector.get("detector_type", "unknown")
                                        violations.append(detector_type)
                    
                    # Format 3: Nested in error dict with lakera_ai_response
                    if isinstance(error_obj, dict) and not violations:
                        lakera_response = error_obj.get("lakera_ai_response", {})
                        if lakera_response:
                            results = lakera_response.get("results", [])
                            if results and results[0].get("flagged"):
                                categories = results[0].get("categories", {})
                                category_scores = results[0].get("category_scores", {})
                                violations = [cat for cat, flagged in categories.items() if flagged]
                
                # If we found violations, raise the appropriate error
                if violations:
                    raise GuardrailViolationError(
                        "LiteLLM has flagged this message due to policy violations",
                        violations=violations,
                        lakera_response=lakera_response,
                    )
                
                # No guardrail violation found, raise generic API error
                error_msg = error_data.get("error", {})
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", str(error_msg))
                elif not isinstance(error_msg, str):
                    error_msg = str(error_data.get("error", "Unknown error"))
                
                raise APIError(f"API error ({response.status_code}): {error_msg}")
            except GuardrailViolationError:
                raise  # Re-raise guardrail violations
            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                raise APIError(f"API error ({response.status_code}): {response.text}")

        return response.json()

    def health_check(self) -> bool:
        """Check if the proxy server is healthy.

        Returns:
            True if the server is healthy, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False


class APIError(Exception):
    """Raised when an API request fails."""

    pass


class GuardrailViolationError(APIError):
    """Raised when a guardrail violation is detected."""

    # Map detector types to human-readable names
    VIOLATION_NAMES = {
        "moderated_content/crime": "Crime-related content",
        "moderated_content/hate": "Hate speech",
        "moderated_content/profanity": "Profanity",
        "moderated_content/sexual": "Sexual content",
        "moderated_content/violence": "Violence",
        "moderated_content/weapons": "Weapons",
        "pii/address": "Personal address",
        "pii/credit_card": "Credit card number",
        "pii/email": "Email address",
        "pii/iban_code": "IBAN code",
        "pii/ip_address": "IP address",
        "pii/name": "Personal name",
        "pii/phone_number": "Phone number",
        "pii/us_social_security_number": "Social Security Number",
        "prompt_attack": "Prompt injection attack",
        "jailbreak": "Jailbreak attempt",
        "prompt_injection": "Prompt injection",
        "unknown_links": "Unknown links",
    }

    def __init__(
        self,
        message: str,
        violations: Optional[List[str]] = None,
        categories: Optional[Dict[str, bool]] = None,
        category_scores: Optional[Dict[str, float]] = None,
        lakera_response: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the guardrail violation error.

        Args:
            message: Error message
            violations: List of detected violation types
            categories: Detected violation categories (legacy format)
            category_scores: Scores for each category
            lakera_response: Full Lakera response
        """
        super().__init__(message)
        self.violations = violations or []
        self.categories = categories or {}
        self.category_scores = category_scores or {}
        self.lakera_response = lakera_response
        
        # Convert categories dict to violations list if needed
        if not self.violations and self.categories:
            self.violations = [cat for cat, flagged in self.categories.items() if flagged]

    def _format_violation_name(self, violation_type: str) -> str:
        """Format a violation type into a human-readable name."""
        # Check if it's a known violation type
        if violation_type in self.VIOLATION_NAMES:
            return self.VIOLATION_NAMES[violation_type]
        
        # Format unknown types nicely
        return violation_type.replace("_", " ").replace("/", " - ").title()

    def __str__(self) -> str:
        """Return a formatted error message."""
        msg = f"{self.args[0]}"
        
        if self.violations:
            msg += "\n\nDetected policy violations:"
            for violation in self.violations:
                violation_name = self._format_violation_name(violation)
                msg += f"\n  • {violation_name}"
                # Add score if available
                if self.category_scores and violation in self.category_scores:
                    score = self.category_scores[violation]
                    msg += f" (confidence: {score:.1%})"
        
        msg += "\n\nPlease revise your message to comply with the content safety policy."
        
        return msg

