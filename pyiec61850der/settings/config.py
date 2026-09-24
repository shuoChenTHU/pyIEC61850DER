# -*- coding: utf-8 -*-
"""
Definition of the class IedConfig and core functions for config file I/O
"""

import json
from datetime import datetime, timedelta, timezone
import time
import pytz
import os
import yaml
import pandas as pd
import threading

# import copy
# import logging
# from datetime import datetime, timedelta, timezone
# import calendar
# import sys
# from typing import Type
# from pandas import DataFrame

import settings.helper as helper
from settings.helper import rotating_logger

logger = rotating_logger(__name__)


class IedConfig(object):
    """
    NOTE: The parameters in the IedConfig class will be used in many other functions/methods
    of pyiec61850DER, which is quite a bad idea. Well for now we have to more or less live with it.
    
    The point here is: try to avoid changing existing settings attributes, as you have no idea in
    which part of other scripts that particular attribute will be called.
    
    Most of the config parameters have a default value when initializing an instance, this makes sure
    even if you don't proceed further with parametrisation, the virtual CLS can still use some dummy info
    to start the service.
    
    Update of the configuration can be done using the function update_config(). It is recommended to
    update the configuration using the YAML config file, because the IEC 61850 data 
    model generator also relies on this YAML configuration when adjusting the data model topology.

    TODO: move all methods to a new class IedManager

    FIXME: here we have some legacy issue due to the outdated implementation of the configuration. Attrs of this
     class should only be used to READ, UPDATE and STORE the configuration, for other purpose the config parameters
     must be passed to other classes (e.g. TimeManager, IedManager, etc.).

    TODO: after a new implementation concept for the configurator is defined, review all config parameters incl.
     their usage in the runtime services, pass value accordingly to other classes and remove duplicated value.
    
    """

    def __init__(self):
        """
        initialise config class templates.
        TODO: there are still some old configurations in this class, check and remove them later.
        """

        self.der = DER()
        self.container = Container()
        self.ied = IED()
        self.pv = PV()
        self.load = LOAD()
        self.sto = STO()
        self.pcc = PCC()
        self.interface = Interface()
        self.influxdb = None  # only a placeholder, will later be assigned by ied_manager.influxdb

    def update_dict_attr(self, attr_key: str, attr_obj: dict, is_add_new_attr:bool=True):
        parent_obj = getattr(self, attr_key, None)
        if parent_obj:
            self.update_attr_in_dict(parent_obj, attr_obj, is_add_new_attr)

    def update_config(self, path_config: str, is_add_new_attr: bool = True) -> bool:

        """
        This function has the job to load a config file and update the attributes
        in the config instance (the second argument), accordingly.

        For a better readability, this global configuration file has now YAML format
        instead of JSON. It facilitates the harmonisation with container applications.

        NOTE: the first argument can be the attribute ied_config of a running IED service, in this case no explict
            return is required. But this kind of usage can be dangerous.

        Parameters
        ----------
        ied_config: object of the IED configuration (initialised as a pseudo object)
        path_config: file path of the user defined config (the YAML file in the current implementation)
        is_add_new_attr: whether unknown (new) parameters in the config file should be added as new attributes

        Returns
        -------
        the updated IED config object ied_config
        """

        logger.info('=================   Begin load local config   =================')
        is_config_updated: bool = True
        if not path_config:
            path_config = self.interface.path_config_yaml

        [config_local, is_yaml_read] = get_dict_from_yaml(path_config)
        if not is_yaml_read:
            is_config_updated = False
        else:
            self.interface.config_yaml = config_local

            for key in ['PV', 'LOAD', 'STO']:
                list_update: list = [item for item in config_local if key in item]  # e.g. 'PV' in 'PV1'
                if len(list_update) > 0:
                    for item in list_update:
                        setattr(self, item.lower(), getattr(self, key.lower()))
                    delattr(self, key.lower())

            for kind in list(config_local.keys()):
                config_class: str = kind.lower()  # all other classes use lower case name
                obj_config = getattr(self, config_class, None)
                if obj_config:
                    self.update_attr_in_dict(obj_config, config_local[kind], is_add_new_attr)

            self.update_der_dicts()

        logger.info('=================   End load local config   =================\n')
        return is_config_updated

    def update_der_dicts(self):
        """
        Update the DER list in config object.

        Calling this function helps to reproduce attributes of DER classes, such as PV, STO and LOAD, based on the
        configuration stored in the user-defined YAML file. In particular, when multiple DER are in presence and with
        different configurations.
        ----------

        Parameters
        ----------
        ied_config: object of the IED configuration (might haven been overwritten by the YAML file)
        """

        # if ied_config.interface.config_yaml is None:
        #     logger.warning('YAML config file is empty, can not proceed, no change in the IED topology will be made.')
        # elif type(ied_config.interface.config_yaml) is not dict:
        #     logger.warning('YAML config has unknown type, can not proceed, no change in the IED topology will be made.')
        # else:
        for key in ['PV', 'LOAD', 'STO']:
            items = [item for item in self.interface.config_yaml if key in item]
            if len(items) > 0:
                self.der.der_dicts[key] = items
            else:
                self.der.der_dicts[key] = []

    @staticmethod
    def update_attr_in_dict(old_dict: dict, new_info_dict: dict, is_add_new_attr: bool) -> dict:
        """
        A supporting function for updating items of an existing dictionary by reading the same key from another dictionary.
        The function direct operates on the old_dict without creating a copy.

        NOTE: if the arg old_dict is a mutable attributes under a class instance, the returned object need not be assigned.
        ----------

        Parameters
        ----------
        old_dict: the original dict
        new_info_dict: the dict with updated information
        is_add_new_attr: whether unknown (new) parameters in the config file should be added as new attributes

        Returns
        -------
        old_dict: the updated dict
        """

        for key, value in new_info_dict.items():
            if key not in dir(old_dict):
                if is_add_new_attr:
                    setattr(old_dict, key, value)
                    logger.info(f'Unknown parameter {key} has been added to  config instance')
                else:
                    logger.warning(f'Unknown parameter {key} detected, skip it')
            else:
                if value in (None, ''):
                    logger.warning(f'Possibly invalid value of parameter {key} detected, please check this parameter')
                else:
                    setattr(old_dict, key, value)
        return old_dict



