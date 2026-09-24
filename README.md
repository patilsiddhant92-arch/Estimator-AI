# Estimator AI

Reads an HVAC/BMS controls bid package and produces the proposal and price sheet an AME estimator issues — built on the team's own templates.

The design is in `docs/superpowers/specs/2026-09-24-estimator-ai-design.md`.

## Set up once

    py -3.13 -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"

Always run things with `.venv/Scripts/python.exe`. The bare `python` on this machine is 3.14 and belongs to another project.

## Make a job's proposal and price sheet

    .venv/Scripts/python.exe -m estimator build JOB.json --out out/JOB

## When the team updates a template

Copy the new file over the one in `assets/templates/`, then run the tests:

    .venv/Scripts/python.exe -m pytest
