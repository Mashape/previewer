#!/bin/bash

setup:
  virtualenv .venv
  .venv/bin/pip install -r requirements.txt

run:
  source .venv/bin/activate && FLASK_APP=main.py flask run --host=0.0.0.0
