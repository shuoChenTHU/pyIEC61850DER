# -*- coding: utf-8 -*-
"""
Storage of functions and implementations provided by a third party.

"""

# %% Timeout handler for multi-threading tasks

"""
Timeout decorator in case a function is stuck in one single never-ending process.
Ref: https://stackoverflow.com/questions/492519/timeout-on-a-function-call
attention: the solution with package signal does not work on Windows.

The windows solution posted by Rich was abandoned because it leaves a forever running thread.
BTW: signal package causes error when used in a multithreading pool, so this approach has to be
dumped anyway...
So we use the open-source code of aaronchall instead.
License @aaronchall: 
https://gist.github.com/aaronchall/6331661fe0185c30a0b4


NOTE: this is still a bad solution for our applicaiton. It exists just to avoid runtime error
in windows environment.
Consider use the wrapt_timeout_decorator lib to handle windows timeouts
Ref: https://towardsdatascience.com/adding-timeouts-to-functions-using-wrapt-timeout-decorator-21790890a49b

"""

import sys
import threading

try:
    import thread
except ImportError:
    import _thread as thread

try:  # use code that works the same in Python 2 and 3
    range, _print = xrange, print

    def print(*args, **kwargs):
        flush = kwargs.pop('flush', False)
        _print(*args, **kwargs)
        if flush:
            kwargs.get('file', sys.stdout).flush()
except NameError:
    pass


def cdquit(fn_name):
    # print to stderr, unbuffered in Python 2.
    print('{0} took too long'.format(fn_name), file=sys.stderr)
    sys.stderr.flush()  # Python 3 stderr is likely buffered.
    thread.interrupt_main()  # raises KeyboardInterrupt


def timeout_checker(max_timeout: int):
    '''
    use as decorator to exit process if
    function takes longer than max_timeout seconds
    '''

    def outer(fn):
        def inner(*args, **kwargs):
            timer = threading.Timer(max_timeout, cdquit, args=[fn.__name__])
            timer.start()
            try:
                result = fn(*args, **kwargs)
            finally:
                timer.cancel()
            return result

        return inner

    return outer



# %% timeout deco
'''
solution for timeout deco, provided by devmonaut
ref: https://stackoverflow.com/questions/492519/timeout-on-a-function-call
FIXME: this piece of code can not be used till the error in mulitthreading context
Error trace:
Traceback (most recent call last):
  File "/work/simulation/virtual_ied.py", line 167, in update_data_buffers
    update_data_buffers(ied_config, ied_server, ctime_local_str, verbose=True)
  File "/work/processing/runtime.py", line 358, in update_data_buffers
    conn_obj_scan(ied_config.interface.df, item)
  File "/work/settings/helper.py", line 141, in time_limited
    signal.signal(signal.SIGALRM, handler)
  File "/usr/local/lib/python3.7/signal.py", line 47, in signal
    handler = _signal.signal(_enum_to_int(signalnum), _enum_to_int(handler))
ValueError: signal only works in main thread

# import signal
# from functools import wraps
# def timeout_checker(timeout_secs: int):
#     def wrapper(func):
#         @wraps(func)
#         def time_limited(*args, **kwargs):
#             # Register an handler for the timeout
#             def handler(signum, frame):
#                 raise Exception(f"Timeout for function '{func.__name__}'")
#             # Register the signal function handler
#             signal.signal(signal.SIGALRM, handler)
#             # Define a timeout for your function
#             signal.alarm(timeout_secs)
#             result = None
#             try:
#                 result = func(*args, **kwargs)
#             except Exception as exc:
#                 raise exc
#             finally:
#                 # disable the signal alarm
#                 signal.alarm(0)
#             return result
#         return time_limited
#     return wrapper
'''

# %% hanging thread monitor

'''
For debugging purpose, use the code provided by Nicco Kunzmann to print out hanging
threads by the daemon thread monitoring_thread
'''

## The MIT License (MIT)
## ---------------------
##
## Copyright (C) 2014 Nicco Kunzmann
##
## https://gist.github.com/niccokunzmann/6038331
##
## Permission is hereby granted, free of charge, to any person obtaining
## a copy of this software and associated documentation files (the "Software"),
## to deal in the Software without restriction, including without limitation
## the rights to use, copy, modify, merge, publish, distribute, sublicense,
## and/or sell copies of the Software, and to permit persons to whom the
## Software is furnished to do so, subject to the following conditions:
##
## The above copyright notice and this permission notice shall be included
## in all copies or substantial portions of the Software.
##
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
## OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
## FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
## IN THE SOFTWARE.

"""
    import hanging_threads

If a thread is at the same place for SECONDS_FROZEN then the stacktrace is printed.

This script prints

--------------------    Thread 6628     --------------------
  File "hanging_threads.py", line 70, in <module>
        time.sleep(3) # TEST
--------------------    Thread 6628     --------------------
  File "hanging_threads.py", line 70, in <module>
        time.sleep(3) # TEST

"""


def hanging_threads(white_list: list = [], SECONDS_FROZEN: int = 10, TESTS_PER_SECOND: int = 10):
    try:
        try:
            from threading import _get_ident as get_ident
        except ImportError:
            from threading import get_ident
    except ImportError:
        from thread import get_ident
    import linecache
    import time

    def frame2string(frame):
        # from module traceback
        lineno = frame.f_lineno  # or f_lasti
        co = frame.f_code
        filename = co.co_filename
        name = co.co_name
        s = '  File "{}", line {}, in {}'.format(filename, lineno, name)
        line = linecache.getline(filename, lineno, frame.f_globals).lstrip()
        return s + '\n\t' + line

    def thread2list(frame):
        l = []
        while frame:
            l.insert(0, frame2string(frame))
            frame = frame.f_back
        return l

    def monitor():
        self = get_ident()
        old_threads = {}
        while 1:
            time.sleep(1. / TESTS_PER_SECOND)
            now = time.time()
            then = now - SECONDS_FROZEN
            frames = sys._current_frames()
            new_threads = {}
            for frame_id, frame in frames.items():
                new_threads[frame_id] = thread2list(frame)
            for th in set(white_list):  # make sure white list threads vanish
                if th in new_threads:
                    del new_threads[th]
            for thread_id, frame_list in new_threads.items():
                if thread_id == self: continue
                if thread_id in white_list: continue
                if thread_id not in old_threads or \
                        frame_list != old_threads[thread_id][0]:
                    new_threads[thread_id] = (frame_list, now)
                elif old_threads[thread_id][1] < then:
                    if frame_id not in white_list:
                        print_frame_list(frame_list, frame_id)
                else:
                    new_threads[thread_id] = old_threads[thread_id]
            old_threads = new_threads

    def print_frame_list(frame_list, frame_id):
        sys.stderr.write('-' * 20 +
                         'Thread {}'.format(frame_id).center(20) +
                         '-' * 20 +
                         '\n' +
                         ''.join(frame_list))

    def start_monitoring():
        '''After hanging SECONDS_FROZEN the stack trace of the deadlock is printed automatically.'''
        th = threading.Thread(target=monitor)
        th.daemon = True
        th.start()
        return th

    monitoring_thread = start_monitoring()

    return monitoring_thread