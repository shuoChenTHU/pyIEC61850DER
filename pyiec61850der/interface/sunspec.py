# -*- coding: utf-8 -*-
"""
Real-time functions for the Sunspec - IEC 61850 interface, incl. a Sunspec client.

Use the open-source lib sunspec2 to establish ModbusTCP connection to a SunSpec
compatible PV inverter.

The first priority at this phase is to get this concept to technically work, optimisation
of code efficiency and communication effort is the next step.

TODO: this sub-module has been growing during the code refactoring. Consider a decomposition into smaller
    sub-moduels with dedicated function blocks.
"""

import sunspec2.modbus.client as client
from sunspec2.modbus.client import  SunSpecModbusClientDeviceTCP, SunSpecModbusClientPoint, SunSpecModbusValueError
from sunspec2.modbus.modbus import ModbusClientError, ModbusClientTimeout
from socket import timeout as SocketTimeout
import pandas as pd
from pandas import DataFrame
import numpy as np
import copy
from difflib import SequenceMatcher
from functools import wraps
import threading
from contextlib import nullcontext
import time
import struct
from collections import defaultdict

import settings.helper as helper
from settings.helper import rotating_logger
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interface.data_buffer import DataBuffer
    from simulation.runtime_manager import IedManager
    from communication.pyiec61850_server import IEC61850ServerMMS
logger = logging.getLogger(f"main_logger.{__name__}")



"""
=======================================================================
=================   ESSENTIAL ROUTINE FUNCTIONS       =================
=======================================================================
"""

def get_cvalue(data_buffer: 'DataBuffer') -> helper.StdDataType.AllTypes:
    val = read_single_value(data_buffer)
    return val

def exec_sunspec_control(sunspec_mappings: list, data_buffer: 'DataBuffer', is_force_enable: bool):
    """
    NOTE: most of control parameters share the same mms_addr as of monitorDA, this will be different if cdc type like
        APC get included in libiec61850, in that case we must navigate to the controlDA through monitorDA address,
        so we directly use monitorDA mms_addr here check if that could be an issue.

    FIXME: need a logic to distinguish multiple sunspec devices

    :param sunspec_mappings:
    :param data_buffer:
    :param is_force_enable:
    :return:
    """

    def _find_para_idx() -> tuple[int | None, DataFrame | None]:
        """
        Pack the sunspec_mappings in outer loop, one data_buffer can only be assigned to maximal one inverter.
        As soon as one unique idx is found, return it.
        :return:
        """

        for mapping in sunspec_mappings:
            addr_to_idx_map = mapping.groupby('mms_addr').groups
            target_addr = data_buffer.iec61850_do.obj_ref_map['monitor_da_mms_addr']
            idx_list = addr_to_idx_map.get(target_addr, [])

            if len(idx_list) == 0:
                logger.warning(f'Could not find the sunspec data entry with target addr {target_addr}')
                return None, mapping
            elif len(idx_list) != 1:
                logger.warning(
                    f'Something went wrong, can not locate unique lookup index for DA'
                    f' {data_buffer.iec61850_do.obj_ref_map["control_da_mms_addr"]}')
                logger.warning(f'Found multiple sunspec data entries with target addr {target_addr}, take the first '
                               f'one')
                return None, mapping
            else:
                return idx_list[0], mapping
        return None, None

    row_idx, sunspec_mapping = _find_para_idx()

    if row_idx is not None:
        model_id = sunspec_mapping.at[row_idx, 'model_id']
        para = sunspec_mapping.at[row_idx, 'name']
        # val_write = data_buffer.get_unscaled_source_value()
        cval_write = data_buffer.value_external
        try:
            # Call your existing writer logic
            is_written, committed_val = write_cvalue_to_inverter(data_buffer.fieldbus_conn_obj, model_id, para,
                                                                 cval_write, is_force_enable)
            if is_written:
                return True, None, committed_val
            return False, 'NETWORK_ERROR', None

        except (SunSpecModbusValueError, ValueError) as val_err:
            logger.error(
                f"[exec_control] Fatal SunSpec value error for DO {data_buffer.id} with value {data_buffer.value_external}: {val_err}"
            )
            return False, 'VALUE_ERROR', None

        except Exception as net_err:
            logger.error(f"[exec_control] Transient error for DO {data_buffer.id}: {net_err}")
            return False, 'NETWORK_ERROR', None

"""
========================================================================
=================  SUNSPEC INTERFACE MAPPING FUNCTIONS =================    
========================================================================
"""

def init_sunspec_interface(ied_manager: 'IedManager'):
    """
    This function performs an initial sunspec service activation after the IED server has been
    started.

    Using the default sunspec mapping table (the xlsx file) as input, this function guarantees a successful parsing.

    TODO: implement an error handler, if the mapping can not be loaded properly, then dump sunspec service

    :param ied_manager: the runtime ied_manager instance
    :return:
    """

    parse_mapping(ied_manager)
    update_mapping_by_initial_scan(ied_manager)

def parse_mapping(ied_manager: 'IedManager'):
    """
    Use the information prepared in ied_config and ied_server to parse the Sunspec mapping, generate a mapping
    table with valid Sunspec parameters and return it.

    Parameters
    ----------
    ied_manager: the runtime ied_manager instance

    """

    logger.info('-------------------------------------------------------------------')
    logger.info('Start parsing the sunspec mapping table')

    [df_mapping, df_lookup] = init_mapping(ied_manager)
    df_mapping_stack = stack_mapping(ied_manager, df_mapping)
    df_mapping_runtime = init_mapping_runtime(df_mapping_stack)
    df_mapping_runtime = build_mapping_runtime(df_mapping_runtime,
                                               df_lookup, ied_manager.ied_server.data_model.ied_name)

    df_mapping_active: DataFrame = df_mapping_runtime.loc[df_mapping_runtime['is_active'] == True]

    # add attribute to the IED configuration
    ied_manager.ied_config.interface.df_sunspec_mapping = df_mapping_active

    logger.info(f'IED server has detected {len(df_mapping_active)} active sunspec parameters.')
    logger.info('-------------------------------------------------------------------\n')


def init_mapping(ied_manager: 'IedManager') -> tuple[DataFrame, DataFrame]:
    """
    Initialise the sunspec mapping table in the form of pandas Dataframe.

    Parameters
    ----------
    ied_manager: the runtime ied_manager instance

    """

    df_lookup: DataFrame = pd.read_csv(ied_manager.ied_config.interface.path_lookup, sep=',')
    df_mapping: DataFrame = pd.read_excel(ied_manager.ied_config.interface.path_sunspec_mapping,
                                          sheet_name="SunSpec_Classic")

    return df_mapping, df_lookup

def stack_mapping(ied_manager: 'IedManager', df_mapping: DataFrame) -> DataFrame:
    """
    In case one IED server contains multiple PV devices (PV inverters), stack the individual parameter mapping into
    one concatenated DataFrame.

    It copies the standard sunspec mapping dataframe (which is used in the single PV device case), and replaces the
    logical device name for additional PV devices accordingly

    Parameters
    ----------
    ied_manager: the runtime ied_manager instance
    df_mapping: DataFrame of the sunspec mapping

    Returns
    -------
    df_mapping_stack: stacked sunspec mapping for multiple PV inverters, also works for n=1

    """

    df_mapping_stack: DataFrame = pd.DataFrame(dtype=object)  # stack the mapping of all PV devices in one DataFrame
    # TODO: require alternative handling of DER configs
    der_dicts = getattr(ied_manager.ied_server.server_config.der, 'der_dicts', {})
    pv_devices: list = der_dicts.get('PV', [])
    if len(pv_devices) == 0:
        logger.warning('No PV devices detected in the data model, the sunspec interface may not work properly.')
        df_mapping_stack = df_mapping
    else:
        for item in pv_devices:
            df_mapping_new: DataFrame = copy.deepcopy(df_mapping)
            df_mapping_new.loc[df_mapping_new['LD'] == 'PV', 'LD'] = item
            df_mapping_stack = pd.concat([df_mapping_stack, df_mapping_new], sort=False)
        df_mapping_stack = df_mapping_stack.reset_index(drop=True)
        df_mapping_stack = df_mapping_stack.drop_duplicates()  # must drop duplicates for unique identification

    return df_mapping_stack

