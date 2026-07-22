package com.quail.android.ui.screens.fitness

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Small helpers for reading a ScheduledWorkoutRecord.prescription
 * (Map<String, JsonElement>) — shapes are produced by
 * app/core/fitness_plan_engine.py and kept loosely typed on the wire since
 * they vary by workout_type: run, pushups, lsit_hold, and the *_test kinds. */

fun Map<String, JsonElement>.str(key: String): String? = this[key]?.jsonPrimitive?.contentOrNull
fun Map<String, JsonElement>.int(key: String): Int? = this[key]?.jsonPrimitive?.intOrNull
fun Map<String, JsonElement>.double(key: String): Double? = this[key]?.jsonPrimitive?.doubleOrNull

/** All distances are stored/computed in km end to end (backend + local
 * models) - converting only at display time, here and everywhere else a km
 * value gets rendered, keeps that data model intact while showing miles
 * throughout the UI per user preference. */
fun kmToMiles(km: Double): Double = km * 0.621371

data class PrescriptionSet(val reps: Int?, val holdSeconds: Int?)

fun Map<String, JsonElement>.setsList(): List<PrescriptionSet> {
    val arr = (this["sets"] as? JsonArray) ?: return emptyList()
    return arr.map { el ->
        val obj = el as? JsonObject ?: return@map PrescriptionSet(null, null)
        PrescriptionSet(reps = obj["reps"]?.jsonPrimitive?.intOrNull, holdSeconds = obj["hold_seconds"]?.jsonPrimitive?.intOrNull)
    }
}

/** A "session" prescription's blocks array (see fitness_plan_engine.py's
 * _skills_week_plan) - each block is itself a small prescription with its
 * own "type"/"sets"/etc, same shape as the old single-exercise
 * prescriptions below, just nested one level down. */
fun Map<String, JsonElement>.blocks(): List<Map<String, JsonElement>> {
    val arr = (this["blocks"] as? JsonArray) ?: return emptyList()
    return arr.mapNotNull { (it as? JsonObject)?.toMap() }
}

/** Short label for one exercise block, e.g. "Pushups", "L-sit", "Core" —
 * used both standalone and joined together for a bundled session. */
fun blockLabel(block: Map<String, JsonElement>): String = when (block.str("type")) {
    "pushups" -> "Pushups"
    "lsit_hold" -> "L-sit"
    // Rotating complementary work (squats, rows, core) - see
    // fitness_plan_engine.py's _ACCESSORY_ROTATION - backend sends the
    // display label directly since it's the one place the rotation lives.
    "accessory", "core_hold" -> block.str("label") ?: "Core"
    "run" -> "Run"
    else -> block.str("type")?.replace('_', ' ')?.replaceFirstChar { it.uppercase() } ?: "Exercise"
}

/** Short one-line summary for list rows, e.g. "5 mi @ 9:30/mi" or "5x12 reps". */
fun prescriptionSummary(workoutType: String, prescription: Map<String, JsonElement>): String {
    val type = prescription.str("type")
    return when (type) {
        "session" -> prescription.blocks().joinToString(" + ") { blockLabel(it) }
        "run" -> {
            val distance = prescription.double("distance_km")
            val pace = prescription.int("target_pace_sec_per_mile")
            buildString {
                if (distance != null) append("${"%.1f".format(kmToMiles(distance))} mi")
                if (pace != null) append(if (isNotEmpty()) " @ ${formatPace(pace)}/mi" else "Target ${formatPace(pace)}/mi")
                if (isEmpty()) append(prescription.str("notes") ?: workoutType)
            }
        }
        "intervals" -> {
            val reps = prescription.int("reps")
            val pace = prescription.int("target_pace_sec_per_mile")
            val distanceMi = prescription.double("distance_km")?.let { kmToMiles(it) } ?: 0.25
            "${reps ?: "?"}x${"%.2f".format(distanceMi)}mi" + (pace?.let { " @ ${formatPace(it)}/mi" } ?: "")
        }
        // pushups/lsit_hold cases below stay for old, already-scheduled
        // rows generated before session-bundling existed - new plans use
        // "session" (above) instead.
        "pushups" -> {
            val sets = prescription.setsList()
            "${sets.size}x${sets.firstOrNull()?.reps ?: "?"} pushups"
        }
        "lsit_hold" -> {
            val sets = prescription.setsList()
            "${sets.size}x${sets.firstOrNull()?.holdSeconds ?: "?"}s L-sit"
        }
        "pushup_test" -> "Max pushups (AMRAP)"
        "lsit_test" -> "Max L-sit hold"
        "run_test" -> "Timed mile + easy run"
        else -> workoutType.replace('_', ' ').lowercase()
    }
}

/** Rough per-set work time when a set is reps-based rather than a timed
 * hold - there's no real per-rep duration anywhere in the data model, so
 * this is a coarse-but-reasonable estimate (3s/rep covers most bodyweight
 * strength moves) used only to build the "~N min" estimate shown in the UI. */
private const val SECONDS_PER_REP = 3

/** Estimated seconds to complete one exercise block: each set's own work
 * time (hold_seconds, or reps * SECONDS_PER_REP) plus rest_seconds between
 * sets (not after the last set). */
fun estimatedSecondsForBlock(block: Map<String, JsonElement>): Int {
    val sets = block.setsList()
    if (sets.isEmpty()) return 0
    val restSeconds = block.int("rest_seconds") ?: 45
    val work = sets.sumOf { it.holdSeconds ?: ((it.reps ?: 0) * SECONDS_PER_REP) }
    val rest = restSeconds * (sets.size - 1).coerceAtLeast(0)
    return work + rest
}

/** Estimated seconds for a run/intervals prescription, from target pace
 * when present, else a generic easy-pace assumption (9:30/mi). Intervals
 * repeat a short distance `reps` times, with rest between reps. */
fun estimatedSecondsForRun(prescription: Map<String, JsonElement>): Int {
    val paceSecPerMile = prescription.int("target_pace_sec_per_mile") ?: 570
    return if (prescription.str("type") == "intervals") {
        val reps = prescription.int("reps") ?: 1
        val distanceMi = prescription.double("distance_km")?.let { kmToMiles(it) } ?: 0.25
        val restSeconds = prescription.int("rest_seconds") ?: 90
        (reps * distanceMi * paceSecPerMile).toInt() + restSeconds * (reps - 1).coerceAtLeast(0)
    } else {
        val distanceMi = prescription.double("distance_km")?.let { kmToMiles(it) } ?: return 0
        (distanceMi * paceSecPerMile).toInt()
    }
}

/** Estimated total seconds to complete an entire scheduled workout's
 * prescription, whichever shape it is (bundled session, single exercise
 * block, or a run) - used to show "~N min" against each day/exercise. */
fun estimatedSecondsForPrescription(prescription: Map<String, JsonElement>): Int = when (prescription.str("type")) {
    "session" -> prescription.blocks().sumOf { estimatedSecondsForBlock(it) }
    "run", "intervals" -> estimatedSecondsForRun(prescription)
    "pushups", "lsit_hold" -> estimatedSecondsForBlock(prescription)
    else -> 0
}

fun formatEstimatedMinutes(seconds: Int): String {
    if (seconds <= 0) return ""
    val minutes = (seconds / 60.0).let { if (it < 1) 1 else Math.round(it) }
    return "~$minutes min"
}

fun formatPace(secPerMile: Int): String {
    val m = secPerMile / 60
    val s = secPerMile % 60
    return "$m:${s.toString().padStart(2, '0')}"
}
