"""
ALM Octane MCP Server

Exposes ALM Octane API operations as MCP tools so AI agents can interact
with defects, user stories, requirements, tests, sprints, and more.

Startup:
    uv run server.py          (recommended)
    python server.py          (alternative)

Configuration is loaded from the .env file in the project root (one level up).
"""

import os
import sys
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import octane_client as oc

# ---------------------------------------------------------------------------
# Bootstrap: load .env and configure the HTTP client
# ---------------------------------------------------------------------------

# Load .env from the server directory (next to .env.example), falling back to
# the project root one level up. The first existing file wins (load_dotenv does
# not override already-set vars).
_here = Path(__file__).resolve().parent
load_dotenv(_here / ".env")
load_dotenv(_here.parent / ".env")

_REQUIRED_ENV_VARS = [
    "OCTANE_BASE_URL",
    "OCTANE_SHARED_SPACE_ID",
    "OCTANE_WORKSPACE_ID",
]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]

# Authenticate with either an API key (CLIENT_ID + CLIENT_SECRET) or
# username + password. Exactly one pair must be fully provided.
_has_api_key = bool(os.environ.get("OCTANE_CLIENT_ID") and os.environ.get("OCTANE_CLIENT_SECRET"))
_has_user_pass = bool(os.environ.get("OCTANE_USERNAME") and os.environ.get("OCTANE_PASSWORD"))
if not _has_api_key and not _has_user_pass:
    _missing.append("OCTANE_CLIENT_ID+OCTANE_CLIENT_SECRET or OCTANE_USERNAME+OCTANE_PASSWORD")

if _missing:
    print(
        f"ERROR: Missing required environment variables: {', '.join(_missing)}\n"
        "Create a .env file at the project root with these variables set.\n"
        "See README.md for details.",
        file=sys.stderr,
    )
    sys.exit(1)

oc.configure(
    base_url=os.environ["OCTANE_BASE_URL"],
    shared_space_id=os.environ["OCTANE_SHARED_SPACE_ID"],
    workspace_id=os.environ["OCTANE_WORKSPACE_ID"],
    client_id=os.environ.get("OCTANE_CLIENT_ID", ""),
    client_secret=os.environ.get("OCTANE_CLIENT_SECRET", ""),
    username=os.environ.get("OCTANE_USERNAME", ""),
    password=os.environ.get("OCTANE_PASSWORD", ""),
    verify_ssl=os.environ.get("OCTANE_VERIFY_SSL", "").lower() in ("true", "1", "yes"),
)

