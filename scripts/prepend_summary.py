#!/usr/bin/env python3
"""Prepend an episode summary to every row's context column in a TSV.

Usage:
    python3 prepend_summary.py <tsv_path> <summary>

Arguments:
    tsv_path - Path to the TSV file (modified in place)
    summary  - The episode summary string to prepend
"""

import csv
import sys

tsv_path = sys.argv[1]
summary = sys.argv[2]

with open(tsv_path, encoding='utf-8') as f:
    reader = list(csv.DictReader(f, delimiter='\t'))

fieldnames = reader[0].keys()

for row in reader:
    row['context'] = 'Episode summary: ' + summary + ' | ' + row['context']

with open(tsv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
    writer.writeheader()
    writer.writerows(reader)
