"""
Main program of the virtual IED for real-time simulation or emulation.
"""


import importlib.util
from settings import config, helper
import queue

helper.set_env_libiec61850()
lib_name = 'pylibiec61850'
if_exist = importlib.util.find_spec(lib_name)
assert if_exist, """The local module pyiec61850der is not configured properly!! \n
    A essential lib pylibiec61850 can not be found in current working dir!! \n
    Please check the structure of the working directory!! \n """

# instantiate the CLS worker
from simulation.virtual_ied import run_virtual_ied

# PATH_CONFIG = './tester/func_tests/config_tester.yaml'
PATH_CONFIG = './settings/config.yaml'

ied_manager = run_virtual_ied(path_config=PATH_CONFIG)

from settings.helper import rotating_logger

name_logger = 'main_logger'
name_logfile = 'main_logger'
log_queue = queue.Queue(-1)
# logger = rotating_logger(name_logger, name_logfile)
logger = rotating_logger(name_logger, name_logfile, log_queue)

