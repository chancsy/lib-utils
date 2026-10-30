"""
SolidWorks PDM Vault utilities.

Uses the PDM COM API directly via win32com — no extra wrapper library required.
Requires SolidWorks PDM Standard/Professional to be installed on the local machine.

Verified against SOLIDWORKS PDM Client 2026 SP03.2 (ConisioLib.EdmVault /
PDMWorks Enterprise Type Library 5.29). ``connect()`` loads whichever 5.x type
library is registered rather than pinning a minor version.

Key COM interfaces used:
    IEdmVault22         -- dispatched via EnsureDispatch('ConisioLib.EdmVault')
    IEdmSearch9         -- returned by IEdmVault21.CreateSearch2(); filename search
                           with the extended search syntax (OR, *, ?). Falls back to
                           IEdmSearch5 (CreateSearch) on clients without CreateSearch2.
    IEdmVariableMgr5    -- accessed via CastTo(client, 'IEdmVariableMgr5')
                           for variable name enumeration (GetFirstVariablePosition /
                           GetNextVariable)
    IEdmEnumeratorVariable5 -- returned by IEdmFile5.GetEnumeratorVariable()
                           for reading variable values:
                           GetVar(name, config) -> (found: bool, value)

Quick start:
    from utils.standalone.solidworks_pdm_utils import SolidWorksPDM

    pdm = SolidWorksPDM('PDM Vault')
    pdm.connect()

    # Server-side filename search - one pattern, or several OR'd in one query
    fisher = r'C:\\PDM Vault\\Master Data Record\\FISHER'
    print(pdm.search_files(fisher, 'GE58337'))
    print(pdm.search_files(fisher, ['GE58337*.pdf', 'GE58340_D*'], details=True))
    print(pdm.search_files(r'C:\\PDM Vault\\Projects', '*'))   # every file under a folder

    # List a directory (one level: sub-folders and files)
    print(pdm.list_dir(r'C:\\PDM Vault\\Projects'))

    # File metadata
    print(pdm.get_file_info(r'C:\\PDM Vault\\Projects\\part.SLDPRT'))

    # All data card variables (non-empty)
    print(pdm.get_file_variables(r'C:\\PDM Vault\\Projects\\part.SLDPRT'))

    # Specific variables only
    print(pdm.get_file_variables(path, var_names=['Description', 'Revision']))

    # List all variable names defined in the vault
    print(pdm.list_variable_names())

    # Download a copy (no checkout)
    pdm.download_file(path, r'C:\\temp')

    # Check out / in
    pdm.checkout(path)
    pdm.checkin(path, comment='updated')

    pdm.disconnect()

    # Or use as a context manager
    with SolidWorksPDM('PDM Vault') as pdm:
        print(pdm.list_dir(r'C:\\PDM Vault'))
"""

import os
import re
import shutil
import stat
import sys

if __name__ == '__main__':
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

_utils = UtilityFunctions()

_VAULT_DISPATCH_KEY  = 'ConisioLib.EdmVault'
_PDM_TYPE_LIB_GUID   = '{5FA2C692-8393-4F31-9BDB-05E6F807D0D3}'
_PDM_TYPE_LIB_MAJOR  = 5
_DISP_E_MEMBERNOTFOUND = -2147352573

# Splits an OR'd search string into terms, for the per-term legacy search fallback.
_OR_SPLIT_RE = re.compile(r'\s+OR\s+|\s*\|\s*')


