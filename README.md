# easy-codex-mcp

An [MCP](https://modelcontextprotocol.io/) server that lets any MCP-compatible AI assistant have **read-only conversations with OpenAI Codex CLI**.

No complex setup — just `codex login` and you're ready.

## Why?

Sometimes your AI assistant needs a second opinion. **easy-codex-mcp** bridges the gap by letting Claude, Cursor, or any MCP client consult Codex for code analysis, review, and Q&A — all in a **non-destructive, read-only sandbox**.

- 🔒 **Read-only by design** — Codex runs in sandbox mode. It reads your code but never modifies files or runs commands.
- 💬 **Conversational** — Start a thread and continue it later with full context preserved.
- 🔧 **Zero config** — No API keys to manage in your MCP config. Just log in to Codex CLI once.


## Quick Start

### 1. Install Codex CLI

```bash
npm install -g @openai/codex
codex login
```

### 2. Add to your MCP client

**Claude Code (recommended):**
```bash
claude mcp add easy-codex uvx -- --from git+https://github.com/dazebug/easy-codex-mcp easy-codex
```

**Claude Desktop** — add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "easy-codex": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/dazebug/easy-codex-mcp", "easy-codex"]
    }
  }
}
```

**Other MCP clients** — use the same config format with `uvx` as the command.

### 3. Use it

Your AI assistant now has two new tools:

| Tool | Description |
|------|-------------|
| `start_new_conversation` | Start a fresh conversation with Codex |
| `continue_conversation` | Resume a previous conversation using `thread_id` |

**Example prompts to your AI assistant:**
- *"Ask Codex to review this file for potential bugs"*
- *"Get Codex's opinion on the architecture of this module"*
- *"Have Codex explain how the authentication flow works"*

## Tools

### `start_new_conversation`

Start a new read-only conversation with Codex.

**Parameters:**
- `prompt` (required) — What to ask Codex.
- `working_directory` (optional) — Directory for Codex to work in.

**Returns:** `{ "thread_id": "...", "response": "..." }`

### `continue_conversation`

Resume a previous conversation with full context.

**Parameters:**
- `thread_id` (required) — Thread ID from a previous conversation.
- `prompt` (required) — Follow-up question.
- `working_directory` (optional) — Directory for Codex to work in.

**Returns:** `{ "thread_id": "...", "response": "..." }`

## How It Works

```
Your AI Assistant  ──MCP──▶  easy-codex-mcp  ──CLI──▶  Codex (read-only sandbox)
       │                          │                          │
       │   "Review this code"     │   codex e --json "..."   │
       │◀─────────────────────────│◀──────────────────────── │
       │   thread_id + response   │   JSONL output           │
```

1. Your assistant calls the MCP tool with a prompt
2. easy-codex-mcp spawns `codex` CLI in read-only sandbox mode
3. Codex analyzes your code and responds
4. The response + thread_id are returned to your assistant
5. Use thread_id to continue the conversation later

## Requirements

- Python 3.12+
- [OpenAI Codex CLI](https://github.com/openai/codex) (`npm install -g @openai/codex`)
- Codex CLI logged in (`codex login`)

## Development

```bash
git clone https://github.com/dazebug/easy-codex-mcp.git
cd easy-codex-mcp
uv sync

# Run tests
uv run pytest

# Dev mode
uv run mcp dev src/easy_codex/server.py
```

## License

MIT
