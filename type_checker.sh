#!/bin/bash

echo "Running type checker for ccd"
mypy src/ccd tests examples testbeds/it_system/scripts testbeds/it_system/tests \
    testbeds/5g_ran/scripts testbeds/5g_ran/tests
