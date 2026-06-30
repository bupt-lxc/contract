# App-wide loading bar + action debounce

**Date:** 2026-06-30
**Status:** approved

## Summary

Add a global loading bar that automatically appears for every `callApi` request (both reads and writes), plus disable action buttons on detail/list views during API calls to prevent double-clicks.

## Motivation

- **Missing loading feedback:** Detail page action buttons (approve, deny, finish, submit, recall, delete, transfer, add/remove vendor, etc.) have no loading indicator. Users click and see no response while the database operation runs.
- **No debouncing:** Users can double-click or click multiple action buttons simultaneously, causing race conditions and duplicate submissions.
- **Current coverage gaps:** Search queries and form dialogs already have loading states, but mutation actions in detail views and list views do not.

## Design

### Layer 1: Global loading bar (all API calls)

**`bridge.js`** — export a reactive loading counter:

```js
import { reactive } from 'vue'

export const loadingState = reactive({ count: 0 })

export async function callApi(method, payload = {}) {
  loadingState.count++
  try {
    let result
    if (DEV_MODE) {
      if (!window.pywebview?.api) {
        throw new ApiError({ code: 'DEV_NO_BRIDGE', message: 'Dev mode: no pywebview bridge. Run in the desktop app.' })
      }
      result = await window.pywebview.api[method](payload)
    } else {
      result = await window.pywebview.api[method](payload)
    }
    if (!result.ok) {
      throw new ApiError(result.error)
    }
    return result.data
  } finally {
    loadingState.count--
  }
}
```

Every `callApi` call automatically increments the counter before the request and decrements after. No individual composable or view needs changes for this layer.

**`AppLoadingBar.vue`** — new component:

- Fixed at top of viewport (`position: fixed; top: 0; left: 0; right: 0; z-index: 9999`)
- 2px tall, CSS indeterminate animated gradient bar
- Wrapped in Vue `<Transition>` with:
  - Enter: `opacity 0→1` with **100ms delay** (prevents flash on sub-100ms calls)
  - Leave: `opacity 1→0` immediately (no delay when hiding)
- Shown when `loadingState.count > 0`

**`App.vue`** — mount the component above `<router-view>`.

**Anti-flash mechanism:** The 100ms CSS transition-delay on enter means API calls that complete in under 100ms (e.g., `list_users`) never visually trigger the bar. Only longer operations produce a visible loading indicator.

### Layer 2: Action button debounce (detail + list views)

Use the same global `loadingState.count > 0` to disable action buttons during any API call. This prevents double-clicks and concurrent mutations.

**Files to modify:**

| File | Buttons to add `:disabled` |
|---|---|
| `ScDetailView.vue` | edit, submit, confirm, approve, deny, recall, delete, finish, transfer, add PO, add vendor, remove vendor |
| `PoDetailView.vue` | edit, submit, finish, recall, delete, add GR, approve GR, deny GR, submit GR |
| `GrDetailView.vue` | edit, confirm, approve, deny, recall, delete |
| `ScListView.vue` | saveDraft (in handleSaveDraft), saveSubmit (in handleSaveSubmit) — or add disabled to New SC / Import buttons |

Pattern:

```vue
<el-button
  v-if="permissions.can_approve_sc"
  type="success"
  :disabled="loadingState.count > 0"
  @click="handleApprove"
>
  {{ $t('common.approve') }}
</el-button>
```

**Why unified `:disabled` instead of per-button `:loading`?**

- 10+ action buttons per view — per-button refs would add significant boilerplate for minimal gain
- The global loading bar already provides the visual "something is happening" signal
- Unified disable is sufficient for debounce — the user can't click any button while any operation is in progress

**What stays unchanged:**

- Form dialog `submitting` refs and `:loading` on submit buttons — these are correct and scoped to the dialog
- Search/list `state.loading` in composables — already works with table `v-loading`
- `BatchProgressModal` for batch operations — already has its own progress UI

### Component tree

```
App.vue
├── <AppLoadingBar />          ← NEW: fixed top bar, driven by loadingState.count
└── <router-view />
    ├── ScListView.vue         ← action buttons gain :disabled="loadingState.count > 0"
    ├── ScDetailView.vue       ← "
    ├── PoDetailView.vue       ← "
    ├── GrDetailView.vue       ← "
    ├── ... (other views unchanged)
    └── <ScFormDialog />       ← existing submitting logic unchanged
```

## Files changed

| File | Change |
|---|---|
| `frontend/src/api/bridge.js` | Add `loadingState` reactive export, increment/decrement in `callApi` |
| `frontend/src/components/common/AppLoadingBar.vue` | **New file** — animated progress bar component |
| `frontend/src/App.vue` | Import and mount `<AppLoadingBar />` |
| `frontend/src/views/ScDetailView.vue` | Import `loadingState`, add `:disabled` to action buttons |
| `frontend/src/views/PoDetailView.vue` | Import `loadingState`, add `:disabled` to action buttons |
| `frontend/src/views/GrDetailView.vue` | Import `loadingState`, add `:disabled` to action buttons |
| `frontend/src/views/ScListView.vue` | Import `loadingState`, add `:disabled` to New SC / Import buttons |

## Testing

- Unit: N/A (pure UI behavior)
- Manual verification:
  1. Click any action button on a detail page — verify the top loading bar appears and the button becomes disabled
  2. Verify the bar auto-hides when the operation completes (success or error)
  3. Verify that clicking a button during an in-flight operation has no effect (debounce)
  4. Verify very fast operations (<100ms) don't cause a visible flash
  5. Verify form dialog submit buttons still work correctly with their own `submitting` state
  6. Verify search/list loading states are unaffected
