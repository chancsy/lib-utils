# %% [markdown]
# ## Prepare the environment
# %%
from utils import *; utils = UtilityFunctions(); output = utils.demo(utils)

# %% [markdown]
# ## test_utils
# %%
from testlib.test_utils import *; test_utils = TestUtilityFunctions(); output = utils.demo(test_utils)

# %% [markdown]
# ## clipboard_utils
# %%
from clipboard_utils import *; clipboard = Clipboard(); output = utils.demo(clipboard)

# ## electronics_utils
# %%
from electronics_utils import *; ee = Electronics(); output = utils.demo(ee)

# ## math_utils
# %%
from math_utils import *; math_utils = MathUtils(); output = utils.demo(math_utils)

# %% [markdown]
# ## widget_utils
# %%
from widget_utils import *; widget = Widgets(); output = utils.demo(widget)
