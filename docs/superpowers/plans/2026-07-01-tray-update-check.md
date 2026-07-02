# Tray Update Check — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check for updates when restoring the app from the system tray, and force-install when a new version is detected.

**Architecture:** Add a silent update check to the Python tray-restore path (`WM_LBUTTONDBLCLK` / `IDM_SHOW`), push a notification to the frontend via `window.evaluate_js`, show a non-dismissable Vue dialog, and execute the installer via a new bridge method.

**Tech Stack:** Python 3.11 + ctypes (existing), Vue 3 + Element Plus, no new dependencies

---

### Task 1: Add `_read_update_info()` and `_trigger_update_check()` to `app_shell.py`

**Files:**
- Modify: `sc_gr_app/app_shell.py`

- [ ] **Step 1: Add `_read_update_info()` helper before `_check_update()`**

Insert after `_webview2_storage()` (line 164) and before `_check_update()` (line 166):

```python


def _read_update_info():
    """Silently check for updates. Returns {version, changelog_cn, installer_name, sha256}
    or None when no update is available or manifest can't be read."""
    from sc_gr_app.update import (
        _releases_dir,
        fetch_manifest,
        is_update_available,
        verify_manifest,
    )

    if os.getenv("SC_GR_DEV") == "1":
        return None

    manifest = fetch_manifest()
    if manifest is None:
        return None
    if not is_update_available(manifest):
        return None
    if not verify_manifest(manifest):
        logger = logging.getLogger(__name__)
        logger.warning("Update manifest is invalid — skipping tray update check")
        return None

    return {
        "version": manifest["version"],
        "changelog_cn": manifest.get("changelog_cn", ""),
        "installer_name": manifest["gui"]["installer"],
        "sha256": manifest["gui"]["sha256"],
    }
```

- [ ] **Step 2: Add `_trigger_update_check(window)` helper after `_read_update_info()`**

```python


def _trigger_update_check(window):
    """Run a silent update check in a daemon thread. If an update is found,
    push it to the JS side via evaluate_js. Must be called after window is shown."""
    import json

    def _check():
        try:
            info = _read_update_info()
            if info is None:
                return
            window.evaluate_js(
                "window.__updateAvailable(" + json.dumps(info) + ")"
            )
        except Exception:
            pass  # update check failure must never break the app

    threading.Thread(target=_check, daemon=True).start()
```

- [ ] **Step 3: Wire `_trigger_update_check(window)` into the two tray restore paths in `wnd_proc`**

In `_setup_tray`, inside the `wnd_proc` function, there are two places where the window is restored:

**Path 1 — `WM_LBUTTONDBLCLK`** (around line 404). Change:

```python
            if msg == WM_TRAYICON and lparam == 0x0203:  # WM_LBUTTONDBLCLK
                window.show()
                window.restore()
                return 0
```

To:

```python
            if msg == WM_TRAYICON and lparam == 0x0203:  # WM_LBUTTONDBLCLK
                window.show()
                window.restore()
                _trigger_update_check(window)
                return 0
```

**Path 2 — `IDM_SHOW`** (around line 410). Change:

```python
                if wparam == IDM_SHOW:
                    window.show()
                    window.restore()
                    return 0
```

To:

```python
                if wparam == IDM_SHOW:
                    window.show()
                    window.restore()
                    _trigger_update_check(window)
                    return 0
```

- [ ] **Step 4: Verify the file parses correctly**

Run: `uv run python -c "from sc_gr_app.app_shell import _read_update_info, _trigger_update_check; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/app_shell.py
git commit -m "feat: add tray-update-check helpers to app_shell"
```

---

### Task 2: Add `install_update` bridge method

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add `install_update` method to the `ApiBridge` class**

Insert after the `get_version` method (after line 64) or at a logical position among the bridge methods. Place it near `get_version` since both relate to version/update:

