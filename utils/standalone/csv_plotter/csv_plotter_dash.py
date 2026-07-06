"""
CSV Graph Plotter - Dash Web Application

Interactive web-based CSV data plotter with SPC statistical analysis.
Launch: python csv_plotter_dash.py [--port 8050] [--file path/to/data.csv]

Features:
- Load multiple CSV/delimited files with auto-detect delimiter
- Select columns to plot (starts with none selected)
- Set USL/LSL limits per column with red highlighting for out-of-spec points
- Basic statistics (count, mean, std, min, max, median, range)
- SPC statistics (Cp, Cpk, Pp, Ppk) with threshold highlighting
- Rolling windowed statistics by sample count or time duration
- Auto-refresh with file change monitoring (incremental loading)
- Save/load limit configurations as JSON
"""

import os
import sys
import json
import argparse
import base64
from io import StringIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dash import Dash, dcc, html, dash_table, callback_context, no_update
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from csv_plotter import CSVDataManager, StatisticsEngine, ConfigManager, FileMonitor

# ──────────────────────────────────────────────────────────────────────────────
# Globals
# ──────────────────────────────────────────────────────────────────────────────

data_mgr = CSVDataManager()
file_mon = FileMonitor()
stats_engine = StatisticsEngine()
config_mgr = ConfigManager()

# Color palette for traces
TRACE_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
]

# ──────────────────────────────────────────────────────────────────────────────
# App Layout
# ──────────────────────────────────────────────────────────────────────────────

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = 'CSV Graph Plotter'

