#!/bin/bash

setup:
	virtualenv .venv
	.venv/bin/pip install -r requirements.txt

run:
	FLASK_APP=main.py .venv/bin/flask run --host=0.0.0.0
