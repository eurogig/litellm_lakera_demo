# LiteLLM Lakera Demo CLI

A command-line utility for interacting with LLMs via the LiteLLM proxy server, secured with Lakera AI guardrails. This demo runs LiteLLM from source, allowing you to modify and extend it as needed.

## Architecture

The demo uses a hybrid architecture where:
- **LiteLLM Proxy Server**: Runs as a separate service (from cloned source) on port 4000
- **CLI Tool**: Communicates with the proxy via HTTP using OpenAI-compatible API
- **Lakera Guardrails**: Configured in LiteLLM's `config.yaml` to scan inputs before LLM calls

```
┌─────────────┐
│   CLI Tool  │
│  (Python)   │
└──────┬──────┘
       │ HTTP (OpenAI format)
       │
┌──────▼──────────────────┐
│  LiteLLM Proxy Server   │
│  (from cloned source)   │
│  Port 4000              │
└──────┬──────────────────┘
       │
       ├──► Lakera Guardrails (pre_call mode)
       │
       └──► OpenAI API
```

## Features

- ✅ Chat with LLMs via LiteLLM proxy
- ✅ Lakera AI security guardrails (prompt injection, PII detection, etc.)
- ✅ Interactive chat mode and single-message mode
- ✅ Automatic proxy server management
- ✅ Clear error messages for guardrail violations
- ✅ Extensible architecture for tools and agentic scenarios

## Prerequisites

- Python 3.8+
- OpenAI API key
- Lakera API key ([Get one here](https://platform.lakera.ai/))
- Git (for cloning LiteLLM)

## Setup

### 1. Create Virtual Environment

Create and activate a Python virtual environment:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate
```

### 2. Clone LiteLLM (if not already done)

The LiteLLM repository should already be cloned as a submodule. If not:

```bash
git submodule update --init --recursive
```

### 3. Install Dependencies

With your virtual environment activated:

```bash
# Install CLI dependencies
pip install -r requirements.txt

# Install LiteLLM from source
pip install -e ./litellm

# Install LiteLLM proxy dependencies (required for proxy server)
pip install 'litellm[proxy]'
```

### 4. Configure Environment Variables

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```bash
OPENAI_API_KEY=your-openai-api-key-here
LAKERA_API_KEY=your-lakera-api-key-here
# Optional: LAKERA_API_BASE=https://api.lakera.ai
```

### 5. Verify Configuration

The `config.yaml` file is already configured with:
- OpenAI models (gpt-3.5-turbo and gpt-4)
- Lakera guardrails in `pre_call` mode

You can modify `config.yaml` to add more models or adjust guardrail settings.

## Usage

**Note**: Make sure your virtual environment is activated before running commands:

```bash
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows
```

### Single Message Mode

Send a single message and get a response:

```bash
python cli.py chat "Hello, how are you?"
```

### Interactive Mode

Start an interactive chat session:

```bash
python cli.py chat
```

In interactive mode:
- Type your messages and press Enter
- Type `quit`, `exit`, or `q` to end the session
- Type `reset` to clear conversation history

### Proxy Management

Manage the LiteLLM proxy server:

```bash
# Restart the proxy (required after config.yaml changes)
python cli.py proxy restart

# Stop the proxy
python cli.py proxy stop

# Check proxy status
python cli.py proxy status
```

**Important**: After modifying `config.yaml`, you must restart the proxy for changes to take effect:

```bash
python cli.py proxy restart
```

### Command Options

```bash
python cli.py chat [message] [options]

Options:
  -m, --model MODEL       Model to use (default: gpt-3.5-turbo)
  -c, --config PATH       Path to LiteLLM config.yaml (default: config.yaml)
  -s, --system TEXT       System message to set context
  --no-guardrails         Disable Lakera guardrails (not recommended)
```

### Examples

```bash
# Use a specific model
python cli.py chat "Explain quantum computing" --model gpt-4

# Set a system message
python cli.py chat "What's the weather?" --system "You are a helpful assistant."

# Use a custom config file
python cli.py chat "Hello" --config my-config.yaml

# Disable guardrails (not recommended for production)
python cli.py chat "Hello" --no-guardrails
```

## How It Works

1. **Proxy Management**: The CLI automatically starts the LiteLLM proxy server if it's not running
2. **Guardrails**: Every message is checked by Lakera before being sent to the LLM
3. **Error Handling**: If a guardrail violation is detected, you'll see a clear error message with details about what was flagged
4. **Conversation History**: The chat session maintains conversation history for context

## Guardrail Violations

If your message triggers a Lakera guardrail, you'll see an error like:

```
⚠ Guardrail Violation:
Content safety policy violated

Detected violations:
  - prompt_injection: 0.999
  - pii: 0.850
```

Common violations include:
- **Prompt Injection**: Attempts to manipulate the AI
- **PII**: Personal Identifiable Information (emails, phone numbers, etc.)
- **Jailbreak**: Attempts to bypass safety measures

## Project Structure

```
litellm_lakera_demo/
├── README.md                 # This file
├── LICENSE                   # MIT License
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── config.yaml              # LiteLLM proxy configuration
├── cli.py                   # Main CLI entry point
├── src/
│   ├── __init__.py
│   ├── proxy_manager.py     # Manages LiteLLM proxy lifecycle
│   ├── client.py            # HTTP client for proxy communication
│   └── chat.py              # Chat interface logic
├── litellm/                 # Cloned LiteLLM repository (submodule)
└── tests/                   # (Future) Test files
```

## Extending the Demo

The architecture is designed to be easily extensible:

### Adding More LLM Providers

Edit `config.yaml` to add more models:

```yaml
model_list:
  - model_name: claude-3-sonnet
    litellm_params:
      model: anthropic/claude-3-sonnet-20240229
      api_key: os.environ/ANTHROPIC_API_KEY
```

### Adding Tools

LiteLLM supports function calling and tools. To add tool support:

1. Define tools in your chat requests
2. Handle `tool_calls` in `src/chat.py`
3. Execute tools and send results back to the LLM

### Agentic Scenarios

For more complex agentic workflows:

1. Add agent orchestration logic
2. Implement tool execution handlers
3. Add planning and decision-making layers

### MCP/A2A Support

LiteLLM proxy already supports MCP (Model Context Protocol) and A2A (Agent-to-Agent) traffic. You can extend the client to handle these protocols.

## Troubleshooting

### Proxy Won't Start

- Check that LiteLLM is installed: `pip list | grep litellm`
- Verify `config.yaml` exists and is valid YAML
- Check that port 4000 is not in use: `lsof -i :4000`
- Review proxy logs for errors

### Guardrail Errors

- If you're getting false positives, you can adjust Lakera settings in `config.yaml`
- Check your Lakera API key is valid
- Review Lakera dashboard for policy settings

### API Errors

- Verify your OpenAI API key is set correctly
- Check your API key has sufficient credits
- Ensure you have network connectivity

## Development

To modify LiteLLM itself:

1. Make changes in the `litellm/` directory
2. Reinstall: `pip install -e ./litellm`
3. Restart the proxy server

## License

MIT License - see LICENSE file for details.

## References

- [LiteLLM Documentation](https://docs.litellm.ai/docs/)
- [LiteLLM GitHub](https://github.com/BerriAI/litellm)
- [Lakera AI Documentation](https://docs.litellm.ai/docs/proxy/guardrails/lakera_ai)
- [Lakera Platform](https://platform.lakera.ai/)
