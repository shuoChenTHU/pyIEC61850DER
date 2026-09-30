# -*- coding: utf-8 -*-
"""
Supporting functions for runtime data processing routines.

This sub-module contains functions that are necessary for the data processing in simulation routine,
these include:
    - get current value from the data_active
    - update measurements for all measuring points
    - passing control values to the data interface instances

TODO: more descp for the data sources

"""

import logging
import random
import os
import numpy as np
import pandas as pd
import threading
from datetime import datetime, timedelta, timezone
import time
import pytz
from pandas import DataFrame

import interface.randomisor as interface_random
import interface.number as interface_number
import interface.local as interface_local
import interface.influxdb as interface_influxdb
import interface.sunspec as interface_sunspec
import interface.calculator as interface_calculator
import interface.iec61850_mms as interface_iec61850_mms
from communication.pyiec61850_server import IEC61850ServerMMS

from interface.data_buffer import DataBuffer
import settings.helper as helper
from settings.third_party import timeout_checker
from settings.helper import rotating_logger
from settings.config import IedConfig
from simulation.runtime_manager import TimeManager, IedManager

iec61850 = helper.import_libiec61850()
logger = logging.getLogger(f"main_logger.{__name__}")


# %% main part of the routine submodule

def display_runtime_data(ied_server:IEC61850ServerMMS):
    """
    This function simply display the current value of th IEC 61850 parameters,
    it considers both the values from source and values prepared for the IEC 61850 server.
    If the data are not identical on both sides, there must be something wrong.

    TODO: display the values in data_buffer and values in IED server on one line?
    """

    logger.debug('-------------------------------------------------------------------')

    logger.debug('Current values of the IEC 61850 DA from the source:')

    for i, item in ied_server.data_buffers.items():
        if item.is_monitor:
            logger.debug(f'{item.id}: {item.value_external}')
    logger.debug('-------------------------------------------------------------------\n')

    logger.debug('-------------------------------------------------------------------')
    logger.debug('Current values of the IEC 61850 DA in the IEC 61850 server:')

    for i, item in ied_server.data_buffers.items():
        if item.is_monitor:
            logger.debug(f'{item.id}: {item.value_iec61850}')

    logger.debug('-------------------------------------------------------------------\n')


def init_data_buffers(ied_config: IedConfig, ied_server:IEC61850ServerMMS, verbose:bool=True):
    """
    Initialization of the measurements for the IEc 61850 server.

    A following action for update_ied_attr is NOT necessary during data_buffer initialisation, it will be triggered
    by a separate function call.

    """

    logger.info('=================   Begin measurement initialization    =================')
    logger.info(f'{ied_server.data_buffer_count} parameters found in the data buffer list')

    assert ied_config.container.ctime_local_str is not None, 'The current time string can not be None!!'

    for i, data_buffer in ied_server.data_buffers.items():
        if not data_buffer.is_monitor:
            continue
        else:
            if data_buffer.data_source in ['local', 'influxdb']:  # only local and influxdb possess TimeSeries
                init_data_buffer_timeseries(data_buffer)

            new_limits = update_limits(data_buffer, ied_server.data_buffers)

            # No need to pass new_limits because they are already in data_buffer.numeric_limits
            data_buffer.init_single_value()

    if verbose:
        logger.info("Display measurements of the running IED server")
        display_runtime_data(ied_server)

    data_sources = set(ied_config.interface.df_lookup['data_source'])
    logger.info(f'Currently active data interfaces in the lookup table are: {data_sources}.')
    active_data_sources = set([dbf.data_source for dbf in ied_server.data_buffers.values()])
    logger.info(f'Currently active data interfaces in the dataBuffers are: {data_sources}.')
    logger.info('=================   End measurement initialization    =================\n')



def data_buffer_worker(ied_manager: IedManager, data_buffer: DataBuffer):
    '''
    A thread work that takes care of the regularly update of measurements and status values in a 
    data_buffer instance.
    TODO: data buffer worker does not really help, consider removing the usage.

    TODO: check whether the update of data_active of many parameters would take more than 1 minute

    TODO: now that time_manager is assigned to all databuffers, ctime_bundle can be called inside databuffer
    '''

    try:
        # make the trigger block into a method of DataBuffer
        if data_buffer.data_source in ('local', 'influxdb'):
            if (ied_manager.time_manager.ctime_unix % data_buffer.time_series.data_refresh_trigger <
                    ied_manager.time_manager.t_interval_data_update):
                logger.info(f'Data update of the data data_active is triggered for the DA {data_buffer.id}')
                init_data_buffer_timeseries(data_buffer)
    
        # logger.info(f'Update parameter values in the data buffer {data_buffer.id}')
        new_limits = update_limits(data_buffer, ied_manager.ied_server.data_buffers)
        # No need to pass new_limits because they are already in data_buffer.numeric_limits
        data_buffer.update_buffer_single_val()

    except Exception as exc:
        # TODO: apply logged_errors set also to other occurrences of exception catcher.
        msg = f'Something went wrong when updating the data_buffer {data_buffer.id}'
        logger.log_new_error(exc, msg)



