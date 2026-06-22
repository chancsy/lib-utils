import re
import sqlite3
from typing import Optional
import os


def _sql_id(name: str) -> str:
    """Validate and double-quote a SQL identifier (table or column name).

    SQLite does not support parameterized identifiers, so we validate against
    a safe pattern and quote with double-quotes to prevent SQL injection.
    Raises ValueError on invalid names.
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


class SQLite():
    """
    Mixin class for SQLite database utility functions.
    Stateless — all methods take conn as an argument.
    """

    # _demo_conn is used only by lib_demo_params to hold a connection across button clicks.
    # The class API itself remains stateless — all methods still take conn as an argument.
    _demo_conn = None

    lib_demo_params = [
        {'key': 'a', 'name': 'Connect', 'function': lambda self, db_path: (
            setattr(self, '_demo_conn', self.connect(db_path)),
            f'Connected: {db_path}',
        )[-1], 'inputs': [
            {'label': 'DB Path', 'name': 'db_path', 'type': str, 'default': 'test.db', 'width': '200px'},
        ]},
        {'key': 'b', 'name': 'Disconnect', 'function': lambda self: (
            self.disconnect(self._demo_conn),
            setattr(self, '_demo_conn', None),
            'Disconnected.',
        )[-1], 'inputs': []},
        {'key': 'c', 'name': 'Send Query', 'function': lambda self, query_string: self.query(
            self._demo_conn, query_string,
        ), 'inputs': [
            {'label': 'Query', 'name': 'query_string', 'type': str, 'default': 'SELECT * FROM my_table LIMIT 10', 'width': '350px'},
        ]},
        {'key': 'd', 'name': 'List Tables', 'function': lambda self: self.list_tables(
            self._demo_conn,
        ), 'inputs': []},
        {'key': 'e', 'name': 'If Table Exists', 'function': lambda self, table_name: self.if_table_exists(
            self._demo_conn, table_name,
        ), 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
        {'key': 'f', 'name': 'Create Table', 'function': lambda self, table_name, columns, constraints: self.create_table(
            self._demo_conn,
            table_name,
            [c.strip() for c in columns.split(',')],
            [c.strip() for c in constraints.split(',')],
        ), 'inputs': [
            {'label': 'Table Name',  'name': 'table_name',  'type': str, 'default': 'my_table',          'width': '100px'},
            {'label': 'Columns',     'name': 'columns',     'type': str, 'default': 'name, value',       'width': '100px', 'placeholder': 'col1, col2'},
            {'label': 'Constraints', 'name': 'constraints', 'type': str, 'default': 'TEXT UNIQUE, REAL',  'width': '100px', 'placeholder': 'TEXT NOT NULL, REAL'},
        ]},
        {'key': 'g', 'name': 'Drop Table', 'function': lambda self, table_name: self.drop_table(
            self._demo_conn, table_name,
        ), 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
        {'key': 'h', 'name': 'Get Row Count', 'function': lambda self, table_name: self.get_row_count(
            self._demo_conn, table_name,
        ), 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
        {'key': 'i', 'name': 'Insert Row', 'function': lambda self, table_name, columns, values, replace, unique_columns: self.insert(
            self._demo_conn,
            table_name,
            [c.strip() for c in columns.split(',')],
            [v.strip() for v in values.split(',')],
            replace=replace,
            unique_columns=[c.strip() for c in unique_columns.split(',')] if unique_columns else None,
        ), 'inputs': [
            {'label': 'Table Name',     'name': 'table_name',     'type': str,  'default': 'my_table',    'width': '100px'},
            {'label': 'Columns',        'name': 'columns',        'type': str,  'default': 'name, value', 'width': '100px', 'placeholder': 'col1, col2'},
            {'label': 'Values',         'name': 'values',         'type': str,  'default': 'hello, 1.0',  'width': '100px', 'placeholder': 'val1, val2'},
            {'label': 'Replace',        'name': 'replace',        'type': bool, 'default': False},
            {'label': 'Unique Columns', 'name': 'unique_columns', 'type': str,  'default': 'name', 'width': '100px', 'placeholder': 'col1, col2 (optional)', 'allow_empty': True},
        ]},
        {'key': 'j', 'name': 'Get Rows', 'function': lambda self, table_name: self.get_rows(
            self._demo_conn, table_name,
        ), 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
    ]

    def connect(self, db_path: str) -> sqlite3.Connection:
        """Open and return a new SQLite connection to db_path.

        Warns if the file does not yet exist (a new file will be created by sqlite3).

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            sqlite3.Connection object.
        """
        if not os.path.isfile(db_path):
            print(f'Warning: file does not exist: {db_path}. New file will be created upon connection attempt. If this is not intended, please check the path and try again.')
        return sqlite3.connect(db_path)

    def disconnect(self, conn: sqlite3.Connection) -> None:
        """Close a database connection.

        Args:
            conn: sqlite3.Connection to close.
        """
        if conn:
            conn.close()

    def list_tables(self, conn: sqlite3.Connection) -> list:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [row[0] for row in cursor.fetchall()]

    def if_table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cursor.fetchone() is not None

    def create_table(self, conn: sqlite3.Connection, table_name: str, column_names: Optional[list] = None, column_constraints: Optional[list] = None):
        _sql_id(table_name)
        """Create a table with an auto-increment 'id' primary key plus caller-defined columns.

        column_names and column_constraints are paired by position — they must have the same length.
        column_constraints is the SQL type/constraint string for each column (e.g. 'TEXT', 'REAL', 'TEXT UNIQUE NOT NULL').
        Does nothing if the table already exists (IF NOT EXISTS).

        Example:
            db.create_table(conn, 'sensors', ['serial', 'temp'], ['TEXT UNIQUE', 'REAL'])
            # CREATE TABLE sensors (id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE, serial TEXT UNIQUE, temp REAL)
        """
        cursor = conn.cursor()
        t = _sql_id(table_name)
        cols = ', '.join([f'{_sql_id(name)} {constraint}' for name, constraint in zip(column_names, column_constraints)])
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {t} (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
            {cols}
            )
        ''')
        conn.commit()

    def drop_table(self, conn: sqlite3.Connection, table_name: str):
        cursor = conn.cursor()
        cursor.execute(f'DROP TABLE IF EXISTS {_sql_id(table_name)}')
        conn.commit()

    def get_row_count(self, conn: sqlite3.Connection, table_name: str) -> int:
        cursor = conn.cursor()
        cursor.execute(f'SELECT COUNT(*) FROM {_sql_id(table_name)}')
        result = cursor.fetchone()
        return result[0] if result else 0

    def find_columns_with_constraint(self, conn: sqlite3.Connection, table_name: str, constraint: str) -> list:
        """Return column names whose definition contains the given constraint keyword.

        Parses the raw CREATE TABLE SQL from sqlite_master — does not use PRAGMA,
        so it works for any constraint string including compound ones.

        Example:
            db.find_columns_with_constraint(conn, 'sensors', 'UNIQUE')   # → ['serial']
            db.find_columns_with_constraint(conn, 'sensors', 'NOT NULL') # → ['serial']
        """
        cursor = conn.cursor()
        # Query for UNIQUE constraints from table creation SQL
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        table_info = cursor.fetchone()

        matching_columns = []
        if table_info:
            create_table_sql = table_info[0]
            columns_info = create_table_sql[create_table_sql.index('(')+1:create_table_sql.rindex(')')].split(',')
            for col_info in columns_info:
                if constraint in col_info:
                    col_name = col_info.strip().split(' ')[0]
                    matching_columns.append(col_name)
        return matching_columns

    def insert(self, conn: sqlite3.Connection, table_name: str, column_names: list, column_values: list, replace: bool = False, unique_columns: Optional[list] = None):
        """Insert a row and return a string result: 'inserted', 'updated', 'ignored', or 'error'.

        Behaviour depends on the replace and unique_columns arguments:
          - replace=False              → INSERT OR IGNORE (skip silently if duplicate)
          - replace=True, no unique    → INSERT OR REPLACE (delete + reinsert, new id)
          - replace=True, unique given → UPSERT via ON CONFLICT (update in-place, preserves id)

        unique_columns must match columns that have a UNIQUE constraint in the table schema,
        otherwise ON CONFLICT will raise an OperationalError (caught and returned as 'error').

        Example:
            db.insert(conn, 'sensors', ['serial', 'temp'], ['SN001', 25.3])
            db.insert(conn, 'sensors', ['serial', 'temp'], ['SN001', 26.1], replace=True, unique_columns=['serial'])
            # → 'updated' (SN001 already exists, temp updated to 26.1, id preserved)
        """
        cursor = conn.cursor()

         # Check if record exists when we have unique columns
        t = _sql_id(table_name)
        safe_cols = [_sql_id(c) for c in column_names]

        record_exists = False
        if unique_columns:
            safe_unique = [_sql_id(c) for c in unique_columns]
            unique_values = [column_values[column_names.index(col)] for col in unique_columns if col in column_names]
            cursor.execute(
                f"SELECT COUNT(*) FROM {t} WHERE {' AND '.join([f'{c} = ?' for c in safe_unique])}",
                unique_values,
            )
            record_exists = cursor.fetchone()[0] > 0

        # Build appropriate query based on replace flag and unique columns
        if replace and unique_columns:
            # UPSERT - preserve auto-increment ID
            safe_unique = [_sql_id(c) for c in unique_columns]
            conflict_columns = ', '.join(safe_unique)
            update_cols = [_sql_id(n) for n in column_names if n not in unique_columns]
            query_string = f'''
                INSERT INTO {t} ({', '.join(safe_cols)})
                VALUES ({', '.join(['?' for _ in column_values])})
                ON CONFLICT({conflict_columns}) DO UPDATE SET
                {', '.join([f'{c} = excluded.{c}' for c in update_cols])}
            '''
        elif replace:
            # Standard replace
            query_string = f'''
                INSERT OR REPLACE INTO {t} ({', '.join(safe_cols)})
                VALUES ({', '.join(['?' for _ in column_values])})
            '''
        else:
            # Ignore duplicates
            query_string = f'''
                INSERT OR IGNORE INTO {t} ({', '.join(safe_cols)})
                VALUES ({', '.join(['?' for _ in column_values])})
            '''

        try:
            cursor.execute(query_string, column_values)
            sqlite_rowcount = cursor.rowcount
            conn.commit()

            # Determine operation result for Fisher test log management
            if replace:
                if record_exists:
                    result = 'updated'
                else:
                    result = 'inserted'
            else:
                # INSERT OR IGNORE case
                if sqlite_rowcount > 0:
                    result = 'inserted'
                else:
                    result = 'ignored'

        except sqlite3.IntegrityError as e:
            print(f'IntegrityError during Fisher test log insert: {e}')
            result = 'ignored'  # Treat errors as ignored for robust EE_SGP workflows
        except sqlite3.Error as e:
            print(f'SQLite error: {e}')
            result = 'error'

        return result

    def get_rows(self, conn: sqlite3.Connection, table_name: str, column_names: Optional[list] = None, column_values: Optional[list] = None, return_column_names: Optional[list] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, time_column: str = 'log_time') -> Optional[list]:
        """Retrieve rows with optional column filtering and date range.

        - column_names / column_values: paired WHERE filters (AND-ed together).
          If both are omitted, all rows are returned.
        - return_column_names: if given, only those columns are included in each returned tuple.
        - start_date / end_date: filter on time_column (ISO format 'YYYY-MM-DD HH:MM:SS').
          Only applied when column_names/column_values are also provided.
        - time_column: name of the datetime column used for date range filtering (default 'log_time').
        - Returns None if no rows match.

        Example:
            db.get_rows(conn, 'sensors')                                        # all rows
            db.get_rows(conn, 'sensors', ['serial'], ['SN001'])                 # rows where serial='SN001'
            db.get_rows(conn, 'sensors', return_column_names=['serial', 'temp'])# all rows, 2 columns only
        """
        if start_date is None:
            start_date = '1970-01-01 00:00:00'
        if end_date is None:
            end_date = '2100-01-01 00:00:00'

        t = _sql_id(table_name)
        cursor = conn.cursor()
        if column_names and column_values:
            safe_filter_cols = [_sql_id(n) for n in column_names]
            cursor.execute(
                f"SELECT * FROM {t} WHERE {' AND '.join([f'{c} = ?' for c in safe_filter_cols])} AND {_sql_id(time_column)} BETWEEN ? AND ?",
                column_values + [start_date, end_date],
            )
        else:
            cursor.execute(f'SELECT * FROM {t}')

        rows = cursor.fetchall()
        if not rows:
            return None

        if return_column_names:
            # Get indices of requested return columns
            cursor.execute(f'PRAGMA table_info({t})')
            table_info = cursor.fetchall()
            col_indices = [i for i, col in enumerate(table_info) if col[1] in return_column_names]
            # Extract only requested columns
            return [tuple(row[i] for i in col_indices) for row in rows]

        return rows

    def query(self, conn: sqlite3.Connection, query_string: str) -> list:
        cursor = conn.cursor()
        cursor.execute(query_string)
        return cursor.fetchall()
