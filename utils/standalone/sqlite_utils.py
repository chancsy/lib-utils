import sqlite3
from typing import Optional

class SQLite():
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path

    def connect(self):
        # check if connection already exists
        if hasattr(self, 'conn') and self.conn:
            print('Connection already exists')
            return
        self.conn = sqlite3.connect(self.db_path)

    def close(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
        self.conn = None

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

    # return a list of column names that match specified constraint
    def find_columns_with_constraint(self, table_name: str, constraint: str) -> list:
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

        self.close()
        return result

    # Retrieve rows with optional filtering by column names and values, if return_column_names is specified, only those columns are returned
    def get_rows(self, table_name: str, column_names: Optional[list] = None, column_values: Optional[list] = None, return_column_names: Optional[list] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[list]:
        if start_date is None:
            start_date = '1970-01-01 00:00:00'
        if end_date is None:
            end_date = '2100-01-01 00:00:00'
        self.connect()

        if column_names and column_values:
            query_string = f'''
                SELECT * FROM {table_name}
                WHERE {' AND '.join([f"{name} = ?" for name in column_names])} AND test_time BETWEEN ? AND ?
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