app.layout = html.Div([
    # ── Stores ──
    dcc.Store(id='loaded-files', data=[]),         # list of loaded file paths
    dcc.Store(id='limits-store', data={}),         # {col: {usl, lsl, stat_limits}}
    dcc.Store(id='trigger-plot-update', data=0),   # counter to trigger plot refresh
    dcc.Store(id='ui-settings-store', data={}),    # _ui_settings from loaded config

    # ── Top Bar ──
    html.Div([
        html.H3('CSV Graph Plotter', style={'margin': '0 20px 0 0', 'whiteSpace': 'nowrap'}),
        # Typed path input
        dcc.Input(
            id='file-path-input',
            type='text',
            placeholder='Paste file path or drag & drop below...',
            style={'flex': '1', 'marginRight': '8px', 'padding': '6px 10px',
                   'fontSize': '14px', 'border': '1px solid #ccc', 'borderRadius': '4px'},
            debounce=True,
        ),
        html.Button('Add File', id='add-file-btn', n_clicks=0,
                     style={'padding': '6px 16px', 'fontSize': '14px',
                            'cursor': 'pointer', 'borderRadius': '4px',
                            'border': '1px solid #2196F3', 'background': '#2196F3',
                            'color': 'white', 'marginRight': '8px'}),
        # Drag-and-drop CSV zone
        dcc.Upload(
            id='upload-csv',
            children=html.Span('Drop CSV here', style={'pointerEvents': 'none'}),
            multiple=True,
            style={
                'padding': '6px 12px', 'fontSize': '13px', 'cursor': 'pointer',
                'borderRadius': '4px', 'border': '2px dashed #2196F3',
                'background': '#e3f2fd', 'color': '#1565c0',
                'whiteSpace': 'nowrap', 'lineHeight': '1.4', 'marginRight': '8px',
            },
        ),
        html.Button('Remove All', id='remove-all-btn', n_clicks=0,
                     style={'padding': '6px 12px', 'fontSize': '14px',
                            'cursor': 'pointer', 'borderRadius': '4px',
                            'border': '1px solid #f44336', 'background': '#f44336',
                            'color': 'white'}),
    ], style={'display': 'flex', 'alignItems': 'center', 'padding': '10px 16px',
              'borderBottom': '1px solid #ddd', 'background': '#fafafa'}),

    # ── Loaded files chips ──
    html.Div(id='loaded-files-display',
             style={'padding': '6px 16px', 'display': 'flex', 'flexWrap': 'wrap', 'gap': '6px'}),

    # ── Status message ──
    html.Div(id='status-message',
             style={'padding': '4px 16px', 'color': '#666', 'fontSize': '13px'}),

    # ── Main Content ──
    html.Div([
        # ── Left Sidebar ──
        html.Div([
            # --- Column Selection ---
            html.Label('X-Axis Column', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            dcc.Dropdown(id='x-axis-dropdown', placeholder='Index (default)',
                         style={'marginBottom': '12px'}),

            html.Label('Y-Axis Columns', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            dcc.Dropdown(id='y-axis-dropdown', multi=True, placeholder='Select columns...',
                         style={'marginBottom': '16px'}),

            html.Hr(),

            # --- Limits ---
            html.Label('Column Limits', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            html.Div(id='limits-inputs-container', style={'marginBottom': '12px'}),
            html.Button('Apply Limits', id='apply-limits-btn', n_clicks=0,
                         style={'width': '100%', 'padding': '6px', 'marginBottom': '16px',
                                'cursor': 'pointer', 'borderRadius': '4px',
                                'border': '1px solid #4CAF50', 'background': '#4CAF50',
                                'color': 'white'}),

            html.Hr(),

            # --- Statistics ---
            html.Label('Statistics', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            dcc.Checklist(id='stats-toggles', options=[
                {'label': ' Basic Stats', 'value': 'basic'},
                {'label': ' SPC Stats (Cp/Cpk/Pp/Ppk)', 'value': 'spc'},
            ], value=[], style={'marginBottom': '12px'}),

            html.Label('Cpk Min Threshold', style={'fontSize': '13px'}),
            dcc.Input(id='cpk-threshold', type='number', value=1.33,
                      style={'width': '100%', 'marginBottom': '16px', 'padding': '4px 8px',
                             'border': '1px solid #ccc', 'borderRadius': '4px'}),

            html.Hr(),

            # --- Windowed Stats ---
            html.Label('Rolling Window', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            dcc.Checklist(id='window-toggle', options=[
                {'label': ' Enable rolling stats', 'value': 'enabled'},
            ], value=[], style={'marginBottom': '8px'}),

            html.Label('Window Type', style={'fontSize': '13px'}),
            dcc.RadioItems(id='window-type', options=[
                {'label': 'Samples', 'value': 'samples'},
                {'label': 'Time', 'value': 'time'},
            ], value='samples', inline=True, style={'marginBottom': '8px'}),

            html.Label('Window Size', style={'fontSize': '13px'}),
            dcc.Input(id='window-size', type='number', value=50, min=2,
                      style={'width': '60%', 'padding': '4px 8px', 'marginRight': '4px',
                             'border': '1px solid #ccc', 'borderRadius': '4px'}),
            dcc.Dropdown(id='window-time-unit', options=[
                {'label': 'Seconds', 'value': 'S'},
                {'label': 'Minutes', 'value': 'T'},
                {'label': 'Hours', 'value': 'H'},
                {'label': 'Days', 'value': 'D'},
                {'label': 'Weeks', 'value': 'W'},
            ], value='D', clearable=False,
                style={'width': '100%', 'marginBottom': '16px'}),

            html.Hr(),

            # --- Auto Refresh ---
            html.Label('Auto Refresh', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            dcc.Checklist(id='refresh-toggle', options=[
                {'label': ' Enable', 'value': 'enabled'},
            ], value=[], style={'marginBottom': '8px'}),

            dcc.Checklist(id='refresh-mode', options=[
                {'label': ' Full reload (instead of incremental)', 'value': 'full'},
            ], value=[], style={'marginBottom': '8px', 'fontSize': '13px'}),

            html.Label('Interval (seconds)', style={'fontSize': '13px'}),
            dcc.Slider(id='refresh-interval', min=1, max=60, step=1, value=10,
                       marks={1: '1', 5: '5', 10: '10', 30: '30', 60: '60'},
                       tooltip={'placement': 'bottom'}),
            html.Div(id='last-refresh-time',
                     style={'fontSize': '12px', 'color': '#999', 'marginTop': '8px'}),

            html.Hr(),

            # --- Config ---
            html.Label('Configuration', style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            # Save section
            html.Label('Save filename:', style={'fontSize': '11px', 'color': '#666'}),
            dcc.Input(id='config-filename', type='text', value='plotter_config.json',
                      placeholder='filename.json',
                      style={'width': '100%', 'marginBottom': '6px', 'padding': '4px 8px',
                             'border': '1px solid #ccc', 'borderRadius': '4px'}),
            html.Button('Save Config (download)', id='save-config-btn', n_clicks=0,
                        style={'width': '100%', 'padding': '6px', 'cursor': 'pointer',
                               'borderRadius': '4px', 'border': '1px solid #FF9800',
                               'background': '#FF9800', 'color': 'white',
                               'marginBottom': '10px'}),
            # Load section
            html.Label('Load config:', style={'fontSize': '11px', 'color': '#666',
                                              'marginBottom': '4px', 'display': 'block'}),
            dcc.Upload(
                id='upload-config',
                children=html.Div([
                    html.Span('Drop config JSON here', style={'display': 'block', 'fontWeight': 'bold'}),
                    html.Span('or click to browse', style={'fontSize': '11px', 'color': '#aaa'}),
                ]),
                style={'width': '100%', 'height': '56px', 'lineHeight': '1.4',
                       'borderWidth': '2px', 'borderStyle': 'dashed', 'borderColor': '#9C27B0',
                       'borderRadius': '4px', 'textAlign': 'center', 'fontSize': '12px',
                       'color': '#9C27B0', 'marginBottom': '6px',
                       'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                       'cursor': 'pointer', 'paddingTop': '8px'},
            ),
            html.Div(id='config-status', style={'fontSize': '12px', 'color': '#666'}),

        ], style={'width': '280px', 'minWidth': '280px', 'padding': '12px 16px',
                  'borderRight': '1px solid #ddd', 'overflowY': 'auto',
                  'maxHeight': 'calc(100vh - 120px)'}),

        # ── Right Main Area ──
        html.Div([
            # Main plot
            dcc.Graph(id='main-plot',
                      config={'scrollZoom': True, 'displayModeBar': True},
                      style={'height': '55vh'}),

            # Rolling stats subplot
            html.Div(id='rolling-plot-container', children=[
                dcc.Graph(id='rolling-plot',
                          config={'scrollZoom': True},
                          style={'height': '25vh'}),
            ], style={'display': 'none'}),

            # Stats tables
            html.Div(id='stats-tables-container', children=[
                html.H4('Basic Statistics', id='basic-stats-header',
                         style={'display': 'none', 'marginTop': '8px', 'marginBottom': '4px'}),
                dash_table.DataTable(
                    id='basic-stats-table',
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'center', 'padding': '4px 8px',
                                'fontSize': '13px', 'minWidth': '80px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'},
                ),
                html.H4('SPC Statistics', id='spc-stats-header',
                         style={'display': 'none', 'marginTop': '12px', 'marginBottom': '4px'}),
                dash_table.DataTable(
                    id='spc-stats-table',
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'center', 'padding': '4px 8px',
                                'fontSize': '13px', 'minWidth': '80px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'},
                    style_data_conditional=[],
                ),
            ], style={'padding': '0 8px 16px 8px'}),
        ], style={'flex': '1', 'overflowY': 'auto', 'maxHeight': 'calc(100vh - 120px)'}),

    ], style={'display': 'flex', 'height': 'calc(100vh - 120px)'}),

    # ── Interval for auto-refresh ──
    dcc.Interval(id='refresh-interval-component', interval=10000, disabled=True),

    # ── Download component for config ──
    dcc.Download(id='download-config'),

], style={'fontFamily': 'Segoe UI, Arial, sans-serif', 'height': '100vh'})


# ──────────────────────────────────────────────────────────────────────────────
# Callbacks
# ──────────────────────────────────────────────────────────────────────────────

# ─── Add / Remove files ──────────────────────────────────────────────────────

@app.callback(
    Output('loaded-files', 'data'),
    Output('status-message', 'children'),
    Output('file-path-input', 'value'),
    Input('add-file-btn', 'n_clicks'),
    Input('remove-all-btn', 'n_clicks'),
    Input('upload-csv', 'contents'),
    State('file-path-input', 'value'),
    State('loaded-files', 'data'),
    State('upload-csv', 'filename'),
    prevent_initial_call=True,
)
def manage_files(add_clicks, remove_clicks, upload_contents, file_path, loaded_files, upload_filenames):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'remove-all-btn':
        for fp in loaded_files:
            data_mgr.remove_file(fp)
            file_mon.unregister(fp)
        return [], 'All files removed.', ''

    if trigger_id == 'upload-csv':
        if not upload_contents:
            raise PreventUpdate
        # Handle one or multiple dropped files
        if not isinstance(upload_contents, list):
            upload_contents = [upload_contents]
            upload_filenames = [upload_filenames]
        messages = []
        new_files = list(loaded_files)
        for content, fname in zip(upload_contents, upload_filenames or []):
            try:
                _ctype, b64 = content.split(',', 1)
                raw = base64.b64decode(b64).decode('utf-8', errors='replace')
                # Use a virtual key so FileMonitor won't try to stat it
                vkey = f'<upload>:{fname}'
                df = pd.read_csv(StringIO(raw), sep=None, engine='python', on_bad_lines='skip')
                data_mgr.dataframes[vkey] = df
                data_mgr._file_headers[vkey] = list(df.columns)
                data_mgr._file_offsets[vkey] = 0   # no disk file to monitor
                if vkey not in new_files:
                    new_files.append(vkey)
                messages.append(f'{fname} ({len(df)} rows, {len(df.columns)} cols)')
            except Exception as e:
                messages.append(f'{fname}: error — {e}')
        return new_files, 'Loaded: ' + ' | '.join(messages), no_update

    if trigger_id == 'add-file-btn':
        if not file_path or not file_path.strip():
            return loaded_files, 'Please enter a file path.', file_path

        fp = file_path.strip().strip('"').strip("'")
        if not os.path.isfile(fp):
            return loaded_files, f'File not found: {fp}', file_path

        fp_norm = os.path.normpath(fp)
        if fp_norm in [os.path.normpath(f) for f in loaded_files]:
            return loaded_files, f'File already loaded.', ''

        try:
            df = data_mgr.load_file(fp_norm)
            file_mon.register(fp_norm)
            loaded_files = loaded_files + [fp_norm]
            return loaded_files, f'Loaded {os.path.basename(fp_norm)} ({len(df)} rows, {len(df.columns)} columns)', ''
        except Exception as e:
            return loaded_files, f'Error loading file: {e}', file_path

    raise PreventUpdate


@app.callback(
    Output('loaded-files-display', 'children'),
    Input('loaded-files', 'data'),
)
def display_loaded_files(loaded_files):
    if not loaded_files:
        return [html.Span('No files loaded', style={'color': '#999', 'fontSize': '13px'})]
    chips = []
    for fp in loaded_files:
        if fp.startswith('<upload>:'):
            label = fp[len('<upload>:'):]
            bg, border = '#fff3e0', '#ffcc80'
        else:
            label = os.path.basename(fp)
            bg, border = '#e3f2fd', '#90caf9'
        chips.append(html.Span(
            label,
            title=fp,
            style={'background': bg, 'padding': '3px 10px', 'borderRadius': '12px',
                   'fontSize': '13px', 'border': f'1px solid {border}'},
        ))
    return chips


# ─── Populate column dropdowns ──────────────────────────────────────────────

@app.callback(
    Output('x-axis-dropdown', 'options'),
    Output('y-axis-dropdown', 'options'),
    Output('x-axis-dropdown', 'value'),
    Output('y-axis-dropdown', 'value'),
    Input('loaded-files', 'data'),
    State('ui-settings-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
)
def update_column_dropdowns(loaded_files, ui_settings, current_x, current_y):
    all_cols = set()
    for fp in (loaded_files or []):
        all_cols.update(data_mgr.get_all_columns(fp))
    options = [{'label': c, 'value': c} for c in sorted(all_cols)]
    col_set = {o['value'] for o in options}

    # Restore column selections from saved config when available
    if ui_settings:
        saved_x = ui_settings.get('x_axis')
        new_x = saved_x if saved_x in col_set else (current_x if current_x in col_set else no_update)
        saved_y = ui_settings.get('y_columns') or []
        restored_y = [c for c in saved_y if c in col_set]
        new_y = restored_y if restored_y else [c for c in (current_y or []) if c in col_set]
        new_y = new_y or no_update
    else:
        new_x = current_x if current_x in col_set else no_update
        new_y = [c for c in (current_y or []) if c in col_set] or no_update

    return options, options, new_x, new_y


# ─── Dynamic limit inputs per selected column ───────────────────────────────

@app.callback(
    Output('limits-inputs-container', 'children'),
    Input('y-axis-dropdown', 'value'),
    State('limits-store', 'data'),
)
def build_limit_inputs(selected_cols, current_limits):
    if not selected_cols:
        return html.Div('Select columns first', style={'color': '#999', 'fontSize': '13px'})

    children = []
    for col in selected_cols:
        stored = current_limits.get(col, {})
        children.append(html.Div([
            html.Label(col, style={'fontSize': '12px', 'fontWeight': 'bold',
                                   'marginBottom': '2px', 'display': 'block',
                                   'overflow': 'hidden', 'textOverflow': 'ellipsis',
                                   'whiteSpace': 'nowrap', 'maxWidth': '240px'}),
            html.Div([
                html.Div([
                    html.Label('LSL', style={'fontSize': '11px', 'marginRight': '4px'}),
                    dcc.Input(
                        id={'type': 'lsl-input', 'column': col},
                        type='number', placeholder='LSL',
                        value=stored.get('lsl'),
                        style={'width': '80px', 'padding': '2px 6px', 'fontSize': '12px',
                               'border': '1px solid #ccc', 'borderRadius': '3px'},
                    ),
                ], style={'display': 'flex', 'alignItems': 'center', 'marginRight': '8px'}),
                html.Div([
                    html.Label('USL', style={'fontSize': '11px', 'marginRight': '4px'}),
                    dcc.Input(
                        id={'type': 'usl-input', 'column': col},
                        type='number', placeholder='USL',
                        value=stored.get('usl'),
                        style={'width': '80px', 'padding': '2px 6px', 'fontSize': '12px',
                               'border': '1px solid #ccc', 'borderRadius': '3px'},
                    ),
                ], style={'display': 'flex', 'alignItems': 'center'}),
            ], style={'display': 'flex', 'marginBottom': '8px'}),
        ]))
    return children


# ─── Apply limits ────────────────────────────────────────────────────────────

@app.callback(
    Output('limits-store', 'data'),
    Output('trigger-plot-update', 'data'),
    Output('ui-settings-store', 'data'),
    Output('config-status', 'children'),
    Input('apply-limits-btn', 'n_clicks'),
    Input('upload-config', 'contents'),
    State('y-axis-dropdown', 'value'),
    State({'type': 'lsl-input', 'column': ALL}, 'value'),
    State({'type': 'lsl-input', 'column': ALL}, 'id'),
    State({'type': 'usl-input', 'column': ALL}, 'value'),
    State({'type': 'usl-input', 'column': ALL}, 'id'),
    State('limits-store', 'data'),
    State('trigger-plot-update', 'data'),
    State('upload-config', 'filename'),
    prevent_initial_call=True,
)
def update_limits(apply_clicks, upload_contents,
                  selected_cols, lsl_values, lsl_ids, usl_values, usl_ids,
                  current_limits, trigger_counter,
                  upload_filename):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    def _split_config(raw):
        """Separate _ui_settings from column limits."""
        ui = raw.pop('_ui_settings', {})
        return raw, ui

    # Upload config via drag-and-drop or click-to-browse
    if trigger_id == 'upload-config':
        if upload_contents:
            try:
                content_type, content_string = upload_contents.split(',')
                decoded = base64.b64decode(content_string).decode('utf-8')
                raw = json.loads(decoded)
                limits, ui = _split_config(raw)
                fname = upload_filename or 'config'
                return limits, (trigger_counter or 0) + 1, ui, f'Config loaded: {fname}'
            except Exception as e:
                return current_limits, trigger_counter or 0, no_update, f'Error loading config: {e}'
        return current_limits, trigger_counter or 0, no_update, no_update

    # Apply limits from UI inputs
    if trigger_id == 'apply-limits-btn':
        new_limits = dict(current_limits) if current_limits else {}
        if lsl_ids:
            for i, lsl_id in enumerate(lsl_ids):
                col = lsl_id['column']
                lsl_val = lsl_values[i]
                usl_val = usl_values[i] if i < len(usl_values) else None
                new_limits[col] = {
                    'lsl': lsl_val,
                    'usl': usl_val,
                    'stat_limits': new_limits.get(col, {}).get('stat_limits', {}),
                }
        return new_limits, (trigger_counter or 0) + 1, no_update, no_update

    raise PreventUpdate


# ─── Restore UI settings from loaded config ──────────────────────────────────

@app.callback(
    Output('x-axis-dropdown', 'value', allow_duplicate=True),
    Output('y-axis-dropdown', 'value', allow_duplicate=True),
    Output('stats-toggles', 'value'),
    Output('cpk-threshold', 'value'),
    Output('window-toggle', 'value'),
    Output('window-type', 'value'),
    Output('window-size', 'value'),
    Output('window-time-unit', 'value'),
    Output('refresh-toggle', 'value'),
    Output('refresh-mode', 'value'),
    Output('refresh-interval', 'value'),
    Input('ui-settings-store', 'data'),
    prevent_initial_call=True,
)
def restore_ui_settings(ui):
    # Column values are also restored here so they apply when files are already loaded.
    # If files aren't loaded yet, update_column_dropdowns will re-apply them on file load.
    if not ui:
        raise PreventUpdate
    return (
        ui.get('x_axis', no_update),
        ui.get('y_columns', no_update),
        ui.get('stats_toggles', no_update),
        ui.get('cpk_threshold', no_update),
        ui.get('window_enabled', no_update),
        ui.get('window_type', no_update),
        ui.get('window_size', no_update),
        ui.get('window_time_unit', no_update),
        ui.get('refresh_enabled', no_update),
        ui.get('refresh_full', no_update),
        ui.get('refresh_interval', no_update),
    )


# ─── Save config ─────────────────────────────────────────────────────────────

@app.callback(
    Output('download-config', 'data'),
    Output('config-status', 'children'),
    Input('save-config-btn', 'n_clicks'),
    State('limits-store', 'data'),
    State('config-filename', 'value'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
    State('stats-toggles', 'value'),
    State('cpk-threshold', 'value'),
    State('window-toggle', 'value'),
    State('window-type', 'value'),
    State('window-size', 'value'),
    State('window-time-unit', 'value'),
    State('refresh-toggle', 'value'),
    State('refresh-mode', 'value'),
    State('refresh-interval', 'value'),
    prevent_initial_call=True,
)
def save_config(n_clicks, limits, config_filename,
               x_axis, y_columns, stats_toggles, cpk_threshold,
               window_enabled, window_type, window_size, window_time_unit,
               refresh_enabled, refresh_full, refresh_interval_val):
    fname = config_filename or 'plotter_config.json'
    ui_settings = {
        'x_axis': x_axis,
        'y_columns': y_columns or [],
        'stats_toggles': stats_toggles or [],
        'cpk_threshold': cpk_threshold,
        'window_enabled': window_enabled or [],
        'window_type': window_type,
        'window_size': window_size,
        'window_time_unit': window_time_unit,
        'refresh_enabled': refresh_enabled or [],
        'refresh_full': refresh_full or [],
        'refresh_interval': refresh_interval_val,
    }
    config = {'_ui_settings': ui_settings}
    config.update(limits or {})
    content = json.dumps(config, indent=2)
    return dict(content=content, filename=fname), f'Config saved as {fname}'


# ─── Configure auto-refresh interval ────────────────────────────────────────

@app.callback(
    Output('refresh-interval-component', 'interval'),
    Output('refresh-interval-component', 'disabled'),
    Input('refresh-toggle', 'value'),
    Input('refresh-interval', 'value'),
)
def configure_refresh(toggle, interval_sec):
    enabled = 'enabled' in (toggle or [])
    return (interval_sec or 5) * 1000, not enabled


# ─── Auto-refresh tick ──────────────────────────────────────────────────────

@app.callback(
    Output('trigger-plot-update', 'data', allow_duplicate=True),
    Output('last-refresh-time', 'children'),
    Input('refresh-interval-component', 'n_intervals'),
    State('loaded-files', 'data'),
    State('refresh-mode', 'value'),
    State('trigger-plot-update', 'data'),
    prevent_initial_call=True,
)
def auto_refresh(n_intervals, loaded_files, refresh_mode, trigger_counter):
    if not loaded_files:
        raise PreventUpdate

    changed = []
    for fp in loaded_files:
        if file_mon.check_modified(fp):
            changed.append(fp)

    if not changed:
        raise PreventUpdate

    full_reload = 'full' in (refresh_mode or [])
    for fp in changed:
        if full_reload:
            data_mgr.load_file(fp)
        else:
            data_mgr.load_incremental(fp)

    from datetime import datetime
    now = datetime.now().strftime('%H:%M:%S')
    return (trigger_counter or 0) + 1, f'Last refresh: {now} ({len(changed)} file(s) updated)'


# ─── Main Plot ───────────────────────────────────────────────────────────────

@app.callback(
    Output('main-plot', 'figure'),
    Input('y-axis-dropdown', 'value'),
    Input('x-axis-dropdown', 'value'),
    Input('trigger-plot-update', 'data'),
    State('loaded-files', 'data'),
    State('limits-store', 'data'),
)
def update_main_plot(selected_cols, x_col, trigger, loaded_files, limits):
    if not selected_cols or not loaded_files:
        fig = go.Figure()
        fig.update_layout(
            title='Select columns to plot',
            xaxis_title='Index',
            yaxis_title='Value',
            template='plotly_white',
            margin=dict(l=50, r=20, t=40, b=40),
        )
        return fig

    fig = go.Figure()
    color_idx = 0

    for fp in loaded_files:
        df = data_mgr.dataframes.get(os.path.normpath(fp))
        if df is None:
            continue
        file_label = os.path.basename(fp)

        # Determine x-axis
        if x_col and x_col in df.columns:
            x_data = df[x_col]
            # Try to parse as datetime for better axis formatting
            try:
                x_data = pd.to_datetime(x_data, format='mixed', errors='coerce')
                if x_data.isna().sum() > len(x_data) * 0.5:
                    x_data = df[x_col]
            except Exception:
                pass
        else:
            x_data = df.index

        for col in selected_cols:
            if col not in df.columns:
                continue

            y_data = pd.to_numeric(df[col], errors='coerce')
            color = TRACE_COLORS[color_idx % len(TRACE_COLORS)]
            color_idx += 1

            # Determine marker colors based on limits
            col_limits = limits.get(col, {})
            usl = col_limits.get('usl')
            lsl = col_limits.get('lsl')

            marker_colors = [color] * len(y_data)
            if usl is not None or lsl is not None:
                for i, val in enumerate(y_data):
                    if pd.isna(val):
                        continue
                    if (usl is not None and val > usl) or (lsl is not None and val < lsl):
                        marker_colors[i] = 'red'

            trace_name = f'{col}' if len(loaded_files) == 1 else f'{col} ({file_label})'
            fig.add_trace(go.Scattergl(
                x=x_data, y=y_data,
                mode='lines+markers',
                name=trace_name,
                marker=dict(color=marker_colors, size=4),
                line=dict(color=color, width=1),
            ))

            # Add limit lines
            if usl is not None:
                fig.add_hline(y=usl, line_dash='dash', line_color='red',
                              annotation_text=f'{col} USL={usl}',
                              annotation_position='top right',
                              opacity=0.6)
            if lsl is not None:
                fig.add_hline(y=lsl, line_dash='dash', line_color='blue',
                              annotation_text=f'{col} LSL={lsl}',
                              annotation_position='bottom right',
                              opacity=0.6)

    x_label = x_col if x_col else 'Index'
    fig.update_layout(
        xaxis_title=x_label,
        yaxis_title='Value',
        template='plotly_white',
        margin=dict(l=50, r=20, t=30, b=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified',
    )
    return fig


# ─── Rolling Stats Plot ─────────────────────────────────────────────────────

@app.callback(
    Output('rolling-plot-container', 'style'),
    Output('rolling-plot', 'figure'),
    Input('window-toggle', 'value'),
    Input('y-axis-dropdown', 'value'),
    Input('trigger-plot-update', 'data'),
    State('loaded-files', 'data'),
    State('limits-store', 'data'),
    State('window-type', 'value'),
    State('window-size', 'value'),
    State('window-time-unit', 'value'),
    State('x-axis-dropdown', 'value'),
)
def update_rolling_plot(window_toggle, selected_cols, trigger,
                        loaded_files, limits, window_type, window_size,
                        time_unit, x_col):
    enabled = 'enabled' in (window_toggle or [])
    if not enabled or not selected_cols or not loaded_files:
        return {'display': 'none'}, go.Figure()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=['Rolling Mean ± 3σ', 'Rolling Cpk'],
                        vertical_spacing=0.12, row_heights=[0.5, 0.5])

    color_idx = 0
    ws = window_size or 50

    for fp in loaded_files:
        df = data_mgr.dataframes.get(os.path.normpath(fp))
        if df is None:
            continue

        # X-axis data
        if x_col and x_col in df.columns:
            try:
                x_data = pd.to_datetime(df[x_col], format='mixed', errors='coerce')
                if x_data.isna().sum() > len(x_data) * 0.5:
                    x_data = df.index
            except Exception:
                x_data = df.index
        else:
            x_data = df.index

        # Timestamps for time-windowed stats
        timestamps = None
        if window_type == 'time':
            ts_col = data_mgr.detect_timestamp_column(fp)
            if ts_col:
                timestamps = df[ts_col]
            win = f'{ws}{time_unit}'
        else:
            win = ws

        for col in selected_cols:
            if col not in df.columns:
                continue

            series = pd.to_numeric(df[col], errors='coerce')
            color = TRACE_COLORS[color_idx % len(TRACE_COLORS)]
            color_idx += 1

            # Rolling stats
            roll = stats_engine.compute_rolling_stats(
                series, win, window_type=window_type, timestamps=timestamps)

            # Rolling mean with ±3σ band
            fig.add_trace(go.Scattergl(
                x=x_data, y=roll['rolling_mean'],
                mode='lines', name=f'{col} μ',
                line=dict(color=color, width=1.5),
                showlegend=True,
            ), row=1, col=1)

            upper = roll['rolling_mean'] + 3 * roll['rolling_std']
            lower = roll['rolling_mean'] - 3 * roll['rolling_std']
            fig.add_trace(go.Scattergl(
                x=x_data, y=upper,
                mode='lines', name=f'{col} +3σ',
                line=dict(color=color, width=0.5, dash='dot'),
                showlegend=False,
            ), row=1, col=1)
            fig.add_trace(go.Scattergl(
                x=x_data, y=lower,
                mode='lines', name=f'{col} -3σ',
                line=dict(color=color, width=0.5, dash='dot'),
                fill='tonexty', fillcolor=f'rgba({_hex_to_rgb(color)}, 0.08)',
                showlegend=False,
            ), row=1, col=1)

            # Rolling Cpk
            col_limits = limits.get(col, {})
            usl = col_limits.get('usl')
            lsl = col_limits.get('lsl')
            if usl is not None or lsl is not None:
                cpk_series = stats_engine.compute_rolling_cpk(
                    series, win, usl=usl, lsl=lsl,
                    window_type=window_type, timestamps=timestamps)
                fig.add_trace(go.Scattergl(
                    x=x_data, y=cpk_series,
                    mode='lines', name=f'{col} Cpk',
                    line=dict(color=color, width=1.5),
                ), row=2, col=1)

    # Add Cpk threshold line
    fig.add_hline(y=1.33, line_dash='dash', line_color='red',
                  annotation_text='Cpk=1.33', row=2, col=1, opacity=0.5)

    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=30, b=20),
        height=350,
        legend=dict(orientation='h', yanchor='bottom', y=1.06, xanchor='left', x=0),
    )
    return {'display': 'block'}, fig


def _hex_to_rgb(hex_color):
    """Convert hex color like '#1f77b4' to 'r,g,b' string."""
    h = hex_color.lstrip('#')
    return ','.join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))


# ─── Statistics Tables ───────────────────────────────────────────────────────

@app.callback(
    Output('basic-stats-table', 'data'),
    Output('basic-stats-table', 'columns'),
    Output('basic-stats-header', 'style'),
    Output('spc-stats-table', 'data'),
    Output('spc-stats-table', 'columns'),
    Output('spc-stats-header', 'style'),
    Output('spc-stats-table', 'style_data_conditional'),
    Input('stats-toggles', 'value'),
    Input('y-axis-dropdown', 'value'),
    Input('trigger-plot-update', 'data'),
    State('loaded-files', 'data'),
    State('limits-store', 'data'),
    State('cpk-threshold', 'value'),
)
def update_stats_tables(stats_toggles, selected_cols, trigger,
                        loaded_files, limits, cpk_threshold):
    show_basic = 'basic' in (stats_toggles or [])
    show_spc = 'spc' in (stats_toggles or [])
    hidden = {'display': 'none', 'marginTop': '8px', 'marginBottom': '4px'}
    shown = {'display': 'block', 'marginTop': '8px', 'marginBottom': '4px'}

    basic_data, basic_cols = [], []
    spc_data, spc_cols = [], []
    spc_conditional = []

    if not selected_cols or not loaded_files:
        return basic_data, basic_cols, hidden, spc_data, spc_cols, hidden, spc_conditional

    # --- Basic Stats ---
    if show_basic:
        stat_keys = ['count', 'mean', 'std', 'min', 'max', 'median', 'range']
        basic_cols = [{'name': 'Statistic', 'id': 'stat'}]
        for fp in loaded_files:
            for col in selected_cols:
                label = col if len(loaded_files) == 1 else f'{col} ({os.path.basename(fp)})'
                basic_cols.append({'name': label, 'id': label})

        for sk in stat_keys:
            row = {'stat': sk}
            for fp in loaded_files:
                df = data_mgr.dataframes.get(os.path.normpath(fp))
                if df is None:
                    continue
                for col in selected_cols:
                    label = col if len(loaded_files) == 1 else f'{col} ({os.path.basename(fp)})'
                    if col not in df.columns:
                        row[label] = ''
                        continue
                    series = pd.to_numeric(df[col], errors='coerce')
                    stats = stats_engine.compute_basic_stats(series)
                    val = stats.get(sk, np.nan)
                    row[label] = f'{val:.6g}' if not np.isnan(val) else ''
            basic_data.append(row)

    # --- SPC Stats ---
    if show_spc:
        spc_keys = ['Cp', 'Cpk', 'Pp', 'Ppk']
        spc_cols = [{'name': 'Metric', 'id': 'metric'}]
        for fp in loaded_files:
            for col in selected_cols:
                label = col if len(loaded_files) == 1 else f'{col} ({os.path.basename(fp)})'
                spc_cols.append({'name': label, 'id': label})

        for sk in spc_keys:
            row = {'metric': sk}
            for fp in loaded_files:
                df = data_mgr.dataframes.get(os.path.normpath(fp))
                if df is None:
                    continue
                for col in selected_cols:
                    label = col if len(loaded_files) == 1 else f'{col} ({os.path.basename(fp)})'
                    if col not in df.columns:
                        row[label] = ''
                        continue
                    series = pd.to_numeric(df[col], errors='coerce')
                    col_limits = limits.get(col, {})
                    usl = col_limits.get('usl')
                    lsl = col_limits.get('lsl')

                    if sk == 'Cp':
                        val = stats_engine.compute_cp(series, usl, lsl)
                    elif sk == 'Cpk':
                        val = stats_engine.compute_cpk(series, usl, lsl)
                    elif sk == 'Pp':
                        val = stats_engine.compute_pp(series, usl, lsl)
                    elif sk == 'Ppk':
                        val = stats_engine.compute_ppk(series, usl, lsl)
                    else:
                        val = np.nan

                    row[label] = f'{val:.4f}' if not np.isnan(val) else 'N/A'

                    # Highlight low Cpk/Ppk
                    if sk in ('Cpk', 'Ppk') and not np.isnan(val):
                        threshold = cpk_threshold or 1.33
                        if val < threshold:
                            spc_conditional.append({
                                'if': {'filter_query': f'{{metric}} = {sk}',
                                       'column_id': label},
                                'backgroundColor': '#ffcdd2',
                                'color': '#c62828',
                                'fontWeight': 'bold',
                            })
            spc_data.append(row)

    basic_style = shown if show_basic else hidden
    spc_style = shown if show_spc else hidden

    return basic_data, basic_cols, basic_style, spc_data, spc_cols, spc_style, spc_conditional


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

USAGE_EXAMPLES = """
CSV Graph Plotter — Usage Examples
===================================

Launch the web UI
-----------------
  # Basic launch (opens at http://127.0.0.1:8050)
  python csv_plotter_dash.py

  # Custom port
  python csv_plotter_dash.py --port 8080

  # Pre-load one or more CSV files on startup
  python csv_plotter_dash.py --file data.csv
  python csv_plotter_dash.py --file log1.csv log2.csv

  # Pre-load a saved limit configuration
  python csv_plotter_dash.py --config my_limits.json

  # Combined: pre-load file + config
  python csv_plotter_dash.py --file test_log.txt --config limits.json

In the Web UI
-------------
  1. Add File       — Paste a file path and click "Add File" (supports CSV and
                      pipe/tab/comma-delimited .txt files — auto-detected)
  2. Y-Axis Columns — Select one or more columns to plot.  Starts empty.
  3. X-Axis Column  — Optional: pick a timestamp or index column for the X axis.
                      Leave blank to use row index.
  4. Column Limits  — Enter LSL / USL for each selected column, then click
                      "Apply Limits".  Out-of-spec points turn red.
  5. Statistics     — Tick "Basic Stats" and/or "SPC Stats" to show count / mean /
                      std / Cpk / Ppk tables below the plot.
  6. Cpk Threshold  — Default 1.33.  Cpk / Ppk cells below this threshold are
                      highlighted red.
  7. Rolling Window — Enable to add a second subplot with rolling mean ± 3σ
                      and rolling Cpk traces.
                        • Samples mode: last N data points  (e.g. 100)
                        • Time mode:    last N time units   (e.g. 7 Days = 1 week)
  8. Save Config    — Saves current column limits to a JSON file that can be
                      reloaded later or shared.  Also available as a download.
  9. Load Config    — Load a previously saved JSON config to restore limits.
                      Drag-and-drop is also supported.
  10. Auto Refresh  — Enable to watch the file for new rows appended by a running
                      test.  Default mode loads only new lines (incremental) for
                      speed; tick "Full reload" to re-read the whole file.

Config JSON format
------------------
  Produced by "Save Config" and editable by hand.
  Column limits are keyed by column name; UI state is under "_ui_settings":

    {
      "_ui_settings": {
        "x_axis": "Test Time",
        "y_columns": ["#8 Internal Main Board Temperature", "#0 Input Current"],
        "stats_toggles": ["basic", "spc"],
        "cpk_threshold": 1.33,
        "window_enabled": ["enabled"],
        "window_type": "samples",
        "window_size": 100,
        "window_time_unit": "D",
        "refresh_enabled": [],
        "refresh_full": [],
        "refresh_interval": 10
      },
      "#8 Internal Main Board Temperature": {
        "usl": 60.0,
        "lsl": 20.0,
        "stat_limits": { "cpk_min": 1.33 }
      },
      "#0 Input Current": {
        "usl": 21.5,
        "lsl": 3.5,
        "stat_limits": { "cpk_min": 1.67 }
      }
    }

File format support
-------------------
  Comma-delimited .csv    — standard CSV
  Pipe-delimited .txt     — reliability test logs (auto-detected)
  Tab-delimited .txt/.tsv — auto-detected
  Any mix of the above in different files loaded simultaneously
"""


def main():
    parser = argparse.ArgumentParser(
        description='CSV Graph Plotter — Interactive Dash web app for CSV data analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--port', type=int, default=8050, help='Port number (default: 8050)')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Host (default: 127.0.0.1)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--file', type=str, nargs='*', help='Pre-load CSV file(s)')
    parser.add_argument('--config', type=str, help='Pre-load a config JSON file')
    parser.add_argument('--examples', action='store_true', help='Print usage examples and exit')
    args = parser.parse_args()

    if args.examples:
        print(USAGE_EXAMPLES)
        return

    # Pre-load files if specified
    if args.file:
        for fp in args.file:
            fp = os.path.normpath(fp)
            if os.path.isfile(fp):
                try:
                    data_mgr.load_file(fp)
                    file_mon.register(fp)
                    print(f'Pre-loaded: {fp}')
                except Exception as e:
                    print(f'Failed to load {fp}: {e}')

    # Pre-load config if specified
    if args.config and os.path.isfile(args.config):
        try:
            config = config_mgr.load_config(args.config)
            print(f'Config loaded: {args.config} ({len(config)} column limits)')
        except Exception as e:
            print(f'Failed to load config: {e}')

    print(f'\n  CSV Graph Plotter')
    print(f'  http://{args.host}:{args.port}\n')

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
