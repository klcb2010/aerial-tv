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
        if new and new in text:
            continue
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"[mod] {path}: expected one {label} anchor, found {count}")
        text = text.replace(old, new, 1)
    file.write_text(text, encoding="utf-8")
    print(f"[mod] patched {path}")


def ensure_import(path, anchor, import_line, label):
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if import_line in text:
        print(f"[mod] import already present: {path}")
        return
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(f"[mod] {path}: expected one {label} anchor, found {count}")
    file.write_text(text.replace(anchor, anchor + import_line, 1), encoding="utf-8")
    print(f"[mod] added import: {path}")


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

edit("app/src/main/java/app/orchard/tv/apps/LayoutStore.kt", [
    ('    fun folders(): List<Folder> = order.mapNotNull(::folderOf)',
     '    /** Moves a first-row tile to the start of row two while preserving its old slot. */\n    fun moveOutOfFirstRow(key: String, target: String) {\n        if (key == target) return\n        val list = order.toMutableList()\n        val from = list.indexOf(key)\n        if (from < 0 || list.indexOf(target) < 0) return\n        list.removeAt(from)\n        list.add(from.coerceAtMost(list.size), FIRST_ROW_GAP_PREFIX + key)\n        val targetIndex = list.indexOf(target)\n        if (targetIndex < 0) return\n        list.add(targetIndex, key)\n        order = list\n        save()\n    }\n\n    fun folders(): List<Folder> = order.mapNotNull(::folderOf)',
     "move first-row tile into second row"),
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
    ('            onMove = { vm.startMove(it, menu?.inFolder) },',
     '            onMove = { vm.startMove(it, menu?.inFolder) },\n            canMoveOutOfFirstRow = menu?.let { m ->\n                vm.apps.indexOfFirst { it.key == m.key } in 0 until columns && vm.apps.size > columns\n            } == true,\n            onMoveOutOfFirstRow = { key ->\n                val index = vm.apps.indexOfFirst { it.key == key }\n                val neighbor = if (index % columns == columns - 1) index - 1 else index + 1\n                focusAfterOverlay = vm.apps.getOrNull(neighbor)?.key ?: vm.apps.getOrNull(index - 1)?.key\n                closeMenu()\n                vm.moveOutOfFirstRow(key)\n            },',
     "one-tap second-row menu callbacks"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/Overlays.kt", [
    ('    onMove: (String) -> Unit,\n    onHide: (String) -> Unit,',
     '    onMove: (String) -> Unit,\n    canMoveOutOfFirstRow: Boolean,\n    onMoveOutOfFirstRow: (String) -> Unit,\n    onHide: (String) -> Unit,',
     "AppMenu move-out parameters"),
    ('                            MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            MenuRow(Glyph.Pencil,',
     '                            MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            if (canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })\n                            MenuRow(Glyph.Pencil,',
     "folder move-out action"),
    ('                            MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            if (inFolder) MenuRow(Glyph.Folder, stringResource(R.string.menu_out_of_folder), { onOutOfFolder(shownApp.key) })',
     '                            MenuRow(Glyph.Move, stringResource(R.string.menu_move), { onMove(shownApp.key) }, focusRequester = first)\n                            if (!inFolder && canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })\n                            if (inFolder) MenuRow(Glyph.Folder, stringResource(R.string.menu_out_of_folder), { onOutOfFolder(shownApp.key) })',
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
     '@Composable\nprivate fun HomePlateOpacity(note: (String?) -> Unit) {\n    var value by remember { mutableStateOf(AerialSettings.homePlateOpacity) }\n    var editing by remember { mutableStateOf(false) }\n    BackHandler(enabled = editing) {\n        AerialSettings.chooseHomePlateOpacity(value)\n        editing = false\n    }\n    SettingRow(R.string.st_plate_opacity, stringResource(R.string.st_plate_opacity_hint), note) {\n        Box(\n            Modifier.onPreviewKeyEvent { event ->\n                if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false\n                val next = when (event.key) {\n                    Key.DirectionLeft -> (value - 5).coerceAtLeast(0)\n                    Key.DirectionRight -> (value + 5).coerceAtMost(100)\n                    else -> return@onPreviewKeyEvent false\n                }\n                value = next\n                editing = true\n                AerialSettings.previewHomePlateOpacity(next)\n                true\n            },\n        ) {\n            Chip("$value%", on = false) {}\n        }\n    }\n}\n\n/** Parental PIN on or off; either way goes through the PIN pad (issue #10). */',
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


# Empty first-row slots remain real D-pad focus targets. This keeps the grid,
# status pill and Back navigation reachable even when every top-row app is hidden.
edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    ('    if (app.emptySlot) {\n        Spacer(modifier.requiredSize(width, height))\n        return\n    }',
     '    if (app.emptySlot) {\n        var emptyFocused by remember { mutableStateOf(false) }\n        Canvas(\n            modifier.requiredSize(width, height)\n                .focusRequester(focusRequester)\n                .onFocusChanged {\n                    emptyFocused = it.isFocused\n                    if (it.isFocused) onFocused()\n                }\n                .focusProperties { if (rowEnd) right = FocusRequester.Cancel }\n                .focusable(enabled),\n        ) {\n            if (emptyFocused) drawRoundRect(\n                color = Color(0xFFADD8FF),\n                cornerRadius = androidx.compose.ui.geometry.CornerRadius(12.dp.toPx()),\n                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3.dp.toPx()),\n            )\n        }\n        return\n    }',
     "focusable empty first-row slot"),
])

# The first-row gaps can be filled directly from any lower-row app's context menu.
edit("app/src/main/java/app/orchard/tv/apps/LayoutStore.kt", [
    ('    fun move(key: String, target: String) {',
     '    /** Moves a tile to the first available first-row gap, or inserts it at the row end. */\n    fun moveToFirstRow(key: String, columns: Int, preserveGaps: Boolean) {\n        if (columns <= 0) return\n        val list = order.toMutableList()\n        val from = list.indexOf(key)\n        if (from < 0 || from < columns) return\n        list.removeAt(from)\n        val gap = if (preserveGaps) list.indices.firstOrNull {\n            it < columns && (list[it].startsWith(FIRST_ROW_GAP_PREFIX) || list[it] in hidden)\n        } else null\n        if (gap != null) {\n            val oldSlot = list[gap]\n            val hiddenKey = oldSlot.removePrefix(FIRST_ROW_GAP_PREFIX)\n            list[gap] = key\n            if (hiddenKey != key && hiddenKey !in list) list.add(hiddenKey)\n        } else list.add((columns - 1).coerceAtMost(list.size), key)\n        order = list\n        save()\n    }\n\n    fun move(key: String, target: String) {',
     "first-row move methods"),
])

edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    ('    private fun arrange() {',
     '    /** Places a lower-row tile in the first row, filling the leftmost saved gap first. */\n    fun moveToFirstRow(key: String) {\n        store.moveToFirstRow(key, AerialSettings.homeColumns, AerialSettings.noFillFirstRow)\n        arrange()\n    }\n\n    private fun arrange() {',
     "move to first row view model"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/Overlays.kt", [
    ('    canMoveOutOfFirstRow: Boolean,\n    onMoveOutOfFirstRow: (String) -> Unit,',
     '    canMoveOutOfFirstRow: Boolean,\n    onMoveOutOfFirstRow: (String) -> Unit,\n    canMoveToFirstRow: Boolean,\n    onMoveToFirstRow: (String) -> Unit,',
     "AppMenu move-to-first-row parameters"),
    ('                            if (canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })',
     '                            if (canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })\n                            if (canMoveToFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_to_first_row), { onMoveToFirstRow(shownApp.key) })',
     "folder move-to-first-row action"),
    ('                            if (!inFolder && canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })',
     '                            if (!inFolder && canMoveOutOfFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_out_first_row), { onMoveOutOfFirstRow(shownApp.key) })\n                            if (!inFolder && canMoveToFirstRow) MenuRow(Glyph.Move, stringResource(R.string.menu_move_to_first_row), { onMoveToFirstRow(shownApp.key) })',
     "app move-to-first-row action"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('            canMoveOutOfFirstRow = menu?.let { m ->\n                vm.apps.indexOfFirst { it.key == m.key } in 0 until columns && vm.apps.size > columns\n            } == true,',
     '            canMoveOutOfFirstRow = menu?.let { m ->\n                vm.apps.indexOfFirst { it.key == m.key } in 0 until columns && vm.apps.size > columns\n            } == true,\n            canMoveToFirstRow = menu?.let { m ->\n                vm.apps.indexOfFirst { it.key == m.key } >= columns\n            } == true,\n            onMoveToFirstRow = { key ->\n                focusAfterOverlay = key\n                closeMenu()\n                vm.moveToFirstRow(key)\n            },',
     "first-row menu callback"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="menu_move_out_first_row">Move out of first row</string>',
     '    <string name="menu_move_out_first_row">Move out of first row</string>\n    <string name="menu_move_to_first_row">Move to first row</string>',
     "English move-to-first-row label"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="menu_move_out_first_row">移出第一行</string>',
     '    <string name="menu_move_out_first_row">移出第一行</string>\n    <string name="menu_move_to_first_row">移到第一行</string>',
     "Chinese move-to-first-row label"),
])

# Keep setting controls in a deterministic focus group; the opacity control is a
# single focus target inside its row and must participate in the TV D-pad sequence.
edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('import androidx.compose.ui.focus.onFocusChanged\n',
     'import androidx.compose.ui.focus.onFocusChanged\n',
     "settings focus group import"),
    ('            .padding(start = 18.dp, end = 10.dp)\n            .onFocusChanged { if (it.hasFocus) note(hint) },',
     '            .padding(start = 18.dp, end = 10.dp)\n            .onFocusChanged { if (it.hasFocus) note(hint) },',
     "settings row focus group"),
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
ensure_import(
    "app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt",
    "import app.orchard.tv.settings.AerialSettings\\n",
    "import app.orchard.tv.update.Updates\\n",
    "manual update check import",
)
edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
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
                            if (Updates.manualCheckStatus == Updates.ManualCheckStatus.UpdateAvailable) {
                                Updates.install(context)
                            } else {
                                Updates.checkIfStale(force = true, manual = true)
                            }
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
# Upstream may change its literal version values between releases. Match the assignments
# by their Kotlin DSL property names and retain the current upstream values as fallbacks.
def patch_release_versions():
    path = "app/build.gradle.kts"
    file = ROOT / path
    lines = file.read_text(encoding="utf-8").splitlines()

    def patch_assignment(property_name, gradle_property, is_string=False):
        matches = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            prefix = property_name + " = "
            if not stripped.startswith(prefix):
                continue
            current = stripped[len(prefix):]
            if gradle_property in current:
                matches.append((index, None))
                continue
            if is_string:
                if len(current) >= 2 and current.startswith('"') and current.endswith('"') and current.count('"') == 2:
                    matches.append((index, current[1:-1]))
            elif current.isdigit():
                matches.append((index, current))
        if len(matches) != 1:
            raise SystemExit(
                f"[mod] {path}: expected one {property_name} assignment, found {len(matches)}"
            )
        index, fallback = matches[0]
        if fallback is None:
            return
        indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
        if is_string:
            lines[index] = (
                f'{indent}{property_name} = '
                f'providers.gradleProperty("{gradle_property}").orNull ?: "{fallback}"'
            )
        else:
            lines[index] = (
                f'{indent}{property_name} = '
                f'providers.gradleProperty("{gradle_property}").orNull?.toInt() ?: {fallback}'
            )

    patch_assignment("versionCode", "aerialVersionCode")
    patch_assignment("versionName", "aerialVersionName", is_string=True)
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[mod] patched {path}")


patch_release_versions()

# All in-app update metadata and APKs must come from klcb2010/aerial-tv, never upstream.
# Update endpoints and APK sources are handled by the initial Updates.kt patch above.\n

# When automatic update checks find a newer release, show one dismissible prompt
# per release. Never download or install until the owner chooses Update Now.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    fun diagnostics(): String = if (!started) "not initialized" else',
     '    fun automaticPromptVersion(): String? {\n        if (!started || !automaticChecksEnabled) return null\n        val latest = available ?: return null\n        return latest.takeIf { prefs.getString("prompt_dismissed", null) != it }\n    }\n\n    fun dismissAutomaticPrompt(version: String) {\n        if (started) prefs.edit { putString("prompt_dismissed", version) }\n    }\n\n    fun diagnostics(): String = if (!started) "not initialized" else',
     "automatic update prompt persistence"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('import androidx.compose.foundation.layout.Box\n',
     'import androidx.compose.foundation.layout.Box\nimport androidx.compose.foundation.layout.Column\nimport androidx.compose.foundation.layout.Arrangement\nimport androidx.compose.foundation.layout.width\n',
     "update prompt layout imports"),
    ('import androidx.compose.ui.draw.drawWithContent\n',
     'import androidx.compose.ui.draw.drawWithContent\nimport androidx.compose.foundation.background\nimport androidx.compose.foundation.shape.RoundedCornerShape\nimport androidx.compose.ui.window.Dialog\n',
     "update prompt dialog imports"),
    ('import app.orchard.tv.ui.components.liquidGlass\n',
     'import app.orchard.tv.ui.components.liquidGlass\nimport app.orchard.tv.ui.components.Pressable\nimport app.orchard.tv.update.Updates\n',
     "update prompt components"),
    ('    val gridEnabled = overlay == Overlay.None && kidsLock == null',
     '    val gridEnabled = overlay == Overlay.None && kidsLock == null\n    var updatePrompt by remember { mutableStateOf<String?>(null) }\n    LaunchedEffect(Updates.available, Updates.automaticChecksEnabled, overlay, vm.loaded, kidsLock, vm.screensaverVisible) {\n        if (!Updates.automaticChecksEnabled) {\n            updatePrompt = null\n        } else if (overlay == Overlay.None && vm.loaded && kidsLock == null && !vm.screensaverVisible) {\n            updatePrompt = Updates.automaticPromptVersion()\n        }\n    }',
     "observe automatic update availability"),
    ('        Screensaver(visible = vm.screensaverVisible, apps = apps, now = now, skips = vm.screensaverSkips, carry = when {\n                filmSaver -> if (Wallpapers.isVideo()) SaverCarry.Video(homeVideo) else SaverCarry.Film(liveFilm)\n                stillCarry != null -> stillCarry\n                else -> null\n            },\n        )',
     '        Screensaver(visible = vm.screensaverVisible, apps = apps, now = now, skips = vm.screensaverSkips, carry = when {\n                filmSaver -> SaverCarry.Film(liveFilm)\n                stillCarry != null -> stillCarry\n                else -> null\n            },\n        )\n\n        updatePrompt?.let { version ->\n            UpdateAvailableDialog(\n                version = version,\n                onLater = { Updates.dismissAutomaticPrompt(version); updatePrompt = null },\n                onUpdate = {\n                    Updates.dismissAutomaticPrompt(version)\n                    updatePrompt = null\n                    vm.overlay = Overlay.ControlCenter(CcPage.Update)\n                },\n            )\n        }',
     "show automatic update prompt"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('/** How long the screensaver waits for the wallpaper\'s film to move before playing its own. */',
     '@Composable\nprivate fun UpdateAvailableDialog(version: String, onLater: () -> Unit, onUpdate: () -> Unit) {\n    val updateFocus = remember { FocusRequester() }\n    LaunchedEffect(Unit) {\n        withFrameNanos { }\n        runCatching { updateFocus.requestFocus() }\n    }\n    Dialog(onDismissRequest = onLater) {\n        Column(\n            Modifier.width(500.dp)\n                .background(Color(0xF01B1B1B), RoundedCornerShape(24.dp))\n                .padding(32.dp),\n            verticalArrangement = Arrangement.spacedBy(18.dp),\n        ) {\n            BasicText(stringResource(R.string.update_prompt_title), style = Type.Title)\n            BasicText(stringResource(R.string.update_prompt_version, version), style = Type.Body)\n            BasicText(stringResource(R.string.update_prompt_message), style = Type.Caption)\n            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {\n                Pressable(onClick = onLater, modifier = Modifier.weight(1f)) { state ->\n                    Box(Modifier.fillMaxWidth().background(Color(0xFF454545), RoundedCornerShape(12.dp)).padding(vertical = 15.dp), contentAlignment = Alignment.Center) {\n                        BasicText(stringResource(R.string.update_prompt_later), style = Type.Body)\n                    }\n                }\n                Pressable(onClick = onUpdate, modifier = Modifier.weight(1f), focusRequester = updateFocus) { state ->\n                    Box(Modifier.fillMaxWidth().background(if (state.focused) Color.White else Color(0xFF777777), RoundedCornerShape(12.dp)).padding(vertical = 15.dp), contentAlignment = Alignment.Center) {\n                        BasicText(stringResource(R.string.update_prompt_now), style = Type.Body.copy(color = if (state.focused) Color.Black else Color.White))\n                    }\n                }\n            }\n        }\n    }\n}\n\n/** How long the screensaver waits for the wallpaper\'s film to move before playing its own. */',
     "automatic update dialog composable"),
])

edit("app/src/main/res/values/strings.xml", [
    ('    <string name="st_check_updates_available">Update available</string>',
     '    <string name="st_check_updates_available">Update available</string>\n    <string name="update_prompt_title">A new version is available</string>\n    <string name="update_prompt_version">Aerial %1$s is ready to install.</string>\n    <string name="update_prompt_message">Would you like to open the update page now?</string>\n    <string name="update_prompt_now">Update now</string>\n    <string name="update_prompt_later">Later</string>',
     "English automatic update prompt strings"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('    <string name="st_check_updates_available">发现新版本</string>',
     '    <string name="st_check_updates_available">发现新版本</string>\n    <string name="update_prompt_title">发现新版本</string>\n    <string name="update_prompt_version">Aerial %1$s 已经可以更新。</string>\n    <string name="update_prompt_message">现在打开更新页面吗？</string>\n    <string name="update_prompt_now">立即更新</string>\n    <string name="update_prompt_later">稍后</string>',
     "Chinese automatic update prompt strings"),
])


# Prefer the fork's lightweight version.txt endpoint; fall back to the Releases API.
# This avoids making manual checks depend on GitHub API rate limits or API reachability.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    private fun readLatestVersion(): String {\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }',
     '    private fun readLatestVersion(): String {\n        val version = runCatching {\n            read("https://raw.githubusercontent.com/klcb2010/aerial-tv/main/version.txt").trim()\n        }.getOrNull()?.takeIf { it.matches(Regex("\\\\d+(\\\\.\\\\d+)*")) }\n        if (version != null) return version\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }',
     "raw version file with releases API fallback"),
    ('        c.readTimeout = 10_000\n        return try {',
     '        c.readTimeout = 10_000\n        c.setRequestProperty("User-Agent", "Aerial-TV-klcb2010")\n        c.setRequestProperty("Accept", "application/vnd.github+json, text/plain, */*")\n        return try {\n            if (c.responseCode !in 200..299) throw java.io.IOException("HTTP ${c.responseCode}")',
     "version endpoint HTTP headers and status validation"),
])

