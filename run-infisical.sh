#!/usr/bin/env bash
# Run a command with Infisical-injected env. Example: ./run-infisical.sh python main.py
# Requires: infisical login, infisical init (see docs/INFISICAL.md)
exec infisical run -- "$@"
