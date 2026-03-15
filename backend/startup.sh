#!/bin/bash

# MIT License
# Author: Inari Solutions Sp. z o.o.
# Project notice: Demonstration code prepared for a hackathon.
# Production notice: This code is not ready for production use.
# File role: Local startup script that prepares the environment and runs the backend service.

# Create virtual env if not exists
if [ ! -d "antenv" ]; then
    python -m venv antenv
fi

# Activate
source antenv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start app (recommended: gunicorn)
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
