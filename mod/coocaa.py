#!/usr/bin/env python3
"""Inject the optional Skyworth / Coocaa compatibility mode into the upstream source."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def edit(path, replacements):
    file = ROOT / path
    source = file.read_text(encoding="utf-8")
    for old, new, label in replacements:
        if new in source:
            continue
        count = source.count(old)
        if count != 1:
            raise SystemExit(f"[mod/coocaa] {path}: expected one {label} anchor, found {count}")
        source = source.replace(old, new, 1)
    file.write_text(source, encoding="utf-8")
    print(f"[mod/coocaa] patched {path}")


edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ('    var peekNextRow by mutableStateOf(true); private set',
     '    var peekNextRow by mutableStateOf(true); private set\n\n    /** Opt-in compatibility mode for Skyworth / Coocaa firmwares. */\n    var coocaaMode by mutableStateOf(false); private set',
     "Coocaa mode state"),
    ('        peekNextRow = prefs.getBoolean("peek_next_row", true)',
     '        peekNextRow = prefs.getBoolean("peek_next_row", true)\n        coocaaMode = prefs.getBoolean("coocaa_mode", false)\n        if (coocaaMode) GuardSetup.startCoocaaMode(app)',
     "Coocaa mode preference load"),
    ('    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("peek_next_row", on) }\n    }',
     '    fun chooseCoocaaMode(on: Boolean) {\n        coocaaMode = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("coocaa_mode", on) }\n        if (on) {\n            GuardSetup.startCoocaaMode(app)\n        } else {\n            GuardSetup.stopCoocaaMode()\n        }\n    }\n\n    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("peek_next_row", on) }\n    }',
     "Coocaa mode setter"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('                    Choices(\n                        R.string.st_home_lock, stringResource(R.string.st_home_lock_hint), note,\n                        listOf(false to R.string.st_off, true to R.string.st_on),\n                        AerialSettings.homeLocked, onHomeLock,\n                    )',
     '                    Choices(\n                        R.string.st_home_lock, stringResource(R.string.st_home_lock_hint), note,\n                        listOf(false to R.string.st_off, true to R.string.st_on),\n                        AerialSettings.homeLocked, onHomeLock,\n                    )\n                    Choices(\n                        R.string.st_coocaa_mode, stringResource(R.string.st_coocaa_mode_hint), note,\n                        listOf(false to R.string.st_off, true to R.string.st_on),\n                        AerialSettings.coocaaMode, AerialSettings::chooseCoocaaMode,\n                    )',
     "Coocaa mode personalization row"),
])

edit("app/src/main/java/app/orchard/tv/ui/control/ControlCenter.kt", [
    ('import androidx.compose.ui.unit.sp\n',
     'import androidx.compose.ui.unit.sp\nimport androidx.compose.ui.window.Dialog\n',
     "Coocaa warning dialog import"),
    ('    val revival = remember { SystemProbe.revivalSettingsIntent(context) }\n    var qr by remember { mutableStateOf<ImageBitmap?>(null) }',
     '    val revival = remember { SystemProbe.revivalSettingsIntent(context) }\n    var qr by remember { mutableStateOf<ImageBitmap?>(null) }\n    var coocaaWarning by remember { mutableStateOf(false) }',
     "Coocaa warning state"),
    ('        home?.let { MenuRow(Glyph.Check, stringResource(R.string.cc_setup_home), onClick = { vm.whenUnlocked { onOpen(it) } }, trailing = "›") }',
     '        home?.let { target ->\n            MenuRow(Glyph.Check, stringResource(R.string.cc_setup_home), onClick = {\n                if (AerialSettings.coocaaMode) coocaaWarning = true\n                else vm.whenUnlocked { onOpen(target) }\n            }, trailing = "›")\n        }',
     "block default Home registration in Coocaa mode"),
    ('    }\n}\n\n/** A round Control Center button: frosted at rest, white when focused. */',
     '    }\n    if (coocaaWarning) {\n        Dialog(onDismissRequest = { coocaaWarning = false }) {\n            Column(\n                Modifier.width(500.dp)\n                    .background(Color(0xF01B1B1B), RoundedCornerShape(24.dp))\n                    .padding(28.dp),\n                verticalArrangement = Arrangement.spacedBy(16.dp),\n            ) {\n                BasicText(stringResource(R.string.cc_setup_coocaa_warning_title), style = Type.Title)\n                BasicText(stringResource(R.string.cc_setup_coocaa_warning_message), style = Type.Body)\n                MenuRow(Glyph.Check, stringResource(R.string.cc_setup_coocaa_warning_ok), onClick = { coocaaWarning = false })\n            }\n        }\n    }\n}\n\n/** A round Control Center button: frosted at rest, white when focused. */',
     "Coocaa warning dialog"),
])

edit("app/src/main/java/app/orchard/tv/guard/GuardSetup.kt", [
    ('    private const val PREFS = "system"',
     '    private const val PREFS = "system"\n    private const val COOCAA_SETTINGS_PREFS = "settings"\n    private const val COOCAA_MODE_KEY = "coocaa_mode"\n    private const val COOCAA_SYNC_INTERVAL_MS = 3_000L\n    private const val COOCAA_SYNC_MAX_BACKOFF_MS = 5 * 60_000L\n\n    private val coocaaHandler = Handler(Looper.getMainLooper())\n    @Volatile private var coocaaContext: Context? = null\n    private var coocaaSyncActive = false\n    private var coocaaSyncDelayMs = COOCAA_SYNC_INTERVAL_MS\n    private var coocaaSyncFailures = 0\n    private var coocaaLastRebindAt = Long.MIN_VALUE / 2\n    private var coocaaLastStatus = ""\n\n    private val coocaaSync = object : Runnable {\n        override fun run() {\n            val context = coocaaContext ?: return\n            if (!coocaaModeEnabled(context)) {\n                stopCoocaaMode()\n                return\n            }\n            val synced = runCatching { syncCoocaaAccessibility(context) }.getOrElse {\n                noteCoocaaStatus("sync failed: ${it.javaClass.simpleName}")\n                false\n            }\n            if (synced) {\n                coocaaSyncFailures = 0\n                coocaaSyncDelayMs = COOCAA_SYNC_INTERVAL_MS\n            } else {\n                coocaaSyncFailures++\n                coocaaSyncDelayMs = (coocaaSyncDelayMs * 2).coerceAtMost(COOCAA_SYNC_MAX_BACKOFF_MS)\n            }\n            coocaaHandler.postDelayed(this, coocaaSyncDelayMs)\n        }\n    }',
     "Coocaa background synchronizer"),
    ('    fun ensureEnabled(context: Context): Boolean {\n        ensureAdb(context)',
     '    /** Whether the owner explicitly enabled the Coocaa compatibility mode. */\n    fun coocaaModeEnabled(context: Context): Boolean = isUserUnlocked(context) &&\n        context.getSharedPreferences(COOCAA_SETTINGS_PREFS, Context.MODE_PRIVATE).getBoolean(COOCAA_MODE_KEY, false)\n\n    /** Start a low-impact sync loop; only missing settings are written. */\n    fun startCoocaaMode(context: Context) {\n        val app = context.applicationContext\n        coocaaHandler.post {\n            if (!coocaaModeEnabled(app)) return@post\n            coocaaContext = app\n            if (coocaaSyncActive) return@post\n            coocaaSyncActive = true\n            coocaaSyncFailures = 0\n            coocaaSyncDelayMs = COOCAA_SYNC_INTERVAL_MS\n            coocaaHandler.postDelayed(coocaaSync, COOCAA_SYNC_INTERVAL_MS)\n            DiagLog.i("compat=coocaa: background accessibility sync started")\n        }\n    }\n\n    /** Stop only the compatibility worker; do not alter the enabled accessibility list. */\n    fun stopCoocaaMode() {\n        coocaaHandler.post {\n            if (!coocaaSyncActive && coocaaContext == null) return@post\n            coocaaHandler.removeCallbacks(coocaaSync)\n            coocaaSyncActive = false\n            coocaaContext = null\n            coocaaLastStatus = ""\n            DiagLog.i("compat=coocaa: background accessibility sync stopped")\n        }\n    }\n\n    private fun noteCoocaaStatus(message: String) {\n        if (coocaaLastStatus == message) return\n        coocaaLastStatus = message\n        DiagLog.i("compat=coocaa: $message")\n    }\n\n    /** Incrementally retain every existing service and append Aerial only when it is absent. */\n    private fun syncCoocaaAccessibility(context: Context): Boolean {\n        if (!isUserUnlocked(context)) return false\n        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_SECURE_SETTINGS) != PackageManager.PERMISSION_GRANTED) {\n            noteCoocaaStatus("WRITE_SECURE_SETTINGS is not granted; waiting for permission")\n            return false\n        }\n        val resolver = context.contentResolver\n        val me = ComponentName(context, HomeGuardService::class.java).flattenToString()\n        val current = Settings.Secure.getString(resolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()\n        val entries = current.split(":").filter { it.isNotBlank() }\n        val alreadyEnabled = entries.any { ComponentName.unflattenFromString(it)?.flattenToString() == me }\n        if (!alreadyEnabled) {\n            val updated = (entries + me).joinToString(":")\n            if (!Settings.Secure.putString(resolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES, updated)) {\n                noteCoocaaStatus("could not append HomeGuardService; retrying with backoff")\n                return false\n            }\n        }\n        if (Settings.Secure.getInt(resolver, Settings.Secure.ACCESSIBILITY_ENABLED, 0) != 1 &&\n            !Settings.Secure.putInt(resolver, Settings.Secure.ACCESSIBILITY_ENABLED, 1)\n        ) {\n            noteCoocaaStatus("could not enable accessibility; retrying with backoff")\n            return false\n        }\n        val verified = Settings.Secure.getString(resolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()\n            .split(":").any { ComponentName.unflattenFromString(it)?.flattenToString() == me }\n        if (!verified) {\n            noteCoocaaStatus("HomeGuardService is still missing from the enabled list; retrying with backoff")\n            return false\n        }\n        if (!HomeGuardService.isRunning) {\n            val now = SystemClock.elapsedRealtime()\n            if (now - coocaaLastRebindAt >= 60_000L) {\n                coocaaLastRebindAt = now\n                rebindIfStalled(context)\n            }\n            noteCoocaaStatus("service is listed but not bound; waiting for Android accessibility activation")\n        } else {\n            noteCoocaaStatus("HomeGuardService is active")\n        }\n        return true\n    }\n\n    fun ensureEnabled(context: Context): Boolean {\n        if (coocaaModeEnabled(context)) startCoocaaMode(context)\n        ensureAdb(context)',
     "Coocaa mode sync and ensureEnabled integration"),
])

edit("app/src/main/java/app/orchard/tv/guard/BootReceiver.kt", [
    ('    private fun onBoot(context: Context, action: String) {\n        GuardSetup.ensureEnabled(context)',
     '    private fun onBoot(context: Context, action: String) {\n        if (action != Intent.ACTION_LOCKED_BOOT_COMPLETED && GuardSetup.coocaaModeEnabled(context)) {\n            // Let Coocaa finish its early boot-time launcher and accessibility service scan.\n            runCatching { Thread.sleep(3_000L) }\n            DiagLog.i("compat=coocaa: delayed boot guard initialization")\n        }\n        GuardSetup.ensureEnabled(context)',
     "delayed Coocaa boot initialization"),
])

edit("app/src/main/java/app/orchard/tv/guard/HomeGuardService.kt", [
    ('        if (fastBootTakeOver) {\n            // Starting the wait again would undo what onCreate saved: on MiTV-MFTR0 the connection\n            // came 1.3 s into it, and Aerial came a few seconds later than it could have.\n            if (!patchwallEarlyTakeOver) takeOverOnceSettled("bound shortly after boot", woke = true)\n            scheduleBootRechecks()\n        }',
     '        if (fastBootTakeOver) {\n            // Coocaa may still be starting its own launcher after the accessibility service binds.\n            // Wait briefly before deciding what is in front; other devices keep the upstream timing.\n            if (GuardSetup.coocaaModeEnabled(this)) {\n                handler.postDelayed({\n                    if (!patchwallEarlyTakeOver) takeOverOnceSettled("bound shortly after boot (Coocaa delay)", woke = true)\n                    scheduleBootRechecks()\n                }, 3_000L)\n            } else {\n                // Starting the wait again would undo what onCreate saved: on MiTV-MFTR0 the connection\n                // came 1.3 s into it, and Aerial came a few seconds later than it could have.\n                if (!patchwallEarlyTakeOver) takeOverOnceSettled("bound shortly after boot", woke = true)\n                scheduleBootRechecks()\n            }\n        }',
     "Coocaa delayed first boot takeover"),
])

edit("app/src/main/java/app/orchard/tv/guard/HomeGuardService.kt", [
    ('        if (skipReason == null) takeOverOnceSettled(how, woke = true)\n        else Log.i(TAG, "$how; not taking over Home ($skipReason)")',
     '        if (skipReason == null) {\n            if (GuardSetup.coocaaModeEnabled(this)) {\n                handler.postDelayed({ takeOverOnceSettled("$how (Coocaa delay)", woke = true) }, 3_000L)\n            } else {\n                takeOverOnceSettled(how, woke = true)\n            }\n        } else Log.i(TAG, "$how; not taking over Home ($skipReason)")',
     "Coocaa delayed takeover after user unlock"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="cc_setup_home">选择默认桌面</string>',
     '    <string name="cc_setup_home">设置为默认桌面</string>\n    <string name="cc_setup_coocaa_warning_title">酷开模式已开启</string>\n    <string name="cc_setup_coocaa_warning_message">酷开系统可能锁定系统默认桌面。当前模式通过 Aerial 桌面守护接管主页，此入口不会执行默认桌面注册。请确认已在系统无障碍设置中启用 Aerial 桌面守护。</string>\n    <string name="cc_setup_coocaa_warning_ok">知道了</string>',
     "Chinese Coocaa warning strings"),
    ('    <string name="st_home_lock">锁定主屏幕</string>',
     '    <string name="st_coocaa_mode">酷开模式</string>\n    <string name="st_coocaa_mode_hint">适用于创维 / 酷开电视。开启后改用 Aerial 桌面守护接管主页，并在后台增量同步无障碍服务配置。首次仍需在系统无障碍设置中手动启用 Aerial 桌面守护；系统权限未授予时无法自动写入。</string>\n    <string name="st_home_lock">锁定主屏幕</string>',
     "Chinese Coocaa mode strings"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="cc_setup_home">Choose the Default Home App</string>',
     '    <string name="cc_setup_home">Set as Default Home</string>\n    <string name="cc_setup_coocaa_warning_title">Coocaa mode is enabled</string>\n    <string name="cc_setup_coocaa_warning_message">Coocaa firmware may lock the system default Home app. This mode uses Aerial Home Guard to handle Home instead. This entry will not register Aerial as the default Home. Make sure Aerial Home Guard is enabled in Accessibility settings.</string>\n    <string name="cc_setup_coocaa_warning_ok">Got it</string>',
     "English Coocaa warning strings"),
    ('    <string name="st_home_lock">Lock Home</string>',
     '    <string name="st_coocaa_mode">Coocaa mode</string>\n    <string name="st_coocaa_mode_hint">For Skyworth / Coocaa TVs. Uses Aerial Home Guard and incrementally syncs its accessibility entry in the background. You must still enable Aerial Home Guard manually in system Accessibility settings the first time; background writes require WRITE_SECURE_SETTINGS.</string>\n    <string name="st_home_lock">Lock Home</string>',
     "English Coocaa mode strings"),
])

# Fail before Gradle if any of the new strings were injected more than once.
for resource_path in (
    "app/src/main/res/values/strings.xml",
    "app/src/main/res/values-zh/strings.xml",
):
    root = ET.parse(ROOT / resource_path).getroot()
    for name in (
        "st_coocaa_mode",
        "st_coocaa_mode_hint",
        "cc_setup_coocaa_warning_title",
        "cc_setup_coocaa_warning_message",
        "cc_setup_coocaa_warning_ok",
    ):
        count = sum(1 for item in root if item.attrib.get("name") == name)
        if count != 1:
            raise SystemExit(f"[mod/coocaa] {resource_path}: expected one {name}, found {count}")

print("[mod/coocaa] Coocaa mode injection verified")
