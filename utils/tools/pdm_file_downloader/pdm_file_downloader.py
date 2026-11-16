# %% [markdown]
# # PDM File Downloader
# Search a SolidWorks PDM vault by item name (several at once, comma-separated, `*` `?` wildcards),
# filter / sort the results, optionally read each file's data-card Revision, and download copies of
# the selected files (no checkout).
#
# Needs the SolidWorks PDM client and pywin32 on this PC. If either is missing, only a warning and a
# **Show UI anyway** button are shown.
#
# Run this notebook, or from code:
# `from utils.tools.pdm_file_downloader.pdm_file_downloader import show_gui; display(show_gui(vault='PDM Vault', look_in=r'C:\PDM Vault\Projects'))`

# %%
import os

from IPython.display import display

from utils import UtilityFunctions
from utils.standalone.solidworks_pdm_utils import SolidWorksPDM
from utils.tools.pdm_file_downloader import DEFAULT_DEST, DEFAULT_VAULT, download_files, is_markup, pdm_missing

utils = UtilityFunctions()
_NBSP = '\u00a0'  # pads the result columns: <select> options collapse normal whitespace
SORT_KEYS = {
    'Filename': lambda r: utils.natural_sort_key(r['name']),
    'Rev':      lambda r: (len(r['rev']), r['rev']),  # A..Z, AA, AB, ...
    'State':    lambda r: r['state'].lower(),
    'Size':     lambda r: r['size'],
    'Date':     lambda r: r['date'],
    'Path':     lambda r: utils.natural_sort_key(r['path']),
}


