import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()

import json
import tkinter as tk
import numpy as np


# Palette for drawing region rectangles — cycles if more than 8 regions
_COLORS = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
           '#1abc9c', '#e67e22', '#e91e63']


class RegionSetupTool:
    """
    Interactive GUI for defining named screen regions on an Android device screenshot.

    Each region is defined by clicking two corners (top-left then bottom-right) on
    a displayed screenshot. Coordinates are saved as normalized fractions (0.0–1.0)
    so the config works across any screen resolution.

    Usage:
        adb = AdbUtils()
        tool = RegionSetupTool(['question', 'A', 'B', 'C', 'D'], adb=adb)
        regions = tool.run('config.json')

    Or with a pre-captured image (for testing without a device):
        tool = RegionSetupTool(['question', 'A'], screenshot='ref_screen.png')
        regions = tool.run('config.json')
    """

    def __init__(self, region_names, adb=None, screenshot=None):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require opencv-python/Pillow - only actually
        # instantiating RegionSetupTool does. Cached on self so the methods below don't
        # need their own import statements.
        utils.exit_if_module_missing('opencv-python')
        utils.exit_if_module_missing('Pillow')
        import cv2
        from PIL import Image, ImageTk
        self._cv2 = cv2
        self._Image = Image
        self._ImageTk = ImageTk
        if adb is None and screenshot is None:
            raise ValueError('Provide either adb= or screenshot=')
        self.region_names = region_names
        self._adb = adb
        self._screenshot_src = screenshot  # numpy array or file path
        self._screenshot = None            # numpy BGR array
        self._scale = 1.0
        self._orig_w = 0
        self._orig_h = 0
        self.regions = {}

    def _load_screenshot(self):
        if self._adb is not None:
            print('Capturing screenshot from device...')
            img = self._adb.take_screenshot()
            if img is None:
                raise RuntimeError('Failed to capture screenshot from device')
            return img
        src = self._screenshot_src
        if isinstance(src, np.ndarray):
            return src
        img = self._cv2.imread(str(src))
        if img is None:
            raise RuntimeError(f'Could not read image: {src}')
        return img

    def run(self, config_path=None):
        """
        Open the GUI. Returns the regions dict after the window closes.
        If config_path is provided, saves the result to that JSON file.
        """
        self._screenshot = self._load_screenshot()
        h, w = self._screenshot.shape[:2]
        self._orig_w, self._orig_h = w, h

        # Scale to fit a reasonable window (max 900px tall, max 600px wide)
        scale_h = 900 / h
        scale_w = 600 / w
        self._scale = min(1.0, scale_h, scale_w)
        disp_w = int(w * self._scale)
        disp_h = int(h * self._scale)

        # Build tk window
        root = tk.Tk()
        root.title('Region Setup')
        root.resizable(False, False)

        # Left: canvas with screenshot
        canvas = tk.Canvas(root, width=disp_w, height=disp_h, cursor='crosshair')
        canvas.grid(row=0, column=0, rowspan=10)

        img_rgb = self._cv2.cvtColor(self._screenshot, self._cv2.COLOR_BGR2RGB)
        pil_img = self._Image.fromarray(img_rgb).resize((disp_w, disp_h), self._Image.LANCZOS)
        tk_img = self._ImageTk.PhotoImage(pil_img)
        canvas.create_image(0, 0, anchor='nw', image=tk_img)

        # Right panel: instructions + region checklist
        panel = tk.Frame(root, padx=10, pady=10)
        panel.grid(row=0, column=1, sticky='n')

        tk.Label(panel, text='Region Setup', font=('Arial', 13, 'bold')).pack(anchor='w')
        tk.Label(panel, text=f'Screen: {w}×{h}', font=('Arial', 9), fg='gray').pack(anchor='w')
        tk.Label(panel, text='').pack()

        instruction_var = tk.StringVar()
        instruction_label = tk.Label(panel, textvariable=instruction_var,
                                     font=('Arial', 11), wraplength=200,
                                     justify='left', fg='#2c3e50')
        instruction_label.pack(anchor='w')
        tk.Label(panel, text='').pack()

        # Region status rows
        tk.Label(panel, text='Regions:', font=('Arial', 10, 'bold')).pack(anchor='w')
        status_vars = {}
        for name in self.region_names:
            row = tk.Frame(panel)
            row.pack(anchor='w', pady=1)
            sv = tk.StringVar(value='○  ' + name)
            lbl = tk.Label(row, textvariable=sv, font=('Arial', 10))
            lbl.pack(anchor='w')
            status_vars[name] = (sv, lbl)

        tk.Label(panel, text='').pack()
        hint = tk.Label(panel, text='Click top-left then\nbottom-right of each region.\nRight-click to redo last.',
                        font=('Arial', 9), fg='gray', justify='left')
        hint.pack(anchor='w')

        # Interaction state
        state = {
            'idx': 0,
            'step': 0,    # 0 = waiting for top-left, 1 = waiting for bottom-right
            'p1': None,
            'p1_item': None,
            'rect_items': {},  # name -> canvas item id
        }

        def current_name():
            return self.region_names[state['idx']] if state['idx'] < len(self.region_names) else None

        def update_instruction():
            name = current_name()
            if name is None:
                instruction_var.set('All regions defined!\nClose this window to save.')
                return
            color = _COLORS[state['idx'] % len(_COLORS)]
            instruction_label.config(fg=color)
            step_text = 'Click TOP-LEFT corner' if state['step'] == 0 else 'Click BOTTOM-RIGHT corner'
            instruction_var.set(f"Region '{name}'\n({state['idx']+1}/{len(self.region_names)})\n\n{step_text}")

        def mark_done(name):
            sv, lbl = status_vars[name]
            color = _COLORS[self.region_names.index(name) % len(_COLORS)]
            sv.set('✓  ' + name)
            lbl.config(fg=color)

        def redo_last(event=None):
            if state['idx'] == 0 and state['step'] == 0:
                return
            # If mid-region (step=1), go back to step 0
            if state['step'] == 1:
                if state['p1_item']:
                    canvas.delete(state['p1_item'])
                state['step'] = 0
                state['p1'] = None
                state['p1_item'] = None
            else:
                # Go back to previous region
                state['idx'] -= 1
                state['step'] = 0
                state['p1'] = None
                state['p1_item'] = None
                name = self.region_names[state['idx']]
                self.regions.pop(name, None)
                if name in state['rect_items']:
                    for item in state['rect_items'].pop(name):
                        canvas.delete(item)
                sv, lbl = status_vars[name]
                sv.set('○  ' + name)
                lbl.config(fg='black')
            update_instruction()

        def on_click(event):
            if state['idx'] >= len(self.region_names):
                return
            name = current_name()
            color = _COLORS[state['idx'] % len(_COLORS)]

            if state['step'] == 0:
                state['p1'] = (event.x, event.y)
                dot = canvas.create_oval(event.x-4, event.y-4, event.x+4, event.y+4,
                                         fill=color, outline=color)
                state['p1_item'] = dot
                state['step'] = 1

            else:
                x1c, y1c = state['p1']
                x2c, y2c = event.x, event.y
                # ensure top-left / bottom-right ordering
                lx, rx = min(x1c, x2c), max(x1c, x2c)
                ty, by = min(y1c, y2c), max(y1c, y2c)

                rect = canvas.create_rectangle(lx, ty, rx, by, outline=color, width=2)
                txt = canvas.create_text((lx+rx)//2, (ty+by)//2, text=name,
                                         fill=color, font=('Arial', 10, 'bold'))
                state['rect_items'][name] = (state['p1_item'], rect, txt)
                state['p1_item'] = None

                # Normalize to 0.0–1.0 against original resolution
                s = self._scale
                ow, oh = self._orig_w, self._orig_h
                self.regions[name] = (
                    round(lx / (s * ow), 4),
                    round(ty / (s * oh), 4),
                    round(rx / (s * ow), 4),
                    round(by / (s * oh), 4),
                )

                mark_done(name)
                state['idx'] += 1
                state['step'] = 0
                state['p1'] = None

                if state['idx'] >= len(self.region_names) and config_path:
                    self._save(config_path)

            update_instruction()

        canvas.bind('<Button-1>', on_click)
        canvas.bind('<Button-3>', redo_last)   # right-click to redo
        root.bind('<BackSpace>', redo_last)

        update_instruction()
        root.mainloop()

        return self.regions

    def _save(self, config_path):
        config = {
            'screen_size': [self._orig_w, self._orig_h],
            'regions': {k: list(v) for k, v in self.regions.items()},
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f'Config saved → {config_path}')


if __name__ == '__main__':
    # Quick standalone test: load a screenshot file and define 2 regions
    import sys
    if len(sys.argv) < 2:
        print('Usage: python region_setup.py <screenshot.png>')
        sys.exit(1)
    tool = RegionSetupTool(['region_1', 'region_2'], screenshot=sys.argv[1])
    result = tool.run('test_config.json')
    print('Result:', result)
