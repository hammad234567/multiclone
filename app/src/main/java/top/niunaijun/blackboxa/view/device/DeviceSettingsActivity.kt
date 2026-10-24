package top.niunaijun.blackboxa.view.device

import android.graphics.Color
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import top.niunaijun.blackbox.BlackBoxCore
import top.niunaijun.blackbox.utils.DeviceProfileStore

/** Fake device identity for one cloned app (built programmatically, no layout XML). */
class DeviceSettingsActivity : AppCompatActivity() {

    private val fields = LinkedHashMap<String, EditText>()
    private var pkg: String = ""
    private var userId: Int = 0

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val p = intent.getStringExtra("pkg")
        if (p == null) {
            finish()
            return
        }
        pkg = p
        userId = intent.getIntExtra("userId", 0)
        val appName = intent.getStringExtra("name") ?: p

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(16))
        }

        root.addView(TextView(this).apply {
            text = "Device Settings"
            textSize = 22f
            setTextColor(Color.BLACK)
        })
        root.addView(TextView(this).apply {
            text = "$appName ($pkg), user $userId\nEmpty field = real value. Restart the app after saving."
            textSize = 13f
            setPadding(0, dp(4), 0, dp(12))
        })

        val labels = linkedMapOf(
            "brand" to "Brand",
            "manufacturer" to "Manufacturer",
            "model" to "Model",
            "device" to "Device",
            "product" to "Product",
            "fingerprint" to "Fingerprint",
            "androidId" to "Android ID (16 hex)",
            "imei" to "IMEI (15 digits)"
        )
        val saved = DeviceProfileStore.load(this, pkg, userId)
        for ((key, label) in labels) {
            val et = EditText(this).apply {
                hint = label
                setSingleLine(true)
                setText(saved[key] ?: "")
            }
            fields[key] = et
            root.addView(et, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(16), 0, 0)
        }
        row.addView(Button(this).apply {
            text = "Randomize"
            setOnClickListener { randomize() }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(Button(this).apply {
            text = "Reset"
            setOnClickListener { fields.values.forEach { it.setText("") }; save() }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(Button(this).apply {
            text = "Save"
            setOnClickListener { save() }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        root.addView(row)

        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun save() {
        val values = HashMap<String, String>()
        for ((k, et) in fields) values[k] = et.text.toString().trim()
        try {
            DeviceProfileStore.save(this, pkg, userId, values)
            try {
                BlackBoxCore.get().stopPackage(pkg, userId)
            } catch (e: Throwable) {
            }
            Toast.makeText(this, "Saved. Open the app again.", Toast.LENGTH_LONG).show()
        } catch (t: Throwable) {
            Toast.makeText(this, "Save failed: ${t.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun randomize() {
        // brand, manufacturer, model, device, product
        val presets = listOf(
            arrayOf("google", "Google", "Pixel 7", "panther", "panther"),
            arrayOf("google", "Google", "Pixel 8", "shiba", "shiba"),
            arrayOf("samsung", "samsung", "SM-S911B", "dm1q", "dm1qxxx"),
            arrayOf("samsung", "samsung", "SM-A546E", "a54x", "a54xnsxx"),
            arrayOf("Xiaomi", "Xiaomi", "2211133G", "fuxi", "fuxi_global")
        )
        val pr = presets.random()
        val build = (1000000..9999999).random()
        set("brand", pr[0])
        set("manufacturer", pr[1])
        set("model", pr[2])
        set("device", pr[3])
        set("product", pr[4])
        set("fingerprint", "${pr[0]}/${pr[4]}/${pr[3]}:13/TQ3A.230805.001/$build:user/release-keys")
        set("androidId", (1..16).map { "0123456789abcdef".random() }.joinToString(""))
        set("imei", randomImei())
    }

    private fun set(key: String, value: String) {
        fields[key]?.setText(value)
    }

    private fun randomImei(): String {
        val body = "35" + (1..12).map { (0..9).random() }.joinToString("")
        var sum = 0
        for (i in body.indices) {
            var d = body[body.length - 1 - i] - '0'
            if (i % 2 == 0) {
                d *= 2
                if (d > 9) d -= 9
            }
            sum += d
        }
        return body + ((10 - sum % 10) % 10)
    }
}
