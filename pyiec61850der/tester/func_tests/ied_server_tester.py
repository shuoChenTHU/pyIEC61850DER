# -*- coding: utf-8 -*-
"""
A test script for structured testing on the IED server side

"""

import importlib.util
from settings import config, helper
from multiprocessing import Process
import multiprocessing
import logging

helper.set_env_libiec61850()
if_exist = importlib.util.find_spec("pylibiec61850")
assert if_exist, """The local module pyiec61850der is not configured properly!! \n
    A essential lib pylibiec61850 can not be found in current working dir!! \n
    Please check the structure of the working directory!! \n """

# instantiate the CLS worker
from simulation.virtual_ied import run_virtual_ied

PATH_CONFIG = './tester/func_tests/config_tester.yaml'

ied_manager = run_virtual_ied(path_config=PATH_CONFIG)


from settings.helper import rotating_logger

nameLogger = 'testLogger'
nameLogfile = 'testLogger'
logger = rotating_logger(nameLogger, nameLogfile)


