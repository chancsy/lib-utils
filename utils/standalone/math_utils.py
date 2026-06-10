import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()

utils.exit_if_module_missing('numpy')
import numpy as np

from itertools import combinations

utils.exit_if_module_missing('sympy')
from sympy import symbols, solve, Eq
from sympy.core.sympify import SympifyError

class IntegerLimits:
    """C-style integer limits for common fixed-width types."""
    UINT8_MAX  = 2**8  - 1  # 255
    UINT16_MAX = 2**16 - 1  # 65535
    UINT32_MAX = 2**32 - 1  # 4294967295
    UINT64_MAX = 2**64 - 1  # 18446744073709551615

    INT8_MAX  = 2**(8  - 1) - 1  # 127
    INT16_MAX = 2**(16 - 1) - 1  # 32767
    INT32_MAX = 2**(32 - 1) - 1  # 2147483647
    INT64_MAX = 2**(64 - 1) - 1  # 9223372036854775807

    INT8_MIN  = -INT8_MAX  - 1  # -128
    INT16_MIN = -INT16_MAX - 1  # -32768
    INT32_MIN = -INT32_MAX - 1  # -2147483648
    INT64_MIN = -INT64_MAX - 1  # -9223372036854775808

# Module-level aliases for direct import convenience
UINT8_MAX  = IntegerLimits.UINT8_MAX
UINT16_MAX = IntegerLimits.UINT16_MAX
UINT32_MAX = IntegerLimits.UINT32_MAX
UINT64_MAX = IntegerLimits.UINT64_MAX
INT8_MAX   = IntegerLimits.INT8_MAX
INT16_MAX  = IntegerLimits.INT16_MAX
INT32_MAX  = IntegerLimits.INT32_MAX
INT64_MAX  = IntegerLimits.INT64_MAX
INT8_MIN   = IntegerLimits.INT8_MIN
INT16_MIN  = IntegerLimits.INT16_MIN
INT32_MIN  = IntegerLimits.INT32_MIN
INT64_MIN  = IntegerLimits.INT64_MIN

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

    # Linear interpolation & extrapolation
    # Example: interpolate(12, [4, 20], [0, 100]) returns 50 (mA to %)
    # Example: interpolate(50, [0, 100], [4, 20]) returns 12 (% to mA)
    def interpolate(self, value, source_range, target_range, extrapolate: bool = True):
        if not extrapolate:
            return np.interp(value, source_range, target_range)
        else:  # extrapolate with linear function (better than np.polyfit)
            # Normalize value to 0 to 1 based on source_range
            normalized_value = (value - source_range[0]) / (source_range[-1] - source_range[0])
            # Scale normalized_value to target_range
            return target_range[0] + normalized_value * (target_range[-1] - target_range[0])

    # Fit polynomial coefficients; optionally cap degree to len(points)-1.
    def polyfit(self, known_x, known_y, degree, prevent_overfit: bool = True):
        if prevent_overfit:
            max_degree = max(0, len(known_x) - 1)
            degree = min(int(degree), max_degree)
        x = np.array(known_x)
        y = np.array(known_y)
        z = np.polyfit(x, y, degree)
        return z

    # Polynomial regression; degree=1 delegates to interpolate() for accuracy
    def trend(self, known_x: list, known_y: list, x: float, degree: int = 1, extrapolate: bool = True, prevent_overfit: bool = True) -> float:
        if prevent_overfit:
            max_degree = max(0, len(known_x) - 1)
            degree = min(int(degree), max_degree)
        if degree == 1:
            return self.interpolate(x, known_x, known_y, extrapolate=extrapolate)
        coefficients = np.polyfit(known_x, known_y, degree) # Fit a polynomial of the specified degree to the data points
        return float(np.polyval(coefficients, x)) # Evaluate the polynomial at the given x value

    # Find the combination of numbers whose sum is closest to target_sum
    def find_best_combo_sum(self, numbers: list, target_sum: float, max_len: int = None, allow_exceed: bool = True) -> tuple:
        best_sum = float('-inf') if allow_exceed else 0
        best_combination = []
        max_len = max_len if max_len is not None else len(numbers)
        for i in range(1, max_len + 1):
            for combo in combinations(numbers, i):
                total_sum = sum(combo)
                if total_sum == target_sum:
                    return list(combo), total_sum
                if (allow_exceed and abs(target_sum - total_sum) < abs(target_sum - best_sum)) or \
                        (not allow_exceed and total_sum <= target_sum and total_sum > best_sum):
                    best_sum = total_sum
                    best_combination = list(combo)
        return best_combination, best_sum

    def print_data_stats(self, read_count, callback, x_min=np.inf, x_max=-np.inf, interval_s=0, calc_stdev=False):
        try:
            timer = utils.IntervalTimer(interval_s) if interval_s > 0 else None
            sum = 0
            current_read_count = 0
            data_count = 0
            if calc_stdev:
                dataset = self.Dataset()
            while(current_read_count < read_count):
                x = callback()
                current_read_count += 1
                if x is not None:
                    x_min = min(x, x_min)
                    x_max = max(x, x_max)
                    sum = sum + x
                    data_count = data_count + 1
                    if calc_stdev:
                        dataset.add_data(x)

                avg = sum / data_count if data_count > 0 else 0
                val = str(x) if x is not None else 'No data'
                print_msg = f'n={data_count}, data={val}, min={x_min}, max={x_max}, avg={avg}'
                if calc_stdev:
                    stdev = dataset.get_std_dev()
                    print_msg += f', stddev={stdev}'
                utils.print_same_line(print_msg)

                if timer:
                    if current_read_count < read_count: # avoid waiting after the last read
                        timer.wait()
            utils.print_same_line_end()
            return avg if data_count > 0 else None
        except KeyboardInterrupt:
            pass

    lib_demo_params = [
        {'key': 'a', 'name': 'Random Integer', 'function': 'random_integer', 'inputs': [
            {'label': 'Start', 'name': 'start', 'type': int, 'default': 0, 'width': '60px'},
            {'label': 'End', 'name': 'end', 'type': int, 'default': 100, 'width': '60px'},
        ]},
        {'key': 'b', 'name': 'Random Float', 'function': 'random_float', 'inputs': [
            {'label': 'Start', 'name': 'start', 'type': float, 'default': 0.0, 'width': '60px'},
            {'label': 'End', 'name': 'end', 'type': float, 'default': 1.0, 'width': '60px'},
        ]},
        {'key': 'c', 'name': 'Deg → Rad', 'function': 'deg_to_rad', 'inputs': [
            {'label': 'Degree', 'name': 'degree', 'type': float, 'default': 180.0, 'width': '60px'},
        ]},
        {'key': 'd', 'name': 'Rad → Deg', 'function': 'rad_to_deg', 'inputs': [
            {'label': 'Radian', 'name': 'rad', 'type': float, 'default': 3.14159, 'width': '80px'},
        ]},
        {'key': 'e', 'name': 'Clip', 'function': 'clip', 'inputs': [
            {'label': 'Value', 'name': 'val', 'type': float, 'default': 5.0, 'width': '60px'},
            {'label': 'Low', 'name': 'clip_low', 'type': float, 'default': None, 'allow_empty': True, 'width': '60px'},
            {'label': 'High', 'name': 'clip_high', 'type': float, 'default': None, 'allow_empty': True, 'width': '60px'},
        ]},
        {'key': 'f', 'name': 'Within Limits', 'function': 'is_within_limits', 'inputs': [
            {'label': 'Value', 'name': 'measurement', 'type': float, 'default': 5.0, 'width': '60px'},
            {'label': 'Low', 'name': 'llim', 'type': float, 'default': 0.0, 'width': '60px'},
            {'label': 'High', 'name': 'ulim', 'type': float, 'default': 10.0, 'width': '60px'},
        ]},
        {'key': 'g', 'name': 'Relative Error', 'function': 'calc_relative_error', 'inputs': [
            {'label': 'Ref', 'name': 'ref', 'type': float, 'default': 1.0, 'width': '60px'},
            {'label': 'Val', 'name': 'val', 'type': float, 'default': 0.9, 'width': '60px'},
        ]},
        {'key': 'h', 'name': 'Interpolate',
         'function': lambda self, source_range_str, target_range_str, value, extrapolate:
             self.interpolate(value, [float(x.strip()) for x in source_range_str.split(',')],
                                     [float(x.strip()) for x in target_range_str.split(',')],
                                     extrapolate=extrapolate),
         'inputs': [
            {'label': 'Source range', 'name': 'source_range_str', 'type': str, 'default': '4,20', 'width': '100px', 'placeholder': 'e.g. 4,20'},
            {'label': 'Target range', 'name': 'target_range_str', 'type': str, 'default': '0,100', 'width': '100px', 'placeholder': 'e.g. 0,100'},
            {'label': 'Value', 'name': 'value', 'type': float, 'default': 12.0, 'width': '60px'},
            {'label': 'Extrapolate', 'name': 'extrapolate', 'type': bool, 'default': True},
        ]},
        {'key': 'i', 'name': 'Polyfit',
         'function': lambda self, known_x_str, known_y_str, degree, prevent_overfit:
             self.polyfit([float(x.strip()) for x in known_x_str.split(',')],
                          [float(x.strip()) for x in known_y_str.split(',')], degree, prevent_overfit),
         'inputs': [
            {'label': 'X values', 'name': 'known_x_str', 'type': str, 'default': '1,2,3', 'width': '120px', 'placeholder': 'e.g. 1,2,3'},
            {'label': 'Y values', 'name': 'known_y_str', 'type': str, 'default': '2,4,6', 'width': '120px', 'placeholder': 'e.g. 2,4,6'},
            {'label': 'Degree', 'name': 'degree', 'type': int, 'default': 1, 'width': '40px'},
            {'label': "Don't overfit", 'name': 'prevent_overfit', 'type': bool, 'default': True},
        ]},
        {'key': 'j', 'name': 'Trend',
         'function': lambda self, known_x_str, known_y_str, x, degree, prevent_overfit:
             self.trend([float(v.strip()) for v in known_x_str.split(',')],
                        [float(v.strip()) for v in known_y_str.split(',')], x, degree, prevent_overfit=prevent_overfit),
         'inputs': [
            {'label': 'X values', 'name': 'known_x_str', 'type': str, 'default': '1,2,3,4', 'width': '120px', 'placeholder': 'e.g. 1,2,3'},
            {'label': 'Y values', 'name': 'known_y_str', 'type': str, 'default': '2.1,3.9,6.08,7.99', 'width': '120px', 'placeholder': 'e.g. 2,4,6'},
            {'label': 'X', 'name': 'x', 'type': float, 'default': 4.0, 'width': '60px'},
            {'label': 'Degree', 'name': 'degree', 'type': int, 'default': 1, 'width': '40px'},
            {'label': "Don't overfit", 'name': 'prevent_overfit', 'type': bool, 'default': True},
        ]},
        {'key': 'k', 'name': 'Best Combo Sum',
         'function': lambda self, numbers_str, target_sum, max_len:
             self.find_best_combo_sum([float(x.strip()) for x in numbers_str.split(',')], target_sum, max_len),
         'inputs': [
            {'label': 'Numbers', 'name': 'numbers_str', 'type': str, 'default': '1,2,3,4,5', 'width': '150px'},
            {'label': 'Target', 'name': 'target_sum', 'type': float, 'default': 7.0, 'width': '60px'},
            {'label': 'Max Len', 'name': 'max_len', 'type': int, 'default': None, 'allow_empty': True, 'width': '60px'},
        ]},
    ]

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

if __name__ == '__main__':
    math = MathUtils()
    utils.demo(math)
