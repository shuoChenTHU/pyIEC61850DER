# -*- coding: utf-8 -*-
"""
Core functions for the data operations in terms of a real-time IEC 61850 MMS interface.

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

iec61850 = helper.import_libiec61850()
logger = rotating_logger(__name__)

# type hints
from typing import Optional, Type, TypedDict
FloatTypes = helper.StdDataType.FloatTypes
IntTypes = helper.StdDataType.IntTypes
BoolTypes = helper.StdDataType.BoolTypes


def update_da_worker(ied_server: IEC61850ServerMMS, ied_server_swig_obj: Type["SwigPyObject"],
                     data_buffer:DataBuffer, server_time_mode:str= 'absolute', verbose:bool=False):
    # [idx, thisVal] = ied_server.get_external_value_by_idx(data_buffer.index)
    # address = ied_server.monitor_obj_addrs[idx]
    # refVal = ied_server.monitor_objs[idx]
    # refTstmp = ied_server.time_objs[idx]

    addr = data_buffer.iec61850_do.obj_ref_map['monitor_da_mms_addr']
    da_obj = data_buffer.iec61850_do.obj_ref_map['monitor_da']
    tstmp_obj = data_buffer.iec61850_do.obj_ref_map['monitor_da_t']
    quality_obj = data_buffer.iec61850_do.obj_ref_map['monitor_da_q']

    q_flag = iec61850.QUALITY_VALIDITY_GOOD
    if da_obj is not None:
        if data_buffer.value_external is not None:
            if helper.is_valid_number(data_buffer.value_external):
                # int, float or bool
                # first use the monitorDA MMS address to determine data type
                # if data type is undefined in the MMS address reference, then use the data type as provided by the data source

                if addr[-2:] == '.f' and type(data_buffer.value_external) not in (
                        np.float64, np.float32, np.floating, float):
                    # pay attention to numpy float64
                    data_buffer.value_external = float(data_buffer.value_external)
                    if verbose:
                        logger.info(
                            f'Data type conversion for DA {data_buffer.id}: type {type(data_buffer.value_external)} -> float.')
                elif addr[-2:] == '.i' and not isinstance(data_buffer.value_external, (
                        int, np.integer, np.int32, np.int64)):
                    # TODO: add logic to distiguish different int types like int32 and int64
                    data_buffer.value_external = int(data_buffer.value_external)
                elif data_buffer.iec61850_do.cdc[0] in ('E', 'I') and not isinstance(data_buffer.value_external, (
                        int, np.integer, np.int32, np.int64)):
                    # IXX -> int; EXX -> int (Enum literal)
                    data_buffer.value_external = int(data_buffer.value_external)
                elif data_buffer.iec61850_do.cdc[0] in ('B', 'S') and type(data_buffer.value_external) is not bool:
                    # BXX -> bool (binary), SXX -> bool (single point)
                    data_buffer.value_external = bool(data_buffer.value_external)
            else:
                data_buffer.value_external = str(data_buffer.value_external)
                if data_buffer.value_external in ('True', 'true'):
                    data_buffer.value_external = True
                elif data_buffer.value_external in ('False', 'false'):
                    data_buffer.value_external = False
                else:
                    # TODO: value_external is non-number (int, float or boolean) -> add a string handler
                    if verbose:
                        logger.info(f'Non-number data type of the DA {data_buffer.id}, skip it')
                    pass
        else:
            if verbose:
                logger.info(f'No value available for the DA {data_buffer.id}, skip it')
            pass

        if type(data_buffer.value_external) in (np.float64, np.float32, np.floating, float):
            iec61850.IedServer_updateFloatAttributeValue(ied_server_swig_obj, iec61850.toDataAttribute(da_obj),
                                                         data_buffer.value_external)
            data_buffer.value_iec61850 = iec61850.IedServer_getFloatAttributeValue(ied_server_swig_obj,
                                                                                   iec61850.toDataAttribute(
                                                                                     da_obj))
        elif type(data_buffer.value_external) in (int, np.integer, np.int32, np.int64):
            iec61850.IedServer_updateInt32AttributeValue(ied_server_swig_obj, iec61850.toDataAttribute(da_obj),
                                                         data_buffer.value_external)
            data_buffer.value_iec61850 = iec61850.IedServer_getInt32AttributeValue(ied_server_swig_obj,
                                                                                   iec61850.toDataAttribute(
                                                                                     da_obj))
        elif type(data_buffer.value_external) is bool:
            iec61850.IedServer_updateBooleanAttributeValue(ied_server_swig_obj, iec61850.toDataAttribute(da_obj),
                                                           data_buffer.value_external)
            data_buffer.value_iec61850 = iec61850.IedServer_getBooleanAttributeValue(ied_server_swig_obj,
                                                                                     iec61850.toDataAttribute(
                                                                                       da_obj))
        elif type(data_buffer.value_external) is str:
            iec61850.IedServer_updateVisibleStringAttributeValue(ied_server_swig_obj, iec61850.toDataAttribute(da_obj),
                                                                 data_buffer.value_external)
            data_buffer.value_iec61850 = iec61850.IedServer_getStringAttributeValue(ied_server_swig_obj,
                                                                                    iec61850.toDataAttribute(
                                                                                      da_obj))
        else:
            q_flag = iec61850.QUALITY_VALIDITY_QUESTIONABLE
            if verbose:
                logger.info(
                    f'Invalid type {type(type(data_buffer.value_external))} for the DA {data_buffer.id}, skip it')

        # TODO: also update the quality of the DO
        data_buffer.update_records(data_buffer.create_single_record())

        if tstmp_obj is not None:
            if server_time_mode == 'absolute':
                iec61850.IedServer_updateUTCTimeAttributeValue(ied_server_swig_obj, iec61850.toDataAttribute(tstmp_obj),
                                                               helper.time_unix_to_unit64())
            elif server_time_mode == 'simulation':
                iec61850.IedServer_updateUTCTimeAttributeValue(ied_server_swig_obj, iec61850.toDataAttribute(tstmp_obj),
                                                               helper.time_unix_to_unit64(
                                                                   ied_server.server_config.container.ctime_unix,
                                                                   'UTC'))
            else:
                logger.warning('Unknown time type, can not add timestamp to the float value')

        if quality_obj is not None:
            # TODO: define more methods to determine the quality flag
            """
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
            """
            iec61850.IedServer_updateQuality(ied_server_swig_obj, iec61850.toDataAttribute(quality_obj), q_flag)

    else:
        logger.info(f'Python reference not available for the DA {data_buffer.id}, skip it')


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

    # FIXME: multithreading is not working particularly well here. So dump this approach.
    # threads = []
    # for idxBuffer, data_buffer in enumerate(ied_server.data_buffers):
    #     if data_buffer.is_monitor:
    #         newThread = threading.Thread(target=update_da_worker, args=(ied_server, ied_server_swig_obj, server_time_mode, data_buffer, verbose))
    #         newThread.start()
    #         threads.append(newThread)
    #     else:
    #         if verbose:
    #             logger.info(f'The monitoring is deactivated for DO {data_buffer.DO.id}, skip it.')

    # for t in threads:
    #     t.join()

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
        is_success = sunspec.exec_sunspec_control(ied_config.interface.active_sunspec_mappings, data_buffer,
                                                  ied_config.interface.is_sunspec_force_enable)

    else:
        logger.warning(f'Unknown data source {data_buffer.data_source}')

    return is_success



