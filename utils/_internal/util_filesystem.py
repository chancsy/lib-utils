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

        if auto_create_dir:
            self.create_directory(os.path.dirname(path))

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

    def list_files(self, directory='.', ext='', recursive=False):
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