class PdmFileDownloaderGUI:
    """vault: PDM vault name. look_in: folder to search under (None or blank: the vault's root folder).
    dest: download folder."""

    def __init__(self, vault: str = DEFAULT_VAULT, look_in: str = None, dest: str = DEFAULT_DEST):
        from utils.standalone.widget_utils import Widgets
        self.w = w = Widgets()
        w.show_widget_on_create = False
        self.vault = vault
        self.pdm = None        # SolidWorksPDM, made on first use (needs pywin32)
        self.connected = False
        self.results = []      # dicts from pdm.search_files(details=True), plus 'rev'

        label_style = {'description_width': '90px'}
        css = w.HTML('<style>.pdm-results select, .pdm-results { font-family: monospace; }</style>')
        self.search_text  = w.Text(desc='Item name(s):', placeholder='comma-separated, * ? wildcards - e.g. AB12345, AB12346*.pdf, AB12347_A*', width='600px', style=label_style)
        self.look_in_text = w.Text(desc='Look in:', value=look_in or '', placeholder=f'blank: the root folder of vault "{vault}"', width='600px', style=label_style)
        self.dest_text    = w.Text(desc='Download to:', value=dest, width='600px', style=label_style)
        self.search_button = w.Button(desc='Search', icon='search', cb=self.search_press, width='120px')
        self.read_rev_checkbox = w.Checkbox(desc='Read revisions (slower)', value=False, width='200px')
        self.hide_markups_checkbox = w.Checkbox(desc='Hide markups (_MU*)', value=False, width='170px', cb=self.refresh_list)
        self.type_dropdown = w.Dropdown(desc='Type:', options=['All'], value='All', width='150px', style={'description_width': '40px'}, cb=self.refresh_list)
        self.sort_dropdown = w.Dropdown(desc='Sort by:', options=list(SORT_KEYS), value='Filename', width='170px', style={'description_width': '55px'}, cb=self.refresh_list)
        self.descending_checkbox = w.Checkbox(desc='Descending', value=False, width='110px', cb=self.refresh_list)
        self.results_header = w.Label()
        self.results_header.add_class('pdm-results')
        self.results_select = w.SelectMultiple(rows=15, width='100%', cb=self.update_selected_count)
        self.results_select.add_class('pdm-results')
        self.select_all_button  = w.Button(desc='Select all', cb=self.select_all_press, width='100px')
        self.select_none_button = w.Button(desc='Select none', cb=self.select_none_press, width='100px')
        self.selected_label = w.Label()
        self.download_button = w.Button(desc='Download selected', icon='download', cb=self.download_press, width='160px')
        self.overwrite_checkbox = w.Checkbox(desc='Overwrite existing', value=False, width='150px')
        self.progress_bar = w.IntProgress(value=0, min=0, max=1, width='400px')
        self.progress_label = w.Label()
        self.status_html = w.HTML()
        self.set_progress(0, 0)
        self.refresh_list()

        self.input_widgets = [self.search_text, self.look_in_text, self.dest_text, self.search_button, self.read_rev_checkbox,
                              self.hide_markups_checkbox, self.type_dropdown, self.sort_dropdown, self.descending_checkbox,
                              self.results_select, self.select_all_button, self.select_none_button, self.download_button,
                              self.overwrite_checkbox]
        self.main_ui = w.VBox([
            css,
            w.HBox([self.search_text, self.search_button, self.read_rev_checkbox]),
            self.look_in_text,
            self.dest_text,
            w.HBox([self.hide_markups_checkbox, self.type_dropdown, self.sort_dropdown, self.descending_checkbox]),
            self.results_header,
            self.results_select,
            w.HBox([self.select_all_button, self.select_none_button, self.selected_label]),
            w.HBox([self.download_button, self.overwrite_checkbox, self.progress_bar, self.progress_label]),
            self.status_html,
        ])

        # Startup check: without the PDM client / pywin32 show only a warning and "Show UI anyway".
        problem = pdm_missing()
        self.warning_html = w.HTML(f'<span style="color:#c0392b">&#9888; {problem}</span>' if problem else '')
        self.show_anyway_button = w.Button(desc='Show UI anyway', cb=self.show_anyway_press, width='160px')
        if problem:
            self.main_ui.layout.display = 'none'
        else:
            self.warning_html.layout.display = 'none'
            self.show_anyway_button.layout.display = 'none'
        self.ui = w.VBox([self.warning_html, self.show_anyway_button, self.main_ui])

    # ── helpers ──────────────────────────────────────────────────────────────
    def show_anyway_press(self, sender):
        self.show_anyway_button.layout.display = 'none'
        self.main_ui.layout.display = ''

    def ensure_connected(self):
        if self.pdm is None:
            try:
                self.pdm = SolidWorksPDM(self.vault)
            except SystemExit:  # SolidWorksPDM exits when pywin32 is missing
                raise RuntimeError('pywin32 is not installed (pip install pywin32)') from None
        if not self.connected:
            self.set_status(f'Connecting to PDM vault "{self.vault}"...')
            self.connected = self.pdm.connect()
            if not self.connected:
                raise RuntimeError(f'Could not connect to PDM vault "{self.vault}"')

    def set_status(self, msg, color=None):
        self.status_html.value = f'<span style="color:{color}">{msg}</span>' if color else msg

    def set_progress(self, done, total):
        self.progress_bar.max = max(total, 1)
        self.progress_bar.value = done
        pct = done / total * 100 if total else 0
        self.progress_label.value = f'{done}/{total} downloaded ({pct:.0f}%)'

    def visible_results(self):
        rows = [r for r in self.results
                if not (self.hide_markups_checkbox.value and is_markup(r['name']))
                and (self.type_dropdown.value in (None, 'All') or os.path.splitext(r['name'])[1].lower() == self.type_dropdown.value)]
        return sorted(rows, key=SORT_KEYS[self.sort_dropdown.value], reverse=self.descending_checkbox.value)

    def refresh_list(self, change=None):
        rows = self.visible_results()
        cols = [('Filename', lambda r: r['name'])]
        if any(r['rev'] for r in self.results):
            cols.append(('Rev', lambda r: r['rev']))
        cols += [
            ('State', lambda r: r['state']),
            ('Size',  lambda r: f'{r["size"] / 1024:,.0f} KB'),
            ('Date',  lambda r: r['date'].strftime('%Y-%m-%d %H:%M')),
        ]
        widths = [max([len(title)] + [len(get(r)) for r in rows]) + 3 for title, get in cols]
        pad = lambda s, n: s.ljust(n).replace(' ', _NBSP)
        self.results_header.value = ''.join(pad(t, n) for (t, _), n in zip(cols, widths)) + 'Path'
        selected = set(self.results_select.value)
        self.results_select.options = [(''.join(pad(get(r), n) for (_, get), n in zip(cols, widths)) + r['path'], r['path']) for r in rows]
        self.results_select.value = tuple(r['path'] for r in rows if r['path'] in selected)
        self.update_selected_count()

    def update_selected_count(self, change=None):
        hidden = len(self.results) - len(self.results_select.options)
        self.selected_label.value = (f'{len(self.results_select.value)} of {len(self.results_select.options)} selected'
                                     + (f' ({hidden} hidden by filters)' if hidden else ''))

    # ── actions ──────────────────────────────────────────────────────────────
    def search_press(self, sender):
        terms = [t.strip() for t in self.search_text.value.split(',') if t.strip()]
        if not terms:
            self.set_status('Enter a search term.', 'red')
            return
        self.w.disable_widget_group(self.input_widgets)
        try:
            self.ensure_connected()
            if not self.look_in_text.value.strip():
                self.look_in_text.value = self.pdm.root_folder()
            look_in = self.look_in_text.value.strip()
            self.set_status(f'Searching for {", ".join(terms)} under {look_in} ...')
            self.results = [{**r, 'rev': ''} for r in self.pdm.search_files(look_in, terms, details=True)]
            exts = sorted({os.path.splitext(r['name'])[1].lower() for r in self.results} - {''})
            if self.type_dropdown.value not in exts:
                self.type_dropdown.value = 'All'
            self.type_dropdown.options = ['All'] + exts
            self.refresh_list()
            if self.read_rev_checkbox.value:
                # One server round trip per file (~0.6-0.8 s each); no batch API usable from pywin32.
                # Only the rows currently shown (i.e. after filters) are read.
                rows = self.visible_results()
                for r in rows:
                    r['rev'] = '...'
                for i, r in enumerate(rows, 1):
                    self.set_status(f'{len(self.results)} file(s) found. Reading revision {i}/{len(rows)} ...')
                    try:
                        r['rev'] = self.pdm.get_file_variables(r['path'], var_names=['Revision'], skip_empty=False).get('Revision') or '-'
                    except Exception:
                        r['rev'] = '?'
                    self.refresh_list()
            self.set_status(f'{len(self.results)} file(s) found. Select file(s) to download (Ctrl/Shift+click for multiple).')
        except Exception as e:
            self.set_status(f'Search failed: {e}', 'red')
        finally:
            self.w.enable_widget_group(self.input_widgets)

    def select_all_press(self, sender):
        self.results_select.value = tuple(v for _, v in self.results_select.options)

    def select_none_press(self, sender):
        self.results_select.value = ()

    def download_press(self, sender):
        selected = list(self.results_select.value)
        if not selected:
            self.set_status('Select at least one file to download.', 'red')
            return
        dest = self.dest_text.value.strip()
        self.w.disable_widget_group(self.input_widgets)
        try:
            self.ensure_connected()

            def progress(done, total, name):
                self.set_progress(done, total)
                if name:
                    self.set_status(f'Downloading {name} ...')

            _, skipped, failed = download_files(self.pdm, selected, dest, self.overwrite_checkbox.value, progress)
            msgs = []
            if skipped:
                msgs.append(f'{len(skipped)} file(s) already exist in {dest}, skipped (tick "Overwrite existing" to replace):<br>' + '<br>'.join(skipped))
            if failed:
                msgs.append(f'{len(failed)} download(s) failed:<br>' + '<br>'.join(failed))
            if msgs:
                self.set_status('<br>'.join(msgs), 'red' if failed else 'orange')
            else:
                self.set_status(f'Done. Saved to {dest}', 'green')
        except Exception as e:
            self.set_status(f'Download failed: {e}', 'red')
        finally:
            self.w.enable_widget_group(self.input_widgets)


def show_gui(**kwargs):
    """Build the PDM File Downloader UI and return its top-level widget (for embedding, e.g. tools_launcher).

    kwargs (all optional): vault (PDM vault name, default 'PDM Vault'), look_in (folder to search under;
    None: the vault's root folder), dest (download folder). An unknown key raises TypeError.
    """
    return PdmFileDownloaderGUI(**kwargs).ui


# %%
if __name__ == '__main__':
    display(show_gui())
