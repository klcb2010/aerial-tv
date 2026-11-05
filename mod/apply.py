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
    ('const val FOLDER_KEY_PREFIX = "folder:"',
     'const val FOLDER_KEY_PREFIX = "folder:"\nprivate const val FIRST_ROW_GAP_PREFIX = "first-row-gap:"',
     "first-row gap key"),
    ('class Arrangement(val home: List<AppEntry>, val folders: Map<String, List<AppEntry>>, val hidden: List<AppEntry>)',
     'class Arrangement(\n    val home: List<AppEntry>,\n    val folders: Map<String, List<AppEntry>>,\n    val hidden: List<AppEntry>,\n    /** Home order with optional empty slots retained in the first row. */\n    val homeSlots: List<AppEntry> = home,\n)',
     "Arrangement homeSlots field"),
    ('    fun arrange(all: List<AppEntry>, folderTile: (Folder, List<AppEntry>) -> AppEntry): Arrangement {',
     '    fun arrange(\n        all: List<AppEntry>,\n        preserveHiddenSlots: Int = 0,\n        folderTile: (Folder, List<AppEntry>) -> AppEntry,\n    ): Arrangement {',
     "arrange signature"),
    ('        val home = order.mapNotNull { key ->\n            val folder = folderOf(key)\n            if (folder != null) contents[folder.id]?.takeIf { it.isNotEmpty() }?.let { folderTile(folder, it) }\n            else byKey[key]?.takeIf { key !in hidden }\n        }\n        val inAnyOrder = order + folders.values.flatMap { it.apps }\n        return Arrangement(home, contents, inAnyOrder.mapNotNull(byKey::get).filter { it.key in hidden })',
     '        val home = mutableListOf<AppEntry>()\n        val homeSlots = mutableListOf<AppEntry>()\n        for (key in order) {\n            if (key.startsWith(FIRST_ROW_GAP_PREFIX)) {\n                if (homeSlots.size < preserveHiddenSlots) {\n                    val originalKey = key.removePrefix(FIRST_ROW_GAP_PREFIX)\n                    val movedApp = byKey[originalKey] ?: folderOf(originalKey)?.let { folder ->\n                        contents[folder.id]?.takeIf { it.isNotEmpty() }?.let { folderTile(folder, it) }\n                    }\n                    movedApp?.let { app ->\n                        homeSlots += app.copy(\n                            packageName = "hidden-slot:${homeSlots.size}",\n                            label = "",\n                            emptySlot = true,\n                        )\n                    }\n                }\n                continue\n            }\n            val folder = folderOf(key)\n            val tile = if (folder != null) {\n                contents[folder.id]?.takeIf { it.isNotEmpty() }?.let { folderTile(folder, it) }\n            } else {\n                byKey[key]?.takeIf { key !in hidden }\n            }\n            if (tile != null) {\n                home += tile\n                homeSlots += tile\n            } else if (homeSlots.size < preserveHiddenSlots && key in hidden) {\n                // Keep only hidden apps that originally occupied a first-row position. Later\n                // rows continue to compact normally; the blank tile has no focus or click target.\n                byKey[key]?.let { hiddenApp ->\n                    homeSlots += hiddenApp.copy(\n                        packageName = "hidden-slot:${homeSlots.size}",\n                        label = "",\n                        emptySlot = true,\n                    )\n                }\n            }\n        }\n        val inAnyOrder = order + folders.values.flatMap { it.apps }\n        return Arrangement(home, contents, inAnyOrder.mapNotNull(byKey::get).filter { it.key in hidden }, homeSlots)',
     "arrangement home loop"),
])

edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('        val arrangement = store.arrange(named + pinned) { folder, inside ->',
     '        val arrangement = store.arrange(\n            named + pinned,\n            preserveHiddenSlots = if (AerialSettings.noFillFirstRow) AerialSettings.homeColumns else 0,\n        ) { folder, inside ->',
     "arrange call"),
    ('            else -> AerialSettings.previewApps.takeIf { it > 0 }?.let { arrangement.home.take(it) } ?: arrangement.home',
     '            else -> AerialSettings.previewApps.takeIf { it > 0 }?.let { arrangement.homeSlots.take(it) } ?: arrangement.homeSlots',
     "Home apps source"),
])

edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ('    var peekNextRow by mutableStateOf(true); private set',
     '    var peekNextRow by mutableStateOf(true); private set\n\n    /** Keep hidden apps in the first row as empty slots instead of pulling later apps forward. */\n    var noFillFirstRow by mutableStateOf(false); private set',
     "noFillFirstRow property"),
    ('        peekNextRow = prefs.getBoolean("peek_next_row", true)',
     '        peekNextRow = prefs.getBoolean("peek_next_row", true)\n        noFillFirstRow = prefs.getBoolean("no_fill_first_row", prefs.getBoolean("hidden_slots", false))',
     "noFillFirstRow preference load"),
    ('    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("peek_next_row", on) }\n    }',
     '    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("peek_next_row", on) }\n    }\n\n    fun chooseNoFillFirstRow(on: Boolean) {\n        noFillFirstRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("no_fill_first_row", on) }\n    }',
     "noFillFirstRow setter"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('                    if (AerialSettings.oneRowHome) Choices(\n                        R.string.st_peek, stringResource(R.string.st_peek_hint), note,\n                        listOf(true to R.string.st_peek_show, false to R.string.st_peek_hide),\n                        AerialSettings.peekNextRow, AerialSettings::choosePeekNextRow,\n                    )',
     '                    if (AerialSettings.oneRowHome) Choices(\n                        R.string.st_peek, stringResource(R.string.st_peek_hint), note,\n                        listOf(true to R.string.st_peek_show, false to R.string.st_peek_hide),\n                        AerialSettings.peekNextRow, AerialSettings::choosePeekNextRow,\n                    )\n                    Choices(\n                        R.string.st_hidden_slots, stringResource(R.string.st_hidden_slots_hint), note,\n                        listOf(false to R.string.st_off, true to R.string.st_on),\n                        AerialSettings.noFillFirstRow, AerialSettings::chooseNoFillFirstRow,\n                    )',
     "hidden slots setting row"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="st_peek">Second Row</string>',
     '    <string name="st_hidden_slots">Do Not Fill First-Row Gaps</string>\n    <string name="st_hidden_slots_hint">When an app in the first row is hidden or moved out, leave its original position empty instead of pulling later apps forward.</string>\n    <string name="st_peek">Second Row</string>',
     "default setting strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="st_peek">第二排</string>',
     '    <string name="st_hidden_slots">移出不补位</string>\n    <string name="st_hidden_slots_hint">隐藏第一排 App 或将其移出第一排后，原位置留空，后面的 App 不会顶上来。</string>\n    <string name="st_peek">第二排</string>',
     "Chinese setting strings"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    ('    val reduced = LocalReducedMotion.current',
     '    if (app.emptySlot) {\n        Spacer(modifier.requiredSize(width, height))\n        return\n    }\n\n    val reduced = LocalReducedMotion.current',
     "empty slot rendering"),
])
edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('        viewModelScope.launch { snapshotFlow { AerialSettings.previewApps }.drop(1).collect { if (loaded) arrange() } }',
     '        viewModelScope.launch { snapshotFlow { AerialSettings.previewApps }.drop(1).collect { if (loaded) arrange() } }\n        viewModelScope.launch { snapshotFlow { AerialSettings.noFillFirstRow }.drop(1).collect { if (loaded) arrange() } }',
     "hidden slots live refresh"),
])


