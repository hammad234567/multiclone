import os, re, sys

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)

def patch(path, old, new, count=1):
    s = open(path).read()
    if s.count(old) != count:
        sys.exit("ANCHOR MISMATCH in %s: %r found %d times" % (path, old[:60], s.count(old)))
    open(path, "w").write(s.replace(old, new))

B = "Bcore/src/main/java/top/niunaijun/blackbox/"
A = "app/src/main/java/top/niunaijun/blackboxa/"

if os.path.exists(B + "utils/DeviceProfileStore.java"):
    sys.exit("Already applied. Nothing to do.")

# ---------- 1. engine: profile store ----------
write(B + "utils/DeviceProfileStore.java", r'''package top.niunaijun.blackbox.utils;

import android.content.Context;
import android.os.Build;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Field;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import top.niunaijun.blackbox.BlackBoxCore;

/**
 * Per-clone fake device identity. The UI (host process) saves a small
 * .properties file; the virtual app process reads it once at bind time.
 */
public final class DeviceProfileStore {
    private static final String TAG = "DeviceProfileStore";
    public static final String[] KEYS = {
            "brand", "manufacturer", "model", "device", "product",
            "fingerprint", "androidId", "imei"
    };

    private static volatile Map<String, String> sActive = Collections.emptyMap();

    private DeviceProfileStore() {
    }

    private static File fileFor(Context ctx, String pkg, int userId) {
        File dir = new File(ctx.getFilesDir(), "device_profiles");
        if (!dir.exists()) {
            dir.mkdirs();
        }
        return new File(dir, pkg + "_" + userId + ".properties");
    }

    public static Map<String, String> load(Context ctx, String pkg, int userId) {
        Map<String, String> out = new HashMap<>();
        File f = fileFor(ctx, pkg, userId);
        if (!f.isFile()) {
            return out;
        }
        try (FileInputStream in = new FileInputStream(f)) {
            Properties p = new Properties();
            p.load(in);
            for (String k : KEYS) {
                String v = p.getProperty(k);
                if (v != null && !v.trim().isEmpty()) {
                    out.put(k, v.trim());
                }
            }
        } catch (Throwable t) {
            Slog.w(TAG, "load failed: " + t.getMessage());
        }
        return out;
    }

    public static void save(Context ctx, String pkg, int userId, Map<String, String> values) throws IOException {
        File f = fileFor(ctx, pkg, userId);
        Properties p = new Properties();
        for (String k : KEYS) {
            String v = values.get(k);
            if (v != null && !v.trim().isEmpty()) {
                p.setProperty(k, v.trim());
            }
        }
        if (p.isEmpty()) {
            f.delete();
            return;
        }
        try (FileOutputStream out = new FileOutputStream(f)) {
            p.store(out, "MultiClone device profile");
        }
    }

    /** Called inside the virtual app process, before the app's own code runs. */
    public static void applyBuild(String pkg, int userId) {
        try {
            Context ctx = BlackBoxCore.getContext();
            if (ctx == null) {
                return;
            }
            Map<String, String> m = load(ctx, pkg, userId);
            sActive = m;
            if (m.isEmpty()) {
                return;
            }
            setBuild("BRAND", m.get("brand"));
            setBuild("MANUFACTURER", m.get("manufacturer"));
            setBuild("MODEL", m.get("model"));
            setBuild("DEVICE", m.get("device"));
            setBuild("PRODUCT", m.get("product"));
            setBuild("FINGERPRINT", m.get("fingerprint"));
            Slog.d(TAG, "Applied device profile for " + pkg + " user " + userId);
        } catch (Throwable t) {
            Slog.w(TAG, "applyBuild failed: " + t.getMessage());
        }
    }

    private static void setBuild(String field, String value) {
        if (value == null || value.isEmpty()) {
            return;
        }
        try {
            Field f = Build.class.getDeclaredField(field);
            f.setAccessible(true);
            f.set(null, value);
        } catch (Throwable t) {
            Slog.w(TAG, "Build." + field + " not set: " + t.getMessage());
        }
    }

    /** IMEI from the profile, or the engine's default when none is configured. */
    public static String imeiOr(String fallback) {
        String v = sActive.get("imei");
        return (v == null || v.isEmpty()) ? fallback : v;
    }

    /** Non-null only when the key is android_id and a profile value exists. */
    public static String overrideForSettingKey(String key) {
        if (key != null && key.equalsIgnoreCase("android_id")) {
            String v = sActive.get("androidId");
            if (v != null && !v.isEmpty()) {
                return v;
            }
        }
        return null;
    }
}
''')

