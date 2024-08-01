#!/bin/bash

# This script returns an infinite sequence of deals (which is convenient for
# passing into the --duplicate argument of engine.py). If you want only a finite
# number, you can pipe its output to head -n NUM_LINES.

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <probability1> <probability2>" >&2
    exit 1
fi

probability1=$1
probability2=$2

for prob in $probability1 $probability2; do
    if (( $(echo "$prob < 0 || $prob > 1" | bc -l) )); then
        echo "Error: Probabilities must be between 0 and 1" >&2
        exit 1
    fi
done

threshold1=$(echo "4294967295 * $probability1" | bc | cut -d'.' -f1)
threshold2=$(echo "4294967295 * $probability2" | bc | cut -d'.' -f1)

while true; do
    if (( $(od -An -N4 -tu4 /dev/urandom) < threshold1 )); then
        num1=3
    else
        num1=2
    fi
    if (( $(od -An -N4 -tu4 /dev/urandom) < threshold2 )); then
        num2=3
    else
        num2=2
    fi
    echo "$num1,$num2"
done
