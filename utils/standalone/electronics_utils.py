from ..utilities import UtilityFunctions
utils = UtilityFunctions()

utils.exit_if_module_missing('eseries')
import eseries
from eseries import E3, E6, E12, E24, E48, E96, E192

from .math_utils import EquationSolver

# Dictionary to map series names to eseries objects

class Electronics:
    RES_SERIES_MAP = {
        'E3': E3,
        'E6': E6,
        'E12': E12,
        'E24': E24,
        'E48': E48,
        'E96': E96,
        'E192': E192
    }

    def __init__(self):
        pass

    # Calculate the maximum value of a component given its nominal value, tolerance, ppm (temperature coefficient), and deltaT (temperature change)
    def calculate_max_value(self, val, tol=0.01, ppm=0, deltaT=0):
        return val * (1 + tol) + val * ppm / 1e6 * deltaT

    # Calculate the minimum value of a component given its nominal value, tolerance, ppm (temperature coefficient), and deltaT (temperature change)
    def calculate_min_value(self, val, tol=0.01, ppm=0, deltaT=0):
        return val * (1 - tol) - val * ppm / 1e6 * deltaT

    # Calculate the minimum and maximum values of a component given its nominal value, tolerance, ppm (temperature coefficient), and deltaT (temperature change)
    def calculate_min_max_value(self, val, tol=0.01, ppm=0, deltaT=0):
        max_value = self.calculate_max_value(val, tol, ppm, deltaT)
        min_value = self.calculate_min_value(val, tol, ppm, deltaT)
        return min_value, max_value

    # Return the value of standard resistor values for specified series, between the given range, using eseries library
    def get_standard_resistor_value(self, series, min_val=100, max_val=1000, exclusive_stop=True):
        if series in self.RES_SERIES_MAP:
            func = eseries.erange if not exclusive_stop else eseries.open_erange
            return list(func(self.RES_SERIES_MAP[series], min_val, max_val))
        else:
            raise ValueError(f"Series {series} is not recognized.")

    # calculate parallel resistance, r_parallel = 1 / (1/r1 + 1/r2 + 1/r3 + ...)
    def r_para(self, resistances):
        return 1 / sum(1 / r for r in resistances)

    # calculate inverting op-amp gain, gain = -Rf / Rin
    def inverting_opamp_gain(self, Rf, Rin):
        return -Rf / Rin

    # calculate non-inverting op-amp gain, gain = 1 + Rf / Rin
    def non_inverting_opamp_gain(self, Rf, Rin):
        return 1 + Rf / Rin

    # calculate the voltage divider output voltage, Vout = Vin * R2 / (R1 + R2)
    def voltage_divider(self, Vin=None, R1=None, R2=None, Vout=None):
        equation_str = 'Vin * R2 / (R1 + R2) - Vout'
        solver = EquationSolver(equation_str)
        return solver.solve(Vin=Vin, R1=R1, R2=R2, Vout=Vout)

    lib_demo_dict = [
        {'key': 'a', 'name': 'Calculate Max Value'},
        {'key': 'b', 'name': 'Calculate Min Value'},
        {'key': 'c', 'name': 'Calculate Min Max Value'},
        {'key': 'd', 'name': 'Get Standard Resistor Value'},
        {'key': 'e', 'name': 'Calculate Parallel Resistance'},
        {'key': 'f', 'name': 'Calculate Inverting Opamp Gain'},
        {'key': 'g', 'name': 'Calculate Non-Inverting Opamp Gain'},
        {'key': 'h', 'name': 'Voltage Divider'}
    ]

    def lib_demo(self, demo_desc):
        result = 0 # default return value
        if demo_desc in ['Calculate Max Value', 'Calculate Min Value', 'Calculate Min Max Value']:
            if (val := utils.get_user_input('Enter value', float)) is None: return None
            tol = utils.get_user_input('Enter tolerance', float, 0.01)
            ppm = utils.get_user_input('Enter ppm', float, 0)
            deltaT = utils.get_user_input('Enter deltaT', float, 0) if ppm != 0 else 0
            if demo_desc == 'Calculate Max Value':
                result = self.calculate_max_value(val, tol, ppm, deltaT)
            elif demo_desc == 'Calculate Min Value':
                result = self.calculate_min_value(val, tol, ppm, deltaT)
            elif demo_desc == 'Calculate Min Max Value':
                result = self.calculate_min_max_value(val, tol, ppm, deltaT)
        elif demo_desc == 'Get Standard Resistor Value':
            series = utils.get_user_input(f'Enter series ({", ".join(self.RES_SERIES_MAP.keys())})', str, 'E24')
            min_val = utils.get_user_input('Enter min value)', float, 100)
            max_val = utils.get_user_input('Enter max value)', float, 1000)
            exclusive_stop = utils.get_user_input('Exclusive stop', bool, 0)
            result = self.get_standard_resistor_value(series, min_val, max_val, exclusive_stop)
        elif demo_desc == 'Calculate Parallel Resistance':
            if (resistances := utils.get_user_input('Enter resistances (comma separated)', str)) is None: return None
            try:
                resistances = [float(r) for r in resistances.split(',')]
            except ValueError:
                print('Invalid input. Please enter comma separated values.')
                return None
            result = self.r_para(resistances)
        elif demo_desc == 'Calculate Inverting Opamp Gain':
            if (Rf := utils.get_user_input('Enter Rf', float)) is None: return None
            if (Rin := utils.get_user_input('Enter Rin', float)) is None: return None
            result = self.inverting_opamp_gain(Rf, Rin)
        elif demo_desc == 'Calculate Non-Inverting Opamp Gain':
            if (Rf := utils.get_user_input('Enter Rf', float)) is None: return None
            if (Rin := utils.get_user_input('Enter Rin', float)) is None: return None
            result = self.non_inverting_opamp_gain(Rf, Rin)
        elif demo_desc == 'Voltage Divider':
            Vin = utils.get_user_input('Enter Vin', float, allow_empty=True)
            R1 = utils.get_user_input('Enter R1', float, allow_empty=True)
            R2 = utils.get_user_input('Enter R2', float, allow_empty=True)
            Vout = utils.get_user_input('Enter Vout', float, allow_empty=True)
            result = self.voltage_divider(Vin, R1, R2, Vout)
        print(result)
        return result
