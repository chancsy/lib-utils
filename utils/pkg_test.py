# %%
from utils import *
utils = UtilityFunctions()
utils.list_to_csv(['a','b','c'])

# %%
from utils.clipboard_utils import *
cb = Clipboard()
cb.copy('test')
cb.paste()

# %%
from utils.log_actions import *
log_demo()

# %%
from utils.math_utils import *
math_utils = MathUtils()
math_utils.demo()

# %%
from utils.selenium_utils import *
sel = SeleniumUtils()
sel.demo()

# %%
from utils.widget_utils import *
widget = Widgets()
widget.demo()

# %%
# this does not work anymore
import sys
sys.path.append(R'C:\Users\E1433368\Documents\Work\EE_SGP\work_dir\utils\utils')

# from utilities import *
# utils = UtilityFunctions()
# utils.list_to_csv(['a','b','c'])

from clipboard_utils import *
cb = Clipboard()
cb.copy('test')
cb.paste()