class SolidWorksPDM:
    """Wrapper around the SolidWorks PDM COM API (IEdmVault5+).

    All ``path`` arguments must be absolute local paths inside the vault,
    e.g. ``r'C:\\PDM Vault\\Projects\\part.SLDPRT'``.
    """

    def __init__(self, vault_name: str = 'PDM Vault') -> None:
        """
        Parameters
        ----------
        vault_name : str
            Exact vault name as it appears in File Explorer (case-sensitive),
            e.g. ``'PDM Vault'``.
        """
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require Windows/pywin32 - only actually
        # instantiating SolidWorksPDM does. Cached on self so the methods don't need
        # their own import statements.
        if sys.platform != 'win32':
            raise ImportError('solidworks_pdm_utils requires Windows')
        _utils.exit_if_module_missing('pywin32')
        import pythoncom
        import win32com.client as win
        import win32com.client.gencache as gencache
        self._pythoncom = pythoncom
        self._win = win
        self._gencache = gencache
        self.vault_name = vault_name
        self._client = None  # IEdmVault22 early-bound COM object
        self._variable_names_cache = None  # cached after first remote call

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the PDM vault using cached Windows credentials.

        Uses early-binding (``EnsureDispatch``) so the generated type library
        wrappers are available -- required for ``CastTo(client, 'IEdmVariableMgr5')``
        and for the ``Edm*`` constants.

        Returns ``True`` on success, ``False`` on failure.
        """
        try:
            self._pythoncom.CoInitialize()
            self._ensure_type_library()
            client = self._gencache.EnsureDispatch(_VAULT_DISPATCH_KEY)
            if not client.IsLoggedIn:
                client.LoginAuto(self.vault_name, 0)
            self._client = client
            return True
        except Exception as exc:
            print(f'SolidWorksPDM: connect failed -- {exc}')
            return False

    def disconnect(self) -> bool:
        """Release the PDM COM connection.

        Returns ``True`` on success, ``False`` on failure.
        """
        try:
            self._client = None
            self._variable_names_cache = None
            self._pythoncom.CoUninitialize()
            return True
        except Exception as exc:
            print(f'SolidWorksPDM: disconnect failed -- {exc}')
            return False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ------------------------------------------------------------------
    # Directory listing
    # ------------------------------------------------------------------

    def list_dir(self, path: str) -> dict:
        """List files and sub-folders inside a vault directory.

        Returns
        -------
        dict
            ``{'folders': [name, ...], 'files': [name, ...]}``
        """
        self._require_connection()
        folder = self._get_folder(path)

        folders = []
        pos = folder.GetFirstSubFolderPosition()
        while not pos.IsNull:
            folders.append(folder.GetNextSubFolder(pos).Name)

        files = []
        pos = folder.GetFirstFilePosition()
        while not pos.IsNull:
            files.append(folder.GetNextFile(pos).Name)

        return {'folders': folders, 'files': files}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_files(self, root_path: str, name_patterns, details: bool = False) -> list:
        """Server-side filename search under a vault folder (recursive).

        Several patterns are OR'd together in a single server query, so searching
        for 4 part numbers costs about the same as searching for one.

        Pattern syntax (PDM extended search syntax, ``IEdmSearch9``):

        - ``*`` matches any run of characters, ``?`` exactly one; ``_`` is literal.
          ``%`` is accepted as an alias for ``*``.
        - A pattern without wildcards matches anywhere in the name
          (``GE58337`` finds ``GE58337_AB.pdf``); once a pattern has a wildcard
          it must match the whole name (``GE58340*.pdf``).
        - A single string may also contain ``OR`` / ``|`` between terms.

        On PDM clients without ``CreateSearch2`` it falls back to one
        ``IEdmSearch5`` query per term (slower), where ``_`` is a single-character
        wildcard rather than literal.

        Parameters
        ----------
        root_path : str
            Starting directory inside the vault.
        name_patterns : str or list of str
            One pattern, or several to OR together.
        details : bool, optional
            If ``True``, return a dict per file instead of just the path. The
            extra fields come with the search result (no extra server calls).

        Returns
        -------
        list of str, or list of dict if ``details``
            Matching files (folders excluded), each listed once. With
            ``details``: ``path``, ``name``, ``state``, ``version``, ``size``
            (bytes), ``date`` (datetime).
        """
        self._require_connection()
        terms = [name_patterns] if isinstance(name_patterns, str) else list(name_patterns)
        terms = [t.strip() for t in terms if t and t.strip()]
        if not terms:
            raise ValueError('search_files: no search pattern given')
        folder_id = self._get_folder(root_path).ID
        try:
            search = self._win.CastTo(self._client.CreateSearch2(), 'IEdmSearch9')
        except (AttributeError, self._pythoncom.com_error):
            return self._search_files_legacy(folder_id, terms, details)
        search.SetToken(self._win.constants.Edmstok_AllVersions, False)  # docs: must be set explicitly
        search.FileName = ' OR '.join(t.replace('%', '*') for t in terms)
        return self._collect_search_results(search, folder_id, details, {})

    # ------------------------------------------------------------------
    # File information
    # ------------------------------------------------------------------

    def get_file_info(self, path: str) -> dict:
        """Return metadata for a single vault file.

        Returns
        -------
        dict with keys:
            ``name``, ``path``, ``state``, ``version``,
            ``revision`` (PDM revision-scheme value; empty for many files),
            ``card_revision`` (the data card ``Revision`` variable, or ``''``),
            ``checked_out`` (bool), ``checked_out_by`` (str or None)
        """
        self._require_connection()
        _, f = self._get_file(path)

        checked_out = bool(f.IsLocked)
        checked_out_by = None
        if checked_out:
            try:
                checked_out_by = f.LockedByUser.Name
            except Exception:
                pass

        try:
            found, card_revision = f.GetEnumeratorVariable().GetVar('Revision', '')
            card_revision = card_revision if found and card_revision is not None else ''
        except Exception:
            card_revision = ''

        return {
            'name':           f.Name,
            'path':           path,
            'state':          f.CurrentState.Name,
            'version':        f.CurrentVersion,
            'revision':       f.CurrentRevision,
            'card_revision':  card_revision,
            'checked_out':    checked_out,
            'checked_out_by': checked_out_by,
        }

    # ------------------------------------------------------------------
    # File download
    # ------------------------------------------------------------------

    def download_file(self, src_path: str, dest_folder: str, dest_name: str = None,
                      version=None) -> str:
        """Download a copy of a vault file to a local folder (no checkout).

        The file is always copied straight from the vault server to
        ``dest_folder`` (~4 s per file), never from the local vault cache, so
        the result is the vault's content even if the cached copy is stale, and
        the local vault cache is left untouched. The copy is writable, and an
        existing file of the same name is replaced.

        Parameters
        ----------
        src_path : str
            Full vault path of the file to download,
            e.g. ``r'C:\\PDM Vault\\Projects\\part.SLDPRT'``.
        dest_folder : str
            Local folder to download to.  Created if it does not exist.
        dest_name : str, optional
            Filename to save as inside ``dest_folder``. Defaults to the
            original vault filename.
        version : int or str, optional
            Version number (e.g. ``3``) or revision name (e.g. ``'AB'``) to
            download. Defaults to the current (latest) version.

        Returns
        -------
        str
            Full path of the downloaded file.

        Raises
        ------
        ValueError
            If ``version`` is a number outside ``1..current version``, or an
            unknown revision name.
        PermissionError
            If an existing file at the destination can't be replaced (e.g. it
            is open in another program).
        """
        self._require_connection()
        _, f = self._get_file(src_path)
        if isinstance(version, int) and not 1 <= version <= f.CurrentVersion:
            raise ValueError(f'version {version} out of range 1..{f.CurrentVersion} for {src_path}')

        os.makedirs(dest_folder, exist_ok=True)
        final_name = dest_name or os.path.basename(src_path)
        final_path = os.path.join(dest_folder, final_name)
        if os.path.exists(final_path):
            # Removed first so a silently failed copy can't leave the old file looking like
            # a successful download; chmod clears a read-only attribute from older downloads.
            os.chmod(final_path, stat.S_IREAD | stat.S_IWRITE)
            os.remove(final_path)

        # GetFileCopy(lParentWnd, poVersionNoOrRevisionName, poPathOrFolderID,
        #             lEdmGetFlags, bsNewName)
        # A path string (rather than a vault folder ID, which targets the local vault
        # cache) copies straight to that folder. It's read as a file path, so the folder
        # needs a trailing backslash - without it the copy lands in the parent folder.
        ver = version if version is not None else f.CurrentVersion
        try:
            f.GetFileCopy(0, ver, os.path.join(os.path.abspath(dest_folder), ''),
                          self._win.constants.EdmGet_Simple, final_name)
        except self._pythoncom.com_error as exc:
            if exc.hresult == _DISP_E_MEMBERNOTFOUND:  # what an unknown revision name raises
                raise ValueError(f'revision {version!r} not found for {src_path}') from exc
            raise
        if not os.path.exists(final_path):
            raise RuntimeError(f'GetFileCopy did not produce {final_path}')
        return final_path

    # ------------------------------------------------------------------
    # Data card variables
    # ------------------------------------------------------------------

    def list_variable_names(self, force_refresh: bool = False) -> list:
        """Return all data card variable names defined in the vault.

        Results are cached on the instance after the first call (which
        makes ~101 round trips to the PDM server). Subsequent calls return
        the cached list immediately.

        Uses ``IEdmVariableMgr5.GetFirstVariablePosition`` / ``GetNextVariable``
        via ``CastTo`` -- requires early-binding (done automatically by
        ``connect()``).

        Parameters
        ----------
        force_refresh : bool, optional
            If ``True``, bypass the cache and re-query the vault.

        Returns
        -------
        list of str
        """
        self._require_connection()
        if self._variable_names_cache is not None and not force_refresh:
            return self._variable_names_cache
        mgr = self._win.CastTo(self._client, 'IEdmVariableMgr5')
        pos = mgr.GetFirstVariablePosition()
        names = []
        while not pos.IsNull:
            names.append(mgr.GetNextVariable(pos).Name)
        self._variable_names_cache = names
        return names

    def get_file_variables(self, path: str, var_names: list = None, config: str = '',
                           skip_empty: bool = True) -> dict:
        """Return PDM data card variable values for a file.

        Each variable is one server round trip (~0.4 s), so pass ``var_names``
        when only a few are needed.

        Parameters
        ----------
        path : str
            Full path to the file inside the vault.
        var_names : list of str, optional
            Variable names to read. If ``None``, all vault variables are
            enumerated via ``list_variable_names()``.
        config : str, optional
            SolidWorks configuration name. Empty string ``''`` reads the
            default (non-config-specific) card values, which is correct for
            most vault variables.
        skip_empty : bool, optional
            If ``True`` (default), variables with empty string values are
            excluded from the result. Set to ``False`` to include them.

        Returns
        -------
        dict
            ``{variable_name: value, ...}``
        """
        self._require_connection()
        _, f = self._get_file(path)

        if var_names is None:
            var_names = self.list_variable_names()

        # IEdmEnumeratorVariable5 -- the correct interface for reading variable values.
        # GetVar(name, config) returns (found: bool, value).
        enum = f.GetEnumeratorVariable()

        result = {}
        for name in var_names:
            try:
                found, val = enum.GetVar(name, config)
                if found and val is not None:
                    if skip_empty and val == '':
                        continue
                    result[name] = val
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # Check out / Check in
    # ------------------------------------------------------------------

    # TODO: not tested
    def checkout(self, path: str) -> None:
        """Check out a file. No-op if already checked out."""
        self._require_connection()
        folder, f = self._get_file(path)
        if f.IsLocked:
            return
        f.LockFile(folder.ID, 0)

    # TODO: not tested
    def checkin(self, path: str, comment: str = '') -> None:
        """Check in a file. No-op if already checked in."""
        self._require_connection()
        _, f = self._get_file(path)
        if not f.IsLocked:
            return
        f.UnlockFile(0, comment)

    # TODO: not tested
    def undo_checkout(self, path: str) -> None:
        """Revert a checkout without saving changes."""
        self._require_connection()
        _, f = self._get_file(path)
        if not f.IsLocked:
            return
        f.UndoLockFile(0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_type_library(self) -> None:
        """Generate / load the early-bound wrappers for the installed PDM type library."""
        # LoadRegTypeLib returns the highest registered minor version >= the one asked for.
        attr = self._pythoncom.LoadRegTypeLib(_PDM_TYPE_LIB_GUID, _PDM_TYPE_LIB_MAJOR, 0, 0).GetLibAttr()
        major, minor = attr[3], attr[4]
        try:
            self._gencache.EnsureModule(_PDM_TYPE_LIB_GUID, 0, major, minor)
        except AttributeError:
            # A stale/truncated gen_py cache raises AttributeError('MinorVersion') —
            # delete the bad directory and retry once so it regenerates cleanly.
            cache_key = f'{_PDM_TYPE_LIB_GUID[1:-1]}x0x{major}x{minor}'
            gen_py_dirs = (
                self._gencache.GetGeneratePath(),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Temp', 'gen_py', f'{sys.version_info.major}.{sys.version_info.minor}'),
            )
            for base in gen_py_dirs:
                bad = os.path.join(base, cache_key)
                if os.path.isdir(bad):
                    shutil.rmtree(bad, ignore_errors=True)
                    print(f'SolidWorksPDM: cleared stale gen_py cache at {bad}')
            self._gencache.EnsureModule(_PDM_TYPE_LIB_GUID, 0, major, minor)

    def _search_files_legacy(self, folder_id: int, terms: list, details: bool) -> list:
        """``IEdmSearch5`` fallback: one query per term (SQL LIKE wildcards ``%`` / ``_``)."""
        # Untested against a real pre-CreateSearch2 client; only exercised by forcing
        # this path on a 2026 client.
        seen = {}
        for term in (t for s in terms for t in _OR_SPLIT_RE.split(s) if t.strip()):
            term = term.strip()
            pattern = term.replace('*', '%').replace('?', '_')
            if not any(c in term for c in '*?%'):
                pattern = f'%{pattern}%'
            search = self._win.CastTo(self._client.CreateSearch(), 'IEdmSearch5')
            search.FileName = pattern
            self._collect_search_results(search, folder_id, details, seen)
        return list(seen.values())

    @staticmethod
    def _collect_search_results(search, folder_id: int, details: bool, seen: dict) -> list:
        """Run a prepared search, adding results to ``seen`` (path -> entry, de-duplicated)."""
        search.FindFiles = True
        search.FindFolders = False
        search.Recursive = True
        search.StartFolderID = folder_id
        res = search.GetFirstResult()
        while res is not None:
            if res.Path not in seen:
                seen[res.Path] = {
                    'path':    res.Path,
                    'name':    res.Name,
                    'state':   res.StateName,
                    'version': res.Version,
                    'size':    res.FileSize,
                    'date':    res.FileDate,
                } if details else res.Path
            res = search.GetNextResult()
        return list(seen.values())

    def _require_connection(self) -> None:
        if self._client is None:
            raise RuntimeError('Not connected to PDM vault. Call connect() first.')

    def _get_folder(self, path: str):
        """Return an IEdmFolder5 for the given path, raising if not found."""
        folder = self._client.GetFolderFromPath(path)
        if folder is None:
            raise FileNotFoundError(f'PDM folder not found: {path}')
        return folder

    def _get_file(self, path: str) -> tuple:
        """Return ``(IEdmFolder5, IEdmFile5)`` for a full vault file path, raising if not found."""
        folder = self._get_folder(os.path.dirname(path))
        try:
            f = folder.GetFile(os.path.basename(path))
        except self._pythoncom.com_error:  # raised ('The file/key name was invalid') rather than returning None
            f = None
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {path}')
        return folder, f

    # ------------------------------------------------------------------
    # Demo
    # ------------------------------------------------------------------

    def demo_download_file(self, src_path: str, dest_folder: str, append_rev_as_suffix: bool = True) -> str:
        """Download a vault file, optionally appending the PDM revision as a filename suffix.

        With ``append_rev_as_suffix=True`` the file is saved as
        ``<stem>_<Revision><ext>`` — e.g. ``GK10608_A.pdf``.
        """

        dest_name = None
        if append_rev_as_suffix:
            variables = self.get_file_variables(src_path, var_names=['Revision'], skip_empty=False)
            revision = (variables.get('Revision') or '').strip()
            if revision:
                stem, ext = os.path.splitext(os.path.basename(src_path))
                dest_name = f'{stem}_{revision}{ext}'
        result = self.download_file(src_path, dest_folder, dest_name=dest_name)
        print(f'Downloaded: {result}')
        return result

    lib_demo_params = [
        {'key': 'a', 'name': 'Connect',           'function': 'connect',           'inputs': []},
        {'key': 'b', 'name': 'Disconnect',         'function': 'disconnect',         'inputs': []},
        {'key': 'c', 'name': 'List Dir',           'function': 'list_dir',           'inputs': [
            {'label': 'Path', 'name': 'path', 'type': str, 'default': r'C:\PDM Vault', 'width': '100px'},
        ]},
        {'key': 'n', 'name': 'Search Files',       'function': 'search_files',       'inputs': [
            {'label': 'Root Path', 'name': 'root_path',     'type': str, 'default': r'C:\PDM Vault\Master Data Record\FISHER', 'width': '100px'},
            {'label': 'Patterns',  'name': 'name_patterns', 'type': lambda s: [v.strip() for v in s.split(',') if v.strip()], 'default': 'GK10608*.pdf, GE58340_D*', 'width': '200px', 'placeholder': 'comma-separated, * ? wildcards'},
            {'label': 'Details',   'name': 'details',       'type': bool, 'default': False, 'width': 'auto'},
        ]},
        {'key': 'g', 'name': 'Get File Info',      'function': 'get_file_info',      'inputs': [
            {'label': 'Path', 'name': 'path', 'type': str, 'default': r'C:\PDM Vault\Master Data Record\FISHER\SCHEMATIC\GK10\GK10608\GK10608.pdf', 'width': '100px'},
        ]},
        {'key': 'h', 'name': 'List Variable Names', 'function': 'list_variable_names', 'inputs': []},
        {'key': 'i', 'name': 'Get File Variables',  'function': 'get_file_variables',  'inputs': [
            {'label': 'Path',      'name': 'path',      'type': str, 'default': '', 'width': '100px', 'placeholder': r'C:\PDM Vault\...'},
            {'label': 'Var Names', 'name': 'var_names', 'type': lambda s: [v.strip() for v in s.split(',') if v.strip()] or None, 'default': '', 'width': '200px', 'placeholder': 'e.g. Description,Revision (blank=all)'},
            {'label': 'Config',    'name': 'config',    'type': str, 'default': '', 'width': '100px'},
            {'label': 'Skip Empty', 'name': 'skip_empty', 'type': bool, 'default': True, 'width': 'auto'},
        ]},
        {'key': 'j', 'name': 'Download File',       'function': 'demo_download_file', 'inputs': [
            {'label': 'Src Path',           'name': 'src_path',             'type': str,  'default': r'C:\PDM Vault\Master Data Record\FISHER\SCHEMATIC\GK10\GK10608\GK10608.pdf', 'width': '100px'},
            {'label': 'Dest Folder',        'name': 'dest_folder',          'type': str,  'default': os.path.join(os.path.expanduser('~'), 'Downloads'), 'width': '100px'},
            {'label': 'Append Rev Suffix',  'name': 'append_rev_as_suffix', 'type': bool, 'default': True},
        ]},
        # Check out check in not tested yet
        # {'key': 'k', 'name': 'Check Out',          'function': 'checkout',           'inputs': [
        #     {'label': 'Path', 'name': 'path', 'type': str, 'default': '', 'width': '100px', 'placeholder': r'C:\PDM Vault\...'},
        # ]},
        # {'key': 'l', 'name': 'Check In',           'function': 'checkin',            'inputs': [
        #     {'label': 'Path',    'name': 'path',    'type': str, 'default': '', 'width': '100px', 'placeholder': r'C:\PDM Vault\...'},
        #     {'label': 'Comment', 'name': 'comment', 'type': str, 'default': '', 'width': '100px'},
        # ]},
        # {'key': 'm', 'name': 'Undo Check Out',     'function': 'undo_checkout',      'inputs': [
        #     {'label': 'Path', 'name': 'path', 'type': str, 'default': '', 'width': '100px', 'placeholder': r'C:\PDM Vault\...'},
        # ]},
    ]
