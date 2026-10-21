#!/bin/bash
# Starts (or restarts) the live demo in the background.
#   ./demo.sh               C920 if it's plugged in, else the laptop camera; capacity 40
#   ./demo.sh --capacity 3  any people-counter-web option can be added
#   ./demo.sh stop
# The process ID is kept in .demo/pid, so stopping never touches other processes. Log: .demo/log
cd "$(dirname "$0")"
mkdir -p .demo
if [ -f .demo/pid ] && kill -0 "$(cat .demo/pid)" 2>/dev/null; then
  kill -INT "$(cat .demo/pid)"
  for _ in $(seq 1 10); do kill -0 "$(cat .demo/pid)" 2>/dev/null || break; sleep 1; done
  echo "Stopped the previous demo."
fi
rm -f .demo/pid
[ "$1" = "stop" ] && exit 0

if grep -qi c920 /sys/class/video4linux/video*/name 2>/dev/null; then source=C920; else source=0; echo "C920 not found: using the laptop camera."; fi
nohup .venv/bin/people-counter-web --source "$source" --tunnel --capacity 40 "$@" > .demo/log 2>&1 &
echo $! > .demo/pid
for _ in $(seq 1 60); do
  grep -q "Phones:" .demo/log && break
  kill -0 "$(cat .demo/pid)" 2>/dev/null || { cat .demo/log; exit 1; }
  sleep 1
done
grep -v WARN .demo/log
