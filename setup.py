# setup.py for lib/

from setuptools import setup, find_packages

setup(
    name='utils',
    version='0.1.0',
    packages=find_packages(include=['utils', 'utils.*']),
    include_package_data=True,
    install_requires=[
        # Add your dependencies here
        'numpy>=1.26.4',
        'pandas>=2.2.2',
    ],
    entry_points={
        'console_scripts': [
            # Add command line scripts here
        ],
    },
)
