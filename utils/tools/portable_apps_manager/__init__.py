"""Portable Apps Manager - deploy, track and update portable Windows apps from GitHub releases
or fixed download URLs.

Prerequisites: requests, truststore (TLS via the Windows certificate store), ipywidgets for the UI,
7-Zip for .7z / .7z.exe assets. PATH handling uses utils.tools.env_path_editor (Windows registry).

UI: portable_apps_manager.py (jupytext py:percent; run it in Jupyter, or call show_gui()).
"""
from ._catalog import CATALOG_PATH, CatalogEntry, load_catalog, recipe, save_to_catalog
from ._config import DEFAULT_ROOT, AppsConfig, AppSpec
from ._http import PrerequisiteError
from ._installer import InstallError, Plan
from ._manifest import MANIFEST_DIR, Manifest
from ._sources import (CHECK_MODES, SourceError, UrlProbe, match_assets, parse_repo, probe_url,
                       suggest_name, suggest_name_from_file, suggest_pattern, up_to_date)
from ._updater import ManifestWriteError, check, finish, folder_missing, prepare, untrack