def init_mapping_runtime(df_mapping_stack: DataFrame,
                         is_remove_exclusions:bool = True,
                         is_remove_incompatibles: bool = False) -> DataFrame:
    """
    Initialise a new dataframe object that contains essential information for runtime operation.

    Parameters
    ----------
    df_mapping_stack: stacked sunspec mapping table built by :func:`stack_mapping`
    is_remove_exclusions: whether remove parameters that are categorised as 'excluded'
    is_remove_incompatibles: whether remove parameters that are categorised as 'incompatible'

    Returns
    -------
    df_mapping_runtime: the dataframe object that contains essential information for runtime operation
    """

    df_mapping_runtime = copy.deepcopy(df_mapping_stack)
    if is_remove_exclusions:
        df_mapping_runtime: DataFrame = df_mapping_runtime.loc[df_mapping_runtime['excluded'] != 'x']  # remove excluded parameters
    if is_remove_incompatibles:
        df_mapping_runtime = df_mapping_runtime.loc[df_mapping_runtime['incompatible'] != 'x']  # remove incompatible parameters

    # remove enumeration value rows
    df_mapping_runtime = df_mapping_runtime.loc[np.isnan(df_mapping_runtime['addr_offset']) == False]
    df_mapping_runtime['is_active'] = False
    df_mapping_runtime['is_delivered'] = False

    return df_mapping_runtime

def build_mapping_runtime(df_mapping_runtime: DataFrame, df_lookup: DataFrame, ied_name: str) -> DataFrame:
    """
    Update the sunspec runtime mapping table based on information provided by the virtual IED lookup table and
    attributes contained in the IEC 61850 data model.

    Parameters
    ----------
    df_mapping_runtime: the DataFrame object initialised by :func:`init_mapping_runtime`
    df_lookup: the IED lookup table of class DataFrame maintained by the ied_manager of class IedManager
    ied_name: name of the virtual IED, it must be identical as the name in the IEC 61850 data model

    Returns
    -------
    df_mapping_runtime: updated DataFrame object for the cross-reference of IEC 61850 objects in runtime
    """

    df_mapping_runtime["mms_addr"] = df_mapping_runtime["mms_addr"].astype(object)  # enforce object type

    for idx in df_mapping_runtime.index:
        item = df_mapping_runtime.loc[idx]
        '''
        NOTE: pay attention to the LN instance (IEC 61850 specific) "1" behind LN name.
              In the current implementation, each LN instance in the IEC 61850 data model has an index number 1, except
              for LLN0, try to find a pythonic way to solve this. Currently we do not use DA under LLN0, so the index 
              mismatch is not a problem.
        '''


        df_mapping_runtime.loc[idx, 'mms_addr'] = f'{ied_name}_{item["LD"]}/{item["LN"]}1.{item["DO"]}.{item["DA"]}'
        is_monitor_active: bool = df_mapping_runtime.loc[idx, 'mms_addr'] in list(df_lookup['monitor_da'])
        is_control_active: bool = (df_mapping_runtime.loc[idx, 'mms_addr'] in list(df_lookup['control_da']) and
                                   df_mapping_runtime.loc[idx, 'rw_access'] == 'RW')
        df_mapping_runtime.loc[idx, 'is_active'] = is_monitor_active or is_control_active

    return df_mapping_runtime

def update_df_lookup_by_mapping(df_lookup: DataFrame,
                                df_active_sunspec: DataFrame,
                                conn_obj: SunSpecModbusClientDeviceTCP,
                                conn_config: str):
    """
    Even though the lookup table of the vIED already contains plenty of prescribed configuration information,
    a part of the parameters, particularly those related to the communication services, can only be validated when
    an active connection is available, e.g. an active sunspec-compatible PV inverter.

    For this purpose, this function takes a filtered dataframe, which only contains active sunspec parameters
    associated with the target sunspec server (inverter) as configured in ied_manager.ied_config, and uses these
    info to update the entries in the vIED lookup table. This process requires the column names to be precisely
    prescribed in the sunspec mapping table.

    NOTE: in the sunspec specification, there is another column named "scale factor" that links the
        measurement parameter with another parameter for scaling, but we are not using that one here. Instead,
        one need to manually assign a numeric value in the column "factor". This might cause a confusion with the
        application of unit factor, currently there is not scaling handler implemented.

    NOTE: since we use the id_map (dict) to search for data_buffer id, it always returns the last one that matches a
    given MMS attr, i.e. this is an injective map. So we do not need to worry about duplicated MMS addrs in the
    table. But in that concern, this approach can not detect duplicats, no warning will be raised if one sunspec
    parameter is accidentally mapped onto two distinctive IEC 61850 addrs.

    TODO: it is hard to unify the configuration of all data sources for a particular vIED, in this function,
     some column names are hard-coded as strings, they appear in many places in the source code and could be
     misleading. We need an approach ot generalise the information update for all communication services.

    :param df_lookup: the vIED lookup table object maintained by ied_manager
    :param df_active_sunspec: the dataframe of active sunspec parameters, provided by the outer function.
    :param conn_obj: the sunspec connection object provided by the outer function
    :param conn_config: the json config of the sunspec TCP connection object, converted into string
    :return: A updated dataframe that incorporates the latest info update based on a communication service scan.
    """

    df = copy.deepcopy(df_lookup)
    addr_to_idx_map = df.groupby('monitor_da').groups
    for idx_para in df_active_sunspec.index.to_list():
        da_mms_addr = df_active_sunspec.at[idx_para, 'mms_addr']

        # controlDA always comes along with a monitorDA
        index = addr_to_idx_map.get(da_mms_addr, [None])[0]

        if not index:
            logger.debug(f'Cannot locate DataBuffer index for DA {da_mms_addr}')
            continue

        logger.debug(f'Successfully located DA {da_mms_addr} by sunspec mapping, enable sunspec data_source')
        df.at[index, 'fieldbus_conn_obj'] = conn_obj  # object saved in the DataFrame will be of the type Series
        df.at[index, 'data_source'] = 'sunspec'
        df.at[index, 'is_monitor'] = True
        df.at[index, 'fieldbus_conn_config'] = conn_config

        # check if the sunspec parameter comes with a scale factor
        model_id = int(df_active_sunspec.loc[idx_para, 'model_id'])
        param_name = str(df_active_sunspec.loc[idx_para, 'name'])
        fallback_sf = df_active_sunspec.loc[idx_para, 'factor']
        calculated_sf = extract_sunspec_dynamic_scale_factor(conn_obj, model_id, param_name, fallback_sf)

        if abs(calculated_sf - 1.0) > 1e-5:
            df.at[index, 'scale_factor'] = calculated_sf
        else:
            df.at[index, 'scale_factor'] = 1.0

        if df_active_sunspec.at[idx_para, 'rw_access'] == 'RW':
            df.at[index, 'is_control'] = True

    return df

def export_updated_df_lookup(df_updated: DataFrame, is_overwrite: bool, path_output:str):
    """
    Overwrite the initial vIED lookup table using the updated one.

    Parameters
    ----------
    df_updated: the updated dataframe contains the latest vIED lookup configuration
    is_overwrite: force overwriting the lookup table that was used as initial configuration?
    path_output: path of the output file in the case of forcing overwriting
    """

    if is_overwrite:
        df_updated.to_csv(path_output, index=False)
        logger.info('Successfully exported the lookup table of running IED with updated configuration')
    else:
        logger.info('The lookup table of running IED has been updated, but will not overwrite the original CSV file.')

