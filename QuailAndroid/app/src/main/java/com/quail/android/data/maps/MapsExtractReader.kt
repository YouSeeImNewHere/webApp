package com.quail.android.data.maps

import android.database.sqlite.SQLiteDatabase

data class MapNode(val id: String, val east: Float, val north: Float, val label: String)

data class MapEdge(val a: String, val b: String, val street: String, val roadClass: String, val speedKph: Float)

data class MapPlace(
    val id: String,
    val nodeId: String,
    val name: String,
    val address: String,
    val icon: String,
    val category: String,
)

data class MapExtractData(
    val nodes: Map<String, MapNode>,
    val edges: List<MapEdge>,
    val places: List<MapPlace>,
)

/** Reads a downloaded city extract straight off disk — the exact schema
 * `maps_pipeline/schema.py`'s EXTRACT_SCHEMA writes (and what
 * quail_maps_car/geo/{roadnet,search_db}.py expect), so this is just a
 * plain read of nodes/edges/places tables, no server round-trip. */
object MapsExtractReader {
    private const val PROGRESS_REPORT_EVERY = 2000

    /** [onProgress] is called with a 0f..1f fraction as rows are read —
     * a 15km-radius extract can be tens of thousands of rows, so this is
     * the only feedback the UI has that a "View map" tap isn't stuck. */
    fun read(filePath: String, onProgress: ((Float) -> Unit)? = null): MapExtractData {
        val db = SQLiteDatabase.openDatabase(filePath, null, SQLiteDatabase.OPEN_READONLY)
        try {
            val totalRows = (rowCount(db, "nodes") + rowCount(db, "edges") + rowCount(db, "places"))
                .coerceAtLeast(1)
            var processed = 0
            fun tick() {
                processed++
                if (onProgress != null && processed % PROGRESS_REPORT_EVERY == 0) {
                    onProgress(processed.toFloat() / totalRows)
                }
            }

            val nodes = LinkedHashMap<String, MapNode>()
            db.rawQuery("SELECT id, east, north, label FROM nodes", null).use { cursor ->
                while (cursor.moveToNext()) {
                    val id = cursor.getString(0)
                    nodes[id] = MapNode(
                        id = id,
                        east = cursor.getFloat(1),
                        north = cursor.getFloat(2),
                        label = cursor.getString(3) ?: "",
                    )
                    tick()
                }
            }

            val edges = ArrayList<MapEdge>()
            db.rawQuery("SELECT a, b, street, road_class, speed_kph FROM edges", null).use { cursor ->
                while (cursor.moveToNext()) {
                    edges.add(
                        MapEdge(
                            a = cursor.getString(0),
                            b = cursor.getString(1),
                            street = cursor.getString(2) ?: "",
                            roadClass = cursor.getString(3) ?: "local",
                            speedKph = cursor.getFloat(4),
                        ),
                    )
                    tick()
                }
            }

            val places = ArrayList<MapPlace>()
            db.rawQuery("SELECT id, node_id, name, address, icon, category FROM places", null).use { cursor ->
                while (cursor.moveToNext()) {
                    places.add(
                        MapPlace(
                            id = cursor.getString(0),
                            nodeId = cursor.getString(1),
                            name = cursor.getString(2) ?: "",
                            address = cursor.getString(3) ?: "",
                            icon = cursor.getString(4) ?: "",
                            category = cursor.getString(5) ?: "",
                        ),
                    )
                    tick()
                }
            }

            onProgress?.invoke(1f)
            return MapExtractData(nodes = nodes, edges = edges, places = places)
        } finally {
            db.close()
        }
    }

    private fun rowCount(db: SQLiteDatabase, table: String): Int {
        db.rawQuery("SELECT COUNT(*) FROM $table", null).use { cursor ->
            return if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
    }
}
