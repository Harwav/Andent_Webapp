#!/usr/bin/env python3
"""
Issue CLI for Andent_Webapp fix-issues workflow.

Usage:
    python .fix-issues/scripts/issues.py list
    python .fix-issues/scripts/issues.py create "Title" --priority P1 --label bug
    python .fix-issues/scripts/issues.py update 1 --status in-progress
    python .fix-issues/scripts/issues.py close 1
    python .fix-issues/scripts/issues.py show 1
    python .fix-issues/scripts/issues.py delete 1
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ISSUES_FILE = Path(__file__).parent.parent / "issues.json"


def load_issues() -> dict:
    if not ISSUES_FILE.exists():
        return {"version": 1, "issues": []}
    with open(ISSUES_FILE) as f:
        return json.load(f)


def save_issues(data: dict) -> None:
    with open(ISSUES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def next_id(data: dict) -> int:
    if not data["issues"]:
        return 1
    return max(i["id"] for i in data["issues"]) + 1


def cmd_list(args) -> None:
    data = load_issues()
    open_issues = [
        i for i in data["issues"]
        if i["status"] in ("open", "in-progress", "reopened")
    ]
    if not open_issues:
        print("No open issues.")
        return

    # Sort by priority
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    open_issues.sort(key=lambda i: (
        priority_order.get(i.get("priority", "P2"), 3),
        i["status"] == "reopened",  # reopened first within priority
        i["id"]
    ))

    for issue in open_issues:
        status_icon = "!" if issue["status"] == "reopened" else "o"
        labels = ", ".join(f"[{l}]" for l in issue.get("labels", []))
        print(f"[{issue['id']}] ({issue.get('priority', 'P?')}, {issue['status']}) [{status_icon}] {issue['title']} {labels}")


def cmd_create(args) -> None:
    data = load_issues()
    issue = {
        "id": next_id(data),
        "title": args.title,
        "description": args.description or "",
        "priority": args.priority or "P2",
        "status": "open",
        "created": str(date.today()),
        "assignee": None,
        "labels": args.label or [],
    }
    data["issues"].append(issue)
    save_issues(data)
    print(f"Created issue [{issue['id']}]: {issue['title']}")


def cmd_update(args) -> None:
    data = load_issues()
    issue = next((i for i in data["issues"] if i["id"] == args.issue_id), None)
    if not issue:
        print(f"Issue #{args.issue_id} not found.")
        sys.exit(1)

    if args.status:
        issue["status"] = args.status
    if args.priority:
        issue["priority"] = args.priority
    if args.title:
        issue["title"] = args.title
    if args.description is not None:
        issue["description"] = args.description

    save_issues(data)
    print(f"Updated [{issue['id']}]: status={issue['status']}, priority={issue['priority']}")


def cmd_close(args) -> None:
    data = load_issues()
    issue = next((i for i in data["issues"] if i["id"] == args.issue_id), None)
    if not issue:
        print(f"Issue #{args.issue_id} not found.")
        sys.exit(1)
    issue["status"] = "confirmed"
    issue["closed"] = str(date.today())
    save_issues(data)
    print(f"Closed issue [{issue['id']}].")


def cmd_reopen(args) -> None:
    data = load_issues()
    issue = next((i for i in data["issues"] if i["id"] == args.issue_id), None)
    if not issue:
        print(f"Issue #{args.issue_id} not found.")
        sys.exit(1)
    issue["status"] = "reopened"
    save_issues(data)
    print(f"Reopened issue [{issue['id']}].")


def cmd_show(args) -> None:
    data = load_issues()
    issue = next((i for i in data["issues"] if i["id"] == args.issue_id), None)
    if not issue:
        print(f"Issue #{args.issue_id} not found.")
        sys.exit(1)
    print(json.dumps(issue, indent=2))


def cmd_delete(args) -> None:
    data = load_issues()
    original = len(data["issues"])
    data["issues"] = [i for i in data["issues"] if i["id"] != args.issue_id]
    if len(data["issues"]) == original:
        print(f"Issue #{args.issue_id} not found.")
        sys.exit(1)
    save_issues(data)
    print(f"Deleted issue #{args.issue_id}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue tracker CLI")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List open issues")

    p_create = sub.add_parser("create", help="Create an issue")
    p_create.add_argument("title", help="Issue title")
    p_create.add_argument("--description", "-d", default=None)
    p_create.add_argument("--priority", "-p", default="P2", choices=["P0", "P1", "P2"])
    p_create.add_argument("--label", "-l", action="append", default=[], dest="label")

    p_update = sub.add_parser("update", help="Update an issue")
    p_update.add_argument("issue_id", type=int, help="Issue ID")
    p_update.add_argument("--status", "-s", choices=["open", "in-progress", "pending-confirmation", "confirmed", "reopened"])
    p_update.add_argument("--priority", "-p", choices=["P0", "P1", "P2"])
    p_update.add_argument("--title", "-t")
    p_update.add_argument("--description", "-d")

    p_close = sub.add_parser("close", help="Close an issue (mark as confirmed)")
    p_close.add_argument("issue_id", type=int)

    p_reopen = sub.add_parser("reopen", help="Reopen a closed issue")
    p_reopen.add_argument("issue_id", type=int)

    p_show = sub.add_parser("show", help="Show issue details")
    p_show.add_argument("issue_id", type=int)

    p_delete = sub.add_parser("delete", help="Delete an issue")
    p_delete.add_argument("issue_id", type=int)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "create": cmd_create,
        "update": cmd_update,
        "close": cmd_close,
        "reopen": cmd_reopen,
        "show": cmd_show,
        "delete": cmd_delete,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