def export_updated_df_mapping(df_updated: DataFrame, path_output:str, idx_device:int):
    """
    Export the updated sunspec mapping table.

    Parameters
    ----------
    df_updated: the updated dataframe contains the latest sunspec mapping
    path_output: path of the output file
    idx_device: idx of the sunspec device
    """

    path_output = f"{path_output.rsplit('.', 1)[0]}_{idx_device}.{path_output.rsplit('.', 1)[1]}"
    df_updated.to_excel(path_output)

def add_conn_obj_online_attr(ied_manager, conn_obj, idx_device):
    # TODO: conn_obj is not yet defined as a class! The attrs operation below may cause inconsistency!

    conn_obj.timeout = 5.0  # leave the conn_obj 5s timeout to avoid long stall due to connection loss
    if not hasattr(conn_obj, 'modbus_lock'):
        conn_obj.modbus_lock = threading.Lock()
    conn_obj.is_active = True  # Tag as online and fully mapped
    conn_obj.idx_device = idx_device
    # also init attr for the tracking of model data stall (in particular after overnight inverter trip)
    conn_obj.active_models = get_sunspec_active_models(ied_manager.ied_server, conn_obj)
    conn_obj.VITAL_MODELS = set([103, 122])  # only watch the models containing dynamic measurements
    conn_obj.model_stall_track = conn_obj.VITAL_MODELS.intersection(conn_obj.active_models)
    conn_obj.is_night = False
    conn_obj.data_stall_count = 0
    conn_obj.MAX_DATA_STALL_COUNT = 5  # exceeding this threshold will trigger a sunspec conn_obj refresh
    conn_obj.last_tracked_values = {}
    conn_obj.last_batch_successful = False

def update_mapping_by_initial_scan(ied_manager: 'IedManager'):
    """
    This function initializes a sunspec connection to the server via ModbusTCP. Meanwhile it updates the interface
    configuration in the vIED lookup table. All sunspec parameters that deliver measurements or status information
    will be recorded in the vIED lookup table.

    During the vIED server routine, associated DO will be updated with "sunspec" as data source. It is possible to
    validate the sunspec parameters regularly, and remove inactivate parameters or add new sunspec parameters.

    Currently the update and export of sunspec mapping and vIED lookup mapping are performed once per device.


    TODO: when indexing the DA ref, only empty list and list with length 1 are considered, because
        each DA should have an unique mms_addr. But duplicated mms_addr could still occur due to
        errors in the engineering process. Implement a unique address check later.
    """

    ied_config = ied_manager.ied_config
    # TODO: check whether it would be much more efficient to operate directly on the original dataframe
    df_mapping = copy.deepcopy(ied_config.interface.df_sunspec_mapping)
    df_lookup = copy.deepcopy(ied_config.interface.df_lookup)

    # Initialize tracking list on ied_manager
    # TODO: this introduces unexpected attr, may cause pydantic error
    if not hasattr(ied_manager, 'pending_sunspec_devices'):
        ied_manager.pending_sunspec_devices = []

    for idx_device, key in enumerate(ied_config.der.der_dicts['PV']):
        logger.info('-------------------------------------------------------------------')
        logger.info(f'Start initial sunspec reading and update of the lookup table for device {idx_device}')

        ipaddr = getattr(ied_config, key.lower()).ip
        slave_id = getattr(ied_config, key.lower()).slave_id
        port = getattr(ied_config, key.lower()).tcp_port

        # Here fieldbus_conn_config means the config info of the conn_obj of interest
        conn_config = str({'ip_addr': ipaddr,
                           'slave_id': slave_id,
                           'port': port,
                           'idx_device': idx_device
                           })

        # termination criteria
        [is_connected, conn_obj] = connect_sunspec_server(ied_manager.SUNSPEC_CONN_REGISTRY, slave_id, ipaddr, port)

        # === OFFLINE AT STARTUP HANDLER ===
        if not is_connected or not scan_sunspec_model(conn_obj):
            logger.warning(
                f"SunSpec host {ipaddr}:{port} (Device {idx_device}) offline during startup. "
                f"Adding to pending background scan queue."
            )

            # Check if an entry with identical connection details is already queued
            is_already_pending = any(
                dev['ip_addr'] == ipaddr and dev['slave_id'] == slave_id and dev['port'] == port
                for dev in ied_manager.pending_sunspec_devices
            )

            # Store pending device configuration for the refresher worker
            if not is_already_pending:
                ied_manager.pending_sunspec_devices.append({
                    'idx_device': idx_device,
                    'key': key,
                    'ip_addr': ipaddr,
                    'slave_id': slave_id,
                    'port': port,
                    'conn_config': conn_config,
                    'conn_obj': conn_obj
                })
            else:
                logger.info(
                    f"SunSpec host {ipaddr}:{port} is already present in pending_sunspec_devices, skipping duplicate.")

            continue

        para_indices = df_mapping.loc[df_mapping['LD'] == key].index.to_list()
        if not para_indices:
            logger.warning(f'Sunspec data model returns an empty list, skip to the next sunspec device.')
            continue

        # add the sunspec device to the list
        ied_manager.active_sunspec_devices.append(conn_obj)

        # perform parameter scan and update the lookup table accordingly
        df_active_sunspec = scan_active_sunspec_parameter(df_mapping, para_indices, conn_obj,
                                                            ied_config.interface.is_keep_none)
        ied_config.interface.active_sunspec_mappings.append(df_active_sunspec)
        df_lookup_updated = update_df_lookup_by_mapping(df_lookup, df_active_sunspec, conn_obj,
                                                        conn_config)
        # export update mapping files
        export_updated_df_mapping(df_active_sunspec, ied_config.interface.path_sunspec_mapping_export, idx_device)

        # === ONLINE HANDLER ===
        # assign the conn_obj and configurations to data_buffer instances
        assign_conn_to_data_buffers(ied_manager.ied_server, df_lookup_updated, df_active_sunspec, conn_obj, conn_config)

        add_conn_obj_online_attr(ied_manager, conn_obj, idx_device)

        df_lookup = df_lookup_updated
        logger.info(
            f'Initial sunspec reading finished, {len(df_active_sunspec)} parameters are available for the IED server.')
        logger.info(f'Active sunspec models for data query: {conn_obj.active_models}')
        logger.info(f'Active sunspec models for health check: {conn_obj.model_stall_track}')
        logger.info('-------------------------------------------------------------------\n')


    if not df_lookup.equals(ied_config.interface.df_lookup):
        ied_manager.ied_server.df_lookup = df_lookup
        ied_manager.ied_server.get_active_do_in_lookup()
        ied_manager.data_sources = list(ied_manager.ied_server.df_lookup['data_source'].unique())
        export_updated_df_lookup(df_lookup, ied_config.interface.is_force_overwrite,
                                ied_config.interface.path_lookup)


