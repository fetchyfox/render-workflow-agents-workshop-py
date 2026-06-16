"""Tests for the Blueprint namespacing script."""

import os
import re
import tempfile
from pathlib import Path

import pytest

from scripts.setup_attendee import (
    namespace_blueprint,
    namespace_name,
    normalize_namespace,
    parse_args,
    setup_attendee,
)

NAIVE_FIXTURE = """\
projects:
  - name: agents-workshop-naive
    environments:
      - name: production
        databases:
          - name: naive-agent-db
        services:
          - type: web
            name: naive-agent
            envVars:
              - key: DATABASE_URL
                fromDatabase:
                  name: naive-agent-db
                  property: connectionString
"""

QUEUE_FIXTURE = """\
projects:
  - name: agents-workshop-queue
    environments:
      - name: production
        databases:
          - name: queue-agents-db
        services:
          - type: keyvalue
            name: queue-agents-valkey
          - type: web
            name: queue-agents-web
            envVars:
              - key: VALKEY_URL
                fromService:
                  name: queue-agents-valkey
                  type: keyvalue
                  property: connectionString
          - type: worker
            name: queue-agents-worker
"""

WORKFLOW_FIXTURE = """\
projects:
  - name: agents-workshop-workflows
    environments:
      - name: production
        databases:
          - name: workflow-agents-db
        services:
          - type: web
            name: workflow-agents
            envVars:
              - key: DATABASE_URL
                fromDatabase:
                  name: workflow-agents-db
                  property: connectionString
"""

FIXTURES = {
    "packages/naive_agent/render.yaml": NAIVE_FIXTURE,
    "packages/queue_agents/render.yaml": QUEUE_FIXTURE,
    "packages/workflow_agents/render.yaml": WORKFLOW_FIXTURE,
}


def _make_temp_repo() -> str:
    root = tempfile.mkdtemp()
    for rel_path, content in FIXTURES.items():
        path = Path(root) / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


def test_normalize_namespace():
    assert normalize_namespace("Octo.User") == "octo-user"
    assert normalize_namespace("my--name") == "my-name"
    with pytest.raises(ValueError):
        normalize_namespace("---")


def test_namespace_name():
    assert namespace_name("naive-agent", "foo") == "foo-naive-agent"
    assert namespace_name("foo-naive-agent", "foo") == "foo-naive-agent"


def test_namespace_blueprint_naive():
    result = namespace_blueprint(NAIVE_FIXTURE, "octo-user")
    contents = result["contents"]
    assert "octo-user-agents-workshop-naive" in contents
    assert "octo-user-naive-agent-db" in contents
    assert "octo-user-naive-agent" in contents
    # fromDatabase reference updated
    assert re.search(r"fromDatabase:\s+name: octo-user-naive-agent-db", contents)


def test_namespace_blueprint_queue():
    result = namespace_blueprint(QUEUE_FIXTURE, "octo-user")
    contents = result["contents"]
    assert "octo-user-queue-agents-valkey" in contents
    assert "octo-user-queue-agents-web" in contents
    assert "octo-user-queue-agents-worker" in contents
    assert re.search(r"fromService:\s+name: octo-user-queue-agents-valkey", contents)


def test_namespace_blueprint_idempotent():
    first = namespace_blueprint(NAIVE_FIXTURE, "octo-user")
    second = namespace_blueprint(first["contents"], "octo-user")
    assert "octo-user-octo-user-" not in second["contents"]


def test_namespace_replaces_previous_prefix():
    first = namespace_blueprint(NAIVE_FIXTURE, "first-user")
    second = namespace_blueprint(first["contents"], "second-user")
    assert "second-user-agents-workshop-naive" in second["contents"]
    assert "second-user-first-user-" not in second["contents"]


def test_setup_attendee_full(monkeypatch):
    root = _make_temp_repo()
    blueprints = list(FIXTURES.keys())
    changes = setup_attendee(blueprints, "octo-user", root)
    assert len(changes) == 3

    naive = (Path(root) / "packages/naive_agent/render.yaml").read_text()
    assert "octo-user-naive-agent" in naive

    queue = (Path(root) / "packages/queue_agents/render.yaml").read_text()
    assert "octo-user-queue-agents-valkey" in queue


def test_parse_args_positional(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    args = parse_args(["MyUser"])
    assert args["namespace"] == "myuser"


def test_parse_args_equals(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    args = parse_args(["--namespace=Equals.User"])
    assert args["namespace"] == "equals-user"


def test_parse_args_github_actor(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTOR", "Actor.Name")
    args = parse_args([])
    assert args["namespace"] == "actor-name"
