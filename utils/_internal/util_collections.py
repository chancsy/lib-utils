class UtilityCollectionsMixin:
    def get_unique_elements(self, input_list, sorted=True, preserve_order=False):
        if sorted:
            unique_list = list(set(input_list))
            unique_list.sort()
        else:
            if preserve_order:
                seen = set()
                unique_list = []
                for item in input_list:
                    if item not in seen:
                        seen.add(item)
                        unique_list.append(item)
            else:
                unique_list = list(set(input_list))
        return unique_list

    def list_to_csv(self, data, delim=',', na_str='nan'):
        if na_str == 'nan':
            return delim.join([na_str if x is None else str(x) for x in data])
        return delim.join([na_str if (x is None or str(x).lower() == 'nan') else str(x) for x in data])

    def dict_reverse_lookup(self, dict, lookup_value):
        for key, value in dict.items():
            if value == lookup_value:
                return key
        return None

    def dict_list_lookup(self, dict_list, lookup_key, lookup_value, return_key=None):
        for d in dict_list:
            if d.get(lookup_key) == lookup_value:
                if return_key is None:
                    return d
                return d.get(return_key)
        return None

    def find_smallest_gte(self, value, values, use_bisect=False):
        sorted_values = sorted(values)
        if use_bisect:
            import bisect
            index = bisect.bisect_left(sorted_values, value)
            if index < len(sorted_values):
                return sorted_values[index]
            return None
        else:
            for v in sorted_values:
                if v >= value:
                    return v
            return None
