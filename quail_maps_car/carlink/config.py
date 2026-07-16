from __future__ import annotations

import os

# The one phone this car accepts a destination from — deliberately not any
# paired device, since RFCOMM has no per-app auth beyond OS-level pairing,
# and this app's own BluetoothCarLink would otherwise happily route
# whatever any paired phone sent it. Get this from the phone's Bluetooth
# settings (Settings > About > Bluetooth address) and either hardcode it
# below or set QUAIL_CAR_PAIRED_PHONE_MAC in the environment (e.g. via the
# systemd unit / qtest alias) so it doesn't need a code change + redeploy
# to pair a different phone.
PAIRED_PHONE_MAC = os.environ.get("QUAIL_CAR_PAIRED_PHONE_MAC", "24:95:2F:DF:7F:9F")