edit("app/src/main/java/app/orchard/tv/update/UpdateCheck.kt", [
    ('    private var checking = false',
     '    private var checking = false\n    private var manualRequested = false',
     "remember manual check during an existing request"),
    ('        if (checking) {\n            record("$source skipped: in flight")',
     '        if (checking) {\n            if (source == "manual") manualRequested = true\n            record("$source skipped: in flight")',
     "manual check joins in-flight request"),
    ('                checking = false\n                scheduleRetry()',
     '                checking = false\n                if (manualRequested) {\n                    manualRequested = false\n                    manualResult(result.startsWith("success"))\n                }\n                scheduleRetry()',
     "complete queued manual check result"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('<string name="st_check_updates">软件更新</string>',
     '<string name="st_check_updates">手动检查更新</string>',
     "rename manual update check setting"),
    ('<string name="st_check_updates_hint">立即检查是否有新版 Aerial，不必等待自动检测。</string>',
     '<string name="st_check_updates_hint">立即手动检查是否有新版 Aerial。</string>',
     "clarify manual update check setting"),
])

edit("app/src/main/res/values/strings.xml", [
    ('<string name="st_check_updates">Updates</string>',
     '<string name="st_check_updates">Manual update check</string>',
     "rename manual update check setting"),
    ('<string name="st_check_updates_hint">Check now for a newer Aerial version instead of waiting for the automatic check.</string>',
     '<string name="st_check_updates_hint">Manually check whether a newer Aerial version is available.</string>',
     "clarify manual update check setting"),
])

# All in-app update metadata and APKs must come from klcb2010/aerial-tv, never upstream.
# Update endpoints and APK sources are handled by the initial Updates.kt patch above.\n

# When automatic update checks find a newer release, show one dismissible prompt
# per release. Never download or install until the owner chooses Update Now.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    fun diagnostics(): String = if (!started) "not initialized" else',
     '    fun automaticPromptVersion(): String? {\n        if (!started || !automaticChecksEnabled) return null\n        val latest = available ?: return null\n        return latest.takeIf { prefs.getString("prompt_dismissed", null) != it }\n    }\n\n    fun dismissAutomaticPrompt(version: String) {\n        if (started) prefs.edit { putString("prompt_dismissed", version) }\n    }\n\n    fun diagnostics(): String = if (!started) "not initialized" else',
     "automatic update prompt persistence"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('import androidx.compose.foundation.layout.Box\n',
     'import androidx.compose.foundation.layout.Box\nimport androidx.compose.foundation.layout.Column\nimport androidx.compose.foundation.layout.Arrangement\nimport androidx.compose.foundation.layout.width\n',
     "update prompt layout imports"),
    ('import androidx.compose.ui.draw.drawWithContent\n',
     'import androidx.compose.ui.draw.drawWithContent\nimport androidx.compose.foundation.background\nimport androidx.compose.foundation.shape.RoundedCornerShape\nimport androidx.compose.ui.window.Dialog\n',
     "update prompt dialog imports"),
    ('import app.orchard.tv.ui.components.liquidGlass\n',
     'import app.orchard.tv.ui.components.liquidGlass\nimport app.orchard.tv.ui.components.Pressable\nimport app.orchard.tv.update.Updates\n',
     "update prompt components"),
    ('    val gridEnabled = overlay == Overlay.None && kidsLock == null',
     '    val gridEnabled = overlay == Overlay.None && kidsLock == null\n    var updatePrompt by remember { mutableStateOf<String?>(null) }\n    LaunchedEffect(Updates.available, Updates.automaticChecksEnabled, overlay, vm.loaded, kidsLock, vm.screensaverVisible) {\n        if (!Updates.automaticChecksEnabled) {\n            updatePrompt = null\n        } else if (overlay == Overlay.None && vm.loaded && kidsLock == null && !vm.screensaverVisible) {\n            updatePrompt = Updates.automaticPromptVersion()\n        }\n    }',
     "observe automatic update availability"),
    ('        Screensaver(visible = vm.screensaverVisible, apps = apps, now = now, skips = vm.screensaverSkips, carry = when {\n                filmSaver -> SaverCarry.Film(liveFilm)\n                stillCarry != null -> stillCarry\n                else -> null\n            },\n        )',
     '        Screensaver(visible = vm.screensaverVisible, apps = apps, now = now, skips = vm.screensaverSkips, carry = when {\n                filmSaver -> SaverCarry.Film(liveFilm)\n                stillCarry != null -> stillCarry\n                else -> null\n            },\n        )\n\n        updatePrompt?.let { version ->\n            UpdateAvailableDialog(\n                version = version,\n                onLater = { Updates.dismissAutomaticPrompt(version); updatePrompt = null },\n                onUpdate = {\n                    Updates.dismissAutomaticPrompt(version)\n                    updatePrompt = null\n                    vm.overlay = Overlay.ControlCenter(CcPage.Update)\n                },\n            )\n        }',
     "show automatic update prompt"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('/** How long the screensaver waits for the wallpaper\'s film to move before playing its own. */',
     '@Composable\nprivate fun UpdateAvailableDialog(version: String, onLater: () -> Unit, onUpdate: () -> Unit) {\n    val updateFocus = remember { FocusRequester() }\n    LaunchedEffect(Unit) {\n        withFrameNanos { }\n        runCatching { updateFocus.requestFocus() }\n    }\n    Dialog(onDismissRequest = onLater) {\n        Column(\n            Modifier.width(500.dp)\n                .background(Color(0xF01B1B1B), RoundedCornerShape(24.dp))\n                .padding(32.dp),\n            verticalArrangement = Arrangement.spacedBy(18.dp),\n        ) {\n            BasicText(stringResource(R.string.update_prompt_title), style = Type.Title)\n            BasicText(stringResource(R.string.update_prompt_version, version), style = Type.Body)\n            BasicText(stringResource(R.string.update_prompt_message), style = Type.Caption)\n            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {\n                Pressable(onClick = onLater, modifier = Modifier.weight(1f)) { state ->\n                    Box(Modifier.fillMaxWidth().background(Color(0xFF454545), RoundedCornerShape(12.dp)).padding(vertical = 15.dp), contentAlignment = Alignment.Center) {\n                        BasicText(stringResource(R.string.update_prompt_later), style = Type.Body)\n                    }\n                }\n                Pressable(onClick = onUpdate, modifier = Modifier.weight(1f), focusRequester = updateFocus) { state ->\n                    Box(Modifier.fillMaxWidth().background(if (state.focused) Color.White else Color(0xFF777777), RoundedCornerShape(12.dp)).padding(vertical = 15.dp), contentAlignment = Alignment.Center) {\n                        BasicText(stringResource(R.string.update_prompt_now), style = Type.Body.copy(color = if (state.focused) Color.Black else Color.White))\n                    }\n                }\n            }\n        }\n    }\n}\n\n/** How long the screensaver waits for the wallpaper\'s film to move before playing its own. */',
     "automatic update dialog composable"),
])