# One-tap placement below the first row, plus a saved opacity control for its glass plate.
edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('    private fun arrange() {',
     '    /** Puts a first-row app or folder at the start of the second row in one step. */\n    fun moveOutOfFirstRow(key: String) {\n        val from = apps.indexOfFirst { it.key == key }\n        val columns = AerialSettings.homeColumns\n        if (from !in 0 until columns || apps.size <= columns) return\n        store.moveOutOfFirstRow(key, apps[columns].key)\n        arrange()\n    }\n\n    private fun arrange() {',
     "move out of first row"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('            onMove = { vm.startMove(it) },',
     '            onMove = { vm.startMove(it) },\n            canMoveOutOfFirstRow = menu?.let { m ->\n                vm.apps.indexOfFirst { it.key == m.key } in 0 until columns && vm.apps.size > columns\n            } == true,\n            onMoveOutOfFirstRow = { key ->\n                val index = vm.apps.indexOfFirst { it.key == key }\n                val neighbor = if (index % columns == columns - 1) index - 1 else index + 1\n                focusAfterOverlay = vm.apps.getOrNull(neighbor)?.key ?: vm.apps.getOrNull(index - 1)?.key\n                closeMenu()\n                vm.moveOutOfFirstRow(key)\n            },',
     "one-tap second-row menu callbacks"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/Overlays.kt", [
    ('    onMove: (String) -> Unit,\n    onHide: (String) -> Unit,',
     '    onMove: (String) -> Unit,\n    canMoveOutOfFirstRow: Boolean,\n    onMoveOutOfFirstRow: (String) -> Unit,\n    onHide: (String) -> Unit,',
     "AppMenu move-out parameters"),
    ('                            MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            MenuRow(Glyph.Pencil,',
     '                            MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            if (canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })\n                            MenuRow(Glyph.Pencil,',
     "folder move-out action"),
    ('                                MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            }\n                            MenuRow(Glyph.Folder,',
     '                                MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            }\n                            if (!inFolder && canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })\n                            MenuRow(Glyph.Folder,',
     "app move-out action"),
])

edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ('    var homePlate by mutableStateOf(true); private set',
     '    var homePlate by mutableStateOf(true); private set\n\n    /** Opacity of the first-row glass plate, in percent. */\n    var homePlateOpacity by mutableIntStateOf(100); private set',
     "home plate opacity state"),
    ('        homePlate = prefs.getBoolean("home_plate", true)',
     '        homePlate = prefs.getBoolean("home_plate", true)\n        homePlateOpacity = prefs.getInt("home_plate_opacity", 100).coerceIn(0, 100)',
     "home plate opacity load"),
    ('    fun chooseHomePlate(on: Boolean) {\n        homePlate = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("home_plate", on) }\n    }',
     '    fun chooseHomePlate(on: Boolean) {\n        homePlate = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean("home_plate", on) }\n    }\n\n    /** Live preview while adjusting; persistence is deliberately deferred until Back. */\n    fun previewHomePlateOpacity(value: Int) {\n        homePlateOpacity = value.coerceIn(0, 100)\n    }\n\n    fun chooseHomePlateOpacity(value: Int) {\n        previewHomePlateOpacity(value)\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putInt("home_plate_opacity", homePlateOpacity) }\n    }',
     "home plate opacity setters"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeChrome.kt", [
    ('private fun Plate(glass: ImageBitmap?, film: ImageBitmap?, filmPlate: Boolean, deepSmoke: Boolean, plate: Rect?, scroll: () -> Float, collapse: Float, cover: () -> Float, filmStopped: () -> Float, toSaver: () -> Float, lift: () -> Float, stillOverFilm: Boolean = false) {',
     'private fun Plate(glass: ImageBitmap?, film: ImageBitmap?, filmPlate: Boolean, deepSmoke: Boolean, plate: Rect?, scroll: () -> Float, collapse: Float, cover: () -> Float, filmStopped: () -> Float, toSaver: () -> Float, lift: () -> Float, stillOverFilm: Boolean = false) {\n    val plateOpacity = AerialSettings.homePlateOpacity / 100f',
     "plate opacity draw input"),
    ('        return rest * (if (stillOverFilm) 1f else 1f - cover() * (1f - filmStopped())) * (1f - toSaver())',
     '        return rest * plateOpacity * (if (stillOverFilm) 1f else 1f - cover() * (1f - filmStopped())) * (1f - toSaver())',
     "plate opacity visibility"),
    ('        val base = (1f - smooth(((scroll() / collapse).coerceIn(0f, 1f) / 0.55f).coerceIn(0f, 1f))) * (1f - toSaver())',
     '        val base = (1f - smooth(((scroll() / collapse).coerceIn(0f, 1f) / 0.55f).coerceIn(0f, 1f))) * plateOpacity * (1f - toSaver())',
     "plate opacity film base"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('import androidx.compose.ui.focus.onFocusChanged\n',
     'import androidx.compose.ui.focus.onFocusChanged\nimport androidx.compose.foundation.focusable\nimport androidx.compose.ui.input.key.Key\nimport androidx.compose.ui.input.key.KeyEventType\nimport androidx.compose.ui.input.key.onPreviewKeyEvent\nimport androidx.compose.ui.input.key.key\nimport androidx.compose.ui.input.key.type\n',
     "opacity key handling imports"),
    ('                        AerialSettings.homePlate, AerialSettings::chooseHomePlate,\n                    )',
     '                        AerialSettings.homePlate, AerialSettings::chooseHomePlate,\n                    )\n                    HomePlateOpacity(note)',
     "plate opacity setting row"),
    ('/** Parental PIN on or off; either way goes through the PIN pad (issue #10). */',
     '@Composable\nprivate fun HomePlateOpacity(note: (String?) -> Unit) {\n    var value by remember { mutableStateOf(AerialSettings.homePlateOpacity) }\n    var editing by remember { mutableStateOf(false) }\n    var focused by remember { mutableStateOf(false) }\n    BackHandler(enabled = editing) {\n        AerialSettings.chooseHomePlateOpacity(value)\n        editing = false\n    }\n    SettingRow(R.string.st_plate_opacity, stringResource(R.string.st_plate_opacity_hint), note) {\n        Row(\n            Modifier\n                .onFocusChanged { state ->\n                    focused = state.isFocused\n                    if (state.isFocused) value = AerialSettings.homePlateOpacity\n                }\n                .focusable()\n                .onPreviewKeyEvent { event ->\n                    if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false\n                    val next = when (event.key) {\n                        Key.DirectionLeft -> (value - 5).coerceAtLeast(0)\n                        Key.DirectionRight -> (value + 5).coerceAtMost(100)\n                        else -> return@onPreviewKeyEvent false\n                    }\n                    value = next\n                    editing = true\n                    AerialSettings.previewHomePlateOpacity(next)\n                    true\n                },\n            verticalAlignment = Alignment.CenterVertically,\n        ) {\n            BasicText("$value%", style = Type.Body, modifier = Modifier.padding(horizontal = 14.dp))\n            BasicText("‹  ›", style = Type.Caption, modifier = Modifier.padding(end = 10.dp))\n        }\n    }\n}\n\n/** Parental PIN on or off; either way goes through the PIN pad (issue #10). */',
     "plate opacity directional control"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="menu_move">Move</string>',
     '    <string name="menu_move">Move</string>\n    <string name="menu_move_out_first_row">Move out of first row</string>',
     "English move-out menu label"),
    ('    <string name="st_plate">Top Row</string>',
     '    <string name="st_plate">Top Row</string>\n    <string name="st_plate_opacity">First-row plate opacity</string>\n    <string name="st_plate_opacity_hint">Left/right adjusts the glass opacity in 5% steps. Press Back to save.</string>',
     "English plate opacity setting strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="menu_move">移动</string>',
     '    <string name="menu_move">移动</string>\n    <string name="menu_move_out_first_row">移出第一行</string>',
     "Chinese move-out menu label"),
    ('    <string name="st_plate">第一排底板</string>',
     '    <string name="st_plate">第一排底板</string>\n    <string name="st_plate_opacity">第一排底板透明度</string>\n    <string name="st_plate_opacity_hint">按左右方向键以 5% 为步进调整透明度，按返回键保存。</string>',
     "Chinese plate opacity setting strings"),
])

print("[mod] all patches applied")


# Back from a lower row returns focus to the first tile on the Home desktop.
edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ("""    BackHandler(enabled = overlay == Overlay.None && moving == null) {
        // tvOS: Back from inside the grid returns to the top row; Back on the top row starts the
        // screensaver. A grid scrolled by touch counts as being inside it.
        val scrolled = dragged && scroll.value > 1f
        dragged = false
        // Handled even when that is turned off: unhandled, Back would close Home itself.
        if (focusedRow > 0 || scrolled) focusApp(focusedIndex.coerceAtLeast(0) % columns)
        else if (AerialSettings.backStartsScreensaver) onStartScreensaver()
    }""",
     """    BackHandler(enabled = overlay == Overlay.None && moving == null) {
        // Back from any lower row returns to the Home desktop's first tile,
        // matching the Home key's reset destination without leaving the launcher.
        val scrolled = dragged && scroll.value > 1f
        dragged = false
        if (focusedRow > 0 || scrolled) focusApp(0)
        else if (AerialSettings.backStartsScreensaver) onStartScreensaver()
    }""",
     "back behaves like Home from lower rows"),
])