```python

    def install_update(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            version = _require_payload_field(payload, "version")
            installer_name = _require_payload_field(payload, "installer_name")
            expected_hash = _require_payload_field(payload, "sha256")
        except Exception as exc:
            return fail(exc)

        from sc_gr_app.update import _releases_dir, sha256_file

        releases_dir = _releases_dir()
        installer_src = releases_dir / installer_name
        temp_dir = Path(os.getenv("TEMP")) / "pomp-update"

        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return fail(exc)

        installer_dst = temp_dir / installer_name

        try:
            import shutil
            shutil.copy2(str(installer_src), str(installer_dst))
        except OSError as exc:
            return fail(exc)

        actual_hash = sha256_file(installer_dst)
        if actual_hash != expected_hash:
            return fail(Exception(
                "Update file is corrupted. Contact your administrator."
            ))

        install_dir = Path(sys.executable).parent
        try:
            import subprocess
            subprocess.Popen(
                [
                    str(installer_dst),
                    "/SILENT",
                    f"/DIR={install_dir}",
                ],
            )
        except OSError as exc:
            return fail(exc)

        import signal
        os._exit(0)
        return ok(None)  # unreachable, but satisfies the return type
```

- [ ] **Step 2: Add missing imports at the top of `bridge.py`**

Add `import os`, `import sys`, and `from pathlib import Path` to the imports at the top of `bridge.py` if not already present.

Check existing imports at line 1-2 — `import os` already exists at line 1, `from pathlib import Path` already exists at line 2. Add `import sys` if not present. Run a quick check:

Run: `uv run python -c "import sc_gr_app.api.bridge; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add install_update bridge method"
```

---

### Task 3: Create `UpdateDialog.vue` component

**Files:**
- Create: `frontend/src/components/system/UpdateDialog.vue`