# Prefer the fork's lightweight version.txt endpoint; fall back to the Releases API.
# This avoids making manual checks depend on GitHub API rate limits or API reachability.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    private fun readLatestVersion(): String {\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }',
     '    private fun readLatestVersion(): String {\n        val version = runCatching {\n            read("https://raw.githubusercontent.com/klcb2010/aerial-tv/main/version.txt").trim()\n        }.getOrNull()?.takeIf { it.matches(Regex("\\\\d+(\\\\.\\\\d+)*")) }\n        if (version != null) return version\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }',
     "raw version file with releases API fallback"),
    ('        c.readTimeout = 10_000\n        return try {',
     '        c.readTimeout = 10_000\n        c.setRequestProperty("User-Agent", "Aerial-TV-klcb2010")\n        c.setRequestProperty("Accept", "application/vnd.github+json, text/plain, */*")\n        return try {\n            if (c.responseCode !in 200..299) throw java.io.IOException("HTTP ${c.responseCode}")',
     "version endpoint HTTP headers and status validation"),
])

edit("app/src/main/java/app/orchard/tv/update/UpdateCheck.kt", [
    ('    private var checking = false',
     '    private var checking = false\n    private var manualRequested = false',
     "remember manual check during an existing request"),
    ('        if (checking) {\n            record("$source skipped: in flight")',
     '        if (checking) {\n            if (source == "manual") manualRequested = true\n            record("$source skipped: in flight")',
     "manual check joins in-flight request"),
    ('                checking = false\n                scheduleRetry()',
     '                checking = false\n                if (manualRequested) {\n                    manualRequested = false\n                    manualResult(result.startsWith("success"))\n                }\n                scheduleRetry()',
     "complete queued manual check result"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('<string name="st_check_updates">软件更新</string>',
     '<string name="st_check_updates">手动检查更新</string>',
     "rename manual update check setting"),
    ('<string name="st_check_updates_hint">立即检查是否有新版 Aerial，不必等待自动检测。</string>',
     '<string name="st_check_updates_hint">立即手动检查是否有新版 Aerial。</string>',
     "clarify manual update check setting"),
])

edit("app/src/main/res/values/strings.xml", [
    ('<string name="st_check_updates">Updates</string>',
     '<string name="st_check_updates">Manual update check</string>',
     "rename manual update check setting"),
    ('<string name="st_check_updates_hint">Check now for a newer Aerial version instead of waiting for the automatic check.</string>',
     '<string name="st_check_updates_hint">Manually check whether a newer Aerial version is available.</string>',
     "clarify manual update check setting"),
])

# All in-app update metadata and APKs must come from klcb2010/aerial-tv, never upstream.
# Update endpoints and APK sources are handled by the initial Updates.kt patch above.\n

# When automatic update checks find a newer release, show one dismissible prompt
# per release. Never download or install until the owner chooses Update Now.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    fun diagnostics(): String = if (!started) "not initialized" else',
     '    fun automaticPromptVersion(): String? {\n        if (!started || !automaticChecksEnabled) return null\n        val latest = available ?: return null\n        return latest.takeIf { prefs.getString("prompt_dismissed", null) != it }\n    }\n\n    fun dismissAutomaticPrompt(version: String) {\n        if (started) prefs.edit { putString("prompt_dismissed", version) }\n    }\n\n    fun diagnostics(): String = if (!started) "not initialized" else',
     "automatic update prompt persistence"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('import androidx.compose.foundation.layout.Box\n',
     'import androidx.compose.foundation.layout.Box\nimport androidx.compose.foundation.layout.Column\nimport androidx.compose.foundation.layout.Arrangement\nimport androidx.compose.foundation.layout.width\n',
     "update prompt layout imports"),
    ('import androidx.compose.ui.draw.drawWithContent\n',
     'import androidx.compose.ui.draw.drawWithContent\nimport androidx.compose.foundation.background\nimport androidx.compose.foundation.shape.RoundedCornerShape\nimport androidx.compose.ui.window.Dialog\n',
     "update prompt dialog imports"),
    ('import app.orchard.tv.ui.components.liquidGlass\n',
     'import app.orchard.tv.ui.components.liquidGlass\nimport app.orchard.tv.ui.components.Pressable\nimport app.orchard.tv.update.Updates\n',
     "update prompt components"),
    ('    val gridEnabled = overlay == Overlay.None && kidsLock == null',
     '    val gridEnabled = overlay == Overlay.None && kidsLock == null\n    var updatePrompt by remember { mutableStateOf<String?>(null) }\n    LaunchedEffect(Updates.available, Updates.automaticChecksEnabled, overlay, vm.loaded, kidsLock, vm.screensaverVisible) {\n        if (!Updates.automaticChecksEnabled) {\n            updatePrompt = null\n        } else if (overlay == Overlay.None && vm.loaded && kidsLock == null && !vm.screensaverVisible) {\n            updatePrompt = Updates.automaticPromptVersion()\n        }\n    }',
     "observe automatic update availability"),
    ('        Screensaver(visible = vm.screensaverVisible, apps = apps, now = now, skips = vm.screensaverSkips, carry = when {\n                filmSaver -> SaverCarry.Film(liveFilm)\n                stillCarry != null -> stillCarry\n                else -> null\n            },\n        )',
     '        Screensaver(visible = vm.screensaverVisible, apps = apps, now = now, skips = vm.screensaverSkips, carry = when {\n                filmSaver -> SaverCarry.Film(liveFilm)\n                stillCarry != null -> stillCarry\n                else -> null\n            },\n        )\n\n        updatePrompt?.let { version ->\n            UpdateAvailableDialog(\n                version = version,\n                onLater = { Updates.dismissAutomaticPrompt(version); updatePrompt = null },\n                onUpdate = {\n                    Updates.dismissAutomaticPrompt(version)\n                    updatePrompt = null\n                    vm.overlay = Overlay.ControlCenter(CcPage.Update)\n                },\n            )\n        }',
     "show automatic update prompt"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ('/** How long the screensaver waits for the wallpaper\'s film to move before playing its own. */',
     '@Composable\nprivate fun UpdateAvailableDialog(version: String, onLater: () -> Unit, onUpdate: () -> Unit) {\n    val updateFocus = remember { FocusRequester() }\n    LaunchedEffect(Unit) {\n        withFrameNanos { }\n        runCatching { updateFocus.requestFocus() }\n    }\n    Dialog(onDismissRequest = onLater) {\n        Column(\n            Modifier.width(500.dp)\n                .background(Color(0xF01B1B1B), RoundedCornerShape(24.dp))\n                .padding(32.dp),\n            verticalArrangement = Arrangement.spacedBy(18.dp),\n        ) {\n            BasicText(stringResource(R.string.update_prompt_title), style = Type.Title)\n            BasicText(stringResource(R.string.update_prompt_version, version), style = Type.Body)\n            BasicText(stringResource(R.string.update_prompt_message), style = Type.Caption)\n            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {\n                Pressable(onClick = onLater, modifier = Modifier.weight(1f)) { state ->\n                    Box(Modifier.fillMaxWidth().background(Color(0xFF454545), RoundedCornerShape(12.dp)).padding(vertical = 15.dp), contentAlignment = Alignment.Center) {\n                        BasicText(stringResource(R.string.update_prompt_later), style = Type.Body)\n                    }\n                }\n                Pressable(onClick = onUpdate, modifier = Modifier.weight(1f), focusRequester = updateFocus) { state ->\n                    Box(Modifier.fillMaxWidth().background(if (state.focused) Color.White else Color(0xFF777777), RoundedCornerShape(12.dp)).padding(vertical = 15.dp), contentAlignment = Alignment.Center) {\n                        BasicText(stringResource(R.string.update_prompt_now), style = Type.Body.copy(color = if (state.focused) Color.Black else Color.White))\n                    }\n                }\n            }\n        }\n    }\n}\n\n/** How long the screensaver waits for the wallpaper\'s film to move before playing its own. */',
     "automatic update dialog composable"),
])






