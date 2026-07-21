#!/bin/bash

echo "Running type checker for ccd"
mypy src/ccd tests examples testbeds/it_system/scripts testbeds/it_system/tests
