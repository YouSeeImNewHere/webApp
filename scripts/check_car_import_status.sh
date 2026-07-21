#!/usr/bin/env bash
# One-word status check for the car computer's standalone region-import
# worker (two chained batches - see standalone_region_import.py).

IMPORT_PID=$(pgrep -f "[s]tandalone_region_import.py" | tail -1)

echo "=== Car Computer Import ==="
if [ -n "$IMPORT_PID" ]; then
    ps -p "$IMPORT_PID" -o pid,stat,pcpu,etime,cmd
else
    echo "not running - check car_import.log / car_import_batch2.log"
fi
echo

echo "=== Completed states ==="
ls ~/webapp/local_maps_data/master/*.sqlite3 2>/dev/null | sed 's#.*/##; s/north-america_us_//; s/\.sqlite3//' | sort
echo "total: $(ls ~/webapp/local_maps_data/master/*.sqlite3 2>/dev/null | wc -l)"
echo

echo "=== Batch 1 log tail ==="
tail -5 ~/webapp/car_import.log 2>/dev/null
echo

echo "=== Batch 2 log tail ==="
tail -5 ~/webapp/car_import_batch2.log 2>/dev/null
echo

echo "=== Disk ==="
df -h /
