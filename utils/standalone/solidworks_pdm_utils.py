"""
SolidWorks PDM Vault utilities.

Uses the PDM COM API directly via win32com — no extra wrapper library required.
Requires SolidWorks PDM Standard/Professional to be installed on the local machine.

Verified against PDM 2025 (ConisioLib.EdmVault / PDMWorks Enterprise Type Library).

Key COM interfaces used:
    IEdmVault22         -- dispatched via EnsureDispatch('ConisioLib.EdmVault')
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

    # List a directory
    print(pdm.list_dir(r'C:\\PDM Vault\\Projects'))

    # File metadata
    print(pdm.get_file_info(r'C:\\PDM Vault\\Projects\\part.SLDPRT'))

    # All data card variables (non-empty)
    print(pdm.get_file_variables(r'C:\\PDM Vault\\Projects\\part.SLDPRT'))

    # Specific variables only
    print(pdm.get_file_variables(path, var_names=['Description', 'Revision']))

    # List all variable names defined in the vault
    print(pdm.list_variable_names())

    # Recursive walk / search
    print(pdm.list_dir_recursive(r'C:\\PDM Vault\\Projects'))
    print(pdm.find_files(r'C:\\PDM Vault', extension='.SLDDRW'))

    # Check out / in
    pdm.checkout(path)
    pdm.checkin(path, comment='updated')

    pdm.disconnect()

    # Or use as a context manager
    with SolidWorksPDM('PDM Vault') as pdm:
        print(pdm.list_dir_root())
"""

import os
import shutil
import sys, os as _os

if sys.platform != 'win32':
    raise ImportError('solidworks_pdm_utils requires Windows')

if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

_u = UtilityFunctions()
_u.exit_if_module_missing('pywin32')
del _u

import pythoncom
import win32com.client as win
import win32com.client.gencache as gencache

