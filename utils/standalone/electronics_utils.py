import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
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

    lib_demo_params = [
        {'key': 'a', 'name': 'Calculate Max Value', 'function': 'calculate_max_value', 'inputs': [
            {'label': 'Value',  'name': 'val',    'type': float, 'default': 1000.0,  'width': '80px'},
            {'label': 'Tol',    'name': 'tol',    'type': float, 'default': 0.05, 'width': '60px'},
            {'label': 'PPM',    'name': 'ppm',    'type': float, 'default': 200,    'width': '60px'},
            {'label': 'DeltaT', 'name': 'deltaT', 'type': float, 'default': 60,    'width': '60px'},
        ]},
        {'key': 'b', 'name': 'Calculate Min Value', 'function': 'calculate_min_value', 'inputs': [
            {'label': 'Value',  'name': 'val',    'type': float, 'default': 1000.0,  'width': '80px'},
            {'label': 'Tol',    'name': 'tol',    'type': float, 'default': 0.05, 'width': '60px'},
            {'label': 'PPM',    'name': 'ppm',    'type': float, 'default': 200,    'width': '60px'},
            {'label': 'DeltaT', 'name': 'deltaT', 'type': float, 'default': 60,    'width': '60px'},
        ]},
        {'key': 'c', 'name': 'Calculate Min/Max Value', 'function': 'calculate_min_max_value', 'inputs': [
            {'label': 'Value',  'name': 'val',    'type': float, 'default': 1000.0,  'width': '80px'},
            {'label': 'Tol',    'name': 'tol',    'type': float, 'default': 0.05, 'width': '60px'},
            {'label': 'PPM',    'name': 'ppm',    'type': float, 'default': 200,    'width': '60px'},
            {'label': 'DeltaT', 'name': 'deltaT', 'type': float, 'default': 60,    'width': '60px'},
        ]},
        {'key': 'd', 'name': 'Get Standard Resistor Values', 'function': 'get_standard_resistor_value', 'inputs': [
            {'label': 'Series',         'name': 'series',         'options': ['E3','E6','E12','E24','E48','E96','E192'], 'default': 'E24'},
            {'label': 'Min',            'name': 'min_val',        'type': float, 'default': 100,  'width': '80px'},
            {'label': 'Max',            'name': 'max_val',        'type': float, 'default': 1000, 'width': '80px'},
            {'label': 'Exclusive stop', 'name': 'exclusive_stop', 'options': [True, False],       'default': True},
        ]},
        {'key': 'e', 'name': 'Parallel Resistance',
         'function': lambda self, resistances: self.r_para([float(r) for r in resistances.split(',')]),
         'inputs': [
            {'label': 'Resistances', 'name': 'resistances', 'type': str, 'default': '100,200', 'placeholder': 'comma-separated', 'width': '150px'},
        ]},
        {'key': 'f', 'name': 'Inverting Op-Amp Gain', 'function': 'inverting_opamp_gain', 'inputs': [
            {'label': 'Rf',  'name': 'Rf',  'type': float, 'default': 10000, 'width': '80px'},
            {'label': 'Rin', 'name': 'Rin', 'type': float, 'default': 1000,  'width': '80px'},
        ]},
        {'key': 'g', 'name': 'Non-Inverting Op-Amp Gain', 'function': 'non_inverting_opamp_gain', 'inputs': [
            {'label': 'Rf',  'name': 'Rf',  'type': float, 'default': 9000, 'width': '80px'},
            {'label': 'Rin', 'name': 'Rin', 'type': float, 'default': 1000,  'width': '80px'},
        ]},
        {'key': 'h', 'name': 'Voltage Divider', 'function': 'voltage_divider', 'inputs': [
            {'label': 'Vin',  'name': 'Vin',  'type': float, 'default': 5, 'allow_empty': True, 'width': '80px'},
            {'label': 'R1',   'name': 'R1',   'type': float, 'default': 1000, 'allow_empty': True, 'width': '80px'},
            {'label': 'R2',   'name': 'R2',   'type': float, 'default': 1000, 'allow_empty': True, 'width': '80px'},
            {'label': 'Vout', 'name': 'Vout', 'type': float, 'default': None, 'allow_empty': True, 'width': '80px'},
        ]},
    ]


if __name__ == '__main__':
    elec = Electronics()
    utils.demo(elec)