def update_data_buffers(ied_manager: IedManager, verbose: bool = True):
    """
    Iteratively update the measurements for the IEC 61850 server.
    Since the cummulative processing time could cause processing time issues, let each databuffer update
    be executed in a separate thread.
    """
    tic = time.perf_counter()

    logger.info('-------------------------------------------------------------------')
    logger.info(f'Start update data buffers with these data sources: {ied_manager.data_sources}')

    # 2. Measurement updates
    server_swig_obj = ied_manager.ied_server.ied_server.swig_obj
    monitor_buffers = [db for db in ied_manager.ied_server.data_buffers.values() if db.is_monitor]

    # Sequential Execution (Fastest & safest if sharing 1 or 2 Modbus sockets)
    for data_buffer in monitor_buffers:
        data_buffer_worker(ied_manager, data_buffer)

    # 3. Synchronize IEC 61850 control attribute inputs
    for data_buffer in ied_manager.ied_server.data_buffers.values():
        if data_buffer.is_control:
            da_ctrl_obj_ref = data_buffer.iec61850_do.obj_ref_map.get('control_da')
            if da_ctrl_obj_ref is not None:
                iec61850_val = iec61850.IedServer_getFloatAttributeValue(
                    server_swig_obj,
                    iec61850.toDataAttribute(da_ctrl_obj_ref)
                )
                data_buffer.value_iec61850 = iec61850_val

    t2 = time.perf_counter() - tic
    logger.warning(f't_perf (Data Buffers Updated): {t2:.4f} s')

    tic = time.perf_counter()
    # 4. Push updates to IEC 61850 C-Server MMS Stack
    interface_iec61850_mms.update_ied_attr(ied_manager.ied_server)

    t3 = time.perf_counter() - tic
    logger.warning(f't_perf (MMS Stack Updated): {t3:.4f} s')

    if verbose:
        display_runtime_data(ied_manager.ied_server)

def init_data_buffer_timeseries(data_buffer: DataBuffer):
    """
    This function can be used to update the short term profiles for each DA.
    """

    logger.info('-------------------------------------------------------------------')
    logger.info(f'Start update the short term data_active for the DA {data_buffer.id}')

    if data_buffer.data_source == 'local':
        interface_local.refresh_daily_time_series(data_buffer)

    elif data_buffer.data_source == 'influxdb':
        interface_influxdb.refresh_daily_time_series(data_buffer)
    else:
        logger.info(f'No data_active interface configured for the data source type {data_buffer.data_source}')

def get_external_value_by_idx(data_buffers:dict, target_idx: int):
    '''
    A helper method to get the correct data_buffer index by a given lookup table index.
    This will be commonly used when a configured lookup talbe is at hand and loaded by
    the read_lookup_csv method.

    It helps to solve the data_buffer mismatch issue, which could be critical for the
    realtime application.

    This method also returns the value_external of that data_buffer.
    '''

    indices = [idx for idx, item in data_buffers.items() if item.index == target_idx]
    if not indices:
        idx = None
        logger.warning(f'Can not locate the index of data_buffer with lookup index {target_idx}')
    elif len(indices) > 1:
        idx = indices[0]
        logger.warning(
            f'Found more than 1 indexes for data_buffer with lookup index {target_idx}, take the first one')
    else:
        idx = indices[0]

    if idx is not None:
        val = data_buffers[idx].value_external
    else:
        val = None

    return idx, val


def resolve_limits(key: str, value, data_buffers:dict):
    """Helper to resolve a numeric limit from various config types."""
    # 1. Direct Numeric Value
    if isinstance(value, (int, float, np.number)):
        return value

    # 2. Dictionary-based configuration
    if isinstance(value, dict):
        # Case A: Index-based lookup
        if 'index' in value:
            idx = value['index']
            _, limit_item = get_external_value_by_idx(data_buffers, idx)
            if limit_item is not None:
                # Assuming the buffer object has a .value or similar numeric attr
                return getattr(limit_item, 'value', limit_item)

                # Case B: Function handler lookup
        handler_name = value.get('handler')
        if handler_name:
            func = getattr(interface_calculator, handler_name, None)
            if func:
                return func(value.get('args', []))

    # 3. Fallback/Default
    logger.warning(f"Could not resolve {key} limit. Using infinity.")
    return np.inf if key == 'upper' else -np.inf


def update_limits(data_buffer:DataBuffer, data_buffers:dict) -> tuple:
    """
    This function is used to update the attribute "limits" of DataBuffer instances. Normally the lower and upper
    limits are two numbers, but to some extend the value could be function handler that points to another data_buffer.
    e.g. in IEC61850, the max of WRtg is taken from WRtgMax, and OutWSet can be limited by WRtg
    This is just an example, the actual implementation could differ from that.

    Anyway, this function takes care of these data_buffer limits and makes sure that of boundary values are updated
    in a real-time environment.

    NOTE: currently we can not make this function a method of DataBuffer because it depends on other data buffer
    objects during the idx search.

    TODO: use some more pythonic names to make the handler of bounds
    TODO: consider rename limits to bounds?

    TODO: this methods is particularly required when the limits are determined by other DO (other data buffers).
     Probably it is better to add another method to handle the inputs dict in the lookup table.

    """
    new_limits = {}
    for key in ['lower', 'upper']:
        value = data_buffer.limits.get(key)
        resolved_val = resolve_limits(key, value, data_buffers)

        # Validation
        if not helper.is_valid_number(resolved_val):
            logger.error(f"Limit {key} resolved to invalid number: {resolved_val}")
            new_limits[key] = np.inf if key == 'upper' else -np.inf
        else:
            new_limits[key] = resolved_val

    data_buffer.numeric_limits = tuple(new_limits.values())

    return data_buffer.numeric_limits