# ---------- 2. engine: call it at bind time ----------
patch(B + "app/BActivityThread.java",
"        PackageInfo packageInfo = BlackBoxCore.getBPackageManager().getPackageInfo(packageName, PackageManager.GET_PROVIDERS, BActivityThread.getUserId());",
"""        try {
            top.niunaijun.blackbox.utils.DeviceProfileStore.applyBuild(packageName, BActivityThread.getUserId());
        } catch (Throwable ignored) {
        }

        PackageInfo packageInfo = BlackBoxCore.getBPackageManager().getPackageInfo(packageName, PackageManager.GET_PROVIDERS, BActivityThread.getUserId());""")

# ---------- 3. engine: IMEI hooks use the profile ----------
tp = B + "fake/service/ITelephonyManagerProxy.java"
s = open(tp).read()
for cls in ("GetDeviceId", "getImeiForSlot", "GetDeviceIdWithFeature"):
    head = "public static class " + cls + " extends MethodHook {"
    i = s.find(head)
    if i < 0:
        sys.exit("class not found: " + cls)
    old = "return Md5Utils.md5(BlackBoxCore.getHostPkg());"
    j = s.find(old, i)
    k = s.find("public static class", i + 10)
    if j < 0 or (k != -1 and j > k):
        sys.exit("return not found in " + cls)
    s = s[:j] + "return top.niunaijun.blackbox.utils.DeviceProfileStore.imeiOr(Md5Utils.md5(BlackBoxCore.getHostPkg()));" + s[j + len(old):]
open(tp, "w").write(s)

# ---------- 4. engine: android_id override ----------
ap = B + "fake/service/AndroidIdProxy.java"
inject = """if (args != null && args.length > 0 && args[0] instanceof String) {
                    String __ov = top.niunaijun.blackbox.utils.DeviceProfileStore.overrideForSettingKey((String) args[0]);
                    if (__ov != null) {
                        return __ov;
                    }
                }
                """
for call in ("getString", "get", "read"):
    old = 'Slog.d(TAG, "AndroidId: Handling %s call");\n                Object result = method.invoke(who, args);' % call
    new = 'Slog.d(TAG, "AndroidId: Handling %s call");\n                %sObject result = method.invoke(who, args);' % (call, inject)
    patch(ap, old, new)

# ---------- 5. disable automatic log upload to a third-party server ----------
patch(B + "app/configuration/ClientConfiguration.java", 'return "-1003719573856";', 'return "";')

# ---------- 6. app: screen ----------
write(A + "view/device/DeviceSettingsActivity.kt", r'''package top.niunaijun.blackboxa.view.device

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
''')

# ---------- 7. app: menu item, string, click handler, manifest ----------
patch("app/src/main/res/menu/app_menu.xml",
      '<item android:id="@+id/app_shortcut" android:title="@string/app_shortcut"/>',
      '<item android:id="@+id/app_shortcut" android:title="@string/app_shortcut"/>\n    <item android:id="@+id/app_device" android:title="@string/app_device"/>')
patch("app/src/main/res/values/strings.xml", "</resources>",
      '    <string name="app_device">Device Settings</string>\n</resources>')
patch(A + "view/apps/AppsFragment.kt",
"""                                    R.id.app_shortcut -> {
                                        ShortcutUtil.createShortcut(requireContext(), userID, data)
                                    }""",
"""                                    R.id.app_shortcut -> {
                                        ShortcutUtil.createShortcut(requireContext(), userID, data)
                                    }

                                    R.id.app_device -> {
                                        val i = android.content.Intent(
                                            requireContext(),
                                            top.niunaijun.blackboxa.view.device.DeviceSettingsActivity::class.java
                                        )
                                        i.putExtra("pkg", data.packageName)
                                        i.putExtra("userId", userID)
                                        i.putExtra("name", data.name)
                                        startActivity(i)
                                    }""")
patch("app/src/main/AndroidManifest.xml",
      '<activity android:name=".view.setting.SettingActivity" />',
      '<activity android:name=".view.setting.SettingActivity" />\n        <activity android:name=".view.device.DeviceSettingsActivity" android:exported="false" />')
print("OK: device settings patch applied")