def update_mapping_for_pending_devices(ied_manager: 'IedManager', stop_event: threading.Event = None) -> None:
    """
    Attempts late initial scanning, lookup table updates, and DataBuffer binding
    for SunSpec devices that were offline during startup.
    """
    if not hasattr(ied_manager, 'pending_sunspec_devices') or not ied_manager.pending_sunspec_devices:
        return

    logger.info("Checking pending SunSpec devices for late startup initialization...")

    ied_config = ied_manager.ied_config
    df_mapping = copy.deepcopy(ied_config.interface.df_sunspec_mapping)
    df_lookup = copy.deepcopy(ied_manager.ied_server.df_lookup)

    still_pending = []
    has_successful_initialization = False

    for dev_info in ied_manager.pending_sunspec_devices:
        if (stop_event and stop_event.is_set()) or not ied_manager.is_running:
            logger.info("Abort signal received while processing pending SunSpec devices.")
            still_pending.extend([dev for dev in ied_manager.pending_sunspec_devices if dev not in still_pending])
            break

        idx_device = dev_info['idx_device']
        key = dev_info['key']
        ipaddr = dev_info['ip_addr']
        port = dev_info['port']
        conn_config = dev_info['conn_config']
        conn_obj = dev_info['conn_obj']

        logger.info('-------------------------------------------------------------------')
        logger.info(f"Attempting late SunSpec scan for pending device {idx_device} ({ipaddr}:{port})...")

        # 1. Probe TCP socket availability
        if not safe_reconnect_sunspec(conn_obj):
            logger.warning(f"Pending SunSpec host {ipaddr}:{port} still unreachable. Retrying next cycle.")
            still_pending.append(dev_info)
            continue

        try:
            # 2. Perform SunSpec model scan
            if not scan_sunspec_model(conn_obj):
                logger.warning(f"SunSpec model scan failed for {ipaddr}:{port}. Retrying next cycle.")
                still_pending.append(dev_info)
                continue

            # Reuse existing active df_mapping filtered for this Logical Device
            para_indices = df_mapping.loc[df_mapping['LD'] == key].index.to_list()
            if not para_indices:
                logger.warning(f"SunSpec mapping returned an empty parameter list for {key}, skipping.")
                continue

            # 3. Perform active parameter scan & update lookup table
            df_active_sunspec = scan_active_sunspec_parameter(
                df_mapping, para_indices, conn_obj, ied_config.interface.is_keep_none
            )
            ied_config.interface.active_sunspec_mappings.append(df_active_sunspec)

            df_lookup_updated = update_df_lookup_by_mapping(
                df_lookup, df_active_sunspec, conn_obj, conn_config
            )

            # 4. Export updated device mapping
            export_updated_df_mapping(
                df_active_sunspec, ied_config.interface.path_sunspec_mapping_export, idx_device
            )

            # 5. Set up thread lock & timeout, then assign connection handle to DataBuffers
            add_conn_obj_online_attr(ied_manager, conn_obj, idx_device)

            assign_conn_to_data_buffers(
                ied_manager.ied_server, df_lookup_updated, df_active_sunspec, conn_obj, conn_config
            )

            df_lookup = df_lookup_updated
            has_successful_initialization = True
            logger.info(f"Late SunSpec initialization complete for device {idx_device} ({ipaddr}:{port}).")
            logger.info(f'Active sunspec models for data query: {conn_obj.active_models}')
            logger.info(f'Active sunspec models for health check: {conn_obj.model_stall_track}')
            logger.info('-------------------------------------------------------------------\n')

        except Exception as scan_err:
            logger.error(f"Failed late initialization for SunSpec device {ipaddr}:{port}: {scan_err}")
            still_pending.append(dev_info)

    # Reassign queue with unresolved devices
    ied_manager.pending_sunspec_devices = still_pending

    # 6. Synchronize global lookup table, data sources, and re-initialize DataBuffers
    if has_successful_initialization and not df_lookup.equals(ied_manager.ied_server.df_lookup):
        ied_manager.ied_server.df_lookup = df_lookup

        # Correctly call get_active_do_in_lookup() which updates df_lookup_active internally
        ied_manager.ied_server.get_active_do_in_lookup()

        ied_manager.data_sources = list(ied_manager.ied_server.df_lookup['data_source'].unique())

        export_updated_df_lookup(
            df_lookup, ied_config.interface.is_force_overwrite, ied_config.interface.path_lookup
        )

    return has_successful_initialization

"""
=======================================================================
=================        SUNSPEC CLIENT FUNCTIONS     =================
=======================================================================
"""

def single_sunspec_scanner(idx, conn_obj: SunSpecModbusClientDeviceTCP):
    try:
        conn_obj.scan()
        logger.info(f'refresh of connObj with index {idx} successfully executed.')
    except Exception as e:
        logger.exception(f'Device scan for connObj with index {idx} failed, no data update in this iteration.')
        logger.exception(e)


def sunspec_scanner(idx: int, conn_obj: SunSpecModbusClientDeviceTCP):
    """
    Scans the SunSpec device models while holding the device thread lock.
    """
    lock = getattr(conn_obj, 'modbus_lock', None)

    if lock:
        with lock:  # Protect conn_obj.models from concurrent MainThread access
            logger.info(f"Scanning SunSpec connection object at index {idx} under lock...")
            single_sunspec_scanner(idx, conn_obj)
    else:
        logger.info(f"Scanning SunSpec connection object at index {idx} (No lock found)...")
        single_sunspec_scanner(idx, conn_obj)

def connect_sunspec_server(SUNSPEC_CONN_REGISTRY: dict,
                           slave_id: int,
                           ip_addr: str,
                           port: int) -> tuple[bool, SunSpecModbusClientDeviceTCP]:
    """
    Returns a cached, single-instance SunSpec connection object for a given IP/port/slave_id.
    """

    key = (ip_addr, int(port), int(slave_id))

    if key in SUNSPEC_CONN_REGISTRY:
        conn_obj = SUNSPEC_CONN_REGISTRY[key]
        # Verify socket health before returning cached handle
        if keep_alive(conn_obj):
            return True, conn_obj
        else:
            # Reconnect dead socket on existing object
            try:
                conn_obj.close()
            except Exception:
                pass
            try:
                conn_obj.connect()
                return True, conn_obj
            except Exception as err:
                logger.warning(f"Failed to reconnect cached SunSpec object for {ip_addr}:{port}: {err}")
                return False, conn_obj

    # Create new connection object if not in registry
    try:
        conn_obj = client.SunSpecModbusClientDeviceTCP(slave_id=slave_id, ipaddr=ip_addr, ipport=port)
        conn_obj.connect()
        SUNSPEC_CONN_REGISTRY[key] = conn_obj
        return True, conn_obj
    except Exception as err:
        logger.error(f"Failed to create SunSpec connection to {ip_addr}:{port}: {err}")
        # Store uninitialized object in registry so late-scans use the same handle
        conn_obj = client.SunSpecModbusClientDeviceTCP(slave_id=slave_id, ipaddr=ip_addr, ipport=port)
        SUNSPEC_CONN_REGISTRY[key] = conn_obj
        return False, conn_obj

def safe_reconnect_sunspec(conn_obj) -> bool:
    """
    Safely tears down stale/dead TCP sockets and establishes a fresh connection
    without re-scanning SunSpec models.
    """
    # 1. Test live Modbus socket responsiveness

    try:
        is_alive = keep_alive(conn_obj)
    except Exception:
        is_alive = False

    if is_alive:
        return True  # Socket is healthy and responsive

    # 2. Socket is dead or unbound (0.0.0.0) -> Force Teardown
    try:
        if hasattr(conn_obj, 'close'):
            conn_obj.close()
        elif hasattr(conn_obj, 'disconnect'):
            conn_obj.disconnect()
    except Exception as err:
        logger.warning(f"Error closing dead SunSpec socket: {err}")

    # 3. Attempt fresh TCP socket connection
    try:
        conn_obj.connect()
        # Verify the new connection works
        logger.info('Try to refresh the current sunspec conn object.')
        return keep_alive(conn_obj)
    except Exception as err:
        logger.error(f"Failed to reconnect SunSpec device: {err}")
        return False

