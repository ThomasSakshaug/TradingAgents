# Coder for Continue

This workspace provides a local Continue agent in
[agents/coder.yaml](agents/coder.yaml). It uses the existing Ollama
`codestral:latest` model; no API key or additional model download is required.
It does not modify the global Continue configuration.

## Use

1. Open this repository as a folder in VS Code with Continue enabled.
2. Click **Main Config** above the chat input to open the config/profile
   selector. This is separate from the Chat/Plan/Agent mode menu and the
   model selector (for example, **Codestral Latest**).
3. Select **coder.yaml**. Continue 2.0.0 initially lists workspace profiles
   by filename; after loading, this profile is displayed as **Coder**.
   If neither name is listed, run **Developer: Reload Window** and open the
   **Main Config** selector again. The repository root containing `.continue`
   must be an opened workspace folder, not merely a nested folder.
4. Select **Agent** mode, not Chat (no tools) or Plan (read-only tools).
5. Check Continue's tool permissions: allow file reads/search, file creation and
   editing, and terminal commands as needed. Keep approval enabled for edits
   and commands; the YAML does not override permissions.
6. Start a new conversation, submit the task, and approve the required tool calls.

### Enable editing tools in Continue 2.0.0

Open Continue's configuration page (not VS Code's general settings), then
select **Tools** in its navigation. Expand **Built-in Tools** and ensure the
group is enabled. For Codestral, set **Edit File** (`edit_existing_file`) and
**Find and Replace** (`single_find_and_replace`) to **Ask First**, not
**Excluded**. Keep **Agent** mode selected; Chat and Plan disable write tools.

These policies are saved in Continue's UI state, not in this agent YAML.
Changing model roles or agent instructions does not override an excluded tool.
After changing permissions, start a new conversation so previous claims about
unavailable tools are not carried forward. If an enabled tool is still reported
as missing, inspect the actual tool call/error rather than trusting the model's
prose. Do not use **Create New File** to overwrite an existing file.

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
