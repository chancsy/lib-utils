# utils/__init__.py

# only utilities module is imported so that it can be accessed directly from utils
# example: from utils import *
from .utilities import *

# standalone helper modules have to be imported explicitly
# example: from utils.standalone.clipboard_utils import *

# dependencies for some functions are only checked at run time to reduce installation footprint
