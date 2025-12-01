#!/bin/bash
set -euo pipefail

# Simple wrapper to run sample.py with logging and ensure root privileges.
LOG="sample_test_$(date +%Y%m%d_%H%M%S).log"

if [ "$(id -u)" -ne 0 ]; then
  echo "Not running as root — re-running with sudo..."
  exec sudo bash "$0" "$@"
fi

echo "Starting sample.py demo at $(date)" | tee "$LOG"
python3 "$(dirname "$0")/sample.py" --demo 2>&1 | tee -a "$LOG"
echo "Finished at $(date)" | tee -a "$LOG"

echo "Log saved to $(pwd)/$LOG"
tail -n 50 "$LOG" || true
