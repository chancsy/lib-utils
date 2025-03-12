# %% [markdown]
# ## Prepare the environment
# %%
from utils import *; utils = UtilityFunctions(); output = utils.demo(utils)

# %% [markdown]
# ## fisher_utils
# %%
from ftestlib.fisher_utils import *; fisher_utils = FisherUtilityFunctions(); output = utils.demo(fisher_utils)

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
