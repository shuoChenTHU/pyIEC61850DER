# -*- coding: utf-8 -*-
"""
Definition of the IEC61850DA class for the IEC 61850 MMS DA objects.

"""

from dataclasses import dataclass

from settings.helper import KwargsHandler
from settings.helper import rotating_logger
logger = rotating_logger(__name__)

@dataclass()
class IEC61850DA(KwargsHandler):
    """
    IEC 61850 relevant information.
    Similar to the class IEC61850DA, currently we only use this class to store some information.
    The processing logic in processing.routine will not access the IEC61850DA instances,
    but in the future, it could be necessary to go down to the DA level.

    TODO: implement more functions to better make use of the information contained in the DA
    """

    def __init__(self, **kwargs):
        self.level: str = 'DA'  # BDA/SDA, DA, DO, ...
        self.id: str | None  = None
        self.mms_addr: str | None  = None
        self.comm_addr: str | None  = None
        self.do_mms_addr: str | None  = None
        self.do_comm_addr: str | None  = None
        self.name: str | None  = None
        self.type: str | None  = None
        self.bType: str | None  = None
        self.fc: str | None  = None
        self.description = None  # currently not used
        self.ld_obj_ref: str | None  = None
        self.ln_obj_ref: str | None  = None
        self.do_obj_ref: str | None  = None
        self.da_obj_ref: str | None  = None
        self.guid: str | None = None
        self.apply_kwargs(True, **kwargs)

    def __str__(self):
        """
        Use the DA id to represent the DA object description.
        """
        return f'{self.id}'

    def __call__(self):
        """
        Use the DA id to represent the DA object when it is called.
        """
        return self.id
