#!/bin/bash

echo "Running Python Linter"
flake8 src/ccd tests examples testbeds/it_system/scripts testbeds/it_system/tests testbeds/it_system/docker \
    testbeds/5g_ran/scripts testbeds/5g_ran/tests \
    testbeds/ics/scripts testbeds/ics/tests testbeds/ics/docker