def keep_alive(sunspec_conn: SunSpecModbusClientDeviceTCP) -> bool:
    """
    Checks active connection to the SunSpec server safely under modbus_lock.
    Clears is_active flag and closes socket cleanly on failure.
    """

    def _test_health():
        client = getattr(sunspec_conn, 'client', None)
        client_dict = getattr(client, '__dict__', {}) if client else {}

        # tag unhealth connection if socket is None
        if client_dict.get('socket') is None:
            return False

        # tag unhealth connection (in daytime) if data stall threshold is exceeded
        if not sunspec_conn.is_night:
            max_count = sunspec_conn.MAX_DATA_STALL_COUNT
            if sunspec_conn.data_stall_count >= max_count:
                logger.error(
                    f"SunSpec data stall limit reached ({sunspec_conn.data_stall_count}/{max_count}). "
                    f"Forcing connection reset to clear stale inverter buffer."
                )
                sunspec_conn.data_stall_count = 0
                sunspec_conn.last_tracked_values = {}
                return False

        if hasattr(sunspec_conn, 'models') and sunspec_conn.models:
            first_model_id = next(iter(sunspec_conn.models))
            model_instance = sunspec_conn.models[first_model_id][0]
            model_instance.read()
        return True

    def _cleanup_stale_socket(conn):
        try:
            # Mark inactive immediately to stop MainThread batch reads
            conn.is_active = False

            if hasattr(conn, 'close'):
                conn.close()

            client = getattr(conn, 'client', None)
            if client:
                if hasattr(client, 'close'):
                    client.close()
                if hasattr(client, '__dict__') and 'socket' in client.__dict__:
                    client.__dict__['socket'] = None
        except Exception as err:
            logger.debug(f"Ignored error during socket cleanup: {err}")

    if sunspec_conn is None:
        return False

    lock = getattr(sunspec_conn, 'modbus_lock', None)

    try:
        # Acquire lock to prevent closing the socket mid-batch read on MainThread
        if lock:
            with lock:
                is_healthy = _test_health()
        else:
            is_healthy = _test_health()

        if is_healthy:
            # Connection is alive and confirmed working
            sunspec_conn.is_active = True
            logger.info("SunSpec connection verified active via live read test.")
            return True
        else:
            sunspec_conn.is_active = False
            logger.warning("Keep-alive action detects unhealthy connection. Marking inactive.")
            _cleanup_stale_socket(sunspec_conn)
            return False

    except (ModbusClientError, ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError) as e:
        logger.warning(f"SunSpec server socket failed live health check: {e}")
        _cleanup_stale_socket(sunspec_conn)
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during SunSpec keep_alive: {e}")
        _cleanup_stale_socket(sunspec_conn)
        return False

def scan_sunspec_model(conn_obj: SunSpecModbusClientDeviceTCP) -> bool:
    """
    Perform a sunspec data model scan, return a bool flag.

    Parameters
    ----------
    conn_obj: the connection object to the sunspec server of interest

    Returns
    -------
    A bool flag
    """

    try:
        conn_obj.scan()
        return True
    except Exception as e:
        logger.exception('Could not perform the sunspec mapping scan, check the slave ID and port')
        logger.exception(e)
        return False

def assign_conn_to_data_buffers(ied_server: 'IEC61850ServerMMS',
                                df_lookup: DataFrame,
                                df_mapping: DataFrame,
                                conn_obj: SunSpecModbusClientDeviceTCP,
                                conn_config: str):
    """
    TODO: the input arg ied_server will later become ied_manager, make amendments and update docstring later

    Parameters
    ----------
    ied_server
    df_lookup
    df_mapping
    conn_obj
    conn_config

    Returns
    -------

    """

    df_lookup_filtered = df_lookup.loc[df_lookup['fieldbus_conn_config'] == conn_config]
    for idx_para in df_lookup_filtered.index.to_list():
        # Attention, index lookup is not always the index in data_buffers, so relocate the data buffer index
        da_mms_addr = df_lookup_filtered.loc[idx_para, 'mms_addr']
        index = ied_server.id_map.get(da_mms_addr)
        if not index:
            logger.warning(
                f'Something went wrong, can not locate DataBuffer index for DA {da_mms_addr}')
        else:
            ied_server.data_buffers[index].data_source = 'sunspec'

            # pass shared sunspec config to data_buffer
            ied_server.data_buffers[index].local_conn_config = conn_obj
            ied_server.data_buffers[index].fieldbus_conn_obj = conn_obj
            ied_server.data_buffers[index].fieldbus_conn_mapping = df_mapping

            ied_server.data_buffers[index].is_monitor = True
            ied_server.data_buffers[index].scaling_factor = df_lookup.loc[idx_para, 'scale_factor']
            if df_lookup_filtered.loc[idx_para, 'is_control']:
                ied_server.data_buffers[index].is_control = True
            ied_server.data_buffers[index].get_id_map(required_cols=['model_id', 'name', 'mms_addr'])


def scan_active_sunspec_parameter(df_mapping: DataFrame,
                                  para_indices: list,
                                  conn_obj: SunSpecModbusClientDeviceTCP,
                                  is_keep_none: bool) -> DataFrame:
    """
    This function takes the pre-scribed SunSPEC mapping table (DataFrame) and a list of indices for sunspec
    parameters in presence (which is provided by the outer function) as inputs, updates the mapping table
    accordingly, and returns the updated dataframe.

    TODO: to stay on the safe side, we operate on a deepcopy of the original dataframe, check if this is unnecessary

    Parameters
    ----------
    df_mapping: the pre-scribed SunSPEC mapping table
    para_indices: a list of indices for sunspec parameters in presence
    conn_obj: the sunspec connection object provided by the outer function
    is_keep_none: whether keep sunspec parameters that return None as value

    Returns
    -------
    A subset of the dataframe that contains only parameters marked as is_delivered
    """

    df = copy.deepcopy(df_mapping)
    for idx_para in para_indices:
        model_id = df.at[idx_para, 'model_id']
        if model_id not in conn_obj.models:
            continue
        para = df.at[idx_para, 'name']
        value = read_cached_point_cvalue(conn_obj, model_id, para)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            if is_keep_none:
                logger.warning(
                    f'The sunspec parameter {model_id} - {para} returns {value}, but still keep it in the list.')
            else:
                logger.warning(
                    f'The sunspec parameter {model_id} - {para} returns {value}, set it to inactive in the sunspec '
                    f'mapping table.')
                continue

        df.at[idx_para, 'is_delivered'] = True

    return df.loc[df['is_delivered'] == True]


def get_required_sunspec_models_per_conn(ied_server) -> dict:
    """
    Scans all monitored SunSpec DataBuffers and collects
    the set of unique model_ids required for each active connection.

    Returns:
        dict: { conn_obj: { model_id_1, model_id_2, ... } }
    """

    req_models_map = defaultdict(set)

    for db in ied_server.data_buffers.values():
        if getattr(db, 'is_monitor', False) and getattr(db, 'data_source', '') == 'sunspec':
            conn_obj = getattr(db, 'fieldbus_conn_obj', None)

            # Retrieve model_id using the DataBuffer's internal mapping ID map
            if conn_obj and hasattr(db, 'fieldbus_conn_mapping') and hasattr(db, 'id_map'):
                mms_addr = db.iec61850_do.obj_ref_map['monitor_da_mms_addr']
                if mms_addr and mms_addr in db.id_map:
                    idx = db.id_map[mms_addr][0]
                    model_id = db.fieldbus_conn_mapping.at[idx, 'model_id']

                    # Convert to int if model_id is numeric (e.g. 103, 120, 123)
                    try:
                        model_id = int(model_id)
                    except (ValueError, TypeError):
                        pass

                    req_models_map[conn_obj].add(model_id)

    return req_models_map

def get_sunspec_active_models(ied_server, conn_obj):

    active_models = []

    for db in ied_server.data_buffers.values():
        if getattr(db, 'is_monitor', False) and getattr(db, 'data_source', '') == 'sunspec':
            if conn_obj != getattr(db, 'fieldbus_conn_obj', None):
                continue

            # Retrieve model_id using the DataBuffer's internal mapping ID map
            if hasattr(db, 'fieldbus_conn_mapping') and hasattr(db, 'id_map'):
                mms_addr = db.iec61850_do.obj_ref_map['monitor_da_mms_addr']
                if mms_addr and mms_addr in db.id_map:
                    idx = db.id_map[mms_addr][0]
                    model_id = db.fieldbus_conn_mapping.at[idx, 'model_id']

                    # Convert to int if model_id is numeric (e.g. 103, 120, 123)
                    try:
                        model_id = int(model_id)
                    except (ValueError, TypeError):
                        pass

                    active_models.append(model_id)
    active_models.sort()
    return set(active_models)