# Prefer the fork's lightweight version.txt endpoint; fall back to the Releases API.
# This avoids making manual checks depend on GitHub API rate limits or API reachability.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('    private fun readLatestVersion(): String {\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }',
     '    private fun readLatestVersion(): String {\n        val version = runCatching {\n            read("https://raw.githubusercontent.com/klcb2010/aerial-tv/main/version.txt").trim()\n        }.getOrNull()?.takeIf { it.matches(Regex("\\\\d+(\\\\.\\\\d+)*")) }\n        if (version != null) return version\n        val tag = JSONObject(read(VERSION_URL)).getString("tag_name")\n        return tag.removePrefix("upstream-").removePrefix("v")\n    }',
     "raw version file with releases API fallback"),
    ('        c.readTimeout = 10_000\n        return try {',
     '        c.readTimeout = 10_000\n        c.setRequestProperty("User-Agent", "Aerial-TV-klcb2010")\n        c.setRequestProperty("Accept", "application/vnd.github+json, text/plain, */*")\n        return try {\n            if (c.responseCode !in 200..299) throw java.io.IOException("HTTP ${c.responseCode}")',
     "version endpoint HTTP headers and status validation"),
])

edit("app/src/main/java/app/orchard/tv/update/UpdateCheck.kt", [
    ('    private var checking = false',
     '    private var checking = false\n    private var manualRequested = false',
     "remember manual check during an existing request"),
    ('        if (checking) {\n            record("$source skipped: in flight")',
     '        if (checking) {\n            if (source == "manual") manualRequested = true\n            record("$source skipped: in flight")',
     "manual check joins in-flight request"),
    ('                checking = false\n                scheduleRetry()',
     '                checking = false\n                if (manualRequested) {\n                    manualRequested = false\n                    manualResult(result.startsWith("success"))\n                }\n                scheduleRetry()',
     "complete queued manual check result"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('<string name="st_check_updates">软件更新</string>',
     '<string name="st_check_updates">手动检查更新</string>',
     "rename manual update check setting"),
    ('<string name="st_check_updates_hint">立即检查是否有新版 Aerial，不必等待自动检测。</string>',
     '<string name="st_check_updates_hint">立即手动检查是否有新版 Aerial。</string>',
     "clarify manual update check setting"),
])

edit("app/src/main/res/values/strings.xml", [
    ('<string name="st_check_updates">Updates</string>',
     '<string name="st_check_updates">Manual update check</string>',
     "rename manual update check setting"),
    ('<string name="st_check_updates_hint">Check now for a newer Aerial version instead of waiting for the automatic check.</string>',
     '<string name="st_check_updates_hint">Manually check whether a newer Aerial version is available.</string>',
     "clarify manual update check setting"),
])

# Fail early if an injected update-prompt resource is duplicated.
import xml.etree.ElementTree as ET

for resource_path in (
    "app/src/main/res/values/strings.xml",
    "app/src/main/res/values-zh/strings.xml",
):
    resource_file = ROOT / resource_path
    resource_root = ET.parse(resource_file).getroot()
    for resource_name in (
        "update_prompt_title",
        "update_prompt_version",
        "update_prompt_message",
        "update_prompt_now",
        "update_prompt_later",
    ):
        matches = [
            item for item in resource_root
            if item.attrib.get("name") == resource_name
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"[mod] {resource_path}: expected one {resource_name}, found {len(matches)}"
            )
print("[mod] update prompt resources verified")


# Remove the app-level signing-certificate precheck completely. The Android
# package installer remains responsible for deciding whether an update can replace
# the installed package.
edit("app/src/main/java/app/orchard/tv/update/Updates.kt", [
    ('                !sameSigner(app, ready) -> Failure.NotOfficial\n', '', "remove signer comparison call"),
    ('        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES\n        val info = runCatching { context.packageManager.getPackageArchiveInfo(file.path, flags) }.getOrNull() ?: return null',
     '        val info = runCatching { context.packageManager.getPackageArchiveInfo(file.path, 0) }.getOrNull() ?: return null',
     "remove signer metadata extraction"),
    ('    /** Whether [apk] is signed like this copy. If the archive\'s signers cannot be read, the installer decides. */\n    @Suppress("DEPRECATION")\n    private fun sameSigner(context: Context, apk: PackageInfo): Boolean {\n        val pm = context.packageManager\n        fun signers(info: PackageInfo?): Set<String>? {\n            val sigs = if (Build.VERSION.SDK_INT >= 28) info?.signingInfo?.apkContentsSigners else info?.signatures\n            return sigs?.takeIf { it.isNotEmpty() }?.map { it.toCharsString() }?.toSet()\n        }\n        val theirs = signers(apk) ?: return true\n        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES\n        val ours = signers(runCatching { pm.getPackageInfo(context.packageName, flags) }.getOrNull()) ?: return true\n        return theirs == ours\n    }\n\n',
     '',
     "remove sameSigner implementation"),
    ('     * ACTION_VIEW on the APK makes the installer itself the one installing. The APK must be this package, signed\n     * with this copy\'s key and no older, or the installer would only fail with a less clear message.',
     '     * ACTION_VIEW on the APK makes the installer itself the one installing. The APK must be this package and no older, or the installer would only fail with a less clear message.',
     "remove signer requirement from updater documentation"),
])

# Tint the actual high-contrast focus ring. The ring is rasterized by ringFrame(),
# separately from the empty-slot outline patched above.
edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    ('intArrayOf(Color.White.toArgb(), Color.White.copy(alpha = 0.78f).toArgb(), Color.White.copy(alpha = 0.94f).toArgb()),',
     'intArrayOf(Color(0xFFADD8FF).toArgb(), Color(0xFFADD8FF).copy(alpha = 0.78f).toArgb(), Color(0xFFADD8FF).copy(alpha = 0.94f).toArgb()),',
     "pale blue high-contrast focus ring gradient"),
    ('line(dp, Color.White.copy(alpha = 0.35f))',
     'line(dp, Color(0xFFADD8FF).copy(alpha = 0.55f))',
     "pale blue inner focus ring"),
])

