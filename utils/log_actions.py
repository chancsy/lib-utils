import os
import sys
from .utilities import UtilityFunctions
utils = UtilityFunctions()

def log_demo():
    print(f'{__name__} demo:')
    log = print_logging_start(logfile_directory_path='.', hide_stdout=True)
    print('test1')
    print('test2')
    print('test3')
    print_logging_end()
    utils.sleep(1.5) # wait for print_log_thread to finish writing to file
    print(log)
    print(utils.read_file(log))
    utils.remove_file(log)

def new_log(outputdir_path='.', prefix='', seconds=True):
    if not os.path.exists(outputdir_path):
        os.makedirs(outputdir_path)
    if seconds:
        time_stamp = utils.get_datetimestamp(style=0)
    else:
        time_stamp = utils.get_datestamp(style=0)
    if len(prefix):
        filename_prefix = f'{prefix}_'
    else:
        filename_prefix = ''

    log = os.path.join(outputdir_path, f'{filename_prefix}{time_stamp}.log')
    return log

def add_lines(filepath, text):
    with open(filepath, 'a') as file:
        file.write(text+'\n')

# Save string to log file, needs to provide line break explicitly, writes happen in separate thread
    # Usage:
    # print_and_log_thread_start(overwrite=True)
    # print_and_log_thread_stop()
print_log_queue = []
print_log = 0
print_log_thread = 0
def processPrintLogQueue():
    while(True):
        utils.sleep(1) # write to file once every second
        if len(print_log_queue):
            try:
                with open(print_log, 'a') as file:
                    while(len(print_log_queue)):
                        file.write(print_log_queue.pop(0))
            except:
                pass
        if print_log_thread.stop_flag():
            break

def startPrintLogThread(outputdir_path='.', overwrite=False):
    global print_log_thread, print_log
    print_log = new_log(outputdir_path, prefix='PrintLog', seconds=False)
    if overwrite:
        open(print_log, "w").close()
    print_log_thread = utils.StoppableThread(target=processPrintLogQueue)
    print_log_thread.start()
    return print_log

def stopPrintLogThread():
    print_log_thread.stop()

orig_stdout = ''

def print_logging_start(logfile_directory_path, add_datetimestamp=True, hide_stdout=False):
    global orig_stdout, print_log_queue

    class Unbuffered:
        def __init__(self, stream):
            self.stream = stream
        def write(self, data):
            if not hide_stdout:
                self.stream.write(data)
                self.stream.flush()

            if data == ('\n'): # ignore trailing newline from print()
                pass
            else:
                if add_datetimestamp:
                    print_log_queue.append(f'{utils.get_datetimestamp(style=1)}|{data}\n')
                else:
                    print_log_queue.append(f'{data}\n')
        def flush(self):
            pass

    print_log_queue = []
    print_log = startPrintLogThread(outputdir_path=logfile_directory_path, overwrite=False)
    orig_stdout = sys.stdout  # capture original state of stdout
    sys.stdout = Unbuffered(sys.stdout)
    return print_log

def print_logging_end():
    sys.stdout = orig_stdout
    stopPrintLogThread()
