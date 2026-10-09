# -*- coding: utf-8 -*-
"""
Core functions for the data operations in terms of a real-time IEC 61850 MMS interface.


Quality flags in libIEC61850:
    #define QUALITY_DETAIL_BAD_REFERENCE   16
    #define QUALITY_DETAIL_FAILURE   64
    #define QUALITY_DETAIL_INACCURATE   512
    #define QUALITY_DETAIL_INCONSISTENT   256
    #define QUALITY_DETAIL_OLD_DATA   128
    #define QUALITY_DETAIL_OSCILLATORY   32
    #define QUALITY_DETAIL_OUT_OF_RANGE   8
    #define QUALITY_DETAIL_OVERFLOW   4
    #define QUALITY_OPERATOR_BLOCKED   4096
    #define QUALITY_SOURCE_SUBSTITUTED   1024
    #define QUALITY_TEST   2048
    #define QUALITY_VALIDITY_GOOD   0
    #define QUALITY_VALIDITY_INVALID   2
    #define QUALITY_VALIDITY_QUESTIONABLE   3
    #define QUALITY_VALIDITY_RESERVED   1

TODO: add more data type handlers, e.g. a string handler
"""


import datetime
# standard python modules
import os
import time
import numpy as np
import pandas as pd

# import threading

# local libs
import settings.helper as helper
import interface.sunspec as sunspec
from settings.helper import rotating_logger
from settings.config import IedConfig
from communication.pyiec61850_server import IedServer, IEC61850ServerMMS
from interface.data_buffer import DataBuffer
import logging

iec61850 = helper.import_libiec61850()
logger = logging.getLogger(f"main_logger.{__name__}")

# type hints
from typing import Optional, Type, TypedDict
FloatTypes = helper.StdDataType.FloatTypes
IntTypes = helper.StdDataType.IntTypes
BoolTypes = helper.StdDataType.BoolTypes

# Comprehensive C-SWIG IEC61850 function dispatch mapping: (update_fn, get_fn)
# This is only a subset of all possible IEC 61850 data types

def _coerce_external_value(data_buffer: DataBuffer, addr: str) -> None:
    """Enhanced CDC-aware type coercion for IEC 61850 attributes."""
    val = data_buffer.value_external
    cdc = data_buffer.iec61850_do.cdc.upper() if data_buffer.iec61850_do.cdc else ""
    cdc_prefix = cdc[0] if cdc else ""

    # 1. Address-suffix specific parsing
    if addr.endswith(".f"):
        data_buffer.value_external = float(val)
        return
    elif addr.endswith(".i"):
        data_buffer.value_external = int(val)
        return
    elif addr.endswith(".b") or addr.endswith(".stVal") and cdc in ("SPS", "SPC"):
        if isinstance(val, str):
            data_buffer.value_external = val.strip().lower() in ("true", "1")
        else:
            data_buffer.value_external = bool(val)
        return

    # 2. CDC-Group specific parsing
    # Status / Enumerated / Controllable Integer Classes
    if cdc in ("INS", "INC", "ENS", "ENC", "DPS", "DPC") or cdc_prefix in ("E", "I"):
        data_buffer.value_external = int(val)

    # Boolean / Binary Classes (Single Point Status / Command)
    elif cdc in ("SPS", "SPC") or cdc_prefix in ("B", "S"):
        if isinstance(val, str):
            data_buffer.value_external = val.strip().lower() in ("true", "1")
        else:
            data_buffer.value_external = bool(val)

    # Description & Nameplate String Classes (DPL, LPL, CSD)
    elif cdc in ("DPL", "LPL", "CSD", "VSG") or cdc_prefix == "D":
        data_buffer.value_external = str(val)

    # Measurand / Analog Settings (MV, SAV, ASG)
    elif cdc in ("MV", "SAV", "ASG", "CMV") or cdc_prefix == "M":
        if helper.is_valid_number(val):
            data_buffer.value_external = float(val)

    # Generic string-based fallback checks
    elif isinstance(val, str):
        val_lower = val.strip().lower()
        if val_lower in ("true", "false"):
            data_buffer.value_external = (val_lower == "true")


