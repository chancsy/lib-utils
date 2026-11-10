# Portable Apps Manager

A Jupyter UI plus API to deploy, track, update and remove portable Windows apps published as **GitHub releases** or at a **fixed download URL**.

```python
from utils.tools.portable_apps_manager.portable_apps_manager import show_gui
display(show_gui())                    # or run portable_apps_manager.py as a notebook; also in the tools launcher

from utils.tools.portable_apps_manager import AppsConfig, DEFAULT_ROOT, check, prepare, finish, up_to_date   # no UI
cfg = AppsConfig(DEFAULT_ROOT).load()
spec = cfg.apps['scrcpy']
release, asset = check(spec)
if not up_to_date(spec, release):
    p = prepare(cfg, spec, release, asset)       # download + plan, nothing written yet
    finish(cfg, spec, p, remove=p.stale)         # or remove=[]; overwrite=p.modified to replace edited files
```

## Prerequisites

- `pip install requests truststore ipywidgets` (`requests` + `truststore` are in lib-utils' `[requests]` extra).
- **`truststore` is required.** All HTTP goes through `_http.session()`, which verifies TLS against the Windows certificate store. Behind the corporate TLS inspection, Python's bundled `certifi` fails with `CERTIFICATE_VERIFY_FAILED` for several hosts (www.gyan.dev, download.sysinternals.com, nodejs.org, the.earth.li). The truststore context is mounted on this session only, not injected globally.
- **7-Zip** (`7z.exe` on PATH or in `C:\Program Files\7-Zip`) for `.7z` / `.7z.exe` assets.

## Files in the root folder

The root defaults to `~\Downloads\Programs` and can be changed per session in the Root field (not saved).

- `portable_apps.ini`: the registry, with each app's settings and installed version. It's written only when an app is added, updated, edited or untracked, never just by opening the tool. Its comment header (the key reference) comes from `config.template.ini`.
- `portable_apps.manifests/<name>.json`: one install manifest per app (see below).
- `<folder>/`: one fixed folder per app.

## Code

- `portable_apps_manager.py`: the UI (jupytext py:percent, paired to `_jupytext-sync-ipynb/`); `show_gui()` returns the widget. `tool.toml` registers it in the tools launcher.
- `_config.py`: `AppSpec` and `AppsConfig` (`load`, `save_app`, `delete_app`, `changed_on_disk`).
- `_sources.py`: `GitHubSource`, `UrlSource`, `probe_url()`, `up_to_date()`, plus the Add form's helpers (`parse_repo`, `match_assets`, `suggest_pattern`, `suggest_name`, `suggest_name_from_file`).
- `_installer.py`: download → `plan()` → `apply()`; also `resolve_version()`, `delete_folder()`, `detect_bin()`.
- `_manifest.py`: install manifests (`load` / `save` / `delete`).
- `_updater.py`: `check` / `prepare` / `finish` / `untrack`, the same steps the UI runs.
- `_catalog.py` + `apps_catalog.ini`: the shared, git-tracked catalog.
- `_pathlink.py`: each app's `bin` folder on the User PATH, through `utils/tools/env_path_editor`.
- `_http.py`: the shared truststore-backed `requests` session.

## Behaviour

### Sources and update detection

- **GitHub release:** the asset is picked by a glob on its name (case-insensitive) or `re:<regex>`, and must match exactly one asset; otherwise the error lists the candidates. Checksum / signature sidecars are never candidates. The marker is the release tag. The download's SHA-256 is checked against GitHub's `digest` when there is one.
- **Direct URL:** the Add form probes the URL (HEAD, redirects followed; a 1-byte ranged GET if HEAD is rejected) and offers the `check_by` modes the server supports, best first:
  - `final_url`: the redirect target names the version (e.g. `.../putty/0.85/...`); the final path is the marker.
  - `etag` / `last_modified`: the header value is the marker.
  - `download`: no usable header. Check reports *Unknown*; Update downloads, compares the SHA-256 with the installed one and stops if identical.
- **Shown version of URL apps** (`version_from`, read when the download is planned): `file` (a `version_file` in the archive, `path:key` or `path`), `top_folder` (`node-v26.13.0-win-x64` → `v26.13.0`), `file_name`, `date` (redirect-URL version or Last-Modified date), or `auto` (in that order). An explicit choice that finds nothing stops the install.
- Downloads retry twice (after 3 s and 10 s) on 5xx and dropped connections; 4xx fails at once.

### Plan and apply

- **Plan without extracting:** the archive listing (path, size, CRC32: `zipfile`, `7z l -slt`, or streamed tar members) is compared against the folder. A single top folder wrapping the archive is stripped. No SFX code runs for `.7z.exe`.
- **Groups:**

  | Group | Meaning | Action |
  |---|---|---|
  | new | in the release, not on disk | written |
  | changed | differs from the release, still what the last install wrote | overwritten |
  | unchanged | identical | skipped |
  | preserved | matches the app's `preserve` globs | never overwritten or removed |
  | modified | differs from the release, edited since the last install (or not written by it) | kept unless picked for overwrite |
  | user | not in the release, not written by the last install (app settings, user data) | never touched, not shown |
  | stale | written by the last install, not in the new release | removed only if chosen |
  | in use | a file to replace or remove is open in a program | Apply refuses to start |

- **Install manifest** (`portable_apps.manifests/<name>.json`, written by every install / update): `format`, `app`, `version`, `asset`, `installed_on` and `files` (`{"rel/path": {"size": n, "crc32": "8 hex"}}`, every file of the release as shipped). Stale files that were kept stay listed, so they're offered for removal again next time.
  - Without a manifest (installed before manifests existed, or an unreadable file), *modified* and *user* don't exist: every differing file is *changed* and every extra file is *stale*. The next install writes one.
  - If writing the manifest fails, the install still counts: the ini is saved and `ManifestWriteError` is logged.
  - `preserve` is applied first; it's only needed for files the release ships that must never be updated.
- **Stale / modified decision** (*Stale files* dropdown): *Ask per app* shows a panel with two lists (stale: highlighted = remove; modified: highlighted = overwrite), *Keep all*, or *Remove all*. *Remove all* skips stale files edited since the install. Modified files are only overwritten when picked in the panel; otherwise the log lists them as kept.
- If Apply refuses because files are in use, the download is kept, so Apply can be retried after closing the program.
- `bin` is auto-detected after install when left blank (the shallowest folder holding an `.exe`).

### The ini

- **Written one app at a time:** `save_app` / `delete_app` re-read the file, replace or remove only that app's section and write it back. Hand edits to other apps and `[settings]`, and unknown keys in the saved app's own section, are kept. Comments other than the template header are dropped.
- **Re-read before every action** when its modified time or size changed (Check, Update, Edit, Add, Save to catalog, PATH checkbox, Untrack). During Update all, each queued app uses its settings as the ini has them at that moment. An app removed from the ini by hand is skipped, not re-added.
- App names are also manifest file names: letters, digits, space, `. _ + -`, not starting / ending with a space or dot; names differing only in case are rejected.

### Catalog

`apps_catalog.ini` records how each app is best tracked: the same `[app:<name>]` keys plus `add_to_path` and a free-text `note`, with no install state. The Add form's **From catalog** fills every field and fetches the release / probes the URL. **Save to catalog** writes the selected apps' settings back, keeping an entry's note. Sharing a recipe = committing the file.

### PATH (User PATH only)

- Nothing about PATH is stored. The **PATH** column is a checkbox per app, read from the registry on every refresh. Ticking appends `<folder>\<bin>` to the User PATH (`%USERPROFILE%\...` when inside the profile); unticking removes every User entry resolving to that folder. Disabled when the entry is in the System PATH, there's no `bin`, or the folder is missing.
- Add form: optional "add to PATH after install" (default from the catalog's `add_to_path`). Edit with a changed `bin` swaps the entry. Untrack asks whether to remove the entry; Untrack & delete removes it. Update never touches PATH.
- Every write backs up both PATH values first (`%TEMP%\env_path_editor_backups`) and broadcasts `WM_SETTINGCHANGE`; programs already running keep their old PATH until restarted.

### Actions

Add (deploy + track), Edit (asset pattern / `check_by` / `version_file` / `version_from`, `bin`, `preserve`; source, name and folder are fixed), Check all, Update selected / all, *Reinstall even if up to date* (a repair against the same version), Untrack (folder kept), Untrack & delete.

## Status

- Working, in the real root: adb, ffmpeg (`.7z`), Git (PortableGit `.7z.exe`, 9616 files), GitExtensions, node, Notepad++, PortMon, TeraTerm, all with manifests matching their folders.
- Stale / modified panel checked in the notebook UI (PortMon): both lists, their select / clear buttons, *(modified since install)* label, remove + overwrite on Apply.
- Not yet tested: a single-file `.exe` asset; a tar asset; a server that rejects HEAD (the ranged-GET fallback).

## Limits and known issues

- **GitHub rate limit:** 60 API requests/hour without a token. Check all costs one per GitHub app, Add/Edit one per fetch. The error shows the reset time and stops Check all.
- **github.com release-link 504s** (seen 2026-11-05 for some assets, cleared within minutes): unknown whether GitHub or the corporate proxy sends them. A fallback through the REST API asset URL is implemented but off (`_installer._GITHUB_API_FALLBACK = False`) until that's investigated.
- **ETag / Last-Modified are change signals, not versions:** a re-upload can show *Update available*; the update then writes nothing but still costs a download.
- **Blocking UI:** downloads run inside the button callback (the progress bar still updates).
- **Single-file assets** are installed under the asset name; if that name has the version in it, each update leaves the old exe as a stale file.
- **PortableGit:** `post-install.bat` is not run. `cmd\git.exe` works without it; some Git Bash features may not.
- **Not trackable:** apps only published behind a bot check (e.g. clever FFmpeg GUI on videohelp.com) stay manual.

## Roadmap

1. Optional GitHub token in `[settings]`, to lift the 60/hour limit.
2. Pre-release / nightly channels (`/releases` instead of `/releases/latest`; rolling tags).
3. Page-scrape / manifest sources for apps without a fixed "latest" URL (nodejs.org `index.json` for an LTS line, sqlite.org, SumatraPDF, MobaXterm, Google's SDK manifest for adb).
4. Version before download via HTTP Range (zip only; dl.google.com accepts Range, nodejs.org and sysinternals don't).
5. A stable install name for single-file `.exe` assets.
