#!/bin/bash

echo "Running Python Linter"
flake8 ccd tests run_scenario_1.py run_scenario_2.py run_scenario_3.py scalability.py inference_scalability.py
