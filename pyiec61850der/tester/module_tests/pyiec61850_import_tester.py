# # -*- coding: utf-8 -*-
"""

This testing script can be used in the docker container to locate module import errors.

@author: chen
"""

from settings import helper
iec61850 = helper.import_libiec61850()