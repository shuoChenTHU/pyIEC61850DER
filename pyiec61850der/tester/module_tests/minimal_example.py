"""
A minimal example of the IEC 61850 server for test purpose.

This script can be used to test whether the libiec61850 module can be imported properly, and whether a minimal demo
server using a simple model can be started and accessed by the client.
"""

import importlib.util
from settings import config, helper
# from multiprocessing import Process
# import multiprocessing
# import logging
import time

helper.set_env_libiec61850()
if_exist = importlib.util.find_spec("pylibiec61850")
assert if_exist, """The local module pyiec61850der is not configured properly!! \n
    A essential lib pylibiec61850 can not be found in current working dir!! \n
    Please check the structure of the working directory!! \n """

iec61850 = helper.import_libiec61850()
model = iec61850.IedModel_create("simple")

ied_server = iec61850.IedServer_create(model)

while True:
    iec61850.IedServer_start(ied_server, 61850)
    # input("Server running, press Enter to stop")


