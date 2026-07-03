# ALM Octane MCP Server

An MCP (Model Context Protocol) server that exposes ALM Octane project management operations as structured tools consumable by any MCP-compatible AI agent (Claude, GitHub Copilot, etc.).

## Architecture

```
mcp_server/
├── server.py           # MCP server — 39 tools across all major entity types
├── octane_client.py    # Async HTTP client with session-based auth
├── requirements.txt    # Python dependencies
└── setup.py            # Package + console entrypoint (octane-mcp)
.env                    # Credentials (never commit this file)
```

## Setup

**Requires Python 3.10 or later.**

### 1. Install dependencies (local development)

```bash
cd mcp_server
uv venv .venv
uv pip install -r requirements.txt
```

Or with plain pip:
```bash
cd mcp_server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install globally on macOS (all VS Code workspaces)

Use `pipx` to install a user-global command:

```bash
cd mcp_server
pipx install .
```

Upgrade/reinstall after pulling changes:

```bash
cd mcp_server
pipx install . --force
```

Verify install:

```bash
command -v octane-mcp
pipx list --short
```

### 3. Verify `.env` file

The `.env` at the project root must contain:

```env
OCTANE_BASE_URL=https://your-octane-instance:8443
OCTANE_SHARED_SPACE_ID=4001
OCTANE_WORKSPACE_ID=21001
OCTANE_CLIENT_ID=your_client_id
OCTANE_CLIENT_SECRET=your_client_secret

# Optional: set to true if your Octane instance has a valid CA-signed certificate.
# Defaults to false to support on-prem instances with self-signed certificates.
OCTANE_VERIFY_SSL=false
```

If a secret starts with `=` or contains shell-sensitive characters, quote it:

```env
OCTANE_CLIENT_SECRET='=your_secret_value'
```

> **Security note:** When `OCTANE_VERIFY_SSL=false` (the default), TLS certificate
> verification is disabled. This is intentional for corporate on-prem deployments
> that use self-signed certificates. Set `OCTANE_VERIFY_SSL=true` whenever your
> instance has a valid CA-signed certificate.

### 4. Register in VS Code (`.vscode/mcp.json`) - workspace-local

```json
{
  "servers": {
    "octane": {
      "type": "stdio",
      "command": "/absolute/path/to/mcp_server/.venv/bin/python",
      "args": ["/absolute/path/to/mcp_server/server.py"]
    }
  }
}
```

Or using `uv run`:
```json
{
  "servers": {
    "octane": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/mcp_server", "python", "server.py"]
    }
  }
}
```

### 5. Register in VS Code user config (global for all workspaces)

Create or update:

`~/Library/Application Support/Code/User/mcp.json`

```json
{
  "servers": {
    "octane": {
      "type": "stdio",
      "command": "/bin/zsh",
      "args": [
        "-lc",
        "set -a; source /absolute/path/to/.env; set +a; exec octane-mcp"
      ]
    }
  }
}
```

Notes:
- Use an absolute `.env` path.
- `octane-mcp` comes from the global `pipx` install.
- Reload VS Code after editing user `mcp.json`.

### 6. Register in Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "octane": {
      "command": "/absolute/path/to/mcp_server/.venv/bin/python",
      "args": ["/absolute/path/to/mcp_server/server.py"]
    }
  }
}
```

Global `pipx` command example:

```json
{
  "mcpServers": {
    "octane": {
      "command": "octane-mcp"
    }
  }
}
```

---

## Available Tools

### Generic CRUD (work on any entity type)

| Tool | Description |
|---|---|
| `octane_list` | Query any entity collection with OQL filtering, field selection, pagination |
| `octane_get` | Get a single entity by ID |
| `octane_create` | Create any entity type |
| `octane_update` | Update any entity by ID |
| `octane_delete` | Delete any entity by ID |
| `describe_entity_fields` | List an entity type's fields (schema) — field names, types, and reference targets. Use it to find the right field before building a query or payload |

Every `octane_*` tool accepts optional `shared_space_id` / `workspace_id` to target a
workspace other than the configured default for that single call. One authenticated
session spans all workspaces and shared spaces the account can access, so switching
scope needs no re-authentication.

### Discovery

| Tool | Description |
|---|---|
| `list_workspaces` | List workspaces in a shared space, to discover `workspace_id` values |
| `list_shared_spaces` | List shared spaces on the server, to discover `shared_space_id` values |