# Make the available-update state explicit: installation starts immediately on click.
edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ('Updates.ManualCheckStatus.UpdateAvailable -> R.string.st_check_updates_available',
     'Updates.ManualCheckStatus.UpdateAvailable -> R.string.st_check_updates_installing',
     "manual update available label"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ('<string name="st_check_updates_available">发现新版本</string>',
     '<string name="st_check_updates_available">发现新版本</string>\n    <string name="st_check_updates_installing">即将自动安装最新版</string>',
     "Chinese installing latest update label"),
])

edit("app/src/main/res/values/strings.xml", [
    ('<string name="st_check_updates_available">Update available</string>',
     '<string name="st_check_updates_available">Update available</string>\n    <string name="st_check_updates_installing">The latest version will install automatically</string>',
     "English installing latest update label"),
])

# Keep the optional Skyworth / Coocaa implementation isolated and easy to revert.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coocaa  # noqa: F401


# Optional square artwork tiles on the first Home row; off by default.
edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ("    var peekNextRow by mutableStateOf(true); private set",
     "    var peekNextRow by mutableStateOf(true); private set\n\n    /** Draw all Home app tiles as squares instead of the usual 16:9 tiles. */\n    var firstRowSquareIcons by mutableStateOf(false); private set",
     "first-row square icons"),
])

edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ("        peekNextRow = prefs.getBoolean(\"peek_next_row\", true)",
     "        peekNextRow = prefs.getBoolean(\"peek_next_row\", true)\n        firstRowSquareIcons = prefs.getBoolean(\"first_row_square_icons\", false)",
     "first-row square icons"),
])

edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    ("    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(\"peek_next_row\", on) }\n    }",
     "    fun choosePeekNextRow(on: Boolean) {\n        peekNextRow = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(\"peek_next_row\", on) }\n    }\n\n    fun chooseFirstRowSquareIcons(on: Boolean) {\n        firstRowSquareIcons = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(\"first_row_square_icons\", on) }\n    }",
     "first-row square icons"),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    ("                    Choices(\n                        R.string.st_columns, stringResource(R.string.st_columns_hint), note,\n                        AerialSettings.HOME_COLUMNS.map { it to it.toString() },\n                        AerialSettings.homeColumns, AerialSettings::chooseHomeColumns,\n                    )",
     "                    Choices(\n                        R.string.st_columns, stringResource(R.string.st_columns_hint), note,\n                        AerialSettings.HOME_COLUMNS.map { it to it.toString() },\n                        AerialSettings.homeColumns, AerialSettings::chooseHomeColumns,\n                    )\n                    Choices(\n                        R.string.st_first_row_square_icons, stringResource(R.string.st_first_row_square_icons_hint), note,\n                        listOf(false to R.string.st_off, true to R.string.st_on),\n                        AerialSettings.firstRowSquareIcons, AerialSettings::chooseFirstRowSquareIcons,\n                    )",
     "first-row square icons"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ("                        val saverFade = { ((toSaver.value - 0.05f * (index % columns)) / 0.6f).coerceIn(0f, 1f) }\n                        AppTile(\n                            app = app,\n                            width = metrics.tileW,",
     "                        val saverFade = { ((toSaver.value - 0.05f * (index % columns)) / 0.6f).coerceIn(0f, 1f) }\n                        AppTile(\n                            app = app,\n                            width = metrics.tileW,",
     "first-row square icons"),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    (".offset { slot.value + IntOffset(tileOffsetX, -lift.roundToInt()) }",
     ".offset { slot.value - IntOffset(0, lift.roundToInt()) }",
     "remove square-tile offset"),
])

edit("app/src/main/res/values-zh/strings.xml", [
    ("    <string name=\"st_hidden_slots\">移出不补位</string>",
     "    <string name=\"st_first_row_square_icons\">全局显示正方形图标</string>\n    <string name=\"st_first_row_square_icons_hint\">开启后，首页所有图标均按正方形比例显示；关闭后恢复原来的长方形图标。</string>\n    <string name=\"st_hidden_slots\">移出不补位</string>",
     "first-row square icons"),
])

edit("app/src/main/res/values/strings.xml", [
    ("    <string name=\"st_hidden_slots\">Do Not Fill First-Row Gaps</string>",
     "    <string name=\"st_first_row_square_icons\">Square icons globally</string>\n    <string name=\"st_first_row_square_icons_hint\">Show all Home app tiles as squares instead of the usual widescreen tiles.</string>\n    <string name=\"st_hidden_slots\">Do Not Fill First-Row Gaps</string>",
     "first-row square icons"),
])


edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    ("private class GridMetrics(screenW: Dp, screenH: Dp, val columns: Int, oneRow: Boolean, plateNames: Boolean, peek: Boolean, plate: Boolean, largeClock: Boolean, clockRight: Boolean) {\n    val margin = GridMargin\n    val gap = gridGap(columns)\n    val tileW = restTileWidth(screenW, columns)\n    val tileH = tileW * 9f / 16f",
     "private class GridMetrics(screenW: Dp, screenH: Dp, val columns: Int, oneRow: Boolean, plateNames: Boolean, peek: Boolean, plate: Boolean, largeClock: Boolean, clockRight: Boolean, squareTiles: Boolean) {\n    private val wideTileW = restTileWidth(screenW, columns)\n    val tileW = if (squareTiles) wideTileW * 9f / 16f else wideTileW\n    val tileH = wideTileW * 9f / 16f\n    // Keep the original screen margins and spread square tiles across the same row width.\n    // This leaves the clock, status controls and glass plate anchored to their stock geometry.\n    val margin = GridMargin\n    val gap = if (squareTiles) {\n        (screenW - GridMargin * 2 - tileW * columns) / (columns - 1)\n    } else {\n        gridGap(columns)\n    }",
     "global square tile grid geometry"),
    ("        val metrics = remember(maxWidth, maxHeight, columns, oneRow, plateNames, peek, hasPlate, largeClock, clockRightNow) {\n            GridMetrics(maxWidth, maxHeight, columns, oneRow, plateNames, peek, hasPlate, largeClock, clockRightNow)\n        }",
     "        val squareTiles = AerialSettings.firstRowSquareIcons\n        val metrics = remember(maxWidth, maxHeight, columns, oneRow, plateNames, peek, hasPlate, largeClock, clockRightNow, squareTiles) {\n            GridMetrics(maxWidth, maxHeight, columns, oneRow, plateNames, peek, hasPlate, largeClock, clockRightNow, squareTiles)\n        }",
     "global square tile metrics"),
])


# Keep the real foreground logo proportional when the tile background is square.
# The artwork plate may fill the square; the transparent foreground logo must not stretch.
edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    ('                            drawImage(\n                                fore,\n                                dstOffset = IntOffset((at.left * pw + px).roundToInt(), (at.top * ph + py).roundToInt()),\n                                dstSize = IntSize((at.width * pw).roundToInt(), (at.height * ph).roundToInt()),\n                                filterQuality = FilterQuality.Medium,\n                            )',
     '                            if (AerialSettings.firstRowSquareIcons) {\n                                val targetW = (at.width * pw).roundToInt().coerceAtLeast(1)\n                                val targetH = (at.height * ph).roundToInt().coerceAtLeast(1)\n                                val fit = minOf(targetW.toFloat() / fore.width, targetH.toFloat() / fore.height)\n                                val logoW = (fore.width * fit).roundToInt().coerceAtLeast(1)\n                                val logoH = (fore.height * fit).roundToInt().coerceAtLeast(1)\n                                drawImage(\n                                    fore,\n                                    dstOffset = IntOffset(\n                                        (at.left * pw + (targetW - logoW) / 2f + px).roundToInt(),\n                                        (at.top * ph + (targetH - logoH) / 2f + py).roundToInt(),\n                                    ),\n                                    dstSize = IntSize(logoW, logoH),\n                                    filterQuality = FilterQuality.Medium,\n                                )\n                            } else {\n                                drawImage(\n                                    fore,\n                                    dstOffset = IntOffset((at.left * pw + px).roundToInt(), (at.top * ph + py).roundToInt()),\n                                    dstSize = IntSize((at.width * pw).roundToInt(), (at.height * ph).roundToInt()),\n                                    filterQuality = FilterQuality.Medium,\n                                )\n                            }',
     "preserve foreground logo aspect ratio on square tiles"),
])

# Match the background-face cache dimensions to the actual square tile dimensions.
# This avoids cache misses and main-thread face generation after enabling square tiles.
edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    ('        val tileW = restTileWidth((screenW / density).dp, AerialSettings.homeColumns).value * density\n        val tileH = tileW * 9f / 16f',
     '        val wideTileW = restTileWidth((screenW / density).dp, AerialSettings.homeColumns).value * density\n        val tileW = if (AerialSettings.firstRowSquareIcons) wideTileW * 9f / 16f else wideTileW\n        val tileH = if (AerialSettings.firstRowSquareIcons) tileW else tileW * 9f / 16f',
     "square tile face cache dimensions"),
])
# ============================================================================================
# 追加到 mod/apply.py 末尾（不要删掉已有的方形 tile 相关 edit，方形画布下它们的结果与原值一致）
#
# 解决：v2.1.150 里“格子方了、美术还是 16:9”，49ef60b6 用 min(targetW/fore.w, targetH/fore.h)
# 等比塞进去，方形格子的 targetW 只有原宽 56% → logo 被缩到约 28% 高，图标挤在方块中央；
# 而 fore == null 的 banner 路径仍被 16:9 硬拉伸。
# 做法：方形模式下美术画布也变方（W 由 352 收到 198 = 原 H，H 保持 198），
#       所有以 H 为单位的 logo/glyph 尺寸不变 → 零拉伸、不再走 min() 缩小那条路。
# 同时把方块里的 logo 从 0.5H 提到 0.58H（比 16:9 时代还大 16%），并把更新提示文案改掉。
# ============================================================================================
 
# 1) 方形格子时，美术画布做成正方形：H 沿用 16:9 的高度，W 收到同一个值。
edit("app/src/main/java/app/orchard/tv/apps/TileArt.kt", [
    (
        '        val w = (dp * density).roundToInt().coerceIn(352, 888)\n'
        '        if (w == W) return false\n'
        '        W = w\n'
        '        H = W * 9 / 16\n'
        '        return true',
        '        val wide = (dp * density).roundToInt().coerceIn(352, 888)\n'
        '        val w = if (AerialSettings.firstRowSquareIcons) wide * 9 / 16 else wide\n'
        '        if (w == W) return false\n'
        '        W = w\n'
        '        H = if (AerialSettings.firstRowSquareIcons) w else w * 9 / 16\n'
        '        return true',
        "square artwork canvas",
    ),
])
 
# 2) banner（应用自带 TV 海报，fore 为 null 的那条路径）也按画布形状裁：方形时切成方图。
#    这是 49ef60b6 没覆盖到的盲区，之前它仍被 16:9 硬拉进方格。
edit("app/src/main/java/app/orchard/tv/apps/TileArt.kt", [
    (
        '        val w = src?.width?.coerceAtMost(2 * W) ?: W\n'
        '        val h = w * 9 / 16',
        '        val w = src?.width?.coerceAtMost(2 * W) ?: W\n'
        '        val h = if (W == H) w else w * 9 / 16',
        "square banner canvas",
    ),
])
 
# 3) 开关切换时重新量美术（跟改列数一样走 reload），否则画布尺寸要重启才生效。
edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    (
        '        viewModelScope.launch {\n'
        '            snapshotFlow { AerialSettings.homeColumns }.drop(1).collect {\n'
        '                if (TileArtFactory.fitColumns()) reload() else if (loaded) prepareFaces()\n'
        '            }\n'
        '        }',
        '        viewModelScope.launch {\n'
        '            snapshotFlow { AerialSettings.homeColumns }.drop(1).collect {\n'
        '                if (TileArtFactory.fitColumns()) reload() else if (loaded) prepareFaces()\n'
        '            }\n'
        '        }\n'
        '        viewModelScope.launch {\n'
        '            snapshotFlow { AerialSettings.firstRowSquareIcons }.drop(1).collect {\n'
        '                if (TileArtFactory.fitColumns()) reload() else if (loaded) prepareFaces()\n'
        '            }\n'
        '        }',
        "square tiles reload artwork",
    ),
])
 
# 4) 方块里更饱满：图标占比 0.5 → 0.58，白色字形 0.58 → 0.66，来源/设备字形 0.5 → 0.58。
#    方形画布 198 宽：0.58H ≈ 115px → 落到 83dp 的方格里约 48dp，占格子 58%（16:9 时代只有 41dp / 50%）。
#    想更满就把 LOGO 调到 0.62~0.66；白字形 0.66H ≈ 131px，居中左右仍各留 33px，不会出界。
edit("app/src/main/java/app/orchard/tv/apps/TileArt.kt", [
    ('    private const val LOGO = 0.5f', '    private const val LOGO = 0.58f', "fuller logo on tiles"),
    ('            val g = H * 0.5f', '            val g = H * 0.58f', "fuller device mark"),
    ('            val g = H * (if (two) 0.36f else 0.42f)', '            val g = H * (if (two) 0.42f else 0.48f)', "fuller source mark"),
    (
        '    fun glyphTile(top: Int, bottom: Int, glyph: Glyph): TileArt {\n'
        '        val back = colorTile(top, bottom)\n'
        '        // The glyph on its own layer, so it shifts against the color when the tile leans. The\n'
        '        // symbols keep a margin inside their box, so the box is larger than the glyph looks.\n'
        '        val g = H * 0.58f',
        '    fun glyphTile(top: Int, bottom: Int, glyph: Glyph): TileArt {\n'
        '        val back = colorTile(top, bottom)\n'
        '        // The glyph on its own layer, so it shifts against the color when the tile leans. The\n'
        '        // symbols keep a margin inside their box, so the box is larger than the glyph looks.\n'
        '        val g = H * 0.66f',
        "fuller system glyph",
    ),
])
 
