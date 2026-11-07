package com.pfc.companion.data

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.ByteArrayInputStream
import java.io.InputStream

/**
 * A CSV selected through the Storage Access Framework. The bytes are streamed from
 * the content URI at upload time, so large files are never copied into app storage.
 */
class CsvUpload private constructor(
    val filename: String,
    val mimeType: String,
    val contentLength: Long,
    private val open: () -> InputStream,
) {
    fun openStream(): InputStream = open()

    companion object {
        const val MAX_BYTES = 5L * 1024 * 1024

        fun fromUri(context: Context, uri: Uri): CsvUpload {
            val resolver = context.contentResolver
            val name = resolver.displayName(uri) ?: "import.csv"
            val size = resolver.sizeOf(uri) ?: -1L
            require(size <= MAX_BYTES) { "That file is larger than the 5 MB import limit." }
            val mime = resolver.getType(uri) ?: "text/csv"
            return CsvUpload(
                filename = name,
                mimeType = mime,
                contentLength = size,
                open = {
                    resolver.openInputStream(uri)
                        ?: throw IllegalStateException("The selected file could not be opened.")
                },
            )
        }

        /** Used by tests and by code that already holds the file bytes. */
        fun fromBytes(filename: String, bytes: ByteArray, mimeType: String = "text/csv"): CsvUpload =
            CsvUpload(filename, mimeType, bytes.size.toLong()) { ByteArrayInputStream(bytes) }
    }
}

private fun ContentResolver.displayName(uri: Uri): String? =
    query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (!cursor.moveToFirst()) return@use null
        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (index >= 0) cursor.getString(index) else null
    }

private fun ContentResolver.sizeOf(uri: Uri): Long? =
    query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { cursor ->
        if (!cursor.moveToFirst()) return@use null
        val index = cursor.getColumnIndex(OpenableColumns.SIZE)
        if (index >= 0 && !cursor.isNull(index)) cursor.getLong(index) else null
    }