_VAULT_DISPATCH_KEY  = 'ConisioLib.EdmVault'
_PDM_TYPE_LIB_GUID   = '{5FA2C692-8393-4F31-9BDB-05E6F807D0D3}'
_PDM_TYPE_LIB_MAJOR  = 5
_PDM_TYPE_LIB_MINOR  = 28


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
            e.g. ``'PDM Vault'``. The vault root is assumed to be
            ``C:\\<vault_name>``.
        """
        self.vault_name = vault_name
        self.root = rf'C:\{vault_name}'
        self._client = None  # IEdmVault22 early-bound COM object
        self._variable_names_cache = None  # cached after first remote call

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the PDM vault using cached Windows credentials.

        Uses early-binding (``EnsureDispatch``) so the generated type library
        wrappers are available -- required for ``CastTo(client, 'IEdmVariableMgr5')``.

        Returns ``True`` on success, ``False`` on failure.
        """
        try:
            pythoncom.CoInitialize()
            # Early-binding: generates / loads Python wrappers from the type library.
            # A stale/truncated gen_py cache raises AttributeError('MinorVersion') —
            # delete the bad directory and retry once so it regenerates cleanly.
            try:
                gencache.EnsureModule(_PDM_TYPE_LIB_GUID, 0, _PDM_TYPE_LIB_MAJOR, _PDM_TYPE_LIB_MINOR)
            except AttributeError:
                _cache_key = f'{_PDM_TYPE_LIB_GUID[1:-1]}x0x{_PDM_TYPE_LIB_MAJOR}x{_PDM_TYPE_LIB_MINOR}'
                for _base in (gencache.GetGeneratePath(), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Temp', 'gen_py', f'{sys.version_info.major}.{sys.version_info.minor}')):
                    _bad = os.path.join(_base, _cache_key)
                    if os.path.isdir(_bad):
                        shutil.rmtree(_bad, ignore_errors=True)
                        print(f'SolidWorksPDM: cleared stale gen_py cache at {_bad}')
                gencache.EnsureModule(_PDM_TYPE_LIB_GUID, 0, _PDM_TYPE_LIB_MAJOR, _PDM_TYPE_LIB_MINOR)
            client = gencache.EnsureDispatch(_VAULT_DISPATCH_KEY)
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
            pythoncom.CoUninitialize()
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
            sub = folder.GetNextSubFolder(pos)
            folders.append(sub.Name)

        files = []
        pos = folder.GetFirstFilePosition()
        while not pos.IsNull:
            f = folder.GetNextFile(pos)
            files.append(f.Name)

        return {'folders': folders, 'files': files}

    def list_dir_root(self) -> dict:
        """Convenience wrapper -- list the vault root directory."""
        return self.list_dir(self.root)

    def list_dir_recursive(self, path: str) -> list:
        """Walk a vault directory tree and return all entries.

        Returns
        -------
        list of dict
            Each entry has ``'path'`` (full path), ``'name'``, and
            ``'type'`` (``'file'`` or ``'folder'``).
        """
        self._require_connection()
        results = []
        self._walk(path, results)
        return results

    def find_files(self, root_path: str, extension: str = None, name_contains: str = None) -> list:
        """Recursively find files in the vault, optionally filtered.

        Parameters
        ----------
        root_path : str
            Starting directory inside the vault.
        extension : str, optional
            Case-insensitive file extension filter, e.g. ``'.SLDPRT'``.
        name_contains : str, optional
            Case-insensitive substring the filename must contain.

        Returns
        -------
        list of str
            Full absolute paths of matching files.
        """
        entries = self.list_dir_recursive(root_path)
        results = []
        for entry in entries:
            if entry['type'] != 'file':
                continue
            name = entry['name']
            if extension and not name.lower().endswith(extension.lower()):
                continue
            if name_contains and name_contains.lower() not in name.lower():
                continue
            results.append(entry['path'])
        return results

    # ------------------------------------------------------------------
    # File information
    # ------------------------------------------------------------------

    def get_file_info(self, path: str) -> dict:
        """Return metadata for a single vault file.

        Returns
        -------
        dict with keys:
            ``name``, ``path``, ``state``, ``revision``, ``version``,
            ``checked_out`` (bool), ``checked_out_by`` (str or None)
        """
        self._require_connection()
        folder_path, filename = self._split_path(path)
        folder = self._get_folder(folder_path)
        f = folder.GetFile(filename)
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {path}')

        checked_out = bool(f.IsLocked)
        checked_out_by = None
        if checked_out:
            try:
                checked_out_by = f.LockedByUser.Name
            except Exception:
                pass

        return {
            'name':           f.Name,
            'path':           path,
            'state':          f.CurrentState.Name,
            'revision':       f.CurrentRevision,
            'version':        f.CurrentVersion,
            'checked_out':    checked_out,
            'checked_out_by': checked_out_by,

        }

    # ------------------------------------------------------------------
    # File download
    # ------------------------------------------------------------------

    def download_file(self, src_path: str, dest_folder: str, dest_name: str = None,
                      version: int = None) -> str:
        """Download a file from the vault to a local folder.

        Uses ``IEdmFile5.GetFileCopy`` which copies the file content from the
        PDM server to ``dest_folder`` without checking it out. Works for both
        locally-cached and off-site (non-cached) vault files.

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
        version : int, optional
            Specific version number to download. Defaults to the current
            (latest) version.

        Returns
        -------
        str
            Full path of the downloaded file.
        """
        self._require_connection()
        folder_path, filename = self._split_path(src_path)
        folder = self._get_folder(folder_path)
        f = folder.GetFile(filename)
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {src_path}')

        os.makedirs(dest_folder, exist_ok=True)
        ver = version if version is not None else f.CurrentVersion

        # GetFileCopy(lParentWnd, poVersionNoOrRevisionName, poPathOrFolderID,
        #             lEdmGetFlags, bsNewName)
        # poPathOrFolderID must be the vault folder's integer .ID (not a string
        # path) — passing a BSTR string causes com_error "Member not found".
        # lEdmGetFlags=16 → EdmGet_UseLocalRootFolder (standard get, no extra refs)
        # The call triggers a sync/download if needed; the file ends up at its
        # local vault-cache path (src_path).  The return value is None when the
        # file was already cached; otherwise it is the downloaded path.
        vault_local_path = f.GetFileCopy(0, ver, folder.ID, 16, '')

        # Resolve the actual local path: prefer the return value, fall back to src_path
        if vault_local_path and os.path.exists(vault_local_path):
            resolved_path = vault_local_path
        elif os.path.exists(src_path):
            resolved_path = src_path
        else:
            raise RuntimeError(
                f'GetFileCopy did not produce a file. '
                f'Return value: {vault_local_path!r}'
            )

        # Copy from vault cache to the requested destination
        final_name = dest_name or filename
        final_path = os.path.join(dest_folder, final_name)
        shutil.copy2(resolved_path, final_path)
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
        mgr = win.CastTo(self._client, 'IEdmVariableMgr5')
        pos = mgr.GetFirstVariablePosition()
        names = []
        while not pos.IsNull:
            var = mgr.GetNextVariable(pos)
            names.append(var.Name)
        self._variable_names_cache = names
        return names

    def get_file_variables(self, path: str, var_names: list = None, config: str = '',
                           skip_empty: bool = True) -> dict:
        """Return PDM data card variable values for a file.

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
        folder_path, filename = self._split_path(path)
        folder = self._get_folder(folder_path)
        f = folder.GetFile(filename)
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {path}')

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

    def checkout(self, path: str) -> None:
        """Check out a file. No-op if already checked out."""
        self._require_connection()
        folder_path, filename = self._split_path(path)
        folder = self._get_folder(folder_path)
        f = folder.GetFile(filename)
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {path}')
        if f.IsLocked:
            return
        f.LockFile(folder.ID, 0)

    def checkin(self, path: str, comment: str = '') -> None:
        """Check in a file. No-op if already checked in."""
        self._require_connection()
        folder_path, filename = self._split_path(path)
        folder = self._get_folder(folder_path)
        f = folder.GetFile(filename)
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {path}')
        if not f.IsLocked:
            return
        f.UnlockFile(0, comment)

    def undo_checkout(self, path: str) -> None:
        """Revert a checkout without saving changes."""
        self._require_connection()
        folder_path, filename = self._split_path(path)
        folder = self._get_folder(folder_path)
        f = folder.GetFile(filename)
        if f is None:
            raise FileNotFoundError(f'PDM file not found: {path}')
        if not f.IsLocked:
            return
        f.UndoLockFile(0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connection(self) -> None:
        if self._client is None:
            raise RuntimeError('Not connected to PDM vault. Call connect() first.')

    def _get_folder(self, path: str):
        """Return an IEdmFolder5 for the given path, raising if not found."""
        folder = self._client.GetFolderFromPath(path)
        if folder is None:
            raise FileNotFoundError(f'PDM folder not found: {path}')
        return folder

    @staticmethod
    def _split_path(path: str) -> tuple:
        """Split a full file path into (folder_path, filename)."""
        return os.path.dirname(path), os.path.basename(path)

    def _walk(self, path: str, results: list) -> None:
        """Recursively populate ``results`` with file and folder entries."""
        folder = self._get_folder(path)

        pos = folder.GetFirstFilePosition()
        while not pos.IsNull:
            f = folder.GetNextFile(pos)
            results.append({'path': os.path.join(path, f.Name), 'name': f.Name, 'type': 'file'})

        pos = folder.GetFirstSubFolderPosition()
        while not pos.IsNull:
            sub = folder.GetNextSubFolder(pos)
            sub_path = os.path.join(path, sub.Name)
            results.append({'path': sub_path, 'name': sub.Name, 'type': 'folder'})
            self._walk(sub_path, results)


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
        {'key': 'd', 'name': 'List Dir Root',      'function': 'list_dir_root',      'inputs': []},
        {'key': 'e', 'name': 'List Dir Recursive', 'function': 'list_dir_recursive', 'inputs': [
            {'label': 'Path', 'name': 'path', 'type': str, 'default': r'C:\PDM Vault', 'width': '100px'},
        ]},
        {'key': 'f', 'name': 'Find Files',         'function': 'find_files',         'inputs': [
            {'label': 'Root Path',     'name': 'root_path',     'type': str, 'default': r'C:\PDM Vault\Master Data Record\FISHER', 'width': '100px'},
            {'label': 'Extension',     'name': 'extension',     'type': str, 'default': '', 'width': '50px', 'placeholder': 'e.g. .SLDPRT', 'allow_empty': True},
            {'label': 'Name Contains', 'name': 'name_contains', 'type': str, 'default': 'GK10608', 'width': '100px'},
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
