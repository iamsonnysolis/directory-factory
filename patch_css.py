#!/usr/bin/env python3
import os

with open('dashboard/static/styles.css', 'r') as f:
    lines = f.readlines()

# The directory detail CSS section starts with this comment (second occurrence)
# and ends just before the current-stage-banner section
print(f"Total lines: {len(lines)}")

# Find both section comments
for i, line in enumerate(lines):
    if 'Directory Detail Page' in line and 'mobile-first' in line:
        print(f"  Line {i+1}: {line.rstrip()[:80]}")

# Show what's around each marker
for target in [1235, 1236, 1375, 1376, 1379, 1380]:
    if 0 <= target-1 < len(lines):
        print(f"  L{target}: {lines[target-1].rstrip()[:80]}")
