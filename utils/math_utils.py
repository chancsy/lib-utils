import numpy as np

class MathUtils:
    def __init__(self):
        pass

    def demo(self, func=None):
        print('random_integer(0, 10):', randint_0_10 := [self.random_integer(0, 10) for x in range(10)])
        print('random_float(0, 1):', rand_float_0_1 := [self.random_float(0, 1) for x in range(5)])
        print('clip(x, 5, 8):', f'x={randint_0_10},', 'result=', [self.clip(x, 5, 8) for x in randint_0_10])
        # print('calc_relative_error(5, 10):', self.calc_relative_error(5, 10)) # to improve
        llim=5; ulim=8; print(f'is_within_limits(x, {llim}, {ulim}):', f'x={randint_0_10},', 'result=', [self.is_within_limits(x, llim, ulim) for x in randint_0_10])
        print('interpolate(x, [0, 1], [4, 20]):', [f'{x/10}->{self.interpolate(x/10, [0,1], [4,20])}' for x in range(0, 11)])
        print('interpolate(x, [0, 20, [0, 1]]):', [f'{x}->{self.interpolate(x, [4,20], [0,1])}' for x in range(4, 21, 4)])

    def random_integer(self, start=0, end=100):
        # from random import randrange
        # return randrange(start, end+1)
        return np.random.randint(start, end + 1)

    def random_float(self, start=0, end=100):
        # from random import uniform
        # return uniform(start, end)
        return np.random.uniform(start, end)

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

    def is_within_limits(self, measurement, lower_limit, upper_limit):
        return lower_limit <= measurement <= upper_limit

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
