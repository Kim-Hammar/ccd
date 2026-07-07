#!/bin/bash

echo "Running type checker for ccd"
mypy ccd tests run_scenario_1.py run_scenario_2.py run_scenario_3.py scalability.py inference_scalability.py sensitivity.py