class DER:
    n_pv: int = 1
    n_load: int = 1
    n_storage: int = 1
    der_dicts: dict = {'PV': ['PV'],
                       'LOAD': ['LOAD'],
                       'STO': ['STO'],
                       }

class IED:
    """
    Dummy settings of the virtual vIED device.
    Entries will be overwritten if a local config yaml file is available.
    TODO: quite many time related attributes are duplicated with Time Synchroniser, consider merge them
    TODO: rename the class to vIED later
    """

    # server settings and stats
    tcp_port: int = 61850  # this should always be 61850, do not overwrite it with the config file!!
    host_name: str = "127.0.0.1"

    # IED setting
    name_ied: str = "demoVirtualCLS"
    ied_guid: str = ''
    t_interval_data_update: int = 60  # data update t_interval_data_update in [seconds]
    N_CTRL_WD_CYCLES: int = 10
    t_monitor_reserve: float = 0.5
    t_interval_archive: int = 900
    t_interval_data_upload: int = 3600

class Container:
    """
    TODO: add more details in docstring

    This class is essential, it is the interface between runtime_manager and databuffers. In particular,
    its instances share the same time related attr as the attr ied_manger.time_manager

    FIXME: quite many time related attributes are legacy from the prototype, they are redundant to attrs of the
    class TimeManager. Must unify the usage of these attrs and remove redundancy.
    """

    # container setting
    container_guid: str | None = None
    service_name: str | None = None
    container_name: str | None = None
    network: str | None = None

    port: int = 61850

    # time settings
    time_start_trigger: str | None = None  # a string of the format YYYY-MM-DD hh:mm:ss
    timezone: str = 'Europe/Berlin'
    time_mode: str = 'simulation'  # simulation or absolute
    time_start_str: str = '2016-07-01 12:00:00'
    time_end_str: str = '2016-07-31 23:59:59'
    time_start_unix: float = 0.0
    time_end_unix: float = 0.0
    time_accelerator_factor: float = 1.0

    # NOTE: all time attr must refer to attrs of ied_manager.time_manager with the same name
    ctime: datetime | None = None
    ctime_utc: datetime | None = None
    ctime_unix: float | None = None
    ctime_local_str: str | None = None
    ctime_utc_str: str | None = None
    ctime_bundle: tuple[float, str, str, datetime, datetime] | None = None

    # global counter
    # global_counter = 0


