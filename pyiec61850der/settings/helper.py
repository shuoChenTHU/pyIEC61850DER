# -*- coding: utf-8 -*-
"""
General helper functions for all submodules.

This sub-module is a collection of helper functions related to module import, time conversion, value type assertion and
such.

Regarding the timestamp management, in general the tuple output of get_ctime_bundles collection three data formats:
    - UNIX time: float
    - time string: str with a specific string format (default: '%Y-%m-%dT%H:%M:%S.%f')
    - datetime object
Some times it is helpful to have them all for interchangeable usage. Sometimes it is more efficient to have one
specific format out of the three. Currently there is a mixed usage of both.

NOTE: the time handling functions were implemented at different time and for different purposes, thus look quite nasty.
    We need to straight out the time format here, many functions has UTC in the function name but they may not really
    handle a time string as UTC properly! Other problems arise as these functions serve a specific purpose, not generalised.
    Consider using standard python libs to handle the time functions, such as time conversion and time diff.

"""

import os
import sys
import ctypes
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Union
import dateutil.parser as time_parser
import pytz  # this module deals with time zones
import time
import calendar
import ast
import json
import uuid
import numbers
import numpy as np
import importlib
import sys
import types
import logging
import logging.handlers
from logging import Logger
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
import queue


logger = logging.getLogger(__name__)

@dataclass()
class KwargsHandler(object):
    """
    A parent class that can handle kwargs uniformly.
    """

    def apply_kwargs(self, is_overwrite:bool = True, **kwargs):
        """
        A post init method to mix in the kwargs pairs with unknown keys.
        """

        field_names = {f.name for f in fields(self)}
        for k, v in kwargs.items():
            if k in field_names:
                if is_overwrite:
                    setattr(self, k, v)
                    logger.warning(f'Unknown attribute {k} has been added and set, this may cause inconsistency')
                else:
                    logger.info(f"Found redundant attr {k}, NO ACTION. Use other methods to overwrite existing attr.")
            else:
                setattr(self, k, v)
                logger.warning(f"Unknown attr {k} added and set. Attention, this may cause inconsistency")

class StdDataType(object):
    """
    A parent class to store some commonly used numeric values for type hint.
    """

    FloatTypes = Union[float, np.floating, np.float64, np.float32,]
    IntTypes = Union[int, np.integer, np.int16, np.int32, np.int64,]
    BoolTypes = Union[bool, np.bool_,]
    NumericTypes = Union[FloatTypes, IntTypes, BoolTypes]
    AllTypes = Union[NumericTypes, str]


def set_work_dir():
    """
    Set the working directory to the sub-folder defined in the Dockerfile.
    Only affects applications running in containers on Linux OS.
    """

    if os.name != 'nt':  # if not windows os
        sys.path.append("/work/")
        list_file = os.listdir("/work/")
        logger.info("check files in working directory")
        logger.info(list_file)
        os.environ["PATH"] = "/work/;" + os.environ["PATH"]
    else:
        logger.info('Running in windows environment, no change required')
        pass


def set_env_libiec61850():
    """
    Set up the Python environment and OS dynamic linking paths, so that the libiec61850 lib can always be seamlessly
    located. It should work platform-independently.
    """
    cdir = os.getcwd()
    lib_ver = os.environ.get('LIB_VERSION', '1.6.0')
    # lib_dependency_folder = os.environ.get('LIB_SRC_NAME', 'libiec61850-1.6')
    if os.name != 'nt':  # Linux / POSIX
        # Folder containing _pyiec61850.so & pyiec61850.py
        lib_name = f'libiec61850_{lib_ver}'
        binding_dir_underscore = os.path.join(cdir, lib_name)
        binding_dir_dash = os.path.join(cdir, lib_name)
        # pylib_dir = os.path.join(cdir, "pylibiec61850", "linux")
        # src_dir = os.path.join(cdir, lib_dependency_folder, "build", "src")

        # 1. Add directories to Python module search path
        for path in [cdir, binding_dir_underscore, binding_dir_dash]:
            if os.path.exists(path) and path not in sys.path:
                sys.path.insert(0, path)

        # 2. Add dynamic library path for runtime linker
        sep = ":"
        ld_paths = [binding_dir_underscore, binding_dir_dash, os.environ.get("LD_LIBRARY_PATH", "")]
        os.environ["LD_LIBRARY_PATH"] = sep.join(filter(None, ld_paths))
    else:  # Windows
        sep = ";"
        lib_name = "pylibiec61850"
        win_dir = os.path.join(cdir, lib_name, "windows")
        for path in [cdir, win_dir]:
            if os.path.exists(path) and path not in sys.path:
                sys.path.insert(0, path)
        os.environ["PATH"] = f"{cdir}{sep}{win_dir}{sep}" + os.environ.get("PATH", "")


