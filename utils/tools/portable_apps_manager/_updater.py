"""Check / install / untrack, tying sources + installer + config together. UI-free, so it can
also be scripted:

    cfg = AppsConfig(DEFAULT_ROOT).load()
    spec = cfg.apps['scrcpy']
    release, asset = check(spec)
    if not up_to_date(spec, release):
        p = prepare(cfg, spec, release, asset)
        finish(cfg, spec, p, remove=p.stale)   # or remove=[] to keep stale files;
                                               # overwrite=p.modified to replace edited files too
Every install writes the app's manifest (_manifest.py), which the next prepare() plans against.
"""
import datetime
import os

from . import _installer, _manifest
from ._config import AppsConfig, AppSpec
from ._installer import InstallError, Plan, ProgressCb
from ._sources import Asset, ReleaseInfo, get_source


class ManifestWriteError(InstallError):
    """finish() installed and recorded the app, but couldn't write its manifest."""


def check(spec: AppSpec) -> tuple[ReleaseInfo, Asset]:
    src = get_source(spec.source)
    release = src.release_for(spec)
    return release, src.resolve(spec, release)


def prepare(cfg: AppsConfig, spec: AppSpec, release: ReleaseInfo, asset: Asset,
            progress: ProgressCb | None = None) -> Plan:
    # GitHub apps keep the release tag as their version; url apps resolve it per spec.version_from
    m = _manifest.load(cfg.root, spec.name)
    return _installer.plan(spec.folder_path(cfg.root), release.version, asset, spec.preserve, progress,
                           marker=release.marker, version_file=spec.version_file,
                           version_from=(spec.version_from or 'auto') if spec.source == 'url' else None,
                           manifest=m.lookup() if m else None)


def finish(cfg: AppsConfig, spec: AppSpec, plan: Plan, remove: list[str], overwrite: list[str] = ()) -> None:
    """Apply the plan (remove = stale files to delete, overwrite = modified files to replace), write
    the app's manifest, record the installed version, and save the app's ini section. Adds spec to
    cfg if new.
    If apply raises (e.g. files in use) the plan's download is kept so the caller can retry
    finish() after the program is closed; call plan.cleanup() to discard it instead.
    A manifest that can't be written doesn't undo the install: the ini is still saved, then
    ManifestWriteError says so (the next update plans without a manifest and writes a new one)."""
    _manifest.manifest_path(cfg.root, spec.name)   # bad name: fail before anything is written
    _installer.apply(plan, remove, overwrite)
    today = datetime.date.today().isoformat()
    manifest_error = None
    try:
        _manifest.save(cfg.root, _manifest.Manifest(app=spec.name, version=plan.version, asset=plan.asset.name,
                                                    installed_on=today, files=plan.file_records(remove)))
    except (OSError, InstallError) as e:
        manifest_error = e
        _manifest.delete(cfg.root, spec.name)   # an old manifest would no longer match the folder
    finally:
        plan.cleanup()
    spec.installed_version = plan.version
    spec.installed_marker = plan.marker
    spec.installed_asset = plan.asset.name
    spec.installed_on = today
    if not spec.bin:
        spec.bin = _installer.detect_bin(spec.folder_path(cfg.root))
    if spec.name not in cfg.apps:
        cfg.add(spec)      # name / folder clash check
    cfg.save_app(spec)     # only this app's section: other edits to the ini are kept
    if manifest_error:
        raise ManifestWriteError(f'{spec.name}: installed, but its install manifest could not be written: {manifest_error}')


def untrack(cfg: AppsConfig, name: str, delete_folder: bool = False) -> None:
    spec = cfg.apps[name]
    if delete_folder:
        _installer.delete_folder(spec.folder_path(cfg.root))   # raises before untracking if files are in use
    cfg.delete_app(name)
    _manifest.delete(cfg.root, name)


def folder_missing(cfg: AppsConfig, spec: AppSpec) -> bool:
    return spec.is_installed and not os.path.isdir(spec.folder_path(cfg.root))