### Work Items

| Tool | Description |
|---|---|
| `list_defects` | List bugs/defects with common filters |
| `create_defect` | Create a new defect with severity, owner, sprint |
| `update_defect` | Update defect phase, severity, owner |
| `list_stories` | List user stories |
| `create_story` | Create a user story with story points and feature link |
| `list_epics` | List epics |
| `create_epic` | Create a new epic |
| `list_features` | List features |
| `create_feature` | Create a feature linked to an epic |

### Requirements

| Tool | Description |
|---|---|
| `list_requirements` | List requirements with filters |
| `create_requirement` | Create a new requirement |

### Testing

| Tool | Description |
|---|---|
| `list_tests` | List all test types (manual, gherkin, automated) |
| `list_gherkin_tests` | List Gherkin/BDD tests with script content |
| `create_gherkin_test` | Create a Gherkin test with feature-file script |
| `list_test_runs` | List automated test run results |
| `list_manual_runs` | List manual test execution runs |

### Planning

| Tool | Description |
|---|---|
| `list_releases` | List releases (filter by name) |
| `list_teams` | List teams in the workspace |
| `list_sprints` | List sprints (filter by release) |
| `list_milestones` | List milestones |
| `list_tasks` | List tasks linked to work items |
| `create_task` | Create a task associated with a story |

### Comments

| Tool | Description |
|---|---|
| `list_comments` | List comments on work items |
| `create_comment` | Add a comment to any work item |

### Reference / Lookup

| Tool | Description |
|---|---|
| `list_phases` | Discover valid phase IDs for workflow transitions |
| `list_workspace_users` | Look up user IDs for ownership assignment |
| `list_ci_builds` | List CI build records |
| `list_scm_commits` | List SCM/git commits |

---

## Octane Query Language (OQL) Quick Reference

All list tools accept an optional `query` parameter using OQL syntax.

> **Important:** All OQL values must be wrapped in outer double-quotes,
> which the server adds automatically. The examples below show the
> string you pass as the `query` parameter.

> **Quoting inside the query:** quote string values and logical-name IDs
> (`severity={id='severity_high'}`), but leave numeric entity IDs unquoted
> (`parent={id=200441}`).

### Work-item hierarchy

`epic > feature > story > task`. Each level points **up** to its parent through
the `parent` field (a task points to its story through the `story` field). There
is no `feature` or `epic` field on a story. To list the children of a work item,
filter on `parent`:

```
parent={id=200441}     # all stories under feature 200441 (or features under an epic)
story={id=200652}      # all tasks under story 200652
```

Not sure which field an entity exposes? Call `describe_entity_fields` (e.g.
`entity_name='story'`) to see its schema — field names, types, and reference targets.

```
# Equality (simple fields)
name='Login bug'
status='passed'

# Cross-entity reference (use curly-brace syntax, NOT dot notation)
phase={name='New'}
severity={id='severity_high'}
owner={name='Jane Doe'}
sprint={name='Sprint 42'}
parent={name='Authentication'}
release={name='Q1 2026 DevSecOps'}

# Glob / substring match (use * wildcards, NOT ~ operator)
name='*login*'          # contains
name='DSO*'             # starts with

# Numeric comparison
id>100000
story_points>5

# Null check
story_points=null

# Combine with semicolon (AND)
phase={name='In Progress'};owner={name='Jane Doe'}

# The MCP server also accepts SQL-style AND/&& and normalizes it to ';'
phase={name='In Progress'} and owner={name='Jane Doe'}
phase={name='In Progress'} && owner={name='Jane Doe'}

# OR with ||
phase={name='New'} || phase={name='In Progress'}
```

**NOT supported on this instance:** `~` (tilde contains), `!=`, `>=`, `<=`, date comparisons.

Note: Some Octane versions may throw internal errors for `owner=null` combined with
certain phase filters. The MCP server includes a fallback that evaluates
`owner=null` client-side so list calls remain usable.

---

## Authentication

Octane uses cookie-based session authentication:

1. The server calls `POST /authentication/sign_in` with `client_id` / `client_secret`.
2. The server stores the `LWSSO_COOKIE_KEY` session cookie.
3. On HTTP 401 responses, the server automatically re-authenticates and retries.

Credentials are never logged and are loaded exclusively from the `.env` file.