# Expose a manual update check in the Settings sheet; automatic checks remain unchanged.
edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('import app.orchard.tv.settings.AerialSettings\n',
     'import app.orchard.tv.settings.AerialSettings\nimport app.orchard.tv.update.Updates\n',
     "manual update check import"),
    ("""                        AerialSettings.effects, AerialSettings::chooseEffects,
                    )
                }

                Spacer(Modifier.height(22.dp))""",
     """                        AerialSettings.effects, AerialSettings::chooseEffects,
                    )
                    SettingRow(R.string.st_check_updates, stringResource(R.string.st_check_updates_hint), note) {
                        ActionChip(stringResource(R.string.st_check_updates_action), Glyph.ChevronRight) {
                            Updates.checkIfStale(force = true)
                        }
                    }
                }

                Spacer(Modifier.height(22.dp))""",
     "manual update check setting"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="st_effects_hint">Lite draws plain panels and the selected app without its sheen, and keeps the screen at 60 Hz: for TVs that stutter.</string>',
     '    <string name="st_effects_hint">Lite draws plain panels and the selected app without its sheen, and keeps the screen at 60 Hz: for TVs that stutter.</string>\n    <string name="st_check_updates">Updates</string>\n    <string name="st_check_updates_action">Check for Updates</string>\n    <string name="st_check_updates_hint">Check now for a newer Aerial version instead of waiting for the automatic check.</string>',
     "English manual update check strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="st_effects_hint">流畅：面板用纯色，选中的 App 不加高光和视差，屏幕保持 60Hz，给会卡顿的电视用。</string>',
     '    <string name="st_effects_hint">流畅：面板用纯色，选中的 App 不加高光和视差，屏幕保持 60Hz，给会卡顿的电视用。</string>\n    <string name="st_check_updates">软件更新</string>\n    <string name="st_check_updates_action">检查更新</string>\n    <string name="st_check_updates_hint">立即检查是否有新版 Aerial，不必等待自动检测。</string>',
     "Chinese manual update check strings"),
])


# Automatic update checks can be disabled without changing the updater's cadence,
# retry policy, or the explicit Check for Updates action.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    var install by mutableStateOf<Install>(Install.Idle); private set',
     '    var install by mutableStateOf<Install>(Install.Idle); private set\n\n    /** Automatic background checks are enabled by default; manual checks always remain available. */\n    var automaticChecksEnabled by mutableStateOf(true); private set',
     "automatic update check state"),
    ('        prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)',
     '        prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)\n        automaticChecksEnabled = prefs.getBoolean("automatic_checks", true)',
     "automatic update check preference load"),
    ('            log = { Log.i(TAG, it); DiagLog.i("update check: $it") },',
     '            log = { Log.i(TAG, it); DiagLog.i("update check: $it") },\n            enabled = { automaticChecksEnabled },',
     "automatic update check gate"),
    ('        networkCameUp: Boolean = false,\n    ) {\n        checker?.check(force, maxAgeMs, networkCameUp, when {',
     '        networkCameUp: Boolean = false,\n        manual: Boolean = false,\n    ) {\n        checker?.check(force || manual, maxAgeMs, networkCameUp, when {',
     "manual update check bypass"),
    ('        checker?.check(force || manual, maxAgeMs, networkCameUp, when {\n            force -> "forced"\n            networkCameUp -> "network"\n            maxAgeMs == CONTROL_CENTER_MAX_AGE_MS -> "control center"\n            else -> "home"\n        })',
     '        checker?.check(force || manual, maxAgeMs, networkCameUp, when {\n            manual -> "manual"\n            force -> "forced"\n            networkCameUp -> "network"\n            maxAgeMs == CONTROL_CENTER_MAX_AGE_MS -> "control center"\n            else -> "home"\n        })',
     "manual update check source"),
    ('    fun diagnostics(): String = if (!started) "not initialized" else',
     '    fun chooseAutomaticChecks(enabled: Boolean) {\n        automaticChecksEnabled = enabled\n        if (started) prefs.edit { putBoolean("automatic_checks", enabled) }\n        if (enabled) checkIfStale()\n    }\n\n    fun diagnostics(): String = if (!started) "not initialized" else',
     "automatic update check setter"),
])