"""
=======================================================================
=================   RUNTIME SUNSPEC FUNCTIONS - READ  =================
=======================================================================
"""

def update_all_sunspec_caches(ied_manager: 'IedManager'):
    """
    Performs block reads ONLY for SunSpec models required by monitored DataBuffers.
    Prevents Modbus Exception 2 and WinError 10038 by avoiding unmapped/proprietary models.

    TODO: currently we only read the first instance in model list by default.
    """

    def _safe_reset_sunspec_model_cache(model_instance):
        """
        Completely wipes cached values, scale factor dependencies, and
        internal point states for a pysunspec2 model instance to prevent
        stale register-shift contamination.
        """
        if model_instance is None:
            return

        try:
            if hasattr(model_instance, 'points') and model_instance.points:
                for pt_name, pt in model_instance.points.items():
                    # Reset all known value layers
                    if hasattr(pt, 'cvalue'):
                        pt.cvalue = None
                    # Clear any error or status flags on the point if present
                    if hasattr(pt, 'dirty'):
                        pt.dirty = True

            # If the model instance has a block or data buffer reference, clear it
            if hasattr(model_instance, 'error_info'):
                model_instance.data = 'read_error'

            logger.debug(f"Successfully purged cache for model {getattr(model_instance, 'model_id', 'unknown')}")
        except Exception as err:
            logger.debug(f"Error during model cache reset: {err}")

    def _selective_batch_read(conn_obj):
        # Track whether this batch read cycle completed successfully
        batch_success = True

        for model_id in conn_obj.active_models:
            # Check if model exists on the pysunspec2 connection object
            model_list = conn_obj.models.get(model_id)
            if not model_list:
                continue

            if len(model_list) > 1:
                logger.warning(f'The object of model ID {model_id} has multiple instances, update cache for all '
                               f'instances, pay special attention to data inconsistency.')

            try:
                # Issue ONE Modbus read request for this required model block
                model_list[0].read()
                time.sleep(ied_manager.time_manager.SUNSPEC_MODEL_READ_PAUSE)

            except (TimeoutError, SocketTimeout, ModbusClientTimeout, Exception) as err:
                batch_success = False
                err_str = str(err).lower()

                logger.warning(f'Sunspec read timeout on Model {model_id}: {err_str}.')

                if isinstance(err, ModbusClientTimeout):
                    logger.error(f"ModbusClientTimeout occurred, must enforce reconnection.")
                    return False

                elif "timed out" in err_str or "timeout" in err_str or isinstance(err, TimeoutError):
                    logger.warning(f"Aborting batch read and invalidating cache. Flag batch_success = {batch_success}")
                    logger.warning(f'Clearing caches in all models.')

                    # Invalidate model points so they don't hold stale shifted data
                    for model_instance in model_list:
                        _safe_reset_sunspec_model_cache(model_instance)
                else:
                    logger.warning(f"Batch Modbus read failed for required Model {model_id}: {err}")
                break

        # Store health state on conn_obj so control loops know if data is fresh
        conn_obj.last_batch_successful = batch_success

        return True


    ied_server = getattr(ied_manager, 'ied_server', None)
    if not ied_server:
        return

    for conn_obj in ied_manager.active_sunspec_devices:
        # Check connection health and active status
        if not getattr(conn_obj, 'is_active', False):
            continue

        logger.info(f'Batch reading the sunspec device idx {conn_obj.idx_device} with models '
                    f'{list(conn_obj.active_models)}')
        lock = getattr(conn_obj, 'modbus_lock', None)

        if lock:
            with lock:
                is_health = _selective_batch_read(conn_obj)
        else:
            is_health = _selective_batch_read(conn_obj)

        if not is_health:
            conn_obj.client.socket = None
            conn_obj.is_active = False

            # Let safe_reconnect_sunspec handle the cleanup and reconnection safely
            is_healthy = safe_reconnect_sunspec(conn_obj)
            if not is_healthy:
                logger.warning('Reconnection failed, wait until the next sunspec conn_obj health check.')
            else:
                logger.info('Reconnection successful.')
                conn_obj.is_active = True

def track_models_data_stall(ied_manager: 'IedManager'):
    """
    This function is called right before the sunspec connection health check, therefore executed with a lower time
    resolution than data buffer update workers. Currently we need it to detect stall state of the model readings.

    :param ied_manager:
    :return:
    """

    ied_server = getattr(ied_manager, 'ied_server', None)
    if not ied_server:
        return
    # req_models_map = get_required_sunspec_models_per_conn(ied_server)
    for conn_obj in ied_manager.active_sunspec_devices:
        # Check connection health and active status
        if not getattr(conn_obj, 'is_active', False):
            continue

        track_model_ids = list(conn_obj.model_stall_track)
        track_model_ids.sort()
        logger.info(f'Checking data stall for sunspec device idx {conn_obj.idx_device} with models {track_model_ids}')
        lock = getattr(conn_obj, 'modbus_lock', None)
        if lock:
            with lock:
                current_values_sig = {}
                for model_id in track_model_ids:
                    current_values_sig[model_id] = {}
                    if model_id in conn_obj.models:
                        inst = conn_obj.models[model_id][0]
                        # Sample key parameters to check for movement
                        for key, point_obj in inst.points.items():
                            c_val = get_point_cvalue(point_obj) if point_obj else None
                            current_values_sig[model_id][f"{key}"] = c_val

                for model_id in track_model_ids:
                    # Compare with previous signature
                    if not conn_obj.last_tracked_values:
                        conn_obj.last_tracked_values = current_values_sig
                        return
                    if conn_obj.last_tracked_values[model_id] == current_values_sig[model_id] and current_values_sig[model_id]:
                        conn_obj.data_stall_count += 1
                        logger.warning(
                            f"SunSpec data stall warning: Values unchanged for {conn_obj.data_stall_count} checks "
                            f"on device {getattr(conn_obj, 'idx_device', 0)}, model ID {model_id}."
                        )
                        return

                # Data is changing normally! Reset counter.
                conn_obj.data_stall_count = 0
                conn_obj.last_tracked_values = current_values_sig


def get_point_cvalue(point_obj):
    # 1. Try reading calculated value (cvalue)
    cval = getattr(point_obj, 'cvalue', None)

    # 2. Fallback to unscaled raw value if cvalue is None (common in dormant states)
    if cval is None:
        val = getattr(point_obj, 'value', None)

        # 3. Handle SunSpec reserved invalid/unimplemented integer values (0x8000, 0x7FFF)
        if val is None or val in (0x8000, 0x80000000, 0x7FFF):
            # Dormant or uninitialized power register by passing a None
            return None
        else:
            pt_type, pt_sf, sf_name = get_sunspec_point_meta_info(point_obj)
            if pt_sf is not None and isinstance(pt_sf, (int, float)):
                try:
                    cval = val * (10.0 ** float(pt_sf))
                except Exception as err:
                    return None
            else:
                return None
    return cval

def read_cached_point_cvalue(conn_obj: SunSpecModbusClientDeviceTCP,
                             model_id:int, parameter:str) -> any:
    """
    Perform a read value event to get cvalue for a specific sunspec parameter.
    """

    try:
        # by default always read the first instance
        # TODO: in the case of multiple sunspec devices, the correct index must be specified!
        model_instance = conn_obj.models[model_id][0]
        point_obj = getattr(model_instance, parameter, None)
        para_val = get_point_cvalue(point_obj) if point_obj else None

        if para_val is None or para_val in (0x8000, 0x80000000, 0x7FFF):
            return None
        else:
            logger.debug(f'Successfully fetched sunspec parameter {model_id} - {parameter} with value {para_val}')
            return para_val
    except (ModbusClientError, ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
        logger.warning(f'Sunspec server for {parameter} unavailable, wait for scheduled reconnection')
        logger.warning(f'New reading for will be performed in the next iteration')
        return None
    except AttributeError:
        logger.warning(f'Reading sunspec parameter {parameter} caused AttributeError, skip this parameter')
        return None
    except Exception as e:
        logger.warning(f'New reading for sunspec parameter {parameter} failed due to unexpected error.')
        return None


def read_single_value(data_buffer: 'DataBuffer') -> any:
    """
    This function can be used to read single sunspec parameters based on the configuration
    stored in the associated DataBuffer instance.
    If the sunspec connection is gone, the process will try to reconnect the server.

    Using the id_map, we do not need to specify the column name any longer, it is assumed that the map is stored in
    data_buffer.fieldbus_conn_mapping while the MMS address is identical to entries in the column 'mms_addr' of the
    mapping table (this is because we always pass mms_addr to data_buffer.id).
    """

    mms_address = data_buffer.iec61850_do.obj_ref_map['monitor_da_mms_addr']
    map = data_buffer.fieldbus_conn_mapping
    idx = data_buffer.id_map.get(mms_address, [None])[0]

    attr_conn_obj = 'fieldbus_conn_obj'

    if not idx:
        logger.warning(f'No matching row found in mapping table for the MMS address {mms_address}.')
        return None

    if not hasattr(data_buffer, attr_conn_obj):
        logger.warning(f'Data_buffer does not have attr {attr_conn_obj}, please check it manually.')
        return None

    conn_obj = getattr(data_buffer, attr_conn_obj)
    model_id = map.at[idx, 'model_id']
    parameter =map.at[idx, 'name']
    return read_cached_point_cvalue(conn_obj, model_id, parameter)


def extract_sunspec_dynamic_scale_factor(conn_obj, model_id: int, parameter: str, fallback_factor: float) -> float:
    """
    Extracts dynamic scale factor (10^sf) directly from pysunspec2 point metadata.
    Falls back to the lookup table factor if dynamic sf is missing.
    """
    try:
        model_instance = conn_obj.models[model_id][0]
        point_obj = getattr(model_instance, parameter, None)

        if point_obj is not None:
            # Check direct sf_value or sf attribute point
            pt_type, pt_sf, sf_name = get_sunspec_point_meta_info(point_obj)

            # If scale factor exponent exists (e.g., sf = -2 -> factor = 10^-2 = 0.01)
            if pt_sf is not None and isinstance(pt_sf, (int, float)) and pt_sf != 0x8000:
                dynamic_factor = 10.0 ** float(pt_sf)
                logger.debug(f"Dynamic SunSpec SF found for {parameter}: 10^({pt_sf}) = {dynamic_factor}")
                return dynamic_factor

    except Exception as err:
        logger.debug(f"Could not extract dynamic SF for {parameter}, using fallback: {err}")

    # Fallback to static mapping factor if valid
    if helper.is_valid_number(fallback_factor) and not np.isnan(fallback_factor) and fallback_factor > 0:
        return float(fallback_factor)

    return 1.0

"""
=======================================================================
=================   RUNTIME SUNSPEC FUNCTIONS - WRITE =================
=======================================================================
"""

def get_sunspec_point_meta_info(point_obj):
    pt_type = getattr(point_obj, 'type', None)
    pt_sf = getattr(point_obj, 'sf_value', None)
    sf_name = getattr(point_obj, 'sf', None)

    # Fallback scale factor lookup if sf attribute is detached
    if pt_sf is None and hasattr(point_obj, 'model') and isinstance(sf_name, str):
        if hasattr(point_obj.model, sf_name):
            sf_point = getattr(point_obj.model, sf_name)
            pt_sf = getattr(sf_point, 'value', None)
    return pt_type, pt_sf, sf_name

def prepare_sunspec_value(point_obj, raw_val):
    """
    Inspects a pysunspec2 point object to determine if it requires an int or float,
    and formats/rounds the input value accordingly.

    Returns:
        clean_val (int | float): The type-safe value ready to assign to para_obj.value.
    """
    # 1. Unwrap numpy scalars (e.g. np.float64, np.int64) to native Python types
    if hasattr(raw_val, 'item'):
        raw_val = raw_val.item()

    # 2. Extract point metadata from pysunspec2
    pt_type, pt_sf, sf_name = get_sunspec_point_meta_info(point_obj)

    # 3. TYPE CHECKING LOGIC:

    # CASE A: Native SunSpec Float32 / Float64
    if pt_type in ('float32', 'float64'):
        # Pass a rounded 32-bit float
        return round(float(raw_val), 3)

    # CASE B: Integer/Acc register WITH a Scale Factor (e.g., WMaxLimPct with sf = -2)
    elif pt_sf is not None and isinstance(pt_sf, (int, float)):
        decimals = abs(int(pt_sf)) if pt_sf < 0 else 0

        if decimals > 0:
            # Scaled point requires a rounded float matching resolution
            return round(float(raw_val), decimals)
        else:
            # Scale factor is 0 or positive -> pure integer
            return int(round(float(raw_val)))

    # CASE C: Bitfields, Enums, or Unscaled Integers (e.g., Enable flags, Status codes)
    elif pt_type in ('int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64', 'enum16', 'enum32', 'bitfield16',
                     'bitfield32'):
        return int(round(float(raw_val)))

    # CASE D: Default Fallback
    else:
        # Default to float if fractional, else int
        f_val = float(raw_val)
        return int(f_val) if f_val.is_integer() else round(f_val, 2)

def write_cvalue_to_point(para_obj: SunSpecModbusClientPoint, value: any) -> bool:
    """
    Write a value (of all kinds) to the pre-defined sunspec parameter, and check whether the writing operation was
    successful by directly compare the reading to value.

    Parameters
    ----------
    para_obj: object of the sunspec parameter to be written
    value: value to be written

    Returns
    -------
    A bool flag for the "write and check" operation
    """

    para_obj.cvalue = value
    para_obj.write()
    logger.info(f'Check returned parameter value: {para_obj.disp()}')
    para_obj.read()
    if para_obj.cvalue != value:
        logger.warning(f'Tried to set cvalue to {value}, but not taken by the inverter.')
        logger.warning('Control probably can not be proceeded.')
        return False
    else:
        return True


def write_numeric_cvalue_to_point(conn_obj: SunSpecModbusClientDeviceTCP,
                                  para_obj: SunSpecModbusClientPoint,
                                  value: float | int,
                                  tol: float = 1e-5,
                                  max_retries: int = 3,
                                  retry_delay: float = 0.1) -> bool:
    """
    Write a numeric value to a pre-defined sunspec parameter, and check whether the performed writing operation was
    successful (i.e. diff <= tol.) by examining the difference.

    Compared to the other function :func:´write_cvalue_to_point´, this one requires numeric values as input and will
    raise a ValueError if the writing operation failed.

    Parameters
    ----------
    para_obj: object of the sunspec parameter that has been written
    value: value that has been written
    tol: tolerance for the precision in validation, default is set to 1e-5.


    Returns
    -------
    A bool flag for the "write and check" operation.
    """

    write_value = prepare_sunspec_value(para_obj, value)
    if not np.isclose(value, write_value):
        logger.info(f'The raw value {value} has been rounded to {write_value} for decimal consistency.')

    lock = getattr(conn_obj, 'modbus_lock', None)
    lock_context = lock if lock is not None else nullcontext()

    try:
        with lock_context:
            para_obj.cvalue = write_value
            # 1. Write the new control value over Modbus
            para_obj.write()

            # 2. Poll for verification with short delay to allow hardware update
            for attempt in range(max_retries):
                time.sleep(retry_delay)  # Yields GIL and gives inverter MCU time to commit registers
                para_obj.read()

                if np.isclose(para_obj.cvalue, write_value, tol):
                    logger.info(
                        f"Success: Param {getattr(para_obj, 'name', 'DO')} "
                        f"updated to {write_value} on attempt {attempt + 1}."
                    )
                    return True, write_value

                # If all retries fail to verify
                logger.error(
                    f"Modbus write failed verification after {max_retries} attempts: "
                    f"Target={write_value}, Retained={para_obj.cvalue}"
                )
                raise ValueError(
                    f"Passing control value {write_value} succeeded on Modbus, but device retained {para_obj.cvalue}"
                )

    except Exception as e:
        logger.error(f"Error during SunSpec write execution: {e}")
        raise e

def enable_control_by_identifier(conn_obj: SunSpecModbusClientDeviceTCP,
                                 model_id: int, parameter: str,
                                 identifiers: tuple = ('Ena', '_Ena', 'ena', '_ena')) -> tuple[str | None, bool]:
    """
    In the sunspec implementation, one client is often required to first enable the control parameter by
    setting 1 to the associated "enabling" parameter, which might interpreted by different strings.

    This function attempts to use possible parameter names to activate the control parameter. If not otherwise
    specified, the default argument of the attribute identifiers will be used to perform the enabling,
    until the server returns a positive response when using one of those naming prefixes.

    Parameters
    ----------
    conn_obj: the sunspec connection object maintained by ied_manager in runtime via data_buffer.fieldbus_conn_obj
    model_id: model_id of the parameter in the sunspec specification
    parameter:  name of the sunspec parameter
    identifiers: a list of naming prefixes for enabling-type parameters, the order indicates priority

    Returns
    -------
    enable_para: name string of the enabler parameter
    is_enabled: a bool flag indicating the enabling status
    """

    is_enabled = False
    enable_para = None
    for enable_id in identifiers:
        try:
            enable_para = f'{parameter}{enable_id}'
            enable_obj = getattr(conn_obj.models[model_id][0], enable_para)
            if enable_obj.cvalue != 1:
                logger.info(f'Target control parameter is not enabled, set {parameter}{enable_id} to 1')
                is_enabled = write_cvalue_to_point(enable_obj, 1)
                break
            else:
                logger.info(f'The enable parameter {enable_para} already has Boolean value 1')
                is_enabled = True
                break
        except Exception as e:
            logger.exception(f'Failed to set 1 to the parameter {parameter}{enable_id}, probably wrong name.')
            logger.exception(e)

    return enable_para, is_enabled

def enable_control_by_fuzzy(conn_obj: SunSpecModbusClientDeviceTCP,
                            model_id: int, parameter: str, ) -> tuple[str|None, bool]:
    """
    In the sunspec implementation, one client is often required to first enable the control parameter by
    setting 1 to the associated "enabling" parameter, which might interpreted by different strings.

    This function attempts to use fuzzy search logic to allocate the correct parameter name of the "enabler"
    parameter and then set its value to 1. The fuzzy search uses the pattern 'parameter_Ena' as default enabler
    address, and determines the parameter with the highest match ratio as the hit.

    Parameters
    ----------
    conn_obj: the sunspec connection object maintained by ied_manager in runtime via data_buffer.fieldbus_conn_obj
    model_id: model_id of the parameter in the sunspec specification
    parameter:  name of the sunspec parameter
    Returns
    -------
    enable_para: name string of the enabler parameter
    is_enabled: a bool flag indicating the enabling status
    """

    is_enabled = False
    model_points = list(conn_obj.models[model_id][0].points)
    matched_points = [(point, SequenceMatcher(None, point, f'{parameter}_Ena').ratio()) for idx, point in
                      enumerate(model_points)]
    if not matched_points:
        enable_para = None
    else:
        enable_para = matched_points[np.argmax([item[1] for item in matched_points])][0]
        enable_obj = getattr(conn_obj.models[model_id][0], enable_para)
        if enable_obj.cvalue != 1:
            logger.info(f'Target control parameter is not enabled, set {enable_para} to 1')
            is_enabled = write_cvalue_to_point(enable_obj, 1)
    return enable_para, is_enabled


def write_cvalue_to_inverter(conn_obj: SunSpecModbusClientDeviceTCP,
                             model_id:int, parameter:str,
                             val:helper.StdDataType.AllTypes,
                             is_force_enable:bool = False) -> bool:
    """
    Perform a write value event by setting the attribute cvalue of a specific sunspec parameter.
    There are two variants, the first directly performs the control on the pre-defined parameter, if the first one
    fails, variant 2 will be called, which set the associated enable parameter on True and then write the value.

    TODO: implement a logic to verify the scale factor of the associated sunspec parameter. Currently the SF is taken
        directly from the sunspec mapping table, which are normally set to 0.01 (-2), e.g. for WMaxLimPct
        to transform between percentage value and the float value. In other use cases this could be different, it is
        better to double check the scale factor before writing any control values.

    NOTE: test whether this method for validating new value works
        On the experimental inverter, control check by reading new values did not throw any error,
        HOWEVER, when WMaxLimPctEna was set to 0, the control limits was taken but not in effect.
        This is really bad but there is no way out other than visually check the actual output power.


    :param conn_obj: the sunspec connection object maintained by ied_manager in runtime via data_buffer.fieldbus_conn_obj
    :param model_id: model_id of the parameter in the sunspec specification
    :param parameter: name of the sunspec parameter
    :param val: value to be written
    :param is_force_enable:
    :return: a bool as status indicator of the writing operation
    """


    def init_options():
        options = []
        if not is_force_enable:
            options.append({
                'option': 'ignore',
                'msg': f'Control variant 1: passing control to inverter by directly setting {parameter} to {val}'
            })

        options.append(
            {
                'option': 'identifier',
                'msg': f'Control variant 2: enable the control parameter by id and then set the value to {val}'
            })

        options.append(
            {
                'option': 'fuzzy',
                'msg': f'Control variant 3: enable the control parameter by fuzzy match and then set the value to {val}'
            })
        return options


    def sunspec_writer(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (SunSpecModbusValueError, struct.error) as fatal_err:
                logger.error(f"Fatal SunSpec value/schema error for '{parameter}' with value {val}: {fatal_err}")
                raise fatal_err
            except AttributeError:
                logger.exception(f"AttributeError: '{parameter}' may not be implemented for the inverter")
            except ValueError:
                logger.exception(f"ValueError: Invalid value {val} of type {type(val)}")
            except KeyError:
                logger.exception(f"KeyError: Possibly incorrect model_id '{model_id}'")
            except TimeoutError:
                logger.exception("TimeoutError: Inverter may be blocking control function")
            except ModbusClientError:
                logger.exception("ModbusClientError: Inverter raised a communication error")
            except OSError:
                logger.exception("ModbusClientError: Inverter raised a communication error")
            except Exception as e:
                logger.exception(f"Unexpected error when writing action to parameter '{parameter}'")
                logger.exception(e)
            return False, None

        return wrapper

    @sunspec_writer
    def _single_value_writer(enable_type:str):
        if enable_type == 'ignore':
            # be careful when using this variant, since some standards require enabling for each writing action
            logger.warning('ENABLE parameter is not available, the control might fail.')
        elif enable_type == 'identifier':
            [enable_para, is_enabled] = enable_control_by_identifier(conn_obj, model_id, parameter)
        elif enable_type == 'fuzzy':
            [enable_para, is_enabled] = enable_control_by_fuzzy(conn_obj, model_id, parameter)
        else:
            logger.warning(f'Unknown type {enable_type} for enabling control parameter, just perform the control')

        logger.info(f'Passing control value {val} to parameter {parameter}')
        obj = getattr(conn_obj.models[model_id][0], parameter)
        is_written, committed_val = write_numeric_cvalue_to_point(conn_obj, obj, val)

        return is_written, committed_val

    logger.info('-------------------------------------------------------------------')

    enable_options = init_options()
    for opt in enable_options:
        is_written, committed_val = _single_value_writer(opt['option'])
        if is_written:
            return True, committed_val
        else:
            logger.warning(opt['msg'])

    logger.warning(
        f"All control attempts failed for '{parameter}' in model {model_id} with value {val}. "
        f"Check inverter or configuration."
    )
    logger.info('-------------------------------------------------------------------\n')
    return False, None

