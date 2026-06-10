import sqlite3
from typing import Optional
import os

class SQLite():
    lib_demo_params = [
        {'key': 'a', 'name': 'Set DB Path', 'function': 'set_db_path', 'inputs': [
            {'label': 'DB Path', 'name': 'db_path', 'type': str, 'default': 'test.db', 'width': '200px'},
        ]},
        {'key': 'b', 'name': 'Send Query', 'function': 'query', 'inputs': [
            {'label': 'Query', 'name': 'query_string', 'type': str, 'default': 'SELECT * FROM my_table LIMIT 10', 'width': '350px'},
        ]},
        {'key': 'c', 'name': 'List Tables', 'function': 'list_tables', 'inputs': []},
        {'key': 'd', 'name': 'If_Table_Exists', 'function': 'if_table_exists', 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
        {'key': 'e', 'name': 'Create Table', 'function': lambda self, table_name, columns, constraints: self.create_table(
            table_name,
            [c.strip() for c in columns.split(',')],
            [c.strip() for c in constraints.split(',')],
        ), 'inputs': [
            {'label': 'Table Name',   'name': 'table_name',   'type': str, 'default': 'my_table',    'width': '100px'},
            {'label': 'Columns',      'name': 'columns',      'type': str, 'default': 'name, value', 'width': '100px', 'placeholder': 'col1, col2'},
            {'label': 'Constraints',  'name': 'constraints',  'type': str, 'default': 'TEXT UNIQUE, REAL',  'width': '100px', 'placeholder': 'TEXT NOT NULL, REAL'},
        ]},
        {'key': 'f', 'name': 'Drop Table', 'function': 'drop_table', 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
        {'key': 'g', 'name': 'Get Row Count', 'function': 'get_row_count', 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
        {'key': 'h', 'name': 'Insert Row', 'function': lambda self, table_name, columns, values, replace, unique_columns: self.insert(
            table_name,
            [c.strip() for c in columns.split(',')],
            [v.strip() for v in values.split(',')],
            replace=replace,
            unique_columns=[c.strip() for c in unique_columns.split(',')] if unique_columns else None,
        ), 'inputs': [
            {'label': 'Table Name',     'name': 'table_name',     'type': str,  'default': 'my_table',    'width': '100px'},
            {'label': 'Columns',        'name': 'columns',        'type': str,  'default': 'name, value', 'width': '100px', 'placeholder': 'col1, col2'},
            {'label': 'Values',         'name': 'values',         'type': str,  'default': 'hello, 1.0',  'width': '100px', 'placeholder': 'val1, val2'},
            {'label': 'Replace',        'name': 'replace',        'type': bool, 'default': False, 'width': 'auto'},
            {'label': 'Unique Columns', 'name': 'unique_columns', 'type': str,  'default': 'name', 'width': '100px', 'placeholder': 'col1, col2 (optional)', 'allow_empty': True},
        ]},
        {'key': 'i', 'name': 'Get Rows', 'function': 'get_rows', 'inputs': [
            {'label': 'Table Name', 'name': 'table_name', 'type': str, 'default': 'my_table', 'width': '100px'},
        ]},
    ]

    def __init__(self, db_path: str = None):
        super().__init__()
        self.db_path = db_path

    def set_db_path(self, db_path: str):
        if not os.path.isfile(db_path):
            print(f'Warning: file does not exist: {db_path}. New file will be created upon connection attempt. If this is not intended, please check the path and try again.')
        self.db_path = db_path

    def connect(self):
        if not self.db_path:
            raise ValueError("Database path is not set. Please set the DB path before connecting.")
        # check if connection already exists
        if hasattr(self, 'conn') and self.conn:
            print('Connection already exists')
            return
        self.conn = sqlite3.connect(self.db_path)

    def close(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
        self.conn = None

    def list_tables(self) -> list:
        self.connect()
        query_string = '''
            SELECT name FROM sqlite_master
            WHERE type='table'
        '''
        cursor = self.conn.cursor()
        cursor.execute(query_string)
        tables = [row[0] for row in cursor.fetchall()]
        self.close()
        return tables

    def if_table_exists(self, table_name: str) -> bool:
        self.connect()
        query_string = f'''
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='{table_name}'
        '''
        cursor = self.conn.cursor()
        cursor.execute(query_string)

        result = cursor.fetchone()
        self.close()
        return result is not None

    def create_table(self, table_name: str, column_names: Optional[list] = None, column_constraints: Optional[list] = None):
        """Create a table with an auto-increment 'id' primary key plus caller-defined columns.

        column_names and column_constraints are paired by position — they must have the same length.
        column_constraints is the SQL type/constraint string for each column (e.g. 'TEXT', 'REAL', 'TEXT UNIQUE NOT NULL').
        Does nothing if the table already exists (IF NOT EXISTS).

        Example:
            db.create_table('sensors', ['serial', 'temp'], ['TEXT UNIQUE', 'REAL'])
            # CREATE TABLE sensors (id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE, serial TEXT UNIQUE, temp REAL)
        """
        self.connect()

        query_string = f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
            {', '.join([f'{name} {constraint}' for name, constraint in zip(column_names, column_constraints)])}
            )
        '''
        cursor = self.conn.cursor()
        cursor.execute(query_string)
        self.conn.commit()

        self.close()

    def drop_table(self, table_name: str):
        self.connect()
        query_string = f'''
            DROP TABLE IF EXISTS {table_name}
        '''
        cursor = self.conn.cursor()
        cursor.execute(query_string)
        self.conn.commit()
        self.close()

    def get_row_count(self, table_name: str) -> int:
        self.connect()
        query_string = f'''
            SELECT COUNT(*) FROM {table_name}
        '''
        cursor = self.conn.cursor()
        cursor.execute(query_string)
        result = cursor.fetchone()
        self.close()
        return result[0] if result else 0

    def find_columns_with_constraint(self, table_name: str, constraint: str) -> list:
        """Return column names whose definition contains the given constraint keyword.

        Parses the raw CREATE TABLE SQL from sqlite_master — does not use PRAGMA,
        so it works for any constraint string including compound ones.

        Example:
            db.find_columns_with_constraint('sensors', 'UNIQUE')  # → ['serial']
            db.find_columns_with_constraint('sensors', 'NOT NULL') # → ['serial']
        """
        self.connect()

        matching_columns = []
        cursor = self.conn.cursor()

        # Query for UNIQUE constraints from table creation SQL
        cursor.execute('''
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name=?
        ''', (table_name,))

        table_info = cursor.fetchone()

        if table_info:
            create_table_sql = table_info[0]
            columns_info = create_table_sql[create_table_sql.index('(')+1:create_table_sql.rindex(')')].split(',')
            for col_info in columns_info:
                if constraint in col_info:
                    col_name = col_info.strip().split(' ')[0]
                    matching_columns.append(col_name)

        self.close()
        return matching_columns

    def insert(self, table_name: str, column_names: list, column_values: list, replace: bool = False, unique_columns: Optional[list] = None):
        """Insert a row and return a string result: 'inserted', 'updated', 'ignored', or 'error'.

        Behaviour depends on the replace and unique_columns arguments:
          - replace=False              → INSERT OR IGNORE (skip silently if duplicate)
          - replace=True, no unique    → INSERT OR REPLACE (delete + reinsert, new id)
          - replace=True, unique given → UPSERT via ON CONFLICT (update in-place, preserves id)

        unique_columns must match columns that have a UNIQUE constraint in the table schema,
        otherwise ON CONFLICT will raise an OperationalError (caught and returned as 'error').

        Example:
            db.insert('sensors', ['serial', 'temp'], ['SN001', 25.3])
            db.insert('sensors', ['serial', 'temp'], ['SN001', 26.1], replace=True, unique_columns=['serial'])
            # → 'updated' (SN001 already exists, temp updated to 26.1, id preserved)
        """
        self.connect()
        cursor = self.conn.cursor()

         # Check if record exists when we have unique columns
        record_exists = False
        if unique_columns:
            unique_values = [column_values[column_names.index(col)] for col in unique_columns if col in column_names]
            check_query = f'''
                SELECT COUNT(*) FROM {table_name}
                WHERE {' AND '.join([f'{col} = ?' for col in unique_columns])}
            '''
            cursor.execute(check_query, unique_values)
            record_exists = cursor.fetchone()[0] > 0

        # Build appropriate query based on replace flag and unique columns
        if replace and unique_columns:
            # UPSERT - preserve auto-increment ID
            conflict_columns = ', '.join(unique_columns)
            update_columns = [name for name in column_names if name not in unique_columns]
            query_string = f'''
                INSERT INTO {table_name} ({', '.join(column_names)})
                VALUES ({', '.join(['?' for _ in column_values])})
                ON CONFLICT({conflict_columns}) DO UPDATE SET
                {', '.join([f'{name} = excluded.{name}' for name in update_columns])}
            '''
        elif replace:
            # Standard replace
            query_string = f'''
                INSERT OR REPLACE INTO {table_name} ({', '.join(column_names)})
                VALUES ({', '.join(['?' for _ in column_values])})
            '''
        else:
            # Ignore duplicates
            query_string = f'''
                INSERT OR IGNORE INTO {table_name} ({', '.join(column_names)})
                VALUES ({', '.join(['?' for _ in column_values])})
            '''

        try:
            cursor.execute(query_string, column_values)
            sqlite_rowcount = cursor.rowcount
            self.conn.commit()

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
        finally:
            self.close()

        return result

    def get_rows(self, table_name: str, column_names: Optional[list] = None, column_values: Optional[list] = None, return_column_names: Optional[list] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, time_column: str = 'log_time') -> Optional[list]:
        """Retrieve rows with optional column filtering and date range.

        - column_names / column_values: paired WHERE filters (AND-ed together).
          If both are omitted, all rows are returned.
        - return_column_names: if given, only those columns are included in each returned tuple.
        - start_date / end_date: filter on time_column (ISO format 'YYYY-MM-DD HH:MM:SS').
          Only applied when column_names/column_values are also provided.
        - time_column: name of the datetime column used for date range filtering (default 'log_time').
        - Returns None if no rows match.

        Example:
            db.get_rows('sensors')                                        # all rows
            db.get_rows('sensors', ['serial'], ['SN001'])                 # rows where serial='SN001'
            db.get_rows('sensors', return_column_names=['serial', 'temp'])# all rows, 2 columns only
        """
        if start_date is None:
            start_date = '1970-01-01 00:00:00'
        if end_date is None:
            end_date = '2100-01-01 00:00:00'
        self.connect()

        if column_names and column_values:
            query_string = f'''
                SELECT * FROM {table_name}
                WHERE {' AND '.join([f"{name} = ?" for name in column_names])} AND {time_column} BETWEEN ? AND ?
            '''
            cursor = self.conn.cursor()
            cursor.execute(query_string, column_values + [start_date, end_date])
        else:
            query_string = f'''
                SELECT * FROM {table_name}
            '''
            cursor = self.conn.cursor()
            cursor.execute(query_string)

        rows = cursor.fetchall()
        self.close()
        if not rows:
            return None

        if return_column_names:
        # Get indices of requested return columns
            self.connect()
            cursor = self.conn.cursor()
            cursor.execute(f'PRAGMA table_info({table_name})')
            table_info = cursor.fetchall()
            col_indices = [i for i, col in enumerate(table_info) if col[1] in return_column_names]

            # Extract only requested columns
            filtered_rows = []
            for row in rows:
                filtered_row = tuple(row[i] for i in col_indices)
                filtered_rows.append(filtered_row)
            self.close()
            return filtered_rows
        return rows

    def query(self, query_string: str) -> list:
        self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(query_string)
            results = cursor.fetchall()
        finally:
            self.close()
        return results
