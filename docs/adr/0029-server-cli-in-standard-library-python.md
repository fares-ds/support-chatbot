# ADR-0029: The server CLI is a standard-library Python script

- Status: Accepted
- Date: 2026-10-06
- Deciders: Fares

## Context

The vendor operates every install with the server CLI: `install`, `upgrade`, `backup`, `restore`, `status`, `report` and `reset-password` ([ADR-0013](0013-upgrades-and-migrations.md), OPS-1 to OPS-8). It runs on the host, outside the containers:

- `upgrade` replaces the application images while it runs.
- The host's cron runs `backup` independently of the application containers ([ADR-0024](0024-stack-review-corrections.md), item 7).

A fresh VPS has Docker and whatever its operating system ships. The vendor works mainly in Python.

## Decision

- The CLI, `sc`, is one Python script. It runs on the host's `python3`, version 3.10 or later, and imports only the standard library.
- It drives `docker compose`, and the host's cron for backups.
- `report` and `reset-password` need the application's code, so `sc` runs them inside the backend image as one-off containers.
- The script ships in the install bundle, versioned with each release ([ADR-0027](0027-repository-layout-and-git-workflow.md)).
- CI tests it with pytest, and runs `install`, `upgrade`, `backup` and `restore` on a fresh runner.

## Consequences

- The host needs nothing installed beyond Docker and a `python3` of 3.10 or later, which current Ubuntu and Debian releases ship. `install` checks the version first.
- No third-party libraries: argparse for arguments, plain text for output, urllib for HTTP checks.
- Upgrade and rollback logic, with its error handling, is written and tested in the vendor's main language rather than in shell.
