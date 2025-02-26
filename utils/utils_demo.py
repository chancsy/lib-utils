# %%
from utils import *
utils = UtilityFunctions()
utils.ipython_auto_reload_modules()

# %% [markdown]
# ## utilities - Logging
# %%
logger = utils.Logger('.', add_datetimestamp=True)
logger.log("This is a debug message", level=logging.DEBUG)
logger.log("This is an info message", level=logging.INFO)
logger.log("This is a warning message", level=logging.WARNING)
logger.stop()
