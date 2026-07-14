import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()

import os

class PdfUtils:
    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require pikepdf - only actually instantiating
        # PdfUtils does. Cached on self so the methods below don't need their own import
        # statements.
        utils.exit_if_module_missing('pikepdf')
        import pikepdf
        self._pikepdf = pikepdf

    # check if pdf is password protected
    def is_encrypted(self, file):
        try:
            pdf = self._pikepdf.open(file)
            pdf.close()
            return False
        except self._pikepdf.PasswordError:
            return True

    # open pdf if not password protected
    def open(self, file):
        try:
            pdf = self._pikepdf.open(file)
            pdf.close()
            return pdf
        except self._pikepdf.PasswordError:
            return None

    # # extract text from pdf
    # def extract_text2(self, file):
    #     with self._pikepdf.Pdf.open(file) as my_pdf:
    #         for page in my_pdf.pages:
    #             page.rotate(180, relative=True)
    #         my_pdf.save('test-rotated.pdf')

    # decrypt pdf
    def decrypt(self, file: str = None, password: str = None, output: str = None, replace_original: bool = False, ui: bool = False):
        _ui = None
        if ui:
            from .ui_utils import UIUtils
            _ui = UIUtils()
            file = file or _ui.open_filedialog(filetypes=(('PDF files', '*.pdf'),))
            if not file:
                print('No file specified.')
                return None

        # Early return if file is not encrypted — check before prompting for password/output.
        try:
            with self._pikepdf.Pdf.open(file) as pdf:
                pass
            print(f'File is not encrypted - "{file}"')
            return None
        except self._pikepdf.PasswordError:
            pass

        if ui:
            if not password:
                password = _ui.prompt_user_password(min_password_len=1)
                if not password:
                    return None
            if not output:
                basename = os.path.splitext(os.path.basename(file))[0]
                output = _ui.save_as_filedialog(
                    filetypes=(('PDF files', '*.pdf'),), initialfile=f'{basename}.pdf'
                )
                if not output:
                    print('No output file specified.')
                    return None

        try:
            if not replace_original:
                pdf = self._pikepdf.open(file, password=password)
            else:
                pdf = self._pikepdf.open(file, password=password, allow_overwriting_input=True)
            if output:
                pdf.save(output)
            # if not output, save to the same file_decrypted.pdf suffix or overwrite the original file if replace_original is True
            else:
                if replace_original:
                    pdf.save(file)
                else:
                    pdf.save(file.replace('.pdf', '_decrypted.pdf'))
            pdf.close()
            return True
        except self._pikepdf.PasswordError:
            print("Invalid password")
            return self._pikepdf.PasswordError

    # Encrypt a PDF with the given password; saves to output path or <basename>_encrypted.pdf.
    def encrypt(self, file: str = None, password: str = None, output: str = None, ui: bool = False) -> None:
        _ui = None
        if ui:
            from .ui_utils import UIUtils
            _ui = UIUtils()
            file = file or _ui.open_filedialog(filetypes=(('PDF files', '*.pdf'),))
            if not file:
                print('No file specified.')
                return

        # Early return if file is already encrypted — check before prompting for password/output.
        try:
            with self._pikepdf.open(file) as pdf:
                pass
        except self._pikepdf.PasswordError:
            print(f'PDF is already encrypted - "{file}"')
            return

        if ui:
            if not password:
                password = _ui.prompt_user_password_twice_matching(min_password_len=1)
                if not password:
                    return
            if not output:
                basename = os.path.splitext(os.path.basename(file))[0]
                output = _ui.save_as_filedialog(
                    filetypes=(('PDF files', '*.pdf'),), initialfile=f'{basename}_encrypted.pdf'
                )
                if not output:
                    print('No output file specified.')
                    return

        with self._pikepdf.open(file, allow_overwriting_input=True) as pdf:
            out_path = output or file.replace('.pdf', '_encrypted.pdf')
            pdf.save(out_path, encryption=self._pikepdf.Encryption(
                user=password, owner=password,
                allow=self._pikepdf.Permissions(extract=False),
            ))

    # Merge a list of PDF files or all PDFs in a directory (non-recursive) into output.
    # Prompts for confirmation before merging in both CLI and UI paths.
    def merge_files(self, files: list[str] = None, dir_path: str = None, output: str = None, ui: bool = False) -> None:
        if ui:
            from .ui_utils import UIUtils
            _ui = UIUtils()
            if not files and not dir_path:
                selected = _ui.open_filedialog(allow_multiple=True, filetypes=(('PDF files', '*.pdf'),))
                files = list(selected) if selected else []
                if not files:
                    print('No files specified.')
                    return
            if not output:
                basename = os.path.splitext(os.path.basename((files or ['merged'])[-1]))[0]
                output = _ui.save_as_filedialog(
                    filetypes=(('PDF files', '*.pdf'),), initialfile=f'{basename}.pdf'
                )
                if not output:
                    print('No output file specified.')
                    return

        if dir_path and not files:
            files = sorted(utils.list_dir_contents(dir_path, 'pdf').files, key=utils.natural_sort_key)

        if not files:
            print('No PDF files found.')
            return
        if not output:
            print('No output file specified.')
            return

        # Confirmation before merge
        print(f'Files to merge ({len(files)}):')
        for f in files:
            print(f'  {f}')
        print(f'Output: {output}')
        if input('Confirm merge? (yes/no): ').strip().lower() != 'yes':
            print('Merge cancelled.')
            return

        pdf = self._pikepdf.Pdf.new()
        try:
            for file in files:
                with self._pikepdf.open(file) as src:
                    pdf.pages.extend(src.pages)
            if not output.endswith('.pdf'):
                output += '.pdf'
            pdf.save(output)
            print(output)
        except Exception as e:
            print(f'Error performing merge: {e}')
        finally:
            pdf.close()

    # Split PDF(s) into per-page files, or extract specific pages into one file if pages spec is given.
    # pages: comma-separated page numbers and/or ranges, e.g. "1,2,4" or "1-4,6" (1-based).
    def split(self, file: str = None, output_dir: str = None, pages: str = None, ui: bool = False) -> None:
        if ui:
            from .ui_utils import UIUtils
            selected = UIUtils().open_filedialog(allow_multiple=True, filetypes=(('PDF files', '*.pdf'),))
            files = list(selected) if selected else []
            if not files:
                print('No file specified.')
                return
            for f in files:
                self.split(f, output_dir, pages)
            return
        out_dir = output_dir or os.path.dirname(file)
        basename = os.path.splitext(os.path.basename(file))[0]
        try:
            with self._pikepdf.open(file) as src:
                if pages:
                    # parse 1-based page spec (supports "-" ranges e.g. "1-4,6") and convert to 0-based
                    indices = [p - 1 for p in utils.parse_range_string(pages, range_sep='-')]
                    dest = self._pikepdf.Pdf.new()
                    for idx in indices:
                        dest.pages.append(src.pages[idx])
                    safe_pages = pages.replace(',', '_')
                    out_path = os.path.join(out_dir, f'{basename}_p{safe_pages}.pdf')
                    print(out_path)
                    dest.save(out_path)
                    dest.close()
                else:
                    for n, page in enumerate(src.pages):
                        dest = self._pikepdf.Pdf.new()
                        dest.pages.append(page)
                        out_path = os.path.join(out_dir, f'{basename}_{n:02d}.pdf')
                        print(out_path)
                        dest.save(out_path)
                        dest.close()
        except Exception as e:
            print(f'Error performing split: {e}')

    # lib_demo_params drives both the CLI (via utils.demo()) and the GUI (via build_lib_demo_widget()).
    # Replaces the old lib_demo_dict + lib_demo() pair.
    lib_demo_params = [
        {'key': 'a', 'name': 'Test PDF encryption', 'function': 'is_encrypted', 'inputs': [
            {'label': 'File', 'name': 'file', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'b', 'name': 'Open PDF', 'function': 'open', 'inputs': [
            {'label': 'File', 'name': 'file', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'c', 'name': 'Decrypt PDF', 'function': 'decrypt', 'inputs': [
            {'label': 'File', 'name': 'file', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Password', 'name': 'password', 'type': str, 'password': True, 'default': '', 'width': '80px'},
            {'label': 'Output', 'name': 'output', 'type': str, 'default': '', 'placeholder': 'blank=auto', 'width': '150px', 'allow_empty': True},
            {'label': 'Replace original', 'name': 'replace_original', 'options': [False, True], 'default': False},
        ]},
        # UI variant — opens file/save dialogs and password prompt.
        {'key': 'C', 'name': 'Decrypt PDF (UI)',
         'function': lambda self: self.decrypt(ui=True), 'inputs': []},
        {'key': 'd', 'name': 'Encrypt PDF', 'function': 'encrypt', 'inputs': [
            {'label': 'File', 'name': 'file', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Password', 'name': 'password', 'type': str, 'password': True, 'default': '', 'width': '80px'},
            {'label': 'Output', 'name': 'output', 'type': str, 'default': '', 'placeholder': 'blank=auto', 'width': '150px', 'allow_empty': True},
        ]},
        # UI variant — opens file/save dialogs and double-entry password prompt.
        {'key': 'D', 'name': 'Encrypt PDF (UI)',
         'function': lambda self: self.encrypt(ui=True), 'inputs': []},
        # Merge from a directory — all PDFs in dir_path merged into output.
        {'key': 'e', 'name': 'Merge PDFs (directory)', 'function': 'merge_files', 'inputs': [
            {'label': 'Directory', 'name': 'dir_path', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Output file', 'name': 'output', 'type': str, 'default': '', 'width': '150px'},
        ]},
        # Merge from a comma-separated file list — uses a lambda to split the string into a list.
        {'key': 'f', 'name': 'Merge PDFs (file list)',
         'function': lambda self, files, output: self.merge_files(
             files=[f.strip() for f in files.split(',') if f.strip()], output=output),
         'inputs': [
            {'label': 'Files', 'name': 'files', 'type': str, 'default': '', 'placeholder': 'comma-separated', 'width': '150px'},
            {'label': 'Output file', 'name': 'output', 'type': str, 'default': '', 'width': '150px'},
        ]},
        # UI variant — opens multi-file picker and save dialog.
        {'key': 'F', 'name': 'Merge PDFs (UI)',
         'function': lambda self: self.merge_files(ui=True), 'inputs': []},
        {'key': 'g', 'name': 'Split PDF', 'function': 'split', 'inputs': [
            {'label': 'File', 'name': 'file', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Output dir', 'name': 'output_dir', 'type': str, 'default': '', 'placeholder': 'blank=same folder', 'width': '150px', 'allow_empty': True},
            {'label': 'Pages', 'name': 'pages', 'type': str, 'default': '', 'placeholder': 'e.g. 1,2,4 or 1-4,6 (blank=split all)', 'width': '220px', 'allow_empty': True},
        ]},
        # UI variant — opens multi-file picker; output dir defaults to same folder as each file.
        {'key': 'G', 'name': 'Split PDF (UI)',
         'function': lambda self: self.split(ui=True), 'inputs': []},
    ]

if __name__ == "__main__":
    pdf_utils = PdfUtils()
    utils.demo(pdf_utils)
