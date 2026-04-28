# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

**Standalone (primary — no dependencies):**
Open `TaskPulse.html` directly in a browser. Everything is self-contained in that single file.

**Flask server version:**
```bash
pip install flask
python app.py          # serves at http://localhost:5000
```
Or double-click `run.bat` on Windows — it installs Flask and opens the browser automatically.

## Two parallel versions

The project ships two independent implementations of the same UI. When adding a feature, **both files usually need to be updated**:

| File | Persistence | JS state key prefix |
|---|---|---|
| `TaskPulse.html` | `localStorage` | `tp_` (e.g. `tp_tasks`, `tp_nextId`) |
| `templates/index.html` + `static/app.js` | Flask REST API → SQLite (`tasks.db`) | n/a (server state) |
| `static/style.css` | shared styles for the Flask version | n/a |

`TaskPulse.html` is entirely self-contained — its `<style>` and `<script>` blocks duplicate the content of `static/style.css` and `static/app.js`. The Flask version splits those out into separate files.

## Task data structure

Both versions use the same shape:
```js
{
  id: number,
  title: string,
  description: string,
  priority: 'high' | 'medium' | 'low' | 'none',
  category: 'general' | 'work' | 'personal' | 'shopping' | 'health' | 'finance' | 'education',
  due_date: string,      // 'YYYY-MM-DD' or ''
  alarm_time: string,    // 'YYYY-MM-DDTHH:MM' or ''
  completed: 0 | 1,
  subtasks: Array<{ id: number, title: string, completed: boolean }>,
  created_at: string,    // ISO datetime
}
```

The Flask/SQLite schema does **not** have a `subtasks` column — subtasks are a `localStorage`-only feature in the standalone version. The Flask `app.py` `fields` allowlist in `update_task` would need extending to persist them server-side.

## Frontend architecture (shared between both versions)

All UI state is module-level variables: `tasks[]`, `currentView`, `currentPri`, `currentCat`, `searchQuery`, `sortMode`, `firedAlarms` (Set), `formSubtasks[]`, `openSubtaskLists` (Set).

**Render pipeline** — every mutation calls `render()` which fans out to:
`renderBadges()` → `renderCategoryFilters()` → `renderStats()` → `renderProgress()` → `renderTasks()` → `buildCard(t)` per task.

Cards are fully rebuilt on every render (no diffing). `openSubtaskLists` (a `Set<id>`) preserves which subtask panels are expanded across rebuilds.

**Alarm checker** — `startAlarmChecker()` runs `checkAlarms()` immediately then every 30 s via `setInterval`. It fires if `(now - alarmTime)` is between 0 and 120 seconds. Fired alarm IDs are persisted to `localStorage` under `tp_firedAlarms` to prevent re-firing on page reload.

## CSS theming

All colours are CSS custom properties defined on `:root` (dark) and overridden on `[data-theme="light"]`. The theme is toggled by setting `document.documentElement.dataset.theme` and saved to `localStorage` under `tp_theme`.

Priority colours: `--p-high` (#ff4757), `--p-med` (#ffa502), `--p-low` (#2ed573), `--p-none` (#747d8c).  
Category colours: `--c-work`, `--c-personal`, etc. — also reflected in `CAT_META` in JS.

When adding a new category, update both `CAT_META` (JS) and the corresponding `--c-*` variable and `.badge-cat-*` rule (CSS), in both `TaskPulse.html` and `static/style.css` / `static/app.js`.

## Git workflow

**Commit and push after every piece of work — no exceptions.** The goal is that GitHub always reflects the current state of the project so no work is ever lost and any change can be reverted.

The repo is at `https://github.com/Arnold415/taskpulse-todo` with remote `origin`, branch `master`.

**When to commit:** After each logical unit of work — a new feature, a bug fix, a UI tweak, a refactor. Do not batch multiple unrelated changes into one commit.

**Commit message rules:**
- Use the imperative present tense: `Add subtask progress bar`, not `Added` or `Adding`
- First line is a short summary (under 72 characters)
- If the change needs more context, add a blank line then a short paragraph
- Never use vague messages like `update`, `fix`, `changes`, or `WIP`

**The sequence after every change:**
```bash
git add <changed files>          # stage only the files that changed
git commit -m "Descriptive summary of what and why"
git push
```

`tasks.db` is gitignored — local task data is never committed.
