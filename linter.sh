#!/bin/bash

echo "Running Python Linter"
flake8 src/ccd tests examples