edit("app/src/main/java/app/orchard/tv/update/UpdateCheck.kt", [
    ('    private val log: (String) -> Unit,',
     '    private val log: (String) -> Unit,\n    private val enabled: () -> Boolean = { true },',
     "automatic update check predicate"),
    ('    ) {\n        if (checking) {',
     '    ) {\n        if (!enabled() && source != "manual") {\n            record("$source skipped: automatic checks disabled")\n            return\n        }\n        if (checking) {',
     "automatic update check suppression"),
    ('        val due = retryAt ?: return\n        if (active && !checking)',
     '        if (!enabled()) return\n        val due = retryAt ?: return\n        if (active && !checking)',
     "disable automatic retry scheduling"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('                    SettingRow(R.string.st_check_updates, stringResource(R.string.st_check_updates_hint), note) {',
     '                    Choices(\n                        R.string.st_auto_updates, stringResource(R.string.st_auto_updates_hint), note,\n                        listOf(true to R.string.st_on, false to R.string.st_off),\n                        Updates.automaticChecksEnabled, Updates::chooseAutomaticChecks,\n                    )\n                    SettingRow(R.string.st_check_updates, stringResource(R.string.st_check_updates_hint), note) {',
     "automatic update check setting row"),
    ('                            Updates.checkIfStale(force = true)',
     '                            Updates.checkIfStale(force = true, manual = true)',
     "manual check bypasses automatic setting"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="st_check_updates">Updates</string>',
     '    <string name="st_auto_updates">Automatic update checks</string>\n    <string name="st_auto_updates_hint">Check for updates automatically using Aerial’s normal Home, network and retry schedule. Manual checks remain available when this is off.</string>\n    <string name="st_check_updates">Updates</string>',
     "English automatic update setting strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="st_check_updates">软件更新</string>',
     '    <string name="st_auto_updates">自动检测更新</string>\n    <string name="st_auto_updates_hint">沿用 Aerial 原有的主页、网络恢复和失败重试检测机制。关闭后仍可手动检查更新。</string>\n    <string name="st_check_updates">软件更新</string>',
     "Chinese automatic update setting strings"),
])


# A one-tap move leaves a durable first-row gap when the setting is enabled.
edit("app/src/main/java/app/orchard/tv/apps/LayoutStore.kt", [
    ('        val list = order.toMutableList()\n        val from = list.indexOf(key)\n        val to = list.indexOf(target)',
     '        val list = order.toMutableList()\n        list.remove(FIRST_ROW_GAP_PREFIX + key)\n        val from = list.indexOf(key)\n        val to = list.indexOf(target)',
     "manual move clears old first-row gap"),
    ('    private fun save() = prefs.edit {',
     '    /** Moves an app below the first row while retaining its old slot as a non-interactive gap. */\n    fun moveOutOfFirstRow(key: String, target: String) {\n        if (key == target) return\n        val list = order.toMutableList()\n        val from = list.indexOf(key)\n        val to = list.indexOf(target)\n        if (from < 0 || to < 0 || from >= to) return\n        list[from] = FIRST_ROW_GAP_PREFIX + key\n        val targetIndex = list.indexOf(target)\n        list.add(targetIndex + 1, key)\n        order = list\n        save()\n    }\n\n    private fun save() = prefs.edit {',
     "move out with reserved first-row slot"),
])

print("[mod] all patches applied")


# Give the manual update action visible progress and a useful final result.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    var automaticChecksEnabled by mutableStateOf(true); private set',
     '    var automaticChecksEnabled by mutableStateOf(true); private set\n\n    enum class ManualCheckStatus { Idle, Checking, UpToDate, UpdateAvailable, Failed }\n    var manualCheckStatus by mutableStateOf(ManualCheckStatus.Idle); private set',
     "manual update check status state"),
    ('            enabled = { automaticChecksEnabled },',
     '            enabled = { automaticChecksEnabled },\n            manualResult = { success ->\n                manualCheckStatus = if (!success) ManualCheckStatus.Failed\n                else if (available != null) ManualCheckStatus.UpdateAvailable\n                else ManualCheckStatus.UpToDate\n            },',
     "manual update check result callback"),
    ('        checker?.check(force || manual, maxAgeMs, networkCameUp, when {',
     '        if (manual) manualCheckStatus = ManualCheckStatus.Checking\n        if (checker == null) {\n            if (manual) manualCheckStatus = ManualCheckStatus.Failed\n            return\n        }\n        checker?.check(force || manual, maxAgeMs, networkCameUp, when {',
     "manual update check visible progress"),
])

