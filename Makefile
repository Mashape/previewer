#!/bin/bash

setup:
	virtualenv .venv
	.venv/bin/pip install -r requirements.txt

hook_server:
	FLASK_APP=web.py .venv/bin/flask run --host=0.0.0.0

task_runner:
	.venv/bin/python task.py

cleanup:
	rm -rf .venv
