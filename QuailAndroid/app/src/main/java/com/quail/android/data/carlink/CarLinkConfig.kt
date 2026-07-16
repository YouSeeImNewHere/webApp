package com.quail.android.data.carlink

/** The one car this phone connects to — get this from the mini PC's
 * Bluetooth settings (or `bluetoothctl show` / `hcitool dev` on the car
 * itself) and fill it in. Blank means car-link is disabled entirely
 * (TileMapScreen only calls [BluetoothCarLinkManager.connectToCar] when
 * this is non-blank), so the app works exactly as before until this is
 * set — no behavior change for anyone who hasn't paired a car yet.
 * Mirrors quail_maps_car/carlink/config.py's PAIRED_PHONE_MAC on the other
 * side of this same pairing. */
const val PAIRED_CAR_MAC: String = "50:31:23:14:68:E9"
