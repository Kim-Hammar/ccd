#!/bin/bash

echo "Running type checker for ccd"
# Each testbed's scripts/ has like-named modules (generate_compose.py, testbed.py, ...),
# so they are checked in separate mypy invocations to avoid duplicate-module errors.
mypy src/ccd tests examples testbeds/it_system/scripts testbeds/it_system/tests || exit 1
mypy testbeds/5g_ran/scripts testbeds/5g_ran/tests