def update_da_worker(ied_server: IEC61850ServerMMS,
                     ied_server_swig_obj: Type["SwigPyObject"],
                     data_buffer: DataBuffer,
                     server_time_mode: str = "absolute",
                     verbose: bool = False):

    """Updates IEC 61850 MMS Data Attributes across all CDC categories."""
    ref_map = data_buffer.iec61850_do.obj_ref_map
    da_obj = ref_map.get("monitor_da")

    if da_obj is None:
        if verbose:
            logger.info(f"Python reference unavailable for DA {data_buffer.id}, skipping.")
        return

    if data_buffer.value_external is None:
        if verbose:
            logger.info(f"No external value available for DA {data_buffer.id}, skipping.")
        return

    addr = ref_map.get("monitor_da_mms_addr", "")
    tstmp_obj = ref_map.get("monitor_da_t")
    quality_obj = ref_map.get("monitor_da_q")
    q_flag = data_buffer.value_quality

    # 1. CDC & Address Aware Coercion
    _coerce_external_value(data_buffer, addr)
    val = data_buffer.value_external

    val, target_key = data_buffer.examine_iec61850_data_by_type(val)

    # 3. Apply MMS SWIG update
    da_attr = iec61850.toDataAttribute(da_obj)

    if target_key in data_buffer.MMS_TYPE_DISPATCH:
        update_fn, get_fn = data_buffer.MMS_TYPE_DISPATCH[target_key]
        update_fn(ied_server_swig_obj, da_attr, val)
        data_buffer.value_iec61850 = get_fn(ied_server_swig_obj, da_attr)
    else:
        q_flag = iec61850.QUALITY_VALIDITY_QUESTIONABLE
        if verbose:
            logger.info(
                f"Unsupported CDC type {type(val).__name__} for DA {data_buffer.id}, set to QUESTIONABLE."
            )

    # 4. Save record history
    data_buffer.update_records(data_buffer.create_single_record())

    # 5. Timestamp update
    if tstmp_obj is not None:
        tstmp_da = iec61850.toDataAttribute(tstmp_obj)
        if server_time_mode == "absolute":
            mms_timestamp = helper.time_unix_to_unit64()
        elif server_time_mode == "simulation":
            sim_time = ied_server.server_config.container.ctime_unix
            mms_timestamp = helper.time_unix_to_unit64(sim_time, "UTC")
        else:
            mms_timestamp = None

        if mms_timestamp is not None:
            iec61850.IedServer_updateUTCTimeAttributeValue(
                ied_server_swig_obj, tstmp_da, mms_timestamp
            )

    # 6. Quality Flag update
    if quality_obj is not None:
        iec61850.IedServer_updateQuality(
            ied_server_swig_obj, iec61850.toDataAttribute(quality_obj), q_flag
        )

def update_ied_attr(ied_server:IEC61850ServerMMS, verbose:bool=False):
    """
    This method can be used to update the values and timestamps in the demo IED Server.
    TODO: this method should be adapted to updateIedMX. Later the update method for the DA is given by the fc.
    """

    server_swig_obj = ied_server.ied_server.swig_obj
    server_time_mode = ied_server.server_config.container.time_mode

    logger.info('-------------------------------------------------------------------')

    if not ied_server or not getattr(ied_server, 'data_buffers', None):
        return

    first_buf = ied_server.data_buffers[0] if ied_server.data_buffers else None
    tm = getattr(first_buf, 'time_manager', None) if first_buf else None

    timestamp_str = tm.ctime_utc_str if tm else "N/A (TimeManager unattached)"
    logger.info(f'Update IED attributes for the timestamp {timestamp_str}')

    for data_buffer in ied_server.data_buffers.values():
        if data_buffer.is_monitor:
            update_da_worker(ied_server, server_swig_obj, data_buffer, server_time_mode, verbose)
        else:
            if verbose:
                logger.info(f'The monitoring is deactivated for DO {data_buffer.iec61850_do.id}, skip it.')

    logger.info('Update of data_buffer instances is completed.')
    logger.info('-------------------------------------------------------------------\n')

    return


def exec_control(ied_config: IedConfig, data_buffer:DataBuffer):
    """
    Perform a control action using the sunspec interface.
    FIXME: comparing old and new value actually does not really make much sense, the proper way would be implementing
    callback functions to catch the data variation.
    NOTE: some interface may require a rescan before reading the new value. Therefore, we use try except to catch the
     error occurred during the write action, no error returns isExecuted = True.
    """

    is_success = False

    if data_buffer.data_source in ('local', 'influxdb', 'random'):
        # nothing happens
        pass
    elif data_buffer.data_source in ('number', 'calculator', ):
        # no handling
        pass
    elif data_buffer.data_source == 'sunspec':
        is_success, err, committed_val = sunspec.exec_sunspec_control(ied_config.interface.active_sunspec_mappings,
                                                                  data_buffer, ied_config.interface.is_sunspec_force_enable)
        return is_success, err, committed_val

    else:
        logger.warning(f'Unknown data source {data_buffer.data_source}')

    return is_success, None, None



