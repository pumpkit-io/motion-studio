# Launches the stand-in Claude Code with its MCP config by path, then talks to it.
Set FontSize 28
Set TypingSpeed 40ms
Launch ./claude --mcp-config secret-mcp.json
Mark ready
Sleep 1s
Type "hello there"
Enter
Sleep 1s
Mark answered
Sleep 1s