mcp = FastMCP(
    name="ALM Octane",
    instructions=(
        "Tools for interacting with an ALM Octane project management instance. "
        "You can query, create, update and delete work items (defects, stories, "
        "epics, features, requirements), tests, runs, sprints and milestones.\n"
        "\n"
        "WORK-ITEM HIERARCHY: epic > feature > story (user story) > task. Each level "
        "points UP to its parent via the `parent` field (a task points to its story via "
        "the `story` field). There is NO `feature` or `epic` field on a story — to get "
        "the stories under a feature, filter on parent: `parent={id=200441}`. Likewise "
        "features under an epic use `parent={id=<epic_id>}`. Call describe_entity_fields "
        "to see the exact fields and reference targets for any entity type.\n"
        "\n"
        "OQL (Octane Query Language) in the `query` parameter:\n"
        "  - Quote string values and logical-name IDs: `name='login'`, "
        "`severity={id='severity_high'}`, `phase={name='New'}`.\n"
        "  - Do NOT quote numeric entity IDs: `parent={id=200441}`, `owner={id=1002}`.\n"
        "  - Reference (relation) fields filter on a sub-condition in braces, by `id` or "
        "`name`: `owner={name='Jane'}`, `release={id=100003}`.\n"
        "  - Combine predicates with `;` (logical AND): "
        "`phase={name='New'};owner={id=1002}`. (`AND`/`&&` are accepted and normalized.)\n"
        "  - `*` is a wildcard in string matches: `name='*timeout*'`.\n"
        "\n"
        "Use `fields` to limit which fields are returned and reduce response size. "
        "The generic octane_* tools accept optional `shared_space_id` / `workspace_id` "
        "to target any workspace per call; discover IDs with list_shared_spaces and "
        "list_workspaces. One authenticated session spans all workspaces and spaces."
    ),
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fmt(result: Any) -> str:
    """Serialize the Octane response to a compact JSON string."""
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Generic CRUD tools — work on ANY Octane entity type
# ---------------------------------------------------------------------------

ENTITY_TYPES_HELP = (
    "Valid resource names include: defects, stories, epics, features, "
    "quality_stories, tasks, requirements, requirement_documents, "
    "gherkin_tests, manual_tests, tests, runs, manual_runs, "
    "sprints, team_sprints, milestones, phases, metaphases, "
    "work_items, attachments, user_tags, ci_builds, scm_commits, "
    "product_areas, application_modules, work_item_roots, "
    "test_suite_link_to_manual_tests, test_suite_link_to_gherkin_tests, "
    "test_suite_link_to_automated_tests, previous_runs, "
    "taxonomy_nodes, timelines, team_member_team_sprints, "
    "cloud_test_runners, test_runners, workspace_users."
)


@mcp.tool()
async def octane_list(
    resource: str,
    query: str = "",
    fields: str = "",
    order_by: str = "",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List / search any Octane entity collection with optional filtering.

    Args:
        resource:  Entity type to query. Valid resource names include:
                   defects, stories, epics, features, quality_stories, tasks,
                   requirements, requirement_documents, gherkin_tests,
                   manual_tests, tests, runs, manual_runs, sprints,
                   team_sprints, milestones, phases, metaphases, work_items,
                   attachments, user_tags, ci_builds, scm_commits,
                   product_areas, application_modules, work_item_roots,
                   test_suite_link_to_manual_tests,
                   test_suite_link_to_gherkin_tests,
                   test_suite_link_to_automated_tests, previous_runs,
                   taxonomy_nodes, timelines, team_member_team_sprints,
                   cloud_test_runners, test_runners, workspace_users.
        query:     OQL filter string (Octane Query Language).
                   Quote string values and logical-name IDs; leave numeric
                   entity IDs unquoted. Reference fields filter in braces by
                   id or name. Combine predicates with ';' (AND).
                   Examples:
                     name='login bug'
                     severity={id='severity_high'}     (logical-name id: quoted)
                     parent={id=200441}                (numeric id: unquoted)
                     phase={name='New'};owner={name='John'}
                     name='*timeout*'                  (* = wildcard)
                   Leave empty to return all entities (up to `limit`).
        fields:    Comma-separated field names to include in response. Leave
                   empty for default fields. Example: 'id,name,phase,severity'
        order_by:  Field to sort by. Prefix with '-' for descending.
                   Example: '-creation_time' or 'name'
        limit:     Number of results per page (default 50, max 1000).
        offset:    Zero-based pagination offset.
        shared_space_id: Target a different shared space (default: configured).
        workspace_id:    Target a different workspace (default: configured).
                         Discover IDs with list_shared_spaces / list_workspaces.

    Returns:
        JSON with keys 'total_count' and 'data' (list of entity objects).
    """
    result = await oc.list_entities(
        resource=resource,
        fields=[f.strip() for f in fields.split(",") if f.strip()] or None,
        query=query or None,
        order_by=order_by or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def octane_get(
    resource: str,
    entity_id: str,
    fields: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Retrieve a single Octane entity by ID.

    Args:
        resource:   Entity type (e.g. 'defects', 'stories', 'requirements').
        entity_id:  The numeric entity ID (as a string).
        fields:     Comma-separated fields to return. Leave empty for default.
        shared_space_id: Target a different shared space (default: configured).
        workspace_id:    Target a different workspace (default: configured).

    Returns:
        JSON object representing the entity, or null if not found.
    """
    result = await oc.get_entity(
        resource=resource,
        entity_id=entity_id,
        fields=[f.strip() for f in fields.split(",") if f.strip()] or None,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def octane_create(
    resource: str,
    data: str,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new entity in Octane.

    Args:
        resource:  Entity type to create (e.g. 'defects', 'stories').
        data:      JSON string representing the new entity's fields.
                   Common fields across most entities:
                     name         (string, usually required)
                     description  (string, HTML allowed)
                     phase        (reference: {"type":"phase","id":"phase_new"})
                     parent       (reference: {"type":"work_item_root","id":"..."})
                     owner        (reference: {"type":"workspace_user","id":"..."})
                   Defect-specific:
                     severity     (reference: {"type":"severity","id":"severity_high"})
                   Story/Feature-specific:
                     story_points (integer)
                     release      (reference: {"type":"release","id":"..."})

    Returns:
        JSON with 'data' array containing the created entity.

    Example data for a defect:
        {"name":"Login fails on timeout","severity":{"type":"severity","id":"severity_high"},
         "parent":{"type":"work_item_root","id":"1001"}}
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as e:
        return f"Error: data must be valid JSON — {e}"
    result = await oc.create_entity(
        resource=resource,
        data=payload,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def octane_update(
    resource: str,
    entity_id: str,
    data: str,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Update an existing Octane entity by ID.

    Args:
        resource:   Entity type (e.g. 'defects', 'stories').
        entity_id:  The numeric entity ID.
        data:       JSON string of fields to update (partial update is supported).
                    Only include the fields you want to change.
                    Example: {"phase":{"type":"phase","id":"phase_fixed"},"severity":{"type":"severity","id":"severity_critical"}}

    Returns:
        JSON of the updated entity.
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as e:
        return f"Error: data must be valid JSON — {e}"
    result = await oc.update_entity(
        resource=resource,
        entity_id=entity_id,
        data=payload,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def octane_delete(
    resource: str,
    entity_id: str,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Delete an Octane entity by ID.

    Args:
        resource:   Entity type (e.g. 'defects', 'tasks', 'attachments').
        entity_id:  The numeric entity ID.
        shared_space_id: Target a different shared space (default: configured).
        workspace_id:    Target a different workspace (default: configured).

    Returns:
        Confirmation JSON {"status":"deleted"}.

    Note: Not all entity types support deletion (e.g. runs, scm_commits are read-only).
    """
    result = await oc.delete_entity(
        resource=resource,
        entity_id=entity_id,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def describe_entity_fields(
    entity_name: str,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List the available fields on an Octane entity type — its schema.

    Use this BEFORE writing an OQL query or a create/update payload when you are
    unsure which field to filter on or set. It resolves questions like "does a
    story have a 'feature' field or a 'parent' field?" (answer: 'parent') without
    trial-and-error 400 errors.

    Args:
        entity_name:  Singular entity type name as Octane knows it internally,
                      e.g. 'story', 'defect', 'feature', 'epic', 'task',
                      'work_item', 'requirement', 'milestone', 'release', 'team'.
                      (Note: singular here, unlike the plural 'resource' names
                      used by octane_list, e.g. resource='stories'.)
        shared_space_id: Target a different shared space (default: configured).
        workspace_id:    Target a different workspace (default: configured).

    Returns:
        JSON metadata whose 'data' array lists each field: 'name' (use this in
        queries and payloads), 'label', 'field_type', editable/required flags,
        and for reference fields the allowed target entity types under
        'field_type_data'.
    """
    result = await oc.list_metadata_fields(
        entity_name=entity_name,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


# ---------------------------------------------------------------------------
# Defects
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_defects(
    query: str = "",
    fields: str = "id,name,phase,severity,owner,creation_time,last_modified",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-creation_time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List defects (bugs) with sensible default fields and sort order.

    Args:
        query:     OQL filter. Common patterns:
                     phase={name='New'}
                     severity={id='severity_high'}
                     owner={name='Jane Doe'}
                     name='*timeout*'         (contains)
        fields:    Fields to return. Available fields include:
                   id, name, description, phase, severity, owner, parent,
                   creation_time, last_modified, story_points, sprint,
                   release, subtype, detected_by, closed_on, steps_to_reproduce
        limit:     Results per page (default 50).
        offset:    Pagination offset.
        order_by:  Sort field (default: newest first).

    Returns:
        JSON with total_count and data array of defect objects.
    """
    result = await oc.list_entities(
        resource="defects",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_defect(
    name: str,
    description: str = "",
    severity_id: str = "severity_medium",
    parent_id: str = "",
    owner_id: str = "",
    sprint_id: str = "",
    release_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new defect (bug report) in Octane.

    Args:
        name:         Defect title/summary (required).
        description:  Detailed description (HTML allowed).
        severity_id:  Severity level ID. Common values:
                        severity_low, severity_medium, severity_high,
                        severity_critical, severity_urgent
                      (Use octane_list resource='list_nodes' query="list_root.logical_name='list_node.severity'" to browse)
        parent_id:    ID of the parent entity (release backlog, feature, etc.).
        owner_id:     Workspace user ID to assign the defect to.
        sprint_id:    Sprint ID to associate with.
        release_id:   Release ID to associate with.

    Returns:
        JSON of the created defect including its new ID.
    """
    data: dict[str, Any] = {"name": name}
    if description:
        data["description"] = description
    data["severity"] = {"type": "severity", "id": severity_id}
    if parent_id:
        data["parent"] = {"type": "work_item_root", "id": parent_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if sprint_id:
        data["sprint"] = {"type": "sprint", "id": sprint_id}
    if release_id:
        data["release"] = {"type": "release", "id": release_id}
    result = await oc.create_entity("defects", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


@mcp.tool()
async def update_defect(
    entity_id: str,
    name: str = "",
    description: str = "",
    severity_id: str = "",
    phase_id: str = "",
    owner_id: str = "",
    sprint_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Update an existing defect.

    Args:
        entity_id:    Defect ID (required).
        name:         New title (leave empty to keep current).
        description:  New description (leave empty to keep current).
        severity_id:  New severity ID (e.g. 'severity_critical').
        phase_id:     New phase/status ID (e.g. 'phase_fixed', 'phase_closed').
                      Use octane_list resource='phases' to find valid phase IDs.
        owner_id:     New owner workspace user ID.
        sprint_id:    New sprint ID.

    Returns:
        JSON of the updated defect.
    """
    data: dict[str, Any] = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if severity_id:
        data["severity"] = {"type": "severity", "id": severity_id}
    if phase_id:
        data["phase"] = {"type": "phase", "id": phase_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if sprint_id:
        data["sprint"] = {"type": "sprint", "id": sprint_id}
    if not data:
        return "Error: no fields specified to update"
    result = await oc.update_entity("defects", entity_id, data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# User Stories
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_stories(
    query: str = "",
    fields: str = "id,name,phase,story_points,owner,sprint,parent,creation_time,last_modified",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-creation_time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List user stories.

    Note: A story references its parent FEATURE via the 'parent' field, NOT a
    'feature' field (which does not exist and returns a 400). To list all
    stories under a feature, filter by parent id: parent={id=200441}.
    (create_story exposes this as the 'feature_id' argument for convenience,
    but the underlying field is 'parent'.)

    Args:
        query:   OQL filter. Examples:
                   parent={id=200441}          (all stories under a feature)
                   phase={name='In Progress'}
                   sprint={name='Sprint 42'}
                   story_points>5
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of story objects.
    """
    result = await oc.list_entities(
        resource="stories",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_story(
    name: str,
    description: str = "",
    story_points: int = 0,
    feature_id: str = "",
    owner_id: str = "",
    sprint_id: str = "",
    release_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new user story.

    Args:
        name:          Story title (required).
        description:   Acceptance criteria / description (HTML allowed).
        story_points:  Effort estimate in story points (0 = unset).
        feature_id:    Parent feature ID (sets the story's 'parent' field to
                       this feature; query it back with parent={id=<feature_id>}).
        owner_id:      Workspace user ID to assign as owner.
        sprint_id:     Sprint ID to add this story to.
        release_id:    Release ID.

    Returns:
        JSON of the created story including its new ID.
    """
    data: dict[str, Any] = {"name": name}
    if description:
        data["description"] = description
    if story_points > 0:
        data["story_points"] = story_points
    if feature_id:
        data["parent"] = {"type": "feature", "id": feature_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if sprint_id:
        data["sprint"] = {"type": "sprint", "id": sprint_id}
    if release_id:
        data["release"] = {"type": "release", "id": release_id}
    result = await oc.create_entity("stories", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Epics & Features
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_epics(
    query: str = "",
    fields: str = "id,name,phase,owner,creation_time",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List epics.

    Args:
        query:  OQL filter (e.g. phase={name='In Progress'}).
        fields: Fields to return.
        limit:  Results per page.
        offset: Pagination offset.

    Returns:
        JSON with total_count and data array of epic objects.
    """
    result = await oc.list_entities(
        resource="epics",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by="-creation_time",
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_epic(
    name: str,
    description: str = "",
    parent_id: str = "",
    owner_id: str = "",
    release_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new epic.

    Args:
        name:        Epic title (required).
        description: Description (HTML allowed).
        parent_id:   Parent entity ID (typically work_item_root or another epic).
        owner_id:    Owner workspace user ID.
        release_id:  Release ID.

    Returns:
        JSON of the created epic.
    """
    data: dict[str, Any] = {"name": name}
    if description:
        data["description"] = description
    if parent_id:
        data["parent"] = {"type": "work_item_root", "id": parent_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if release_id:
        data["release"] = {"type": "release", "id": release_id}
    result = await oc.create_entity("epics", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


@mcp.tool()
async def list_features(
    query: str = "",
    fields: str = "id,name,phase,owner,parent,release,team,milestone,creation_time",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List features.

    Note: Features use 'parent' (not 'epic') to reference their parent epic.

    Args:
        query:  OQL filter (e.g. parent={name='My Epic'}).
        fields: Fields to return. Use 'parent' to see the parent epic.
        limit:  Results per page.
        offset: Pagination offset.

    Returns:
        JSON with total_count and data array of feature objects.
    """
    result = await oc.list_entities(
        resource="features",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by="-creation_time",
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_feature(
    name: str,
    description: str = "",
    acceptance_criteria: str = "",
    epic_id: str = "",
    owner_id: str = "",
    release_id: str = "",
    team_id: str = "",
    milestone_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new feature.

    IMPORTANT: When assigning a release, the 'team' and 'milestone' fields
    become required. Use list_teams and list_milestones to find valid IDs.

    Args:
        name:                Feature title (required).
        description:         Description (HTML allowed).
        acceptance_criteria:  Plain-text acceptance criteria (stored in
                             acceptance_criteria_udf custom field).
        epic_id:             Parent epic ID (use list_epics to find valid IDs).
        owner_id:            Owner workspace user ID.
        release_id:          Release ID. When set, team_id and milestone_id
                             are also required.
        team_id:             Team ID (required when release is set).
                             Use list_teams to find valid IDs.
        milestone_id:        Milestone ID (required when release is set).
                             Use list_milestones to find valid IDs.

    Returns:
        JSON of the created feature.
    """
    data: dict[str, Any] = {"name": name}
    if description:
        data["description"] = description
    if acceptance_criteria:
        data["acceptance_criteria_udf"] = acceptance_criteria
    if epic_id:
        data["parent"] = {"type": "epic", "id": epic_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if release_id:
        data["release"] = {"type": "release", "id": release_id}
    if team_id:
        data["team"] = {"type": "team", "id": team_id}
    if milestone_id:
        data["milestone"] = {"type": "milestone", "id": milestone_id}
    result = await oc.create_entity("features", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


@mcp.tool()
async def update_feature(
    entity_id: str,
    name: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    phase_id: str = "",
    owner_id: str = "",
    release_id: str = "",
    team_id: str = "",
    milestone_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Update an existing feature.

    IMPORTANT: When assigning a release for the first time, 'team' and
    'milestone' are also required. Use list_teams and list_milestones to
    find valid IDs.

    Args:
        entity_id:           Feature ID (required).
        name:                New title (leave empty to keep current).
        description:         New description (leave empty to keep current).
        acceptance_criteria:  New acceptance criteria (plain text, stored in
                             acceptance_criteria_udf custom field).
        phase_id:            New phase ID (e.g. 'phase.feature.done',
                             'phase.feature.inprogress', 'phase.feature.new').
                             Use list_phases to find valid phase IDs.
        owner_id:            New owner workspace user ID.
        release_id:          Release ID. When setting for the first time,
                             also provide team_id and milestone_id.
        team_id:             Team ID.
        milestone_id:        Milestone ID.

    Returns:
        JSON of the updated feature.
    """
    data: dict[str, Any] = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if acceptance_criteria:
        data["acceptance_criteria_udf"] = acceptance_criteria
    if phase_id:
        data["phase"] = {"type": "phase", "id": phase_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if release_id:
        data["release"] = {"type": "release", "id": release_id}
    if team_id:
        data["team"] = {"type": "team", "id": team_id}
    if milestone_id:
        data["milestone"] = {"type": "milestone", "id": milestone_id}
    if not data:
        return "Error: no fields specified to update"
    result = await oc.update_entity("features", entity_id, data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_requirements(
    query: str = "",
    fields: str = "id,name,phase,owner,creation_time,last_modified",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-creation_time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List requirements.

    Args:
        query:   OQL filter. Examples:
                   phase={name='Draft'}
                   owner={name='Jane'}
                   parent={name='Security Requirements'}
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of requirement objects.
    """
    result = await oc.list_entities(
        resource="requirements",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_requirement(
    name: str,
    description: str = "",
    parent_id: str = "",
    owner_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new requirement.

    Args:
        name:         Requirement title (required).
        description:  Requirement description/body (HTML allowed).
        parent_id:    Parent requirement folder or document ID.
        owner_id:     Owner workspace user ID.

    Returns:
        JSON of the created requirement.
    """
    data: dict[str, Any] = {"name": name}
    if description:
        data["description"] = description
    if parent_id:
        data["parent"] = {"type": "requirement_document", "id": parent_id}
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    result = await oc.create_entity("requirements", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_tests(
    query: str = "",
    fields: str = "id,name,subtype,phase,owner,creation_time",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-creation_time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List test items (manual, gherkin/BDD, automated).

    Args:
        query:   OQL filter. Examples:
                   subtype='test_manual'
                   subtype='test_gherkin'
                   phase={name='Ready'}
                   owner={name='Tester'}
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of test objects.
    """
    result = await oc.list_entities(
        resource="tests",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def list_gherkin_tests(
    query: str = "",
    fields: str = "id,name,phase,owner,script,creation_time",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List Gherkin (BDD) tests including their feature-file scripts.

    Args:
        query:   OQL filter (e.g. name='*login*', phase={name='Ready'}).
        fields:  Fields to return. Include 'script' to get the Gherkin text.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of gherkin test objects.
    """
    result = await oc.list_entities(
        resource="gherkin_tests",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_gherkin_test(
    name: str,
    script: str,
    description: str = "",
    owner_id: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new Gherkin (BDD) test with a feature-file script.

    Args:
        name:        Test name (required).
        script:      Gherkin feature file content (Feature/Scenario/Given/When/Then).
        description: Additional description.
        owner_id:    Owner workspace user ID.

    Returns:
        JSON of the created gherkin test.

    Example script:
        Feature: User Login
          Scenario: Successful login
            Given the user is on the login page
            When they enter valid credentials
            Then they should be redirected to the dashboard
    """
    data: dict[str, Any] = {"name": name, "script": script}
    if description:
        data["description"] = description
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    result = await oc.create_entity("gherkin_tests", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Test Runs
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_test_runs(
    query: str = "",
    fields: str = "id,name,status,test,started,duration,run_by",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-started",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List automated test run results.

    Args:
        query:   OQL filter. Examples:
                   status='passed'
                   status='failed'
                   test={name='LoginTest'}
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.
        order_by: Sort field (default: most recent first).

    Returns:
        JSON with total_count and data array of test run objects.
    """
    result = await oc.list_entities(
        resource="runs",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def list_manual_runs(
    query: str = "",
    fields: str = "id,name,status,test,last_modified,run_by",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-last_modified",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List manual test execution runs.

    Args:
        query:   OQL filter (e.g. status='failed', test={name='Checkout'}).
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of manual run objects.
    """
    result = await oc.list_entities(
        resource="manual_runs",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


# ---------------------------------------------------------------------------
# Planning: Sprints & Milestones
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_sprints(
    query: str = "",
    fields: str = "id,name,start_date,end_date,release",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List sprints in the workspace.

    Args:
        query:   OQL filter (e.g. release={name='Q2 2026'}).
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of sprint objects.
    """
    result = await oc.list_entities(
        resource="sprints",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def list_milestones(
    query: str = "",
    fields: str = "id,name,date,release,description,acceptance_criteria_udf",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List milestones.

    Args:
        query:   OQL filter (e.g. release={name='Q1 2026 DevSecOps'}).
        fields:  Fields to return. Include 'acceptance_criteria_udf'
                 to see acceptance criteria.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of milestone objects.
    """
    result = await oc.list_entities(
        resource="milestones",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_milestone(
    name: str,
    date: str,
    release_id: str,
    acceptance_criteria: str,
    description: str = "",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new milestone.

    Args:
        name:                Milestone name (required).
        date:                Target date in ISO 8601 format, e.g.
                             '2026-06-30T12:00:00Z' (required).
        release_id:          Release ID to associate with (required).
                             Use list_releases to find valid IDs.
        acceptance_criteria:  Plain-text acceptance criteria (required).
                             This is a required custom field
                             (acceptance_criteria_udf).
        description:         Description (HTML allowed).

    Returns:
        JSON of the created milestone.
    """
    data: dict[str, Any] = {
        "name": name,
        "date": date,
        "release": {"type": "release", "id": release_id},
        "acceptance_criteria_udf": acceptance_criteria,
    }
    if description:
        data["description"] = description
    result = await oc.create_entity("milestones", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_tasks(
    query: str = "",
    fields: str = "id,name,phase,owner,story,creation_time",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List tasks associated with work items.

    Args:
        query:   OQL filter (e.g. story={id='1234'}, owner={name='Jane'}, phase={name='New'}).
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of task objects.
    """
    result = await oc.list_entities(
        resource="tasks",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_task(
    name: str,
    story_id: str,
    description: str = "",
    owner_id: str = "",
    estimated_hours: float = 0.0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a task associated with a user story.

    Args:
        name:             Task title (required).
        story_id:         Parent story ID (required).
        description:      Task description.
        owner_id:         Owner workspace user ID.
        estimated_hours:  Estimated effort in hours (0 = unset).

    Returns:
        JSON of the created task.
    """
    data: dict[str, Any] = {
        "name": name,
        "story": {"type": "story", "id": story_id},
    }
    if description:
        data["description"] = description
    if owner_id:
        data["owner"] = {"type": "workspace_user", "id": owner_id}
    if estimated_hours > 0:
        data["estimated_hours"] = estimated_hours
    result = await oc.create_entity("tasks", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Reference / lookup tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_phases(
    query: str = "",
    fields: str = "id,name,logical_name",
    limit: int = 200,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List workflow phases available in the workspace.

    Use this to discover valid phase IDs when creating or updating entities.
    Phase IDs look like 'phase_new', 'phase_in_progress', 'phase_fixed', etc.

    Args:
        query:  OQL filter (left empty returns all phases).
        fields: Fields to return.
        limit:  Results per page (default 200 to get all phases in one call).

    Returns:
        JSON with total_count and data array of phase objects.
    """
    result = await oc.list_entities(
        resource="phases",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def list_workspace_users(
    query: str = "",
    fields: str = "id,name,email,full_name",
    limit: int = 100,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List users with access to this Octane workspace.

    Use this to look up user IDs when assigning ownership of work items.

    Args:
        query:  OQL filter (e.g. name='*john*', email='*@example.com*').
        fields: Fields to return.
        limit:  Results per page.
        offset: Pagination offset.

    Returns:
        JSON with total_count and data array of workspace user objects.
    """
    result = await oc.list_entities(
        resource="workspace_users",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def list_ci_builds(
    query: str = "",
    fields: str = "id,name,status,ci_server,started_time,duration,branch",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-started_time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List CI build records tracked in Octane.

    Args:
        query:    OQL filter (e.g. status='failed', branch='*main*').
        fields:   Fields to return.
        limit:    Results per page.
        offset:   Pagination offset.
        order_by: Sort field (default: most recent first).

    Returns:
        JSON with total_count and data array of CI build objects.
    """
    result = await oc.list_entities(
        resource="ci_builds",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def list_scm_commits(
    query: str = "",
    fields: str = "id,revision,message,committer,time,branch",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List SCM (source control) commits tracked in Octane.

    Args:
        query:    OQL filter (e.g. committer={name='Jane'}, branch='*release*').
        fields:   Fields to return.
        limit:    Results per page.
        offset:   Pagination offset.
        order_by: Sort field (default: most recent first).

    Returns:
        JSON with total_count and data array of SCM commit objects.
    """
    result = await oc.list_entities(
        resource="scm_commits",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_releases(
    query: str = "",
    fields: str = "id,name,start_date,end_date",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List releases in the workspace.

    Args:
        query:   OQL filter (e.g. name='*2026*').
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of release objects.
    """
    result = await oc.list_entities(
        resource="releases",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_release(
    name: str,
    start_date: str,
    end_date: str,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Create a new release.

    Args:
        name:        Release name (required), e.g. 'Q2 2026 DevSecOps'.
        start_date:  Start date in ISO 8601 format, e.g. '2026-04-01T12:00:00Z'.
        end_date:    End date in ISO 8601 format, e.g. '2026-06-30T12:00:00Z'.

    Returns:
        JSON of the created release including its new ID.
    """
    data: dict[str, Any] = {
        "name": name,
        "start_date": start_date,
        "end_date": end_date,
    }
    result = await oc.create_entity("releases", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_teams(
    query: str = "",
    fields: str = "id,name",
    limit: int = 50,
    offset: int = 0,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List teams in the workspace.

    Args:
        query:   OQL filter (e.g. name='*DevSecOps*').
        fields:  Fields to return.
        limit:   Results per page.
        offset:  Pagination offset.

    Returns:
        JSON with total_count and data array of team objects.
    """
    result = await oc.list_entities(
        resource="teams",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_comments(
    query: str = "",
    fields: str = "id,text,author,creation_time,owner_work_item",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-creation_time",
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    List comments on work items.

    Args:
        query:    OQL filter. Examples:
                    owner_work_item={id='1234'}
                    author={name='Jane'}
        fields:   Fields to return.
        limit:    Results per page.
        offset:   Pagination offset.
        order_by: Sort field (default: newest first).

    Returns:
        JSON with total_count and data array of comment objects.
    """
    result = await oc.list_entities(
        resource="comments",
        fields=[f.strip() for f in fields.split(",") if f.strip()],
        query=query or None,
        order_by=order_by,
        limit=limit,
        offset=offset,
        shared_space_id=shared_space_id or None,
        workspace_id=workspace_id or None,
    )
    return _fmt(result)


@mcp.tool()
async def create_comment(
    work_item_id: str,
    text: str,
    shared_space_id: str = "",
    workspace_id: str = "",
) -> str:
    """
    Add a comment to a work item.

    Args:
        work_item_id:  ID of the work item (story, defect, task, etc.).
        text:          Comment text (HTML allowed).

    Returns:
        JSON of the created comment.
    """
    data = {
        "text": text,
        "owner_work_item": {"type": "work_item", "id": work_item_id},
    }
    result = await oc.create_entity("comments", data, shared_space_id=shared_space_id or None, workspace_id=workspace_id or None)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Workspace / shared-space discovery
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_workspaces(
    shared_space_id: str = "",
    query: str = "",
    fields: str = "id,name,description",
    order_by: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """
    List the workspaces in a shared space.

    Use this to discover workspace_id values to pass to the octane_* tools when
    working across multiple workspaces. A single authenticated session spans
    every workspace and shared space the account can access, so no
    re-authentication is needed when switching scope.

    Args:
        shared_space_id: Shared space to list from (default: configured).
        query:           OQL filter, e.g. name='*Team*'.
        fields:          Comma-separated fields to return.
        order_by:        Sort field; prefix with '-' for descending.
        limit:           Results per page.
        offset:          Pagination offset.

    Returns:
        JSON with total_count and data array of workspace objects.
    """
    result = await oc.list_workspaces(
        shared_space_id=shared_space_id or None,
        query=query or None,
        fields=[f.strip() for f in fields.split(",") if f.strip()] or None,
        order_by=order_by or None,
        limit=limit,
        offset=offset,
    )
    return _fmt(result)


@mcp.tool()
async def list_shared_spaces(
    query: str = "",
    fields: str = "id,name",
    order_by: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """
    List the shared spaces (sites) on the Octane server.

    Use this to discover shared_space_id values. Results are limited to spaces
    the account can access; enumerating every space requires site-admin rights.

    Args:
        query:    OQL filter, e.g. name='Production*'.
        fields:   Comma-separated fields to return.
        order_by: Sort field; prefix with '-' for descending.
        limit:    Results per page.
        offset:   Pagination offset.

    Returns:
        JSON with total_count and data array of shared-space objects.
    """
    result = await oc.list_shared_spaces(
        query=query or None,
        fields=[f.strip() for f in fields.split(",") if f.strip()] or None,
        order_by=order_by or None,
        limit=limit,
        offset=offset,
    )
    return _fmt(result)


# ---------------------------------------------------------------------------
# Cross-cutting doc: surface the OQL query normalization on every query tool
# ---------------------------------------------------------------------------

# The client silently normalizes a few non-Octane query habits (see
# octane_client._normalize_query): SQL-style `AND` / `&&` conjunctions become
# Octane's `;`, and stray/duplicate `;` are collapsed. Append that note to the
# description of every tool exposing a `query` parameter, so it shows up
# per-tool in the schema instead of only in the server-level instructions.
# ponytail: reaches into FastMCP's tool registry (_tool_manager). If a future
# FastMCP renames it, drop this loop and inline the note into each docstring.
_QUERY_NORMALIZATION_NOTE = (
    "\n\nOQL note: conjunctions written as SQL-style `AND` or `&&` are "
    "automatically normalized to Octane's `;` separator, and duplicate/trailing "
    "`;` are collapsed — so `phase={name='New'} AND owner={id=1002}` is accepted."
)

for _tool in mcp._tool_manager.list_tools():
    if "query" in (_tool.parameters or {}).get("properties", {}):
        _tool.description = (_tool.description or "") + _QUERY_NORMALIZATION_NOTE


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
