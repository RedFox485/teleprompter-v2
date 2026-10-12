#!/bin/bash
# Teleprompter V2 - Startup script

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the teleprompter
python run.py "$@"