def import_libiec61850():
    """
    Import libiec61850 Python bindings with detailed error logging.
    """

    platform_name = "windows" if os.name == "nt" else "linux"

    # Search candidates: direct module import FIRST, then subpackages
    candidates = [
        "pyiec61850",                               # Direct import from sys.path (libiec61850_1.6.0)
        "iec61850",
        f"pylibiec61850.{platform_name}.pyiec61850",
        f"pylibiec61850.{platform_name}.iec61850",
    ]

    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", None)
            logger.info(
                f"Successfully imported module '{module_name}'"
                f"{f' (version {version})' if version else ''}"
            )
            return module

        except Exception as err:
            # Output full exception details
            logger.warning(f"Could not import '{module_name}': {type(err).__name__} - {err}")

    logger.error("Failed to import libiec61850 Python bindings.")
    return None

def safe_parse_config(value):
    if not isinstance(value, str) or not value.strip():
        return {}

    try:
        # 1. Strip the outer CSV-wrapping double quotes if they exist
        # e.g., "{'a':1}" -> {'a':1}
        clean_value = value.strip().strip('"')

        # 2. Use ast.literal_eval to convert the string to a Python dict.
        # This handles single quotes perfectly: {'guid': '...'}
        data_dict = ast.literal_eval(clean_value)
        return data_dict
    except (ValueError, SyntaxError):
        # 3. Fallback: if it's already strict JSON
        try:
            return json.loads(value.replace("'", '"'))
        except Exception as e:
            logger.exception(e)
            return {}

def is_valid_timezone(tz_str):
    try:
        ZoneInfo(tz_str)
        return True
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False

def get_tz_diff_seconds(tz_sim:str, tz_data:str, ref_time: datetime):

    assert is_valid_timezone(tz_sim) and is_valid_timezone(tz_data), 'Timezone string must have valid format!'

    # Use the ctime as a specific reference moment
    ref_time = ref_time.replace(tzinfo=ZoneInfo('UTC'))

    offset_sim = ref_time.astimezone(ZoneInfo(tz_sim)).utcoffset()
    offset_data = ref_time.astimezone(ZoneInfo(tz_data)).utcoffset()

    # returns a timedelta by reverse subtraction
    diff = offset_sim - offset_data
    return diff.total_seconds()


def time_string_validator(time_string: str = None, time_format: str = None) -> bool:
    """
    This method helps to validate the time string format when handling data interface.
    
    Parameters
    ----------
    time_string: the actual time string
    time_format: desired text string format

    Returns
    -------

    """

    try:
        time.strptime(time_string, time_format)
        return True
    except ValueError:
        return False


def time_utc_str_to_unix(time_utc_str:str, time_str_format:str|None=None) -> float:
    """
    Convert a UTC timestamp string into a UNIX float time value.
    ----------
    
    Parameters
    ----------
    time_utc_str: UTC time of string format
    time_str_format: time string format for decoding, e.g. '%Y-%m-%d %H:%M:%S'

    Returns
    -------
    time_unix: the desired float value representing UNIX time
    """

    if not time_str_format:
        time_unix = time_parser.parse(time_utc_str).timestamp()
    else:
        time_dt = datetime.strptime(time_utc_str, time_str_format)
        time_unix = time.mktime(time_dt.timetuple())

    return time_unix


