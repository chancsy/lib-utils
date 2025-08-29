from utils.utilities import UtilityFunctions
utils = UtilityFunctions()

utils.exit_if_module_missing('numpy')
import numpy as np

utils.exit_if_module_missing('sympy')
from sympy import symbols, solve, Eq
from sympy.core.sympify import SympifyError

# Constants for the maximum values of different unsigned integer types
# These are calculated based on the size of the data types in bytes
# For example, for an unsigned 8-bit integer (uint8), the maximum value is 2^8 - 1 = 255.
UINT8_MAX = 2**8 - 1 # 2^8 - 1 = 255
UINT16_MAX = 2**16 - 1 # 2^16 - 1 = 65535
UINT32_MAX = 2**32 - 1 # 2^32 - 1 = 4294967295
UINT64_MAX = 2**64 - 1 # 2^64 - 1 = 18446744073709551615

INT8_MAX = 2*(8-1) - 1 # 2^7 - 1 = 127
INT16_MAX = 2*(16-1) - 1 # 2^15 - 1 = 32767
INT32_MAX = 2*(32-1) - 1 # 2^31 - 1 = 2147483647
INT64_MAX = 2*(64-1) - 1 # 2^63 - 1 = 9223372036854775807

INT8_MIN = -INT8_MAX - 1 # -128
INT16_MIN = -INT16_MAX - 1 # -32768
INT32_MIN = -INT32_MAX - 1 # -2147483648
INT64_MIN = -INT64_MAX - 1 # -9223372036854775808

class MathUtils:
    def __init__(self):
        pass

    # # round to nearest integer, instead of Python's round to even
    # def round_nearest_int(self, x):
    #     return int(x + 0.5) if x >= 0 else int(x - 0.5)
    #
    # conventional rounding to n decimal places
    def _round(self, x, n=0):
        def _round_int(x):
            return int(x + 0.5) if x >= 0 else int(x - 0.5)
        factor = 10 ** n
        return _round_int(x * factor) / factor

    def random_integer(self, start=0, end=100):
        # from random import randrange
        # return randrange(start, end+1)
        return np.random.randint(start, end + 1)

    def random_float(self, start=0, end=100):
        # from random import uniform
        # return uniform(start, end)
        return np.random.uniform(start, end)

    def deg_to_rad(self, degree):
        return degree * np.pi / 180

    def rad_to_deg(self, rad):
        return rad * 180 / np.pi

    def clip(self, val, clip_low=None, clip_high=None):
        # if clip_low:
        #     val = max(val, clip_low)
        # if clip_high:
        #     val = min(val, clip_high)
        # return val
        return np.clip(val, clip_low, clip_high)

    def calc_relative_error(self, ref, val):
        if ref != 0:
            return (val-ref)/ref
        return float("nan")

    def is_within_limits(self, measurement, llim, ulim):
        return llim <= measurement <= ulim

    # Same as linear interpolation, see interpolate()
    # def scale_value_between_ranges(self, value, source_range, target_range):
    #     # Normalize value to 0 to 1 based on source_range
    #     normalized_value = (value - source_range[0]) / (source_range[1] - source_range[0])
    #     # Scale normalized_value to target_range
    #     return target_range[0] + normalized_value * (target_range[1] - target_range[0])

    def interpolate(self, value, source_range, target_range):
        return np.interp(value, source_range, target_range)

    def polyfit(self, known_x, known_y, degree):
        x = np.array(known_x)
        y = np.array(known_y)
        z = np.polyfit(x, y, degree)
        return z

    def lib_demo(self):
        print('random_integer(0, 10):', randint_0_10 := [self.random_integer(0, 10) for x in range(10)])
        print('random_float(0, 1):', rand_float_0_1 := [self.random_float(0, 1) for x in range(5)])
        print('deg_to_rad(90):', rad_90 := self.deg_to_rad(90))
        print(f'rad_to_deg({rad_90}):', self.rad_to_deg(rad_90))
        print('clip(x, 5, 8):', f'x={randint_0_10},', 'result=', [self.clip(x, 5, 8) for x in randint_0_10])
        print('calc_relative_error(1, 0.9):', self.calc_relative_error(1, 0.9)) # to improve
        llim=5; ulim=8; print(f'is_within_limits(x, {llim}, {ulim}):', f'x={randint_0_10},', 'result=', [self.is_within_limits(x, llim, ulim) for x in randint_0_10])
        print('interpolate(x, [0, 1], [4, 20]):', [f'{x/10}->{self.interpolate(x/10, [0,1], [4,20])}' for x in range(0, 11)])
        print('interpolate(x, [0, 20, [0, 1]]):', [f'{x}->{self.interpolate(x, [4,20], [0,1])}' for x in range(4, 21, 4)])
        print('1st degree polyfit([1,2,3], [4,5,6], 1):', self.polyfit([1,2,3], [4,5,6], 1))
        print('2nd degree polyfit([1,2,3], [4,5,6], 2):', self.polyfit([1,2,3], [4,5,6], 2))
        print('3rd degree polyfit([1,2,3], [4,5,6], 3):', self.polyfit([1,2,3], [4,5,6], 3))

# Solve equations with one unknown variable
class EquationSolver:
    def __init__(self, equation_str):
        try:
            # Extract variable symbols from the equation string
            self.symbols = {var: symbols(var) for var in self.extract_symbols(equation_str)}
            # Parse the equation string to create a symbolic equation
            self.equation = Eq(eval(equation_str, {**self.symbols}), 0)
        except SympifyError:
            raise ValueError("Invalid equation string or variable symbols")
        except Exception as e:
            raise ValueError(f"Error creating symbolic equation: {e}")

    def extract_symbols(self, equation_str):
        import re
        # Find all variable names in the equation string
        return set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', equation_str))

    def solve(self, **kwargs):
        knowns = {self.symbols[var]: value for var, value in kwargs.items() if value is not None}
        unknowns = [self.symbols[var] for var in self.symbols if kwargs.get(var) is None]

        if len(unknowns) != 1:
            raise ValueError("You must specify the values of all but one variable, leaving one to be calculated")

        result = solve(self.equation.subs(knowns), unknowns[0])
        return result[0] if result else None
