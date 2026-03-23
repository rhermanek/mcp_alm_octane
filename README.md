# ALM Octane MCP Server

An MCP (Model Context Protocol) server that exposes ALM Octane project management operations as structured tools consumable by any MCP-compatible AI agent (Claude, GitHub Copilot, etc.).

## Architecture

```
mcp_server/
├── server.py           # MCP server — 33 tools across all major entity types
├── octane_client.py    # Async HTTP client with session-based auth
└── requirements.txt    # Python dependencies
.env                    # Credentials (never commit this file)
```

## Setup

**Requires Python 3.10 or later.**

### 1. Install dependencies

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

### 2. Verify `.env` file

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

> **Security note:** When `OCTANE_VERIFY_SSL=false` (the default), TLS certificate
> verification is disabled. This is intentional for corporate on-prem deployments
> that use self-signed certificates. Set `OCTANE_VERIFY_SSL=true` whenever your
> instance has a valid CA-signed certificate.

### 3. Register in VS Code (`.vscode/mcp.json`)

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

### 4. Register in Claude Desktop (`claude_desktop_config.json`)

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

```
# Equality (simple fields)
name='Login bug'
status='passed'

# Cross-entity reference (use curly-brace syntax, NOT dot notation)
phase={name='New'}
severity={id='severity_high'}
owner={name='Jane Doe'}
sprint={name='Sprint 42'}
feature={name='Authentication'}
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

# OR with ||
phase={name='New'} || phase={name='In Progress'}
```

**NOT supported on this instance:** `~` (tilde contains), `&&`, `!=`, `>=`, `<=`, date comparisons.

---

## Authentication

Octane uses cookie-based session authentication:

1. The server calls `POST /authentication/sign_in` with `client_id` / `client_secret`.
2. The server stores the `LWSSO_COOKIE_KEY` session cookie.
3. On HTTP 401 responses, the server automatically re-authenticates and retries.

Credentials are never logged and are loaded exclusively from the `.env` file.
