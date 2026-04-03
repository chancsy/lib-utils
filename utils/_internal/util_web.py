import base64
import os
import socket
import urllib.parse
import urllib.request
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

try:
    from IPython.display import HTML
except ImportError:
    HTML = None


class UtilityWebMixin:
    class URLExtractor:
        def __init__(self, base_url, ext):
            self.base_url = base_url
            self.ext = ext
            self.urls = []
            self.html_parser = HTMLParser()
            self.html_parser.handle_starttag = self.handle_starttag

        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                for attr in attrs:
                    if attr[0] == 'href' and attr[1].endswith(self.ext):
                        self.urls.append(urllib.parse.urljoin(self.base_url, attr[1]))

        def feed(self, data):
            self.html_parser.feed(data)

    def fetch_content(self, url):
        with urllib.request.urlopen(url) as response:
            return response.read().decode(errors='replace')

    def extract_urls(self, url, ext='', params={}):
        query_string = urllib.parse.urlencode(params)
        full_url = f'{url}?{query_string}' if params else url
        response = self.fetch_content(full_url)
        base_url = '{0.scheme}://{0.netloc}/'.format(urllib.parse.urlsplit(url))
        parser = self.URLExtractor(base_url, ext)
        parser.feed(response)
        return parser.urls

    def list_files_http(self, url, recursive=False, ignore_first_link=False, ext=''):
        FileListResult = namedtuple('FileListResult', ['files', 'dirs'])
        filelist = []
        dirlist = []
        links = self.extract_urls(url)
        if ignore_first_link:
            links = links[1:]
        for link in links:
            if link.endswith('/'):
                dirlist.append(link)
                if recursive:
                    filelist_child, dirlist_child = self.list_files_http(url=link, recursive=True, ignore_first_link=ignore_first_link, ext=ext)
                    filelist.extend(filelist_child)
                    dirlist.extend(dirlist_child)
            elif link.endswith(ext):
                filelist.append(link)
        return FileListResult(files=filelist, dirs=dirlist)

    def download_file(self, url, download_dir='.', overwrite=False, show_abs_path=True, suppress_output=False):
        try:
            filename = urllib.parse.unquote(url.split('/')[-1])
            file_path = os.path.join(download_dir, filename)

            if os.path.exists(file_path) and not overwrite:
                print(f"File '{os.path.abspath(file_path) if show_abs_path else os.path.basename(file_path)}' already exists. Skipping download.") if not suppress_output else None
                return 'skipped'

            urllib.request.urlretrieve(url, file_path)
            print(f"Downloaded '{os.path.abspath(file_path) if show_abs_path else os.path.basename(file_path)}'") if not suppress_output else None
            return 'downloaded'
        except Exception as e:
            self.print(f'Error downloading {urllib.parse.unquote(url)}: {e}')
            return 'failed'

    def download_file_to_memory(self, url):
        try:
            with urllib.request.urlopen(url) as response:
                return response.read()
        except Exception as e:
            self.print(f'Error downloading {urllib.parse.unquote(url)}: {e}')
            return None

    def download_files(self, urls, download_dir='.', overwrite=False, parallel_download=True, max_workers=5, output_type='progress', auto_retry_count=1):
        suppress_output = output_type == 'quiet' or output_type != 'full'

        def get_summary_line():
            return f'Total: {len(urls)}, Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}'

        self.create_directory(download_dir)
        print(f'Download directory: {os.path.abspath(download_dir)}')

        retries = 0

        while retries < auto_retry_count+1:
            downloaded = 0
            skipped = 0
            failed = 0

            if retries:
                print(f'Retrying download... ({retries}/{auto_retry_count})') if output_type != 'quiet' else None

            if not parallel_download:
                for url in urls:
                    result = self.download_file(url, download_dir, overwrite, show_abs_path=False, suppress_output=suppress_output)
                    if result == 'downloaded':
                        downloaded += 1
                    elif result == 'skipped':
                        skipped += 1
                    else:
                        failed += 1
                    self.print_same_line(f'{get_summary_line()}') if output_type == 'progress' else None
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_url = {executor.submit(self.download_file, url, download_dir, overwrite, show_abs_path=False, suppress_output=suppress_output): url for url in urls}

                    for future in as_completed(future_to_url):
                        result = future.result()
                        if result == 'downloaded':
                            downloaded += 1
                        elif result == 'skipped':
                            skipped += 1
                        else:
                            failed += 1
                        self.print_same_line(f'{get_summary_line()}') if output_type == 'progress' else None
            if failed == 0:
                break
            if retries == auto_retry_count:
                print(f'Failed to download {failed} files after {retries} retries. Stopping.') if output_type != 'quiet' else None
                break
            retries += 1
            self.print_same_line_end()

        self.print_same_line_end() if output_type == 'progress' else print(f'{get_summary_line()}')

    def post_to_teams(self, webhook_url, text):
        text_conditioned_for_teams = str(text).replace('\n', '\n\n')
        jsonData = {
            'text': text_conditioned_for_teams
        }
        return self.send_webhook(webhook_url, jsonData)

    def send_webhook(self, webhook_url, json_data):
        if not self.module_exists('requests'):
            return
        import requests

        response = requests.post(webhook_url, json=json_data, verify=False)
        if not (response.status_code == 201 or response.status_code == 201 or response.status_code == 202):
            print(f'{response} - Please check')
        return response

    def get_public_ip(self):
        if not self.module_exists('requests'):
            return
        import requests
        response = requests.get('https://api.ipify.org?format=json')
        data = response.json()
        ip = data['ip']
        return ip

    def get_location_from_ip(self, ip):
        if not self.module_exists('requests'):
            return
        import requests
        response = requests.get('https://ipinfo.io/'+ip+'/json')
        data = response.json()
        city = data['city']
        country = data['country']
        return city, country

    def extract_host_from_url(self, url):
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme and parsed_url.netloc:
            return parsed_url.netloc
        return url

    def is_host_reachable(self, host, port=80, timeout=5):
        host = self.extract_host_from_url(host)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.timeout, socket.error):
            return False

    def img_to_base64(self, img_path):
        with open(img_path, 'rb') as img_file:
            return base64.b64encode(img_file.read()).decode()

    def display_img_from_base64(self, img_base64):
        if HTML is None:
            raise ImportError('IPython is required for display_img_from_base64()')
        return HTML(f'<img src="data:image/png;base64,{img_base64}">')