def time_unix_to_unit64(unix_time: float = None,
                        local_timezone: str = 'Europe/Berlin') -> int:
    """
    Get current time and convert to uint64_t for libiec61850 applications. 
    If 
    
    Parameters
    ----------
    unix_time: float value for UNIX time
    local_timezone: standard local local_tz string. If local_tz is None, the unix time will be considered UTC time.

    Returns
    -------
    ctime_uint64: an integer value representing the current time, with precision of ms. (This is required by the 
    application of libiec61850, as regulated in the IEC 61850 standard).
    """

    if local_timezone in ('UTC', None):
        tz = pytz.timezone('UTC')
    else:
        # 1. Normalize timezone object (handle string or None)
        tz = pytz.timezone(local_timezone) if isinstance(local_timezone, str) else local_timezone

    # 2. Get target datetime object in target timezone
    if unix_time is None:
        ctime = datetime.now(tz)
    else:
        ctime = datetime.fromtimestamp(unix_time, tz)

    # 3. Calculate target Unix epoch timestamp directly (No manual math needed)
    # .timestamp() automatically handles tz-aware objects seamlessly
    return int(ctime.timestamp() * 1000)



def time_unix_to_str(time_unix: float = None,
                     time_str_format: str ='%Y-%m-%d %H:%M:%S') -> str:
    """
    Takes datetime object and return the time stamp as a String.
    ----------

    Parameters
    ----------
    time_unix: float value of the UNIX time
    time_str_format: desired time string format

    Returns
    -------
    time_str: time string in the desired format
    """

    time_str = datetime.strftime(datetime.fromtimestamp(round(int(time_unix) / 10) * 10), time_str_format)
    return time_str

def convert_time_str_format(time_str: str = None,
                            to_str_format: str = '%Y-%m-%dT%H:%M:%SZ') -> str:
    """
    Convert the time String into desired string format.
    One must also specify the from_str_format and to_str_format to make it work.
    ----------

    Parameters
    ----------
    time_str: time string to be converted
    to_str_format: target string format

    Returns
    -------
    time_str_new: converted time string according to the target string format
    """

    time_unix = time_parser.parse(time_str).timestamp()
    time_str_new = time_unix_to_str(time_unix, to_str_format)
    return time_str_new


def get_time_str_by_diff(time_str: str = None,
                         time_str_format: str = '%Y-%m-%d %H:%M:%S',
                         time_diff: int = -300) -> str:
    """
    Input a time String and the string format, define a time difference, then get a new TimeStr by adding the
    time_diff and return that new time string.
    TODO: move to TimeManager??
    ----------

    Parameters
    ----------
    time_str
    time_str_format
    time_diff

    Returns
    -------
    time_str_new: new time string in the same string format after adding the time diff
    """

    if not time_str_format:
        time_unix = time_parser.parse(time_str).timestamp()
        time_str_format = '%Y-%m-%d %H:%M:%S'
    else:
        time_unix = time_utc_str_to_unix(time_str, time_str_format)
    time_str_new = time_unix_to_str(time_unix + time_diff, time_str_format)

    return time_str_new


def is_valid_guid(val:str) -> bool:
    """
    Check if the guid is valid.
    ----------

    Parameters
    ----------
    val: a string value that is supposed to encode a guid, capital or lower case doesn't matter

    Returns
    -------
    a boolean value
    """

    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


def is_valid_number(val: object) -> bool:
    """
    Check if a variable is number
    ----------

    Parameters
    ----------
    val: a variable of any type

    Returns
    -------
    boolean value indicating whether the input variable is a numeric type excluding nan type
    """

    is_number = isinstance(val, numbers.Number)

    if is_number and np.isnan(val):
        is_number = False

    return is_number


