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

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

_REQUIRED_ENV_VARS = [
    "OCTANE_BASE_URL",
    "OCTANE_SHARED_SPACE_ID",
    "OCTANE_WORKSPACE_ID",
    "OCTANE_CLIENT_ID",
    "OCTANE_CLIENT_SECRET",
]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
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
    client_id=os.environ["OCTANE_CLIENT_ID"],
    client_secret=os.environ["OCTANE_CLIENT_SECRET"],
    verify_ssl=os.environ.get("OCTANE_VERIFY_SSL", "").lower() in ("true", "1", "yes"),
)

mcp = FastMCP(
    name="ALM Octane",
    instructions=(
        "Tools for interacting with an ALM Octane project management instance. "
        "You can query, create, update and delete work items (defects, stories, "
        "epics, features, requirements), tests, runs, sprints and milestones. "
        "Most list tools accept an `query` parameter using Octane Query Language (OQL): "
        "e.g. `name='login'`, `severity={id='severity_high'}`, `phase={name='New'}`. "
        "Use `fields` to limit which fields are returned and reduce response size."
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
                   Examples:
                     name='login bug'
                     severity={id='severity_high'}
                     phase={name='New'};owner={name='John'}
                     name='*timeout*'
                   Leave empty to return all entities (up to `limit`).
        fields:    Comma-separated field names to include in response. Leave
                   empty for default fields. Example: 'id,name,phase,severity'
        order_by:  Field to sort by. Prefix with '-' for descending.
                   Example: '-creation_time' or 'name'
        limit:     Number of results per page (default 50, max 1000).
        offset:    Zero-based pagination offset.

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
    )
    return _fmt(result)


@mcp.tool()
async def octane_get(
    resource: str,
    entity_id: str,
    fields: str = "",
) -> str:
    """
    Retrieve a single Octane entity by ID.

    Args:
        resource:   Entity type (e.g. 'defects', 'stories', 'requirements').
        entity_id:  The numeric entity ID (as a string).
        fields:     Comma-separated fields to return. Leave empty for default.

    Returns:
        JSON object representing the entity, or null if not found.
    """
    result = await oc.get_entity(
        resource=resource,
        entity_id=entity_id,
        fields=[f.strip() for f in fields.split(",") if f.strip()] or None,
    )
    return _fmt(result)


@mcp.tool()
async def octane_create(
    resource: str,
    data: str,
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
    result = await oc.create_entity(resource=resource, data=payload)
    return _fmt(result)


@mcp.tool()
async def octane_update(
    resource: str,
    entity_id: str,
    data: str,
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
    result = await oc.update_entity(resource=resource, entity_id=entity_id, data=payload)
    return _fmt(result)


@mcp.tool()
async def octane_delete(
    resource: str,
    entity_id: str,
) -> str:
    """
    Delete an Octane entity by ID.

    Args:
        resource:   Entity type (e.g. 'defects', 'tasks', 'attachments').
        entity_id:  The numeric entity ID.

    Returns:
        Confirmation JSON {"status":"deleted"}.

    Note: Not all entity types support deletion (e.g. runs, scm_commits are read-only).
    """
    result = await oc.delete_entity(resource=resource, entity_id=entity_id)
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
    result = await oc.create_entity("defects", data)
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
    result = await oc.update_entity("defects", entity_id, data)
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
) -> str:
    """
    List user stories.

    Args:
        query:   OQL filter. Examples:
                   phase={name='In Progress'}
                   sprint={name='Sprint 42'}
                   parent={name='Authentication'}
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
) -> str:
    """
    Create a new user story.

    Args:
        name:          Story title (required).
        description:   Acceptance criteria / description (HTML allowed).
        story_points:  Effort estimate in story points (0 = unset).
        feature_id:    Parent feature ID (associates this story with a feature).
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
    result = await oc.create_entity("stories", data)
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
    )
    return _fmt(result)


@mcp.tool()
async def create_epic(
    name: str,
    description: str = "",
    parent_id: str = "",
    owner_id: str = "",
    release_id: str = "",
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
    result = await oc.create_entity("epics", data)
    return _fmt(result)


@mcp.tool()
async def list_features(
    query: str = "",
    fields: str = "id,name,phase,owner,parent,release,team,milestone,creation_time",
    limit: int = 50,
    offset: int = 0,
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
    result = await oc.create_entity("features", data)
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
    result = await oc.update_entity("features", entity_id, data)
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
    )
    return _fmt(result)


@mcp.tool()
async def create_requirement(
    name: str,
    description: str = "",
    parent_id: str = "",
    owner_id: str = "",
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
    result = await oc.create_entity("requirements", data)
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
    )
    return _fmt(result)


@mcp.tool()
async def list_gherkin_tests(
    query: str = "",
    fields: str = "id,name,phase,owner,script,creation_time",
    limit: int = 50,
    offset: int = 0,
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
    )
    return _fmt(result)


@mcp.tool()
async def create_gherkin_test(
    name: str,
    script: str,
    description: str = "",
    owner_id: str = "",
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
    result = await oc.create_entity("gherkin_tests", data)
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
    )
    return _fmt(result)


@mcp.tool()
async def list_manual_runs(
    query: str = "",
    fields: str = "id,name,status,test,last_modified,run_by",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-last_modified",
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
    )
    return _fmt(result)


@mcp.tool()
async def list_milestones(
    query: str = "",
    fields: str = "id,name,date,release,description,acceptance_criteria_udf",
    limit: int = 50,
    offset: int = 0,
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
    )
    return _fmt(result)


@mcp.tool()
async def create_milestone(
    name: str,
    date: str,
    release_id: str,
    acceptance_criteria: str,
    description: str = "",
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
    result = await oc.create_entity("milestones", data)
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
    )
    return _fmt(result)


@mcp.tool()
async def create_task(
    name: str,
    story_id: str,
    description: str = "",
    owner_id: str = "",
    estimated_hours: float = 0.0,
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
    result = await oc.create_entity("tasks", data)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Reference / lookup tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_phases(
    query: str = "",
    fields: str = "id,name,logical_name",
    limit: int = 200,
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
    )
    return _fmt(result)


@mcp.tool()
async def list_workspace_users(
    query: str = "",
    fields: str = "id,name,email,full_name",
    limit: int = 100,
    offset: int = 0,
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
    )
    return _fmt(result)


@mcp.tool()
async def list_ci_builds(
    query: str = "",
    fields: str = "id,name,status,ci_server,started_time,duration,branch",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-started_time",
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
    )
    return _fmt(result)


@mcp.tool()
async def list_scm_commits(
    query: str = "",
    fields: str = "id,revision,message,committer,time,branch",
    limit: int = 50,
    offset: int = 0,
    order_by: str = "-time",
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
    )
    return _fmt(result)


@mcp.tool()
async def create_release(
    name: str,
    start_date: str,
    end_date: str,
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
    result = await oc.create_entity("releases", data)
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
    )
    return _fmt(result)


@mcp.tool()
async def create_comment(
    work_item_id: str,
    text: str,
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
    result = await oc.create_entity("comments", data)
    return _fmt(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
