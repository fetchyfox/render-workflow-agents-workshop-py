"""
Namespace Render Blueprint resource names for attendee forks so deploys don't
collide. Reads/writes YAML, prefixes all resource names with a namespace derived
from the attendee's GitHub username.

Usage:
    python scripts/setup_attendee.py your-github-username
    python scripts/setup_attendee.py --namespace=your-github-username
    GITHUB_ACTOR=username python scripts/setup_attendee.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_BLUEPRINTS = [
    "packages/naive_agent/render.yaml",
    "packages/queue_agents/render.yaml",
    "packages/workflow_agents/render.yaml",
]

BASE_RESOURCE_NAMES = [
    "agents-workshop-naive",
    "naive-agent-db",
    "naive-agent",
    "agents-workshop-queue",
    "queue-agents-db",
    "queue-agents-valkey",
    "queue-agents-web",
    "queue-agents-worker",
    "agents-workshop-workflows",
    "workflow-agents-db",
    "workflow-agents",
]

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def normalize_namespace(value: str) -> str:
    namespace = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not namespace:
        raise ValueError("Namespace must contain at least one letter or number.")
    return namespace


def namespace_name(name: str, namespace: str) -> str:
    if name.startswith(f"{namespace}-"):
        return name
    base_name = next(
        (c for c in BASE_RESOURCE_NAMES if name == c or name.endswith(f"-{c}")),
        None,
    )
    return f"{namespace}-{base_name or name}"


def namespace_blueprint(source: str, namespace: str) -> dict[str, Any]:
    doc = yaml.safe_load(source)
    if not isinstance(doc, dict):
        return {"contents": source, "changed_names": []}

    name_changes: dict[str, str] = {}
    changed_names: list[dict[str, str]] = []

    def collect_name(node: dict[str, Any]) -> None:
        current = node.get("name")
        if not isinstance(current, str):
            return
        next_name = namespace_name(current, namespace)
        if next_name != current:
            name_changes[current] = next_name
            changed_names.append({"from": current, "to": next_name})
            for base in BASE_RESOURCE_NAMES:
                if current == base or current.endswith(f"-{base}"):
                    name_changes[base] = next_name
                    break
            node["name"] = next_name

    def collect_from_list(items: list[Any]) -> None:
        for item in items:
            if isinstance(item, dict):
                collect_name(item)

    for project in doc.get("projects", []):
        if not isinstance(project, dict):
            continue
        collect_name(project)
        for env in project.get("environments", []):
            if not isinstance(env, dict):
                continue
            for key in ("databases", "services"):
                items = env.get(key, [])
                if isinstance(items, list):
                    collect_from_list(items)

    for key in ("databases", "services"):
        items = doc.get(key, [])
        if isinstance(items, list):
            collect_from_list(items)

    def update_references(node: Any) -> None:
        if isinstance(node, dict):
            for ref_key in ("fromDatabase", "fromService"):
                ref = node.get(ref_key)
                if isinstance(ref, dict):
                    current = ref.get("name")
                    if isinstance(current, str) and current in name_changes:
                        ref["name"] = name_changes[current]
            for v in node.values():
                update_references(v)
        elif isinstance(node, list):
            for item in node:
                update_references(item)

    update_references(doc)

    return {
        "contents": yaml.dump(doc, default_flow_style=False, sort_keys=False),
        "changed_names": changed_names,
    }


def parse_args(argv: list[str]) -> dict[str, Any]:
    args: dict[str, Any] = {
        "blueprints": list(DEFAULT_BLUEPRINTS),
        "namespace": os.environ.get("GITHUB_ACTOR"),
        "root": str(DEFAULT_ROOT),
    }

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--namespace="):
            args["namespace"] = arg[len("--namespace="):]
            i += 1
            continue
        if arg == "--namespace":
            if i + 1 >= len(argv):
                raise ValueError("Missing value for --namespace.")
            args["namespace"] = argv[i + 1]
            i += 2
            continue
        if arg == "--root":
            if i + 1 >= len(argv):
                raise ValueError("Missing value for --root.")
            args["root"] = str(Path(argv[i + 1]).resolve())
            i += 2
            continue
        if arg.startswith("--"):
            raise ValueError(f"Unknown argument: {arg}")
        if args["namespace"] and args["namespace"] != os.environ.get("GITHUB_ACTOR"):
            raise ValueError(f"Unexpected extra argument: {arg}")
        args["namespace"] = arg
        i += 1

    if not args["namespace"]:
        raise ValueError(
            "Missing namespace. Run `python scripts/setup_attendee.py your-github-username`."
        )

    args["namespace"] = normalize_namespace(args["namespace"])
    return args


def setup_attendee(blueprints: list[str], namespace: str, root: str) -> list[dict[str, Any]]:
    changes = []
    for relative_path in blueprints:
        path = Path(root) / relative_path
        source = path.read_text()
        result = namespace_blueprint(source, namespace)
        path.write_text(result["contents"])
        changes.append({"path": relative_path, "changed_names": result["changed_names"]})
    return changes


def print_summary(changes: list[dict[str, Any]]) -> None:
    for change in changes:
        print(change["path"])
        if not change["changed_names"]:
            print("  no changes")
            continue
        for item in change["changed_names"]:
            print(f"  {item['from']} -> {item['to']}")


def main() -> None:
    try:
        args = parse_args(sys.argv[1:])
        changes = setup_attendee(args["blueprints"], args["namespace"], args["root"])
        print_summary(changes)
    except (ValueError, FileNotFoundError) as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
