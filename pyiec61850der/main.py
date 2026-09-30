"""
Main program of the virtual IED for real-time simulation or emulation.
"""


import importlib.util
from settings import config, helper
import queue
import logging

helper.set_env_libiec61850()
lib_name = 'pylibiec61850' # Use this lib name for libIEC61850 >= 1.6.0
# lib_name = 'iec61850'  # Use this lib name for libIEC61850 <= 1.5.1
if_exist = importlib.util.find_spec(lib_name)
assert if_exist, """The local module pyiec61850der is not configured properly!! \n
    A essential lib pylibiec61850 can not be found in current working dir!! \n
    Please check the structure of the working directory!! \n """

from settings.helper import rotating_logger

# NOTE: the name main_logger is shared by all sub-modules
name_logger = 'main_logger'
name_logfile = 'main_logger'
log_queue = queue.Queue(-1)
# logger = rotating_logger(name_logger, name_logfile)
logger = rotating_logger(name_logger, name_logfile, log_queue, LOG_LEVEL_FH=logging.INFO, LOG_LEVEL_SH=logging.INFO)

# instantiate the CLS worker
from simulation.virtual_ied import run_virtual_ied
# PATH_CONFIG = './tester/func_tests/config_tester.yaml'
PATH_CONFIG = './settings/config.yaml'

ied_manager = run_virtual_ied(path_config=PATH_CONFIG)