# 5) 更新提示文案：即将自动安装最新版 → 最新版安装过程中会卡一会儿（英文同步）。
#    也可以直接改 apply.py 第 815 / 821 行的字符串，效果相同。
edit("app/src/main/res/values-zh/strings.xml", [
    (
        '<string name="st_check_updates_installing">即将自动安装最新版</string>',
        '<string name="st_check_updates_installing">最新版安装过程中会卡一会儿</string>',
        "Chinese installing label wording",
    ),
])
 
edit("app/src/main/res/values/strings.xml", [
    (
        '<string name="st_check_updates_installing">The latest version will install automatically</string>',
        '<string name="st_check_updates_installing">Installing the latest version can take a while</string>',
        "English installing label wording",
    ),
])
 
 
# ============================================================================================
# 以下是可选项，默认不启用（要用就把对应那两行开头的 # 去掉）
# ============================================================================================
 
# a) 间距上限：现在 gap = 剩余宽度全摊给间隙，4 列时会到 143dp，图标之间空得厉害。
#    加个上限：间隙最多 1.2 × 格子宽。
# edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
#     ('        (screenW - GridMargin * 2 - tileW * columns) / (columns - 1)\n    } else {',
#      '        (screenW - GridMargin * 2 - tileW * columns) / (columns - 1)).coerceAtMost(tileW * 1.2f)\n    } else {',
#      "cap square tile gap"),
# ])
 
# b) 名字宽度：方形格子下 requiredSize(width + 36.dp) 只剩约 119dp，长名字被省略号切。
#    保底 150dp。
# edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
#     ('                .requiredSize(width + 36.dp, 24.dp)',
#      '                .requiredSize(maxOf(width + 36.dp, 150.dp), 24.dp)',
#      "wider names on square tiles"),
# ])


# Square mode: enlarge each square tile by 30%, capped at 108dp.
# Keep the original widescreen dimensions unchanged when the setting is off.
edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    (
        "    private val wideTileW = restTileWidth(screenW, columns)\n"
        "    val tileW = if (squareTiles) wideTileW * 9f / 16f else wideTileW\n"
        "    val tileH = wideTileW * 9f / 16f",
        "    private val wideTileW = restTileWidth(screenW, columns)\n"
        "    private val squareSide = minOf(wideTileW * 9f / 16f * 1.2f, 108.dp)\n"
        "    val tileW = if (squareTiles) squareSide else wideTileW\n"
        "    val tileH = if (squareTiles) squareSide else wideTileW * 9f / 16f",
        "30 percent larger square tiles",
    ),
])


# Adjustable square-tile enlargement, available only while global square tiles are enabled.
edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    (
        "    var firstRowSquareIcons by mutableStateOf(false); private set",
        "    var firstRowSquareIcons by mutableStateOf(false); private set\n    var squareIconScalePercent by mutableIntStateOf(15); private set",
        "square icon scale setting",
    ),
    (
        "        firstRowSquareIcons = prefs.getBoolean(\"first_row_square_icons\", false)",
        "        firstRowSquareIcons = prefs.getBoolean(\"first_row_square_icons\", false)\n        squareIconScalePercent = prefs.getInt(\"square_icon_scale_percent\", 20).takeIf { it in SQUARE_ICON_SCALE_CHOICES } ?: 20",
        "square icon scale setting",
    ),
    (
        "    fun chooseFirstRowSquareIcons(on: Boolean) {\n        firstRowSquareIcons = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(\"first_row_square_icons\", on) }\n    }",
        "    fun chooseFirstRowSquareIcons(on: Boolean) {\n        firstRowSquareIcons = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(\"first_row_square_icons\", on) }\n    }\n\n    val SQUARE_ICON_SCALE_CHOICES = listOf(15, 20, 25, 30)\n\n    fun chooseSquareIconScalePercent(percent: Int) {\n        if (percent !in SQUARE_ICON_SCALE_CHOICES) return\n        squareIconScalePercent = percent\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putInt(\"square_icon_scale_percent\", percent) }\n    }",
        "square icon scale setting",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    (
        "                        AerialSettings.firstRowSquareIcons, AerialSettings::chooseFirstRowSquareIcons,\n                    )",
        "                        AerialSettings.firstRowSquareIcons, AerialSettings::chooseFirstRowSquareIcons,\n                    )\n                    if (AerialSettings.firstRowSquareIcons) Choices(\n                        R.string.st_square_icon_scale, stringResource(R.string.st_square_icon_scale_hint), note,\n                        AerialSettings.SQUARE_ICON_SCALE_CHOICES.map { it to (it.toString() + \"%\") },\n                        AerialSettings.squareIconScalePercent, AerialSettings::chooseSquareIconScalePercent,\n                    )",
        "square icon scale setting",
    ),
])

edit("app/src/main/res/values-zh/strings.xml", [
    (
        "    <string name=\"st_first_row_square_icons_hint\">开启后，首页所有图标均按正方形比例显示；关闭后恢复原来的长方形图标。</string>",
        "    <string name=\"st_first_row_square_icons_hint\">开启后，首页所有图标均按正方形比例显示；关闭后恢复原来的长方形图标。</string>\n    <string name=\"st_square_icon_scale\">正方形图标放大</string>\n    <string name=\"st_square_icon_scale_hint\">使用遥控器左右键调整正方形图标放大比例，提供 15%、20%、25% 和 30% 四档。</string>",
        "square icon scale labels",
    ),
])

