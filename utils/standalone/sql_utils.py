import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()
utils.exit_if_module_missing('pyodbc')

import pyodbc


class SQL():
    """
    Mixin class for database-related utility functions.
    Supports SQL Server connections with Windows Authentication or SQL Authentication.
    """

    # _demo_conn is used only by lib_demo_params to hold a connection across button clicks.
    # The class API itself remains stateless — all methods still take conn as an argument.
    _demo_conn = None

    lib_demo_params = [
        {'key': 'a', 'name': 'Connect', 'function': lambda self, server, database, username, password: (
            setattr(self, '_demo_conn', self.db_connect(server, database, username or None, password or None)),
            f'Connected to {server}/{database}',
        )[-1], 'inputs': [
            {'label': 'Server',   'name': 'server',   'type': str, 'default': 'localhost', 'width': '150px'},
            {'label': 'Database', 'name': 'database', 'type': str, 'default': 'master',    'width': '150px'},
            {'label': 'Username', 'name': 'username', 'type': str, 'default': '', 'width': '120px', 'placeholder': 'blank = Windows Auth', 'allow_empty': True},
            {'label': 'Password', 'name': 'password', 'type': str, 'default': '', 'width': '120px', 'placeholder': 'blank = Windows Auth', 'allow_empty': True, 'password': True},
        ]},
        {'key': 'b', 'name': 'Close', 'function': lambda self: (
            self.db_close(self._demo_conn),
            setattr(self, '_demo_conn', None),
            'Disconnected.',
        )[-1], 'inputs': []},
        {'key': 'c', 'name': 'Query', 'function': lambda self, sql, as_dataframe: self.db_query(
            self._demo_conn, sql, as_dataframe=as_dataframe,
        ), 'inputs': [
            {'label': 'SQL',          'name': 'sql',          'type': str,  'default': 'SELECT TOP 10 * FROM sys.tables', 'width': '350px'},
            {'label': 'As DataFrame', 'name': 'as_dataframe', 'type': bool, 'default': True},
        ]},
        {'key': 'd', 'name': 'Execute', 'function': lambda self, sql: self.db_execute(
            self._demo_conn, sql,
        ), 'inputs': [
            {'label': 'SQL', 'name': 'sql', 'type': str, 'default': '', 'width': '350px'},
        ]},
    ]

    def db_connect(
        self,
        server: str,
        database: str,
        username: str = None,
        password: str = None,
        driver: str = "ODBC Driver 17 for SQL Server",
    ) -> pyodbc.Connection:
        """Connect to a SQL Server database.

        Uses Windows Authentication (Trusted_Connection) when username/password
        are omitted, otherwise uses SQL Server Authentication.

        Args:
            server: Server hostname or IP (e.g. 'myserver' or 'myserver\\instance').
            database: Database name.
            username: SQL login username. Omit for Windows Authentication.
            password: SQL login password. Omit for Windows Authentication.
            driver: ODBC driver name. Defaults to 'ODBC Driver 17 for SQL Server'.

        Returns:
            pyodbc.Connection object.
        """
        if username and password:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password};"
            )
        else:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
            )
        return pyodbc.connect(conn_str)

    def db_close(self, conn: pyodbc.Connection) -> None:
        """Close a database connection.

        Args:
            conn: pyodbc.Connection to close.
        """
        if conn:
            conn.close()

    def db_query(
        self,
        conn: pyodbc.Connection,
        sql: str,
        params: tuple = None,
        as_dataframe: bool = True,
    ):
        """Execute a SQL query and return the results.

        Args:
            conn: Active pyodbc.Connection.
            sql: SQL query string. Use '?' as parameter placeholders.
            params: Optional tuple of parameter values for parameterised queries.
            as_dataframe: If True (default), return a pandas DataFrame.
                          If False, return a list of pyodbc.Row objects.

        Returns:
            pandas.DataFrame or list[pyodbc.Row] depending on as_dataframe.
        """
        import pandas as pd

        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        if as_dataframe:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return pd.DataFrame.from_records(rows, columns=columns)
        else:
            return cursor.fetchall()

    def db_execute(
        self,
        conn: pyodbc.Connection,
        sql: str,
        params: tuple = None,
        commit: bool = True,
    ) -> int:
        """Execute a non-query SQL statement (INSERT / UPDATE / DELETE / DDL).

        Args:
            conn: Active pyodbc.Connection.
            sql: SQL statement string. Use '?' as parameter placeholders.
            params: Optional tuple of parameter values.
            commit: If True (default), commit the transaction automatically.

        Returns:
            Number of rows affected.
        """
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        if commit:
            conn.commit()
        return cursor.rowcount
