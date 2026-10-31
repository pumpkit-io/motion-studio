# The host agent makes every editorial choice; motion-studio never calls a model for judgement

motion-studio is a deterministic CLI plus skills and an `AGENTS.md`. The coding agent the creator already uses reads the packed index and contact sheets, and writes the EDL. motion-studio never calls an LLM itself and exposes no MCP server. This keeps motion-studio offline, free of API keys and agent-agnostic: any agent that can run shell commands and read files can drive it. The cost is that edit quality depends on the host agent and on the skills that teach it.

## Considered Options

- An MCP server wrapping the CLI. Rejected for v0.1.0: the CLI with `--json` already works in every agent, and an MCP server adds a second interface to keep stable. It stays on the roadmap as an optional wrapper.
- Calling an LLM API from motion-studio for hook and cut selection. Rejected: it adds a paid dependency and duplicates the judgement of the agent that is already in the loop.
