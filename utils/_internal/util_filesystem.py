import os
import shutil
import tempfile
from collections import namedtuple


class UtilityFilesystemMixin:
    def create_directory(self, path):
        if os.path.exists(path):
            if os.path.isfile(path):
                raise FileExistsError(f"A file with the name '{path}' already exists.")
        os.makedirs(path, exist_ok=True)

    def remove_directory(self, path, force=False):
        if os.path.exists(path):
            if os.path.isfile(path):
                raise FileNotFoundError(f"Cannot remove '{path}' because it is a file.")
            if force:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
        else:
            raise FileNotFoundError(f"Directory '{path}' does not exist.")

    def remove_file(self, path):
        if os.path.exists(path):
            if os.path.isdir(path):
                raise FileNotFoundError(f"Cannot remove '{path}' because it is a directory.")
            os.remove(path)
        else:
            raise FileNotFoundError(f"File '{path}' does not exist.")

    def read_file(self, path, binary=False):
        mode = 'rb' if binary else 'r'
        with open(path, mode) as file:
            return file.read()

    def write_file(self, path, content, overwrite=False, auto_create_dir=True):
        mode = 'w' if overwrite else 'a'

        if isinstance(content, bytes):
            mode = mode + 'b'

        if auto_create_dir and (dir_part := os.path.dirname(path)):
            self.create_directory(dir_part)

        if not overwrite and not isinstance(content, bytes):
            try:
                with open(path, 'r') as file:
                    file.seek(0, os.SEEK_END)
                    if file.tell() > 0:
                        file.seek(file.tell() - 1)
                        last_char = file.read(1)
                        if last_char != '\n':
                            content = '\n' + content
            except FileNotFoundError:
                pass

        with open(path, mode) as file:
            file.write(content)

    def list_dir_contents(self, directory='.', ext='', recursive=False):
        FileListResult = namedtuple('FileListResult', ['files', 'dirs'])

        filelist = []
        dirlist = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(ext.lower()):
                    filelist.append(os.path.join(root, file))
            for dir in dirs:
                dirlist.append(os.path.join(root, dir))
            if not recursive:
                break

        return FileListResult(filelist, dirlist)

    # Return only the files list from list_dir_contents.
    def list_files(self, directory: str = '.', ext: str = '', recursive: bool = False) -> list[str]:
        return self.list_dir_contents(directory=directory, ext=ext, recursive=recursive).files

    # Check if a file exists, optionally printing a message when missing.
    def file_exists(self, path: str, verbose: bool = False) -> bool:
        if not os.path.isfile(path):
            if verbose:
                print(f"File '{path}' not found.")
            return False
        return True

    # List subdirectories under path; wraps list_files to reuse its walk logic.
    def list_folders(self, path: str = '.', recursive: bool = False) -> list[str]:
        return self.list_dir_contents(directory=path, recursive=recursive).dirs

    # Return the filename (with extension) from a path.
    def get_filename(self, file_path: str) -> str:
        return os.path.basename(file_path)

    # Return the filename without extension from a path.
    def get_basename(self, file_path: str) -> str:
        return os.path.splitext(os.path.basename(file_path))[0]

    # Return the file extension (including dot) from a path.
    def get_extension(self, file_path: str) -> str:
        return os.path.splitext(file_path)[1]

    # Return the absolute path.
    def get_abs_path(self, file_path: str) -> str:
        return os.path.abspath(file_path)

    # Return the directory component of a path.
    def get_dir_path(self, file_path: str) -> str:
        return os.path.dirname(file_path)

    def create_temp_dir(self):
        dir = tempfile.mkdtemp()
        self.temporary_dir_list.add(dir)
        return dir

    def remove_temp_dir(self, temp_dir):
        if temp_dir in self.temporary_dir_list:
            shutil.rmtree(temp_dir)
            self.temporary_dir_list.remove(temp_dir)

    def remove_all_temp_dirs(self):
        for dir in self.temporary_dir_list:
            shutil.rmtree(dir)
        self.temporary_dir_list.clear()

    # If a directory contains exactly one subdirectory and no loose files, return
    # that subdirectory — handles archives that wrap everything in a base folder.
    # Otherwise returns the original directory unchanged.
    def unwrap_single_dir_archive(self, extract_dir: str) -> str:
        entries = os.listdir(extract_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
            return os.path.join(extract_dir, entries[0])
        return extract_dir

    # Returns files present in dest_dir but absent in source_dir (relative paths).
    def find_orphaned_files(self, source_dir: str, dest_dir: str) -> list[str]:
        def relative_files(directory: str) -> set[str]:
            result = set()
            for root, _, files in os.walk(directory):
                for f in files:
                    abs_path = os.path.join(root, f)
                    result.add(os.path.relpath(abs_path, directory))
            return result

        source_files = relative_files(source_dir)
        dest_files = relative_files(dest_dir)
        return sorted(dest_files - source_files)

    # Generic named-placeholder formatter for structured file/directory naming,
    # e.g. build_structured_filename('{provider}_{account_no}_{period}.pdf', provider='TNB', account_no='123', period='202607').
    # Field values are sanitized (path separators stripped) so a stray '/' or '\' in a
    # field can't split into an unintended extra path segment; the template's own
    # separators are left untouched.
    def build_structured_filename(self, template: str, **fields) -> str:
        safe_fields = {k: str(v).replace('/', '_').replace('\\', '_') for k, v in fields.items()}
        return template.format(**safe_fields)

    def calculate_file_hash(self, file_path, hash_algorithm='md5'):
        import hashlib

        hash_func = getattr(hashlib, hash_algorithm, None)
        if hash_func is None:
            raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}")

        hasher = hash_func()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