- [ ] **Step 1: Create the component file**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :close-on-click-modal="false"
    :show-close="false"
    :title="$t('update.newVersionAvailable')"
    width="480px"
    center
  >
    <p style="margin-bottom:12px">{{ $t('update.mustInstall', { version }) }}</p>
    <div v-if="changelog" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;max-height:200px;overflow-y:auto;white-space:pre-wrap;font-size:13px;color:#475569">{{ changelog }}</div>

    <template #footer>
      <el-button
        type="primary"
        :loading="loading"
        @click="$emit('install')"
      >
        {{ $t('update.installNow') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, required: true },
  version: { type: String, default: '' },
  changelog: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

defineEmits(['install'])
</script>
```

- [ ] **Step 2: Verify the component imports cleanly**

No command needed — the build will verify this in a later task. For now, check the file exists at the right path.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/system/UpdateDialog.vue
git commit -m "feat: add UpdateDialog component for forced update"
```

---

### Task 4: Wire `UpdateDialog` into `App.vue`

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add import and template for UpdateDialog**

In the `<template>`, add `<UpdateDialog>` right after `<AppLoadingBar />`:

```vue
  <AppLoadingBar />
  <UpdateDialog
    :visible="!!updateInfo"
    :version="updateInfo?.version || ''"
    :changelog="updateInfo?.changelog_cn || ''"
    :loading="updating"
    @install="handleInstallUpdate"
  />
  <LoginView v-if="layout === 'standalone'" />
```

- [ ] **Step 2: Add script setup logic**

In `<script setup>`, add the import, refs, and handler:

Add import:
```javascript
import UpdateDialog from '@/components/system/UpdateDialog.vue'
```

Add after `const sidebarCollapsed = ref(false)`:
```javascript

const updateInfo = ref(null)
const updating = ref(false)

window.__updateAvailable = (info) => {
  updateInfo.value = info
}
```

Add `handleInstallUpdate` function before `onMounted`:
```javascript

async function handleInstallUpdate() {
  updating.value = true
  try {
    await callApi('install_update', {
      version: updateInfo.value.version,
      installer_name: updateInfo.value.installer_name,
      sha256: updateInfo.value.sha256
    })
  } catch (e) {
    ElMessage.error(e.message || 'Update failed')
    updating.value = false
  }
}
```

Add the import for `callApi` and `ElMessage` at the top of imports:
```javascript
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'
```

- [ ] **Step 3: Verify the full `App.vue` script section is correct**

The `<script setup>` block should look like:

```javascript
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import SideNav from '@/components/layout/SideNav.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import LoginView from '@/views/LoginView.vue'
import AppLoadingBar from '@/components/common/AppLoadingBar.vue'
import UpdateDialog from '@/components/system/UpdateDialog.vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const route = useRoute()
const sidebarCollapsed = ref(false)

const updateInfo = ref(null)
const updating = ref(false)

window.__updateAvailable = (info) => {
  updateInfo.value = info
}

const layout = computed(() => route.meta?.layout || 'default')

async function handleInstallUpdate() {
  updating.value = true
  try {
    await callApi('install_update', {
      version: updateInfo.value.version,
      installer_name: updateInfo.value.installer_name,
      sha256: updateInfo.value.sha256
    })
  } catch (e) {
    ElMessage.error(e.message || 'Update failed')
    updating.value = false
  }
}

onMounted(() => {
  if (window.__isBeta) {
    document.title = 'PO Management Platform Beta'
  }
})
```

- [ ] **Step 4: Build check**

Run: `cd frontend && npx vite build`
Expected: build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: wire UpdateDialog into App.vue with window.__updateAvailable handler"
```

---

### Task 5: Add i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/en-US.js`
- Modify: `frontend/src/i18n/locales/zh-CN.js`

- [ ] **Step 1: Add English keys**

In `en-US.js`, insert a new `update` section before the final `}`. Place it before the `exportCol` section (before line 700):

```javascript

  update: {
    newVersionAvailable: 'Update Required',
    mustInstall: 'A new version {version} is available. You must install it to continue.',
    installNow: 'Install Now',
    installing: 'Installing...'
  },
```

- [ ] **Step 2: Add Chinese keys**

In `zh-CN.js`, insert a new `update` section before the final `}`. Place it before the `exportCol` section (before line 700):

```javascript

  update: {
    newVersionAvailable: '版本更新',
    mustInstall: '新版本 {version} 已发布，必须安装才能继续使用。',
    installNow: '立即安装',
    installing: '安装中...'
  },
```

- [ ] **Step 3: Rebuild to verify**

Run: `cd frontend && npx vite build`
Expected: build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: add update dialog i18n keys"
```

---

### Task 6: Manual verification checklist

No automated tests — the tray + pywebview integration requires manual verification.

- [ ] **Step 1: Build the app**

Run: `powershell -ExecutionPolicy Bypass -File packaging/build.ps1`

- [ ] **Step 2: Prepare test manifest**

Create a test `manifest.json` in the releases directory with `version` different from `__version__` ("2.2.17"). Include valid `gui.installer` and `gui.sha256` fields pointing to a real `.exe` file (can be any small exe, e.g., a copy of `setup.exe`). Compute SHA256 with `certutil -hashfile setup.exe SHA256` or Python `hashlib.sha256`.

- [ ] **Step 3: Verify tray restore triggers update dialog**

1. Launch the app — startup check passes (same version or manifest absent)
2. Close the window (X button) → app hides to tray
3. Copy the new `manifest.json` with a higher version to the releases directory
4. Double-click the tray icon OR right-click → "Show Window"
5. **Expected:** `UpdateDialog` appears showing the new version and changelog text

- [ ] **Step 4: Verify dialog is non-dismissable**

- Click the overlay/mask area → nothing happens
- Press Escape → nothing happens
- No X button in the dialog header

- [ ] **Step 5: Verify "Install Now" workflow**

- Click "Install Now"
- **Expected:** Button shows loading state
- **Expected:** Installer launches (Inno Setup `/SILENT` — app closes and reopens after install)
- If the installer hash doesn't match: **Expected:** Error message appears, dialog stays open, button unloads

- [ ] **Step 6: Verify normal restore (no update) still works**

1. Remove or rename the test `manifest.json`
2. Launch app, minimize to tray, restore
3. **Expected:** Window restores normally, no dialog appears
