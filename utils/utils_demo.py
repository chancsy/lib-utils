# %%
from utils import *
utils = UtilityFunctions()
utils.ipython_auto_reload_modules()

# %% [markdown]
# ## utilities - Logging
# %%
logger = utils.Logger('.', log_prefix='Test')
logger.log("This is a debug message", level=logging.DEBUG)
logger.log("This is an info message", level=logging.INFO)
logger.log("This is a warning message", level=logging.WARNING)
logger.log("This is a critical message", level=logging.CRITICAL)
logger.stop()
