#!/usr/bin/env python3
"""Apply the local Aerial customization to a clean upstream checkout.

The patch is intentionally strict: if upstream moves the integration points, fail the
build instead of silently producing an APK without the requested behavior.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def edit(path, replacements):
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    for old, new, label in replacements:
        count = text.count(old)
        if count == 0 and new in text:
            continue
        if count != 1:
            raise SystemExit(f"[mod] {path}: expected one {label} anchor, found {count}")
        text = text.replace(old, new, 1)
    file.write_text(text, encoding="utf-8")
    print(f"[mod] patched {path}")

# AppEntry marks a non-interactive tile-sized gap. AppTile draws it as an empty slot.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('import java.net.URL\n', 'import java.net.URL\nimport org.json.JSONObject\n', "release JSON import"),
    ('    private const val VERSION_URL = "https://aerial.qust.me/download/version.txt"\n', '    private const val VERSION_URL = "https://api.github.com/repos/klcb2010/aerial-tv/releases/latest"\n', "own release version URL"),
    ('            read = { withContext(Dispatchers.IO) { read(VERSION_URL) } },', '            read = { withContext(Dispatchers.IO) { readLatestVersion() } },', "own release version reader"),
    ('    private fun read(url: String): String {', '    private fun readLatestVersion(): String {\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }\n\n    private fun read(url: String): String {', "release tag parser"),
    ('            "https://github.com/pengchujin/aerial-tv/releases/latest/download/$name",', '            "https://github.com/klcb2010/aerial-tv/releases/latest/download/$name",', "own release APK URL"),
    ('            "https://aerial.qust.me/download/$name",\n', '', "remove official APK source"),
])

edit("app/src/main/java/app/orchard/tv/apps/Apps.kt", [
    ('    val shortcut: Intent? = null,\n) {',
     '    val shortcut: Intent? = null,\n    /** An intentionally empty Home slot left by hiding a first-row app. */\n    val emptySlot: Boolean = false,\n) {',
     "AppEntry emptySlot field"),
])

# LayoutStore is shared with Aerial Lite. Give Lite's separate AppEntry the small
# copy-compatible surface used by the shared layout code, without changing Lite's UI.
edit("lite/src/main/java/app/orchard/tv/lite/Apps.kt", [
    ('    val folder: Folder? = null,\n) {',
     '    val folder: Folder? = null,\n    val emptySlot: Boolean = false,\n) {\n    val packageName: String get() = key\n\n    fun copy(\n        packageName: String = this.packageName,\n        label: String = this.label,\n        emptySlot: Boolean = this.emptySlot,\n    ) = AppEntry(packageName, label, component, leanback, removable, tile, placeholder, folder, emptySlot)',
     "Lite AppEntry compatibility"),
])

edit("app/src/main/java/app/orchard/tv/apps/LayoutStore.kt", [
    ('class Arrangement(val home: List<AppEntry>, val folders: Map<String, List<AppEntry>>, val hidden: List<AppEntry>)',
     'class Arrangement(\n    val home: List<AppEntry>,\n    val folders: Map<String, List<AppEntry>>,\n    val hidden: List<AppEntry>,\n    /** Home order with optional empty slots retained in the first row. */\n    val homeSlots: List<AppEntry> = home,\n)',
     "Arrangement homeSlots field"),
    ('    fun arrange(all: List<AppEntry>, folderTile: (Folder, List<AppEntry>) -> AppEntry): Arrangement {',
     '    fun arrange(\n        all: List<AppEntry>,\n        preserveHiddenSlots: Int = 0,\n        folderTile: (Folder, List<AppEntry>) -> AppEntry,\n    ): Arrangement {',
     "arrange signature"),
    ('        val home = order.mapNotNull { key ->\n            val folder = folderOf(key)\n            if (folder != null) contents[folder.id]?.takeIf { it.isNotEmpty() }?.let { folderTile(folder, it) }\n            else byKey[key]?.takeIf { key !in hidden }\n        }\n        val inAnyOrder = order + folders.values.flatMap { it.apps }\n        return Arrangement(home, contents, inAnyOrder.mapNotNull(byKey::get).filter { it.key in hidden })',
     '        val home = mutableListOf<AppEntry>()\n        val homeSlots = mutableListOf<AppEntry>()\n        for (key in order) {\n            val folder = folderOf(key)\n            val tile = if (folder != null) {\n                contents[folder.id]?.takeIf { it.isNotEmpty() }?.let { folderTile(folder, it) }\n            } else {\n                byKey[key]?.takeIf { key !in hidden }\n            }\n            if (tile != null) {\n                home += tile\n                homeSlots += tile\n            } else if (homeSlots.size < preserveHiddenSlots && key in hidden) {\n                // Keep only hidden apps that originally occupied a first-row position. Later\n                // rows continue to compact normally; the blank tile has no focus or click target.\n                byKey[key]?.let { hiddenApp ->\n                    homeSlots += hiddenApp.copy(\n                        packageName = "hidden-slot:${homeSlots.size}",\n                        label = "",\n                        emptySlot = true,\n                    )\n                }\n            }\n        }\n        val inAnyOrder = order + folders.values.flatMap { it.apps }\n        return Arrangement(home, contents, inAnyOrder.mapNotNull(byKey::get).filter { it.key in hidden }, homeSlots)',
     "arrangement home loop"),
])

edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('        val arrangement = store.arrange(named + pinned) { folder, inside ->',
     '        val arrangement = store.arrange(\n            named + pinned,\n            preserveHiddenSlots = if (AerialSettings.hiddenSlots) AerialSettings.homeColumns else 0,\n        ) { folder, inside ->',
     "arrange call"),
    ('            else -> AerialSettings.previewApps.takeIf { it > 0 }?.let { arrangement.home.take(it) } ?: arrangement.home',
     '            else -> AerialSettings.previewApps.takeIf { it > 0 }?.let { arrangement.homeSlots.take(it) } ?: arrangement.homeSlots',
     "Home apps source"),
])

edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ('    var peekNextRow by mutableStateOf(true); private set',
     '    var peekNextRow by mutableStateOf(true); private set\n\n    /** Keep hidden apps in the first row as empty slots instead of pulling later apps forward. */\n    var hiddenSlots by mutableStateOf(false); private set',
     "hiddenSlots property"),
    ('        peekNextRow = prefs.getBoolean("peek_next_row", true)',
     '        peekNextRow = prefs.getBoolean("peek_next_row", true)\n        hiddenSlots = prefs.getBoolean("hidden_slots", false)',
     "hiddenSlots preference load"),
    ('    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("peek_next_row", on) }\n    }',
     '    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("peek_next_row", on) }\n    }\n\n    fun chooseHiddenSlots(on: Boolean) {\n        hiddenSlots = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("hidden_slots", on) }\n    }',
     "hiddenSlots setter"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('                    if (AerialSettings.oneRowHome) Choices(\n                        R.string.st_peek, stringResource(R.string.st_peek_hint), note,\n                        listOf(true to R.string.st_peek_show, false to R.string.st_peek_hide),\n                        AerialSettings.peekNextRow, AerialSettings::choosePeekNextRow,\n                    )',
     '                    if (AerialSettings.oneRowHome) Choices(\n                        R.string.st_peek, stringResource(R.string.st_peek_hint), note,\n                        listOf(true to R.string.st_peek_show, false to R.string.st_peek_hide),\n                        AerialSettings.peekNextRow, AerialSettings::choosePeekNextRow,\n                    )\n                    Choices(\n                        R.string.st_hidden_slots, stringResource(R.string.st_hidden_slots_hint), note,\n                        listOf(false to R.string.st_off, true to R.string.st_on),\n                        AerialSettings.hiddenSlots, AerialSettings::chooseHiddenSlots,\n                    )',
     "hidden slots setting row"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="st_peek">Second Row</string>',
     '    <string name="st_hidden_slots">Keep First-Row Gaps</string>\n    <string name="st_hidden_slots_hint">When an app in the first row is hidden, leave its original position empty instead of pulling later apps forward.</string>\n    <string name="st_peek">Second Row</string>',
     "default setting strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="st_peek">第二排</string>',
     '    <string name="st_hidden_slots">隐藏不补位</string>\n    <string name="st_hidden_slots_hint">隐藏第一排中的 App 后，原位置留空，后面的 App 不会顶上来，保持第一排整洁。</string>\n    <string name="st_peek">第二排</string>',
     "Chinese setting strings"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    ('    val reduced = LocalReducedMotion.current',
     '    if (app.emptySlot) {\n        Spacer(modifier.requiredSize(width, height))\n        return\n    }\n\n    val reduced = LocalReducedMotion.current',
     "empty slot rendering"),
])
edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('        viewModelScope.launch { snapshotFlow { AerialSettings.previewApps }.drop(1).collect { if (loaded) arrange() } }',
     '        viewModelScope.launch { snapshotFlow { AerialSettings.previewApps }.drop(1).collect { if (loaded) arrange() } }\n        viewModelScope.launch { snapshotFlow { AerialSettings.hiddenSlots }.drop(1).collect { if (loaded) arrange() } }',
     "hidden slots live refresh"),
])

print("[mod] all patches applied")