edit("app/src/main/res/values/strings.xml", [
    (
        "    <string name=\"st_first_row_square_icons_hint\">Show all Home app tiles as squares instead of the usual widescreen tiles.</string>",
        "    <string name=\"st_first_row_square_icons_hint\">Show all Home app tiles as squares instead of the usual widescreen tiles.</string>\n    <string name=\"st_square_icon_scale\">Square icon enlargement</string>\n    <string name=\"st_square_icon_scale_hint\">Use the left and right remote keys to choose 15%, 20%, 25% or 30% enlargement.</string>",
        "square icon scale labels",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    (
        "        val squareTiles = AerialSettings.firstRowSquareIcons\n        val metrics = remember(maxWidth, maxHeight, columns, oneRow, plateNames, peek, hasPlate, largeClock, clockRightNow, squareTiles) {",
        "        val squareTiles = AerialSettings.firstRowSquareIcons\n        val squareScalePercent = AerialSettings.squareIconScalePercent\n        val metrics = remember(maxWidth, maxHeight, columns, oneRow, plateNames, peek, hasPlate, largeClock, clockRightNow, squareTiles, squareScalePercent) {",
        "square icon scale recomposition",
    ),
    (
        "    private val squareSide = minOf(wideTileW * 9f / 16f * 1.2f, 108.dp)",
        "    private val squareSide = wideTileW * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f)",
        "square icon scale geometry",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    (
        "        val tileW = if (AerialSettings.firstRowSquareIcons) wideTileW * 9f / 16f else wideTileW\n        val tileH = if (AerialSettings.firstRowSquareIcons) tileW else tileW * 9f / 16f",
        "        val tileW = if (AerialSettings.firstRowSquareIcons) wideTileW * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f) else wideTileW\n        val tileH = if (AerialSettings.firstRowSquareIcons) tileW else tileW * 9f / 16f",
        "square icon scale face cache",
    ),
])


# Square tile scale: use one bounded geometry in Home, cached faces and artwork.
# 10/15/20/25% are stored as a Float multiplier (1.10f..1.25f).
edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    (
        '        squareIconScalePercent = prefs.getInt("square_icon_scale_percent", 20).takeIf { it in SQUARE_ICON_SCALE_CHOICES } ?: 20',
        '        val savedSquareScale = if (prefs.contains("square_tile_scale")) {\n'
        '            (prefs.getFloat("square_tile_scale", 1.15f).coerceIn(1.1f, 1.25f) * 100f).roundToInt() - 100\n'
        '        } else {\n'
        '            prefs.getInt("square_icon_scale_percent", 15)\n'
        '        }\n'
        '        squareIconScalePercent = savedSquareScale.takeIf { it in SQUARE_ICON_SCALE_CHOICES } ?: 15',
        "square tile float preference load",
    ),
    (
        '    val SQUARE_ICON_SCALE_CHOICES = listOf(15, 20, 25, 30)\n\n'
        '    fun chooseSquareIconScalePercent(percent: Int) {\n'
        '        if (percent !in SQUARE_ICON_SCALE_CHOICES) return\n'
        '        squareIconScalePercent = percent\n'
        '        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putInt("square_icon_scale_percent", percent) }\n'
        '    }',
        '    val SQUARE_ICON_SCALE_CHOICES = listOf(10, 15, 20, 25)\n\n'
        '    fun chooseSquareIconScalePercent(percent: Int) {\n'
        '        if (percent !in SQUARE_ICON_SCALE_CHOICES) return\n'
        '        squareIconScalePercent = percent\n'
        '        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putFloat("square_tile_scale", 1f + percent / 100f) }\n'
        '    }',
        "square tile float preference save and choices",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/home/HomeScreen.kt", [
    (
        '    private val squareSide = wideTileW * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f)',
        '    // At 130dp and above the large clock reaches its minimum top offset; keep the shared cap at 132dp.\n'
        '    private val squareSide = minOf(wideTileW * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f), 132.dp)',
        "square tile shared 132dp cap",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    (
        '        val tileW = if (AerialSettings.firstRowSquareIcons) wideTileW * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f) else wideTileW\n'
        '        val tileH = if (AerialSettings.firstRowSquareIcons) tileW else tileW * 9f / 16f',
        '        val squareSide = minOf(wideTileW * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f), 132f * density)\n'
        '        val tileW = if (AerialSettings.firstRowSquareIcons) squareSide else wideTileW\n'
        '        val tileH = if (AerialSettings.firstRowSquareIcons) tileW else tileW * 9f / 16f',
        "square tile face cache shared 132dp cap",
    ),
])

edit("app/src/main/java/app/orchard/tv/apps/TileArt.kt", [
    (
        '        val wide = (dp * density).roundToInt().coerceIn(352, 888)\n'
        '        val w = if (AerialSettings.firstRowSquareIcons) wide * 9 / 16 else wide\n'
        '        if (w == W) return false\n'
        '        W = w\n'
        '        H = if (AerialSettings.firstRowSquareIcons) w else w * 9 / 16',
        '        val wide = (dp * density).roundToInt().coerceIn(352, 888)\n'
        '        val squareSide = minOf(wide * 9f / 16f * (1f + AerialSettings.squareIconScalePercent / 100f), 132f * density).roundToInt()\n'
        '        val w = if (AerialSettings.firstRowSquareIcons) squareSide else wide\n'
        '        if (w == W) return false\n'
        '        W = w\n'
        '        H = if (AerialSettings.firstRowSquareIcons) w else w * 9 / 16',
        "square artwork canvas shared 132dp cap",
    ),
])

edit("app/src/main/java/app/orchard/tv/HomeViewModel.kt", [
    (
        '        viewModelScope.launch {\n'
        '            snapshotFlow { AerialSettings.firstRowSquareIcons }.drop(1).collect {\n'
        '                if (TileArtFactory.fitColumns()) reload() else if (loaded) prepareFaces()\n'
        '            }\n'
        '        }',
        '        viewModelScope.launch {\n'
        '            snapshotFlow { AerialSettings.firstRowSquareIcons }.drop(1).collect {\n'
        '                if (TileArtFactory.fitColumns()) reload() else if (loaded) prepareFaces()\n'
        '            }\n'
        '        }\n'
        '        viewModelScope.launch {\n'
        '            snapshotFlow { AerialSettings.squareIconScalePercent }.drop(1).collect {\n'
        '                TileArtFactory.fitColumns()\n'
        '                if (loaded) reload()\n'
        '            }\n'
        '        }',
        "square tile scale always reload",
    ),
])

edit("app/src/main/res/values-zh/strings.xml", [
    (
        '提供 15%、20%、25% 和 30% 四档。',
        '提供 10%、15%、20% 和 25% 四档。',
        "square tile scale Chinese choices",
    ),
])
edit("app/src/main/res/values/strings.xml", [
    (
        'choose 15%, 20%, 25% or 30% enlargement.',
        'choose 10%, 15%, 20% or 25% enlargement.',
        "square tile scale English choices",
    ),
])


edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    (
        'import java.security.MessageDigest\n',
        'import java.security.MessageDigest\nimport kotlin.math.roundToInt\n',
        "square tile scale rounding import",
    ),
])


# TileArt uses the same fixed 960dp canvas geometry as HomeScreen, not its old
# oversized 222/176dp sampling widths; otherwise four-column art hits 132dp too early.
edit("app/src/main/java/app/orchard/tv/apps/TileArt.kt", [
    (
        '        val dp = if (AerialSettings.homeColumns == 4) 222 else 176\n'
        '        val wide = (dp * density).roundToInt().coerceIn(352, 888)',
        '        val columns = AerialSettings.homeColumns\n'
        '        val gap = when (columns) { 4 -> 34f; 6 -> 24f; else -> 28f }\n'
        '        val dp = (960f - 112f - gap * (columns - 1)) / columns\n'
        '        val wide = (dp * density).roundToInt().coerceIn(1, 888)',
        "TileArt canvas matches HomeScreen grid",
    ),
])


edit("app/src/main/res/values-zh/strings.xml", [
    (
        '提供 10%、15%、20% 和 25% 四档。',
        '提供 10、15、20 和 25 四档。',
        "avoid percent format substitutions in Chinese",
    ),
])
edit("app/src/main/res/values/strings.xml", [
    (
        'choose 10%, 15%, 20% or 25% enlargement.',
        'choose 10, 15, 20 or 25 percent enlargement.',
        "avoid percent format substitutions in English",
    ),
])


# Optional: disable the temporary enlargement when an app receives remote focus.
edit("app/src/main/java/app/orchard/tv/settings/AerialSettings.kt", [
    (
        "    var homePlate by mutableStateOf(true); private set",
        "    var homePlate by mutableStateOf(true); private set\n\n    /** Do not enlarge an app tile when it receives remote focus. */\n    var disableFocusZoom by mutableStateOf(false); private set",
        "disable focus zoom setting state",
    ),
    (
        '        homePlate = prefs.getBoolean("home_plate", true)',
        '        homePlate = prefs.getBoolean("home_plate", true)\n        disableFocusZoom = prefs.getBoolean("disable_focus_zoom", false)',
        "disable focus zoom preference load",
    ),
    (
        "    fun chooseFocusStyle(style: FocusStyle) {\n        chosenFocusStyle = style\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putString(\"focus_style\", style.key) }\n    }",
        "    fun chooseFocusStyle(style: FocusStyle) {\n        chosenFocusStyle = style\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putString(\"focus_style\", style.key) }\n    }\n\n    fun chooseDisableFocusZoom(on: Boolean) {\n        disableFocusZoom = on\n        app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(\"disable_focus_zoom\", on) }\n    }",
        "disable focus zoom preference setter",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/home/AppTile.kt", [
    (
        "            focused || moving -> FOCUSED_SCALE",
        "            (focused || moving) && !AerialSettings.disableFocusZoom -> FOCUSED_SCALE",
        "disable focused tile enlargement",
    ),
])

edit("app/src/main/java/app/orchard/tv/ui/wallpaper/WallpaperSheet.kt", [
    (
        "                    Choices(\n                        R.string.st_focus_style,",
        "                    Choices(\n                        R.string.st_disable_focus_zoom, stringResource(R.string.st_disable_focus_zoom_hint), note,\n"
        "                        listOf(false to R.string.st_no, true to R.string.st_yes),\n"
        "                        AerialSettings.disableFocusZoom, AerialSettings::chooseDisableFocusZoom,\n"
        "                    )\n"
        "                    Choices(\n                        R.string.st_focus_style,",
        "disable focus zoom setting row",
    ),
])

edit("app/src/main/res/values-zh/strings.xml", [
    (
        '    <string name="st_focus_style">焦点样式</string>',
        '    <string name="st_yes">是</string>\n'
        '    <string name="st_no">否</string>\n'
        '    <string name="st_disable_focus_zoom">关闭APP图标对焦放大显示</string>\n'
        '    <string name="st_disable_focus_zoom_hint">开启后，遥控器选中应用时不再临时放大图标。</string>\n'
        '    <string name="st_focus_style">焦点样式</string>',
        "Chinese disable focus zoom labels",
    ),
])

edit("app/src/main/res/values/strings.xml", [
    (
        '    <string name="st_focus_style">Focus Style</string>',
        '    <string name="st_yes">Yes</string>\n'
        '    <string name="st_no">No</string>\n'
        '    <string name="st_disable_focus_zoom">Disable Focus Zoom</string>\n'
        '    <string name="st_disable_focus_zoom_hint">Do not temporarily enlarge an app tile when it receives remote focus.</string>\n'
        '    <string name="st_focus_style">Focus Style</string>',
        "English disable focus zoom labels",
    ),
])
