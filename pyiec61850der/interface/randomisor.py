# -*- coding: utf-8 -*-
"""
Initialise data buffer instances with random data for test purpose.

"""

import pandas as pd
import random
from settings import helper

from settings.helper import rotating_logger
from typing import Union, get_args
import logging
logger = logging.getLogger(f"main_logger.{__name__}")

FloatTypes = helper.StdDataType.FloatTypes
IntTypes = helper.StdDataType.IntTypes
BoolTypes = helper.StdDataType.BoolTypes


"""
=======================================================================
=================   Begin Essential routine functions =================
=======================================================================
"""


def get_cvalue(val: FloatTypes | IntTypes | BoolTypes | None) -> FloatTypes | IntTypes | BoolTypes:
    if val is not None:
        if type(val) not in get_args(BoolTypes):
            val += random.randint(-1000, 1000) / 10000
    return val


"""
=======================================================================
=================   End Essential routine functions =================
=======================================================================
"""
