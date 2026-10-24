package top.niunaijun.blackbox.utils;

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
