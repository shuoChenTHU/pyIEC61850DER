# -*- coding: utf-8 -*-
"""
Initialise data buffer instances with dummy data for test purpose.

"""


import pandas as pd
import random
from settings import helper

from settings.helper import rotating_logger

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
    return val



"""
=======================================================================
=================   End Essential routine functions =================
=======================================================================
"""
