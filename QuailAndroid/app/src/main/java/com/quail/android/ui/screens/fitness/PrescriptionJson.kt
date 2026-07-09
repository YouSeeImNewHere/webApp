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

data class PrescriptionSet(val reps: Int?, val holdSeconds: Int?)

fun Map<String, JsonElement>.setsList(): List<PrescriptionSet> {
    val arr = (this["sets"] as? JsonArray) ?: return emptyList()
    return arr.map { el ->
        val obj = el as? JsonObject ?: return@map PrescriptionSet(null, null)
        PrescriptionSet(reps = obj["reps"]?.jsonPrimitive?.intOrNull, holdSeconds = obj["hold_seconds"]?.jsonPrimitive?.intOrNull)
    }
}

/** Short one-line summary for list rows, e.g. "5 mi @ 9:30/mi" or "5x12 reps". */
fun prescriptionSummary(workoutType: String, prescription: Map<String, JsonElement>): String {
    val type = prescription.str("type")
    return when (type) {
        "run" -> {
            val distance = prescription.double("distance_km")
            val pace = prescription.int("target_pace_sec_per_mile")
            buildString {
                if (distance != null) append("${"%.1f".format(distance)} km")
                if (pace != null) append(if (isNotEmpty()) " @ ${formatPace(pace)}/mi" else "Target ${formatPace(pace)}/mi")
                if (isEmpty()) append(prescription.str("notes") ?: workoutType)
            }
        }
        "intervals" -> {
            val reps = prescription.int("reps")
            val pace = prescription.int("target_pace_sec_per_mile")
            "${reps ?: "?"}x400m" + (pace?.let { " @ ${formatPace(it)}/mi" } ?: "")
        }
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

fun formatPace(secPerMile: Int): String {
    val m = secPerMile / 60
    val s = secPerMile % 60
    return "$m:${s.toString().padStart(2, '0')}"
}
