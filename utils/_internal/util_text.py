import re
import string
import urllib.request


class UtilityTextMixin:
    def remove_non_printable_ascii(self, a_str):
        ascii_chars = set(string.printable)
        return ''.join(x for x in a_str if x in ascii_chars)

    def contains_non_printable_ascii(self, a_str):
        return any(char not in string.printable for char in a_str)

    def contains_digits(self, string):
        return any(char.isdigit() for char in string)

    def contains_uppercase(self, string):
        return any(x.isupper() for x in string)

    def contains_lowercase(self, string):
        return any(x.islower() for x in string)

    def pad_char(self, text, char='-', length=80):
        if len(text) <= length-4:
            return f' {text} '.center(length, char)
        return text

    def pad_left(self, text, char=' ', length=80):
        return text.rjust(length, char)

    def pad_right(self, text, char=' ', length=80):
        return text.ljust(length, char)

    def str2float(self, val):
        try:
            return float(val)
        except ValueError:
            return None

    def str2int(self, val):
        try:
            return int(float(val))
        except ValueError:
            return None

    # natural sort key for sorting strings with numbers
    def natural_sort_key(self, text):
        return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

    def capitalize_title(self, title):
        exceptions = {'of', 'the', 'and', 'in', 'on', 'at', 'to', 'for', 'with', 'a', 'an'}
        words = title.split()
        capitalized_words = [word.capitalize() if word.lower() not in exceptions else word.lower() for word in words]
        if capitalized_words:
            capitalized_words[0] = capitalized_words[0].capitalize()
        return ' '.join(capitalized_words)

    # Generates an HTML anchor tag
    def generate_html_link(self, url, text=None, new_window=True):
        if text is None:
            text = url
        if new_window:
            return '<a target="_blank" href="{}">{}</a>'.format(url, text)
        else:
            return '<a href="{}">{}</a>'.format(url, text)

    def extract_lines(self, lines, string1, string2, include_matching_string_line=False):
        lines_between = []
        inside_range = False

        for line in lines:
            if string1 in line:
                inside_range = True
                if include_matching_string_line:
                    lines_between.append(line)
                continue
            if string2 in line and inside_range:
                if include_matching_string_line:
                    lines_between.append(line)
                break
            if inside_range:
                lines_between.append(line)
        return lines_between

    def extract_lines_from_file(self, file_path, string1, string2, include_matching_string_line=False):
        if file_path.startswith('https://') or file_path.startswith('http://'):
            data = urllib.request.urlopen(file_path)
            lines = data.readlines()
            lines = [line.decode('utf-8') for line in lines]
            lines = [line.rstrip('\n\r') for line in lines]
            return self.extract_lines(lines, string1, string2, include_matching_string_line)
        else:
            with open(file_path, 'r') as lines:
                return self.extract_lines(lines, string1, string2, include_matching_string_line)

    def parse_range_string(self, range_str, range_sep='~'):
        if not range_str:
            return []
        result = set()
        parts = range_str.split(',')
        for part in parts:
            if range_sep in part:
                start, end = part.split(range_sep)
                try:
                    start = int(start)
                    end = int(end)
                    if start <= end:
                        result.update(range(start, end + 1))
                except ValueError:
                    pass
            else:
                try:
                    result.add(int(part))
                except ValueError:
                    pass
        return sorted(result)

    def range_to_string(self, numbers, range_sep='~'):
        if not numbers:
            return ''
        numbers = sorted(set(numbers))
        ranges = []
        start = prev = numbers[0]

        for num in numbers[1:]:
            if num == prev + 1:
                prev = num
            else:
                if start == prev:
                    ranges.append(f"{start}")
                else:
                    ranges.append(f"{start}{range_sep}{prev}")
                start = prev = num

        if start == prev:
            ranges.append(f"{start}")
        else:
            ranges.append(f"{start}{range_sep}{prev}")

        return ','.join(ranges)