edit("app/src/main/java/app/orchard/tv/update/UpdateCheck.kt", [
    ('    private val enabled: () -> Boolean = { true },',
     '    private val enabled: () -> Boolean = { true },\n    private val manualResult: (Boolean) -> Unit = {},',
     "manual update result callback"),
    ('                result = "success version=$latest"',
     '                result = "success version=$latest"\n                if (source == "manual") manualResult(true)',
     "manual update success callback"),
    ('                else "failed ${e.javaClass.simpleName}" + (e.cause?.let { "/${it.javaClass.simpleName}" } ?: "")',
     '                else "failed ${e.javaClass.simpleName}" + (e.cause?.let { "/${it.javaClass.simpleName}" } ?: "")\n                if (source == "manual") manualResult(false)',
     "manual update failure callback"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ("""                        ActionChip(stringResource(R.string.st_check_updates_action), Glyph.ChevronRight) {
                            Updates.checkIfStale(force = true, manual = true)
                        }""",
     """                        val checkLabel = when (Updates.manualCheckStatus) {
                            Updates.ManualCheckStatus.Idle -> R.string.st_check_updates_action
                            Updates.ManualCheckStatus.Checking -> R.string.st_check_updates_checking
                            Updates.ManualCheckStatus.UpToDate -> R.string.st_check_updates_latest
                            Updates.ManualCheckStatus.UpdateAvailable -> R.string.st_check_updates_available
                            Updates.ManualCheckStatus.Failed -> R.string.st_check_updates_failed
                        }
                        ActionChip(stringResource(checkLabel), Glyph.ChevronRight) {
                            Updates.checkIfStale(force = true, manual = true)
                        }""",
     "manual update check result label"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="st_check_updates_action">Check for Updates</string>',
     '    <string name="st_check_updates_action">Check for Updates</string>\n    <string name="st_check_updates_checking">Checking…</string>\n    <string name="st_check_updates_latest">Already up to date</string>\n    <string name="st_check_updates_available">Update available</string>\n    <string name="st_check_updates_failed">Check failed · Try again</string>',
     "English manual update status strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="st_check_updates_action">检查更新</string>',
     '    <string name="st_check_updates_action">检查更新</string>\n    <string name="st_check_updates_checking">正在检查…</string>\n    <string name="st_check_updates_latest">已经是最新版本</string>\n    <string name="st_check_updates_available">发现新版本</string>\n    <string name="st_check_updates_failed">检查失败，点击重试</string>',
     "Chinese manual update status strings"),
])


# Use this fork's own monotonically increasing release version for every CI build.
edit("app/build.gradle.kts", [
    ('        versionCode = 116',
     '        versionCode = providers.gradleProperty("aerialVersionCode").orNull?.toInt() ?: 116',
     "fork release version code"),
    ('        versionName = "1.85"',
     '        versionName = providers.gradleProperty("aerialVersionName").orNull ?: "1.85"',
     "fork release version name"),
])

# All in-app update metadata and APKs must come from klcb2010/aerial-tv, never upstream.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    private const val VERSION_URL = "https://aerial.qust.me/download/version.txt"',
     '    private const val VERSION_URL = "https://raw.githubusercontent.com/klcb2010/aerial-tv/main/version.txt"',
     "fork update version endpoint"),
    ('    private const val NOTES_URL = "https://aerial.qust.me/download/notes.json"',
     '    private const val NOTES_URL = "https://raw.githubusercontent.com/klcb2010/aerial-tv/main/release-notes.json"',
     "fork release notes endpoint"),
    ('        val sources = listOf(\n            "https://aerial.qust.me/download/$name",\n            "https://github.com/pengchujin/aerial-tv/releases/latest/download/$name",\n        )',
     '        val sources = listOf(\n            "https://github.com/klcb2010/aerial-tv/releases/latest/download/$name",\n        )',
     "fork-only APK download source"),
])
