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


# One-tap placement below the first row, plus a saved opacity control for its glass plate.
edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('    fun hide(key: String) {\n        store.hide(key)\n        arrange()\n    }',
     '    fun hide(key: String) {\n        store.hide(key)\n        arrange()\n    }\n\n    /** Puts a first-row app or folder at the start of the second row in one step. */\n    fun moveOutOfFirstRow(key: String) {\n        val from = apps.indexOfFirst { it.key == key }\n        val columns = AerialSettings.homeColumns\n        if (from !in 0 until columns || apps.size <= columns) return\n        store.move(key, apps[columns].key)\n        arrange()\n    }',
     "move out of first row"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('            onMove = { vm.startMove(it) },',
     '            onMove = { vm.startMove(it) },\n            canMoveOutOfFirstRow = menu?.let { m ->\n                vm.apps.indexOfFirst { it.key == m.key } in 0 until columns && vm.apps.size > columns\n            } == true,\n            onMoveOutOfFirstRow = { key ->\n                closeMenu()\n                vm.moveOutOfFirstRow(key)\n            },',
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
    ('    <string name="st_plate">First-row plate</string>',
     '    <string name="st_plate">First-row plate</string>\n    <string name="st_plate_opacity">First-row plate opacity</string>\n    <string name="st_plate_opacity_hint">Left/right adjusts the glass opacity in 5% steps. Press Back to save.</string>',
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
