import pandas as pd


class UtilityDataFrameMixin:
    def unique_names(self, names):
        names = list(names)
        seen = {}
        for i, col in enumerate(names):
            if col in seen:
                seen[col] += 1
                names[i] = f"{col}_{seen[col]}"
            else:
                seen[col] = 0
        return names

    def array_to_df(self, array, has_header=True, column_names=None):
        if has_header:
            df = pd.DataFrame(array[1:], columns=array[0])
        else:
            if column_names is not None:
                if len(column_names) != len(array[0]):
                    raise ValueError("Column names length does not match array length.")
                df = pd.DataFrame(array, columns=column_names)
            else:
                df = pd.DataFrame(array)
        return df

    def df_unique_columns(self, df):
        unique_header = self.unique_names(df.columns)
        df.columns = unique_header
        return df

    def df_to_numeric(self, df):
        df = self.df_unique_columns(df)

        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (TypeError, ValueError) as e:
                print(f"Error converting column '{col}' to numeric: {e}")
        return df