def round_up_val(val: any, digit: int = 6) -> any:
    """
    Round up a numeric value up to the desired decimal digits, or return the original value if it can not be rounded.

    Parameters
    ----------
    val: value to be rounded up
    digit: number of decimal digits

    Returns
    -------
    bool, val_new: bool indicator and the new (or the original if failed) value
    """


    try:
        if not is_valid_number(val):
            logger.warning(f'Value of the type {type(val)} can not be rounded up to the {digit}-th decimal')
            return np.nan
        else:
            return round(val, digit)
    except Exception as exc:
        logger.exception(exc)
        return np.nan


def vprint(msg: str, msg_level: int = 1, print_level: int = 1):
    """
    Verbose print for small test scripts where logger is not required.
    ----------

    Parameters
    ----------
    msg: msg string
    print_level: minimal msg level for print
    msg_level: user-defined msg_level (e.g. 0 - debug (verbose), 1 - info, 2 - warning, 3 - critical)
    """

    if msg_level >= print_level:
        print(msg)


class ColorLogFormatter(logging.Formatter):
    """
    Inspired by the answer of Sergey Pleshakov in:
    https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
    """

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = '(%(thread)d-%(threadName)-9s) - %(levelname)s - %(name)s - %(message)s'

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def rotating_logger(name_logger: str = 'unknown_logger',
                    name_logfile: str = None,
                    log_queue: queue.Queue = None,
                    MAX_BYTES: int = 300 * 1000 * 1000,
                    BACKUP_COUNT: int = 10) -> Logger:
    """
    A logger function that can be repeatedly used, it creates a rotating log for a specific process.
    Each logger writes in up to BACKUP_COUNT log files, each rotation log file has MAX_BYTES. For now, these parameters
    are set static.

    NOTE: DEBUG logging level may cause log overflow (e.g. the Rx:timeout debug log from influxdb), level it down to INFO.

    To call the loggers in all sub-modules, we can:
        - either use for each sub-module a specific logger by creating a new instance: logger = rotating_logger(__name__)
        - or have one centralised parent logger and use logger = logging.getLogger(__name__) to inherit from it.

    Currently we use the first one.
    ----------

    Parameters
    ----------
    name_logger: name of the logger
    name_logfile: name of the output .log file
    log_queue: log queue for multiprocessing
    MAX_BYTES: maximal bytes for local log archive
    BACKUP_COUNT: number of log archives with a total size up to MAX_BYTES

    Returns
    -------
    logger: the logging handler of type Logger

    """

    # create a rotating handler
    if not name_logfile:
        name_logfile = name_logger
    log_file_path = f'./logs/{name_logfile}.log'

    # logging.basicConfig(stream=sys.stdout, filemode='a')
    logging.disable(logging.DEBUG)

    logger = logging.getLogger(name_logger)
    logger.setLevel(logging.DEBUG)

    if not hasattr(logger, "logged_errors"):
        logger.logged_errors = set()

        def log_new_error(self, err, msg: str | None = None):
            key = (type(err), str(err))
            if key not in logger.logged_errors:
                logger.logged_errors.add(key)
                logger.exception(err)
                if msg is not None:
                    logger.exception(msg)

        logger.log_new_error = types.MethodType(log_new_error, logger)

    fh = RotatingFileHandler(log_file_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(process)d - (%(thread)d-%(threadName)-9s) - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)

    if log_queue is not None:
        # Main app logger writes non-blockingly to queue
        queue_handler = QueueHandler(log_queue)
        logger.addHandler(queue_handler)
        # Background thread handles slow disk/file writes
        listener = QueueListener(log_queue, fh)
        listener.start()
        return logger
    else:
        # if not using queue, just add fileHandler and streamHanlder to the logger
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        formatter = ColorLogFormatter()
        sh.setFormatter(formatter)

        # if multiple handlers should be merged into one logger, the next two rows need to be removed.
        # if logger.hasHandlers:
        #     logger.handlers.clear()
        logger.addHandler(fh)
        logger.addHandler(sh)

        return logger
