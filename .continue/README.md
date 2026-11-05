# Coder for Continue

This workspace provides a local Continue agent in
[agents/coder.yaml](agents/coder.yaml). It uses the existing Ollama
`codestral:latest` model; no API key or additional model download is required.
It does not modify the global Continue configuration.

## Use

1. Open this repository as a folder in VS Code with Continue enabled.
2. Select **Coder** in Continue's agent/config selector. If it is not listed,
   run **Developer: Reload Window**.
3. Select **Agent** mode, not Chat (no tools) or Plan (read-only tools).
4. Check Continue's tool permissions: allow file reads/search, file creation and
   editing, and terminal commands as needed. Keep approval enabled for edits
   and commands; the YAML does not override permissions.
5. Submit the task and approve the required tool calls.

For example, ask Coder to create a temporary JSON array in the workspace,
append one object, and parse the saved file to verify that the original entries
are preserved. Inspect the tool results and saved file before using it on real
profile data.

## Capabilities and limitations

The agent instructions cover code inspection, file edits, JSON updates, targeted
tests, PowerShell, and preservation of unrelated changes. These are instructions,
not new tools: execution requires Agent mode and the corresponding built-in
Continue tools to be enabled.

The installed Codestral model does not advertise native tool calling. Continue
supports system-message tools for such models, so the configuration deliberately
does not assert `capabilities: [tool_use]`. Model reliability may still vary;
instructions cannot guarantee successful tool use. If tools are unavailable or
calls are unreliable, check the selected mode and permissions, then consider a
tool-capable model rather than falsely advertising native support.

References:

- [Continue Agent mode](https://docs.continue.dev/ide-extensions/agent/quick-start)
- [Agent model setup and system-message tools](https://docs.continue.dev/ide-extensions/agent/model-setup)
- [Configuration reference](https://docs.continue.dev/reference)
