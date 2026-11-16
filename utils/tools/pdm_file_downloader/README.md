# PDM File Downloader

A Jupyter UI plus API to search a SolidWorks PDM vault by item name and download copies of the files.

```python
from utils.tools.pdm_file_downloader.pdm_file_downloader import show_gui
display(show_gui(vault='PDM Vault', look_in=r'C:\PDM Vault\Projects'))   # or run pdm_file_downloader.py as a notebook

from utils.tools import pdm_file_downloader as pfd                        # no UI
from utils.standalone.solidworks_pdm_utils import SolidWorksPDM
pfd.pdm_missing()                                  # '' or why the PDM client / pywin32 isn't usable
pdm = SolidWorksPDM('PDM Vault'); pdm.connect()
saved, skipped, failed = pfd.download_files(pdm, pdm.search_files(r'C:\PDM Vault\Projects', 'AB12345*.pdf'), r'C:\temp')
```

## Files

- `__init__.py`: the API: `pdm_missing()`, `is_markup(name)`, `download_files(pdm, paths, dest, overwrite, on_progress)`, `DEFAULT_VAULT`, `DEFAULT_DEST`.
- `pdm_file_downloader.py`: the UI (jupytext py:percent, paired to `_jupytext-sync-ipynb/`); `show_gui(**kwargs)` returns the widget. Keys (all optional): `vault` (default `'PDM Vault'`), `look_in` (default: the vault's root folder), `dest` (default `~\Downloads\Downloaded PDM Files`); an unknown key raises `TypeError`.
- Vault access: `utils.standalone.solidworks_pdm_utils.SolidWorksPDM`.

## Behaviour

- **Startup check:** `pdm_missing()` looks for the PDM client's COM class (`HKCR\ConisioLib.EdmVault\CLSID`) and pywin32. If either is missing, the UI shows only the reason and a **Show UI anyway** button, which hides itself and shows the full UI. It doesn't connect, so a missing vault or login problem shows up on the first Search.
- **Connect** happens on the first Search or Download, not on start.
- **Look in:** `look_in=None` (or a blank field) searches from the vault's root folder, filled in on the first Search.
- **Search:** comma-separated names, OR'd in one server query (`SolidWorksPDM.search_files`): without a wildcard a name matches anywhere in the file name; with `*` / `?` it must match the whole name.
- **Read revisions (slower):** one server call per shown file for the data-card `Revision` (`-` empty, `?` failed).
- **Download:** copies straight from the vault server (no checkout). A file already in the destination is skipped unless **Overwrite existing**.
