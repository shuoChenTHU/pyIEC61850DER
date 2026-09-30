# -*- coding: utf-8 -*-
"""
Build the IEC 61850 data model inside the IEC 61850 MMS server.
"""

import xmltodict
import copy
from dataclasses import dataclass, field
from typing import Optional, Type, TypedDict, Any, TYPE_CHECKING

from settings.helper import rotating_logger, import_libiec61850
import logging

logger = logging.getLogger(f"main_logger.{__name__}")


@dataclass()
class DataModel(object):
    """
    An inner-class that contains several properties that are associated with the build process of the IEC 61850
    data model in the IED server.
    TODO: implement a method to backup the data model upon each modification

    The SCL contents and the server model in the SCL dict will be modified during the parsing processes,
    because some cdc types are not supported, these two dicts must be returned. Only these modified dictionary
    objects will be used to initialise the IED server, and thus must be consistent with the data model on the client
    side.

    Naming conventions for private attrs:
        - scl_model: the full dict contents in the SCL file
        - server_model: scl_model['SCL']['IED']['AccessPoint']['Server']
        - swig_obj: the SWIG object containing the IEC61850 data model structure
    """

    scl_model_orig: dict | None = None  # this is a place_holder for the data model dictionary
    server_model_orig: dict | None = None  # this is a place_holder for the IED Server dictionary, a sub dict of scl
    _scl_model: dict | None = None  # the SCL of the final Server must be returned as some cdc types are not supported
    _server_model: dict | None = None
    _swig_obj: Type["SwigPyObject"] | None = None
    ied_name: str = 'unknown'
    ln_templates: list = field(default_factory=list)
    da_templates: list = field(default_factory=list)
    do_templates: list = field(default_factory=list)
    enum_templates: list = field(default_factory=list)
    ln_templates_buffer: list = field(default_factory=list)

    archives: list = field(default_factory=list)  # this is a list to store all historical data models
    version: str = '1.0'

    @property
    def swig_obj(self) -> Type["SwigPyObject"]:
        """The getter: returns the internal data model."""
        return self._swig_obj

    @swig_obj.setter
    def swig_obj(self, value: Type["SwigPyObject"]):
        """The setter: allows replacing the entire model with validation."""
        # FIXME: big issue with type hint for swig objects, need to bypass parametric generics Type["SwigPyObject"]
        # if not isinstance(value, Type["SwigPyObject"]):
        #     raise TypeError("data_model must be a dictionary.")
        self._swig_obj = value

    @property
    def scl_model(self) -> dict:
        """The getter: returns the internal data model."""
        return self._scl_model

    @scl_model.setter
    def scl_model(self, value: dict):
        if not isinstance(value, dict):
            raise TypeError("scl_model must be a dictionary.")
        self._scl_model = value

    @property
    def server_model(self) -> dict:
        """The getter: returns the internal data model."""
        return self._server_model

    @server_model.setter
    def server_model(self, value: dict):
        if not isinstance(value, dict):
            raise TypeError("server_model must be a dictionary.")
        self._server_model = value

    def parse_scl_data_model(self, file_path) -> bool:
        """ This method will read the SCL file, parse the data model topology contained in it. The dictionary
        has a quite clear structure, hence it is not necessary to implement a high-level parsing logic,
        just return the dictionary object and the rest of the server builder should be able to extract what they need.
        """

        try:
            scl_contents = read_scl_data_model(file_path)
            self.scl_model_orig = scl_contents
            self.ied_name = scl_contents['SCL']['IED']['@name']
            self.server_model_orig = scl_contents['SCL']['IED']['AccessPoint']['Server']

            self.ln_templates = scl_contents['SCL']['DataTypeTemplates']['LNodeType']
            self.da_templates = scl_contents['SCL']['DataTypeTemplates']['DAType']
            self.do_templates = scl_contents['SCL']['DataTypeTemplates']['DOType']
            self.enum_templates = scl_contents['SCL']['DataTypeTemplates']['EnumType']

            # copy dictionaries of the SCL for modification
            # Note that the list of LN dict will also be updated as some DO with unsupported cdc will be dumped
            self.scl_model = copy.deepcopy(scl_contents)
            self.server_model = copy.deepcopy(self.server_model_orig)
            self.ln_templates_buffer = copy.deepcopy(self.ln_templates)

            return True

        except Exception as e:
            logger.error(e)
            return False

def read_scl_data_model(file_path:str, encoding='utf-8') -> dict:
    with open(file_path, "r", encoding=encoding) as fd:
        # TODO: add an exception catcher to handle parsing failure
        # parse data model structure
        scl_contents: dict = xmltodict.parse(fd.read())

    return scl_contents