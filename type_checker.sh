#!/bin/bash

echo "Running type checker for ccd"
mypy src/ccd tests examples
