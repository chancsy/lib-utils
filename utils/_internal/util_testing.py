class UtilityTestingMixin:
    def print_test_environment(self, pkg_list=[]):
        print(self.pad_char('Test Environment'))
        print(
            f'PC Info: '
            f'Name={self.get_hostname()}, '
            f'SN={self.get_serial_number()}, '
            f'OS={self.os_info()}, '
            f'Up Time={self.get_up_time_days():.1f}days'
            )
        python_version_info = f'Python={self.get_python_version()}'
        jupyterlab_info = f', Jupyterlab={self.get_python_pkg_version("jupyterlab")}' if self.in_ipython() else ''
        print(f'Python Info: {python_version_info + jupyterlab_info}')

        pkg_versions = ', '.join([f'{pkg}={self.get_python_pkg_version(pkg)}' for pkg in pkg_list])
        if pkg_versions:
            print(f'Packages Info: {pkg_versions}')
