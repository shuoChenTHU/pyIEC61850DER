# -*- coding: utf-8 -*-
"""
A test script for structured testing on the virtual IED main program.
"""

import importlib.util
from settings import config, helper
from multiprocessing import Process
import multiprocessing
import logging
import queue
from settings.helper import rotating_logger

helper.set_env_libiec61850()
if_exist = importlib.util.find_spec("pylibiec61850")
assert if_exist, """The local module pyiec61850der is not configured properly!! \n
    A essential lib pylibiec61850 can not be found in current working dir!! \n
    Please check the structure of the working directory!! \n """

name_logger = 'testLogger'
name_logfile = 'testLogger'
log_queue = queue.Queue(-1)
# logger = rotating_logger(name_logger, name_logfile)
logger = rotating_logger(name_logger, name_logfile, log_queue, LOG_LEVEL_FH=logging.INFO, LOG_LEVEL_SH=logging.DEBUG)

# instantiate the CLS worker
from simulation.virtual_ied import run_virtual_ied

PATH_CONFIG = './tester/func_tests/config_tester.yaml'

ied_manager = run_virtual_ied(path_config=PATH_CONFIG)




