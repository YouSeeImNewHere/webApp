#!/usr/bin/env bash
# One-word status check for the nationwide maps import + Valhalla tile
# build. Looks the import PID up dynamically (pgrep) rather than a
# hardcoded number, so this stays correct across restarts.

IMPORT_PID=$(pgrep -f "[m]aps_update_master.py")

echo "=== Maps Import ==="
if [ -n "$IMPORT_PID" ]; then
    ps -p "$IMPORT_PID" -o pid,stat,pcpu,etime,cmd
else
    echo "not running - check maps_import.log"
fi
ls -la /mnt/maps-data/master/ | tail -10
echo

echo "=== Valhalla ==="
docker logs --tail 10 valhalla
du -sh /mnt/maps-data/valhalla
echo

echo "=== Notifier ==="
cat /tmp/quail_maps_notify.log 2>/dev/null
echo

echo "=== Disk ==="
df -h /mnt/maps-data
echo

echo "=== Memory ==="
free -h