class PV:
    #data_source = 'local'
    #ratedPower = 100
    #unit_factor = 1
    #scaling_factor = 1
    ip: str = '192.168.1.1'
    slave_id: int = 1
    tcp_port: int = 502

class PCC:
    place_holder = None

class STO:
    place_holder = None

class LOAD:
    place_holder = None

class Interface:
    """
    The default parameters will be overwritten by the config.yaml as long as it exists.
    """
    # dictionary and pandas DataFrame objects
    df_lookup: pd.DataFrame = None  # initialisation will be performed by interface.sunspec
    df_sunspec_mapping: pd.DataFrame = None  # initialisation will be performed by communication._swig_obj
    # TODO: currently only one sunspec device is active, it's okay to use list, convert it to dict later
    active_sunspec_mappings: list = []  # store sunspec mapping dataframes in runtime, can handle multi devices
    config_yaml: dict = None  # initialisation will be performed by settings.config.update_config()

    # paths relevant for file i/o and communication interfaces
    path_config_yaml: str = './settings/config.yaml'
    path_data_model_config: str = './model/config_IEC61850_model.xlsx'
    path_lookup: str = './settings/IEC61850_DA_lookup_demoIED.csv'
    path_sunspec_mapping: str = './interface/interface_SunSpec.xlsx'
    path_sunspec_mapping_export: str = './interface/interface_SunSpec_export.xlsx'
    path_scl: str = None
    is_keep_none: bool = True
    read_lookup_columns: list = ['index', 'data_source', 'fieldbus_conn_config', 'guid', 'is_monitor', 'is_control']
    is_force_overwrite: bool = False
    is_sunspec_force_enable: bool = False

def get_dict_from_yaml(path_file: str) -> tuple[dict, bool]:
    """
    Read the contents of a YAML file and return the contents as a dictionary.

    Parameters
    ----------
    path_file: path of the YAML file

    Returns
    -------
    file_contents: dict containing the file contents

    """

    file_contents: dict = dict()
    is_yaml_read: bool = True
    with open(path_file, "r") as stream:
        try:
            file_contents: dict = yaml.safe_load(stream)

            if file_contents is None:
                logger.warning('YAML config file is empty, can not proceed, no change in the DER config will be made.')
            elif type(file_contents) is not dict:
                logger.warning(
                    'YAML config has unknown type, can not proceed, no change in the DER config will be made.')
        except yaml.YAMLError as errorCode:
            logger.exception(f'The config YAML can not be loaded, error code: {errorCode}')
            logger.warning(f'The program will proceed using default configuration, which would cause errors!!!')
            is_yaml_read = False

    return file_contents, is_yaml_read


def read_secret(ied_config: IedConfig,
                filename: str,
                is_add_new_attr: bool = True) -> bool:

    """
    Load user credentials that are stored in secret files, mostly relevant for activating data interfaces. This function
    uses the same logic as the function update_config(), for security reasons we should not consolidate them.

    All secret files should be placed in the sub-folder ./secret, the filename must include it extensions, for example
    a JSON file. For demonstration, a secret template for the influxdb data interface is available.
    ----------

    Parameters
    ----------
    ied_config:  object of the IED configuration (might haven been overwritten by the YAML file)
    filename: name of the secret file
    is_add_new_attr: whether unknown (new) parameters in the secret file should be added as new attributes

    Returns
    -------
    is_secret_read: bool indicator to tell whether the secret_json have been successfully read

    """

    is_secret_read: bool = True
    config_class: str = filename.split('.')[0]

    if filename not in os.listdir('./secret'):
        logger.error(f'Secret file {filename} not found, please check it and restart the program.')
        is_secret_read = False
    elif config_class not in dir(ied_config):
        logger.error(
            f'The secret file has unknown config class {config_class}, please check it and restart the program.')
        is_secret_read = False
    else:
        with open(f'./secret/{filename}', 'r', encoding='utf-8') as f:
            secret_json = json.load(f)
        ied_config.update_dict_attr(config_class, secret_json, is_add_new_attr)

    return is_secret_read








