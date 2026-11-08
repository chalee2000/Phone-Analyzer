package th.spni.agent

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.CallLog
import android.provider.ContactsContract
import android.view.Gravity
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Exports contacts, call log and SMS to JSON files in the app's external files
 * folder (Android/data/th.spni.agent/files/export). Phone Analysis pulls
 * them over ADB and then uninstalls this app, which removes the files too.
 *
 * Started with: am start -n th.spni.agent/.ExportActivity --es kinds contacts,calls,sms
 */
class ExportActivity : Activity() {

    private val required = arrayOf(
        Manifest.permission.READ_CONTACTS,
        Manifest.permission.READ_CALL_LOG,
        Manifest.permission.READ_SMS,
    )
    private lateinit var status: TextView
    private var kinds: Set<String> = setOf("contacts", "calls", "sms")
    private var started = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply {
            textSize = 18f
            gravity = Gravity.CENTER
            setPadding(56, 56, 56, 56)
            text = getString(R.string.exporting)
        }
        setContentView(status)
        intent.getStringExtra("kinds")?.let { value ->
            val parsed = value.split(",").map { it.trim() }.filter { it.isNotEmpty() }.toSet()
            if (parsed.isNotEmpty()) kinds = parsed
        }
        val missing = required.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            status.text = getString(R.string.please_allow)
            requestPermissions(missing.toTypedArray(), REQUEST_CODE)
        } else {
            startExport()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        startExport()
    }

    private fun startExport() {
        if (started) return
        started = true
        status.text = getString(R.string.exporting)
        Thread {
            val dir = File(getExternalFilesDir(null), "export").apply { mkdirs() }
            val summary = JSONObject()
            fun write(name: String, block: () -> JSONArray) {
                val file = File(dir, "$name.json")
                try {
                    val items = block()
                    file.writeText(items.toString())
                    summary.put(name, items.length())
                } catch (e: Exception) {
                    file.writeText(JSONObject().put("error", e.toString()).toString())
                    summary.put(name, "error: $e")
                }
            }
            if ("contacts" in kinds) write("contacts") { contacts() }
            if ("calls" in kinds) write("calls") { calls() }
            if ("sms" in kinds) write("sms") { sms() }
            summary.put("sdk", Build.VERSION.SDK_INT)
            summary.put("finished", System.currentTimeMillis())
            File(dir, "done.json").writeText(summary.toString())
            runOnUiThread {
                status.text = getString(R.string.done)
                finish()
            }
        }.start()
    }

    private inline fun query(uri: Uri, projection: Array<String>, each: (Cursor) -> Unit) {
        contentResolver.query(uri, projection, null, null, null)?.use { c ->
            while (c.moveToNext()) each(c)
        }
    }

    private fun Cursor.str(column: String): String? {
        val i = getColumnIndex(column)
        return if (i >= 0 && !isNull(i)) getString(i) else null
    }

    private fun Cursor.long(column: String): Long {
        val i = getColumnIndex(column)
        return if (i >= 0 && !isNull(i)) getLong(i) else 0L
    }

    private fun contacts(): JSONArray {
        val byId = LinkedHashMap<Long, JSONObject>()
        val projection = arrayOf(
            ContactsContract.Data.CONTACT_ID,
            ContactsContract.Data.MIMETYPE,
            ContactsContract.Data.DISPLAY_NAME,
            ContactsContract.Data.DATA1,
            ContactsContract.Data.STARRED,
            ContactsContract.RawContacts.ACCOUNT_TYPE,
        )
        query(ContactsContract.Data.CONTENT_URI, projection) { c ->
            val id = c.long(ContactsContract.Data.CONTACT_ID)
            val item = byId.getOrPut(id) {
                JSONObject()
                    .put("name", c.str(ContactsContract.Data.DISPLAY_NAME) ?: "")
                    .put("account", c.str(ContactsContract.RawContacts.ACCOUNT_TYPE) ?: "")
                    .put("starred", c.long(ContactsContract.Data.STARRED) == 1L)
                    .put("phones", JSONArray())
                    .put("emails", JSONArray())
            }
            val value = c.str(ContactsContract.Data.DATA1) ?: return@query
            when (c.str(ContactsContract.Data.MIMETYPE)) {
                ContactsContract.CommonDataKinds.Phone.CONTENT_ITEM_TYPE -> item.getJSONArray("phones").put(value)
                ContactsContract.CommonDataKinds.Email.CONTENT_ITEM_TYPE -> item.getJSONArray("emails").put(value)
                ContactsContract.CommonDataKinds.Organization.CONTENT_ITEM_TYPE -> item.put("organization", value)
                ContactsContract.CommonDataKinds.Note.CONTENT_ITEM_TYPE -> item.put("note", value)
            }
        }
        return JSONArray(byId.values)
    }

    private fun calls(): JSONArray {
        val out = JSONArray()
        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
            CallLog.Calls.PHONE_ACCOUNT_ID,
            CallLog.Calls.GEOCODED_LOCATION,
        )
        query(CallLog.Calls.CONTENT_URI, projection) { c ->
            out.put(
                JSONObject()
                    .put("number", c.str(CallLog.Calls.NUMBER) ?: "")
                    .put("name", c.str(CallLog.Calls.CACHED_NAME) ?: "")
                    .put("type", c.long(CallLog.Calls.TYPE))
                    .put("date", c.long(CallLog.Calls.DATE))
                    .put("duration", c.long(CallLog.Calls.DURATION))
                    .put("subscription_id", c.str(CallLog.Calls.PHONE_ACCOUNT_ID) ?: "")
                    .put("location", c.str(CallLog.Calls.GEOCODED_LOCATION) ?: "")
            )
        }
        return out
    }

    private fun sms(): JSONArray {
        val out = JSONArray()
        val projection = arrayOf("_id", "thread_id", "address", "date", "type", "read", "body")
        query(Uri.parse("content://sms"), projection) { c ->
            out.put(
                JSONObject()
                    .put("id", c.long("_id"))
                    .put("thread_id", c.long("thread_id"))
                    .put("address", c.str("address") ?: "")
                    .put("date", c.long("date"))
                    .put("type", c.long("type"))
                    .put("read", c.long("read"))
                    .put("body", c.str("body") ?: "")
            )
        }
        return out
    }

    companion object {
        private const val REQUEST_CODE = 41
    }
}
