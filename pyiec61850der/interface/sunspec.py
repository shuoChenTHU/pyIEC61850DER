# -*- coding: utf-8 -*-
"""
Real-time functions for the Sunspec - IEC 61850 interface, incl. a Sunspec client.

Use the open-source lib sunspec2 to establish ModbusTCP connection to a SunSpec
compatible PV inverter.

The first priority at this phase is to get this concept to technically work, optimisation
of code efficiency and communication effort is the next step.

TODO: make sure that the two objects ied_config and ied_server are only there to provide information, not to be modified
"""

import sunspec2.modbus.client as client
from sunspec2.modbus.client import  SunSpecModbusClientDeviceTCP, SunSpecModbusClientPoint
from sunspec2.modbus.modbus import ModbusClientError
import pandas as pd
from pandas import DataFrame
import numpy as np
import copy
from difflib import SequenceMatcher
from functools import wraps
import threading
from contextlib import nullcontext
import time

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

    def find_para_idx() -> tuple[int|None, DataFrame|None]:
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

    row_idx, sunspec_mapping = find_para_idx()
    if row_idx is not None:
        model_id = sunspec_mapping.at[row_idx, 'model_id']
        para = sunspec_mapping.at[row_idx, 'name']
        val_write = data_buffer.get_current_source_value()

        is_written = write_value_to_inverter(data_buffer.fieldbus_conn_obj, model_id, para,
                                                     val_write, is_force_enable)
        return is_written
    else:
        return False



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
    update_mapping_by_scan(ied_manager)

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

        if index is not None:
            logger.debug(f'Successfully located DA {da_mms_addr} by sunspec mapping, enable sunspec data_source')
            df.at[index, 'fieldbus_conn_obj'] = conn_obj  # object saved in the DataFrame will be of the type Series
            df.at[index, 'data_source'] = 'sunspec'
            df.at[index, 'is_monitor'] = True
            df.at[index, 'fieldbus_conn_config'] = conn_config

            # check if the parameter is coming with a scale factor
            if (helper.is_valid_number(df_active_sunspec.at[idx_para, 'factor']) and
                    not np.isnan(df_active_sunspec.at[idx_para, 'factor'])):
                df.at[index, 'scale_factor'] = df_active_sunspec.at[idx_para, 'factor']
            if df_active_sunspec.at[idx_para, 'rw_access'] == 'RW':
                df.at[index, 'is_control'] = True
        else:
            logger.warning(f'Failed to locate DA by addr {da_mms_addr}, please check the vIED lookup table manually.')

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


def update_mapping_by_scan(ied_manager: 'IedManager'):
    """
    This function initializes a sunspec connection to the server via ModbusTCP. Meanwhile it updates the interface
    configuration in the vIED lookup table. All sunspec parameters that deliver measurements or status information
    will be recorded in the vIED lookup table.

    During the vIED server routine, associated DO will be updated with "sunspec" as data source. It is possible to
    validate the sunspec parameters regularly, and remove inactivate parameters or add new sunspec parameters.

    Currently the update and export of sunspec mapping and vIED lookup mapping are performed once per device.

    TODO: could it be more beneficial to update and export only once after the entire loop?

    TODO: when indexing the DA ref, only empty list and list with length 1 are considered, because
        each DA should have an unique mms_addr. But duplicated mms_addr could still occur due to
        errors in the engineering process. Implement a unique address check later.
    """

    ied_config = ied_manager.ied_config
    # TODO: check whether it would be much more efficient to operate directly on the original dataframe
    df_mapping = copy.deepcopy(ied_config.interface.df_sunspec_mapping)
    df_lookup = copy.deepcopy(ied_config.interface.df_lookup)

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
        [is_connected, conn_obj] = connect_sunspec_server(slave_id, ipaddr, port)
        if not is_connected:
            logger.warning(f'No connection to the sunspec host {ipaddr}:{port}, skip to the next sunspec device.')
            continue

        logger.info(f'Trigger sunspec data model scan for device {ipaddr}:{port}.')
        if not scan_sunspec_model(conn_obj):
            logger.warning(f'Sunspec data model scan failed, skip to the next sunspec device.')
            continue

        para_indices = df_mapping.loc[df_mapping['LD'] == key].index.to_list()
        if not para_indices:
            logger.warning(f'Sunspec data model returns an empty list, skip to the next sunspec device.')
            continue

        # perform parameter scan and update the lookup table accordingly
        df_active_sunspec = scan_active_sunspec_parameter(df_mapping, para_indices, conn_obj,
                                                            ied_config.interface.is_keep_none)
        ied_config.interface.active_sunspec_mappings.append(df_active_sunspec)
        df_lookup_updated = update_df_lookup_by_mapping(df_lookup, df_active_sunspec, conn_obj,
                                                        conn_config)
        # export update mapping files
        export_updated_df_mapping(df_active_sunspec, ied_config.interface.path_sunspec_mapping_export, idx_device)

        # assign the conn_obj and configurations to data_buffer instances
        conn_obj.timeout = 5.0  # leave the conn_obj 5s timeout to avoid long stall due to connection loss
        conn_obj.modbus_lock = threading.Lock()
        assign_conn_to_data_buffers(ied_manager.ied_server, df_lookup_updated, df_active_sunspec, conn_obj, conn_config)

        df_lookup = df_lookup_updated
        logger.info(
            f'Initial sunspec reading finished, {len(df_active_sunspec)} parameters are available for the IED server.')
        logger.info('-------------------------------------------------------------------\n')


    if not df_lookup.equals(ied_config.interface.df_lookup):
        ied_manager.ied_server.df_lookup = df_lookup
        ied_manager.ied_server.get_active_do_in_lookup()
        ied_manager.data_sources = list(ied_manager.ied_server.df_lookup['data_source'].unique())
        export_updated_df_lookup(df_lookup, ied_config.interface.is_force_overwrite,
                                ied_config.interface.path_lookup)


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

def connect_sunspec_server(slave_id:int=1,
                           ip_addr:str= '192.168.1.1',
                           port:int=502) -> tuple[bool, SunSpecModbusClientDeviceTCP]:
    """
    It checks the availability of the configured sunspec server. If the server exists and can be connected,
    then move on to an initial reading and update the virtual IED lookup table accordingly.

    Otherwise, return a none object.

    Parameters
    ----------
    slave_id: slave ID of the PV inverter, 1 as default
    ip_addr: IP address of the PV inverter, '192.168.1.1' as default
    port: TCP port of the PV inverter, 502 as default

    Returns
    -------
    is_connected: a bool flag that indicating the current health status of the sunspec connection
    sunspec_conn: the newly established sunspec connection object

    """

    is_connected: bool = False
    sunspec_conn: SunSpecModbusClientDeviceTCP | None = None

    try:
        d = client.SunSpecModbusClientDeviceTCP(slave_id, ip_addr, port)
        d.connect()
        is_connected = True
        sunspec_conn = d
        logger.info(f'Connected to the sunspec server {ip_addr}')
    except ModbusClientError as err:  # most probably ModbusClientError
        logger.exception(f'The configured sunspec server {ip_addr} is not available')
        logger.exception(err)
    except Exception as err:
        logger.exception('unexpected sunspec connection error, using profiles instead of real-time data')
        logger.exception(err)
    return is_connected, sunspec_conn

def reconnect_sunspec_server(sunspec_conn:SunSpecModbusClientDeviceTCP):
    """
    This function can be used to reconnect to the sunspec server using the established TCP device object. The
    main advantage of calling this function is that one would not pass all the device info as arguments.

    Parameters
    ----------
    sunspec_conn: the connection object to the sunspec server of interest

    Returns
    -------
    is_reconnected: a bool flag that indicating the status of the sunspec connection
    """

    is_reconnected = False
    try:
        sunspec_conn.connect()
        is_reconnected = True
        logger.info('The sunspec server is successfully reconnected.')
    except ModbusClientError:
        logger.exception('Sunspec Server reconnection failed, ModbusClientError')
    except Exception as e:
        logger.exception('unexpected sunspec connection error, using profiles instead of real-time data')
        logger.exception(e)
    return is_reconnected

def keep_alive(sunspec_conn: SunSpecModbusClientDeviceTCP) -> bool:
    """
    Checks the active connection to the SunSpec server.
    Only attempts reconnect if the socket is actually closed/None.
    """

    def _cleanup_stale_socket(sunspec_conn):
        """
        Forces the closure of dead socket references in pysunspec2.
        """
        try:
            if hasattr(sunspec_conn, 'close'):
                sunspec_conn.close()

            client = getattr(sunspec_conn, 'client', None)
            if client:
                if hasattr(client, 'close'):
                    client.close()
                # Explicitly clear the socket reference inside client.__dict__
                if hasattr(client, '__dict__') and 'socket' in client.__dict__:
                    client.__dict__['socket'] = None
        except Exception as err:
            logger.debug(f"Ignored error during socket cleanup: {err}")

    if sunspec_conn is None:
        return False

        # 1. If flagged offline by read_value_from_point, treat as dead immediately
    if getattr(sunspec_conn, 'is_offline', False):
        logger.info("SunSpec connection flagged offline. Invalidating stale socket...")
        _cleanup_stale_socket(sunspec_conn)
        return False

    try:
        # Inspect client and socket
        client = getattr(sunspec_conn, 'client', None)
        client_dict = getattr(client, '__dict__', {}) if client else {}
        active_socket = client_dict.get('socket')

        if active_socket is None:
            logger.info("SunSpec socket is None. Connection is down.")
            return False

        # 2. Perform an actual live I/O check (e.g. read Common Model 1 ID or first model addr)
        # Checking if socket object exists is NOT enough when network cable is unplugged.
        if hasattr(sunspec_conn, 'models') and sunspec_conn.models:
            # Pick the first available model instance to test socket responsiveness
            first_model_id = next(iter(sunspec_conn.models))
            model_instance = sunspec_conn.models[first_model_id][0]

            # Attempt a minimal read to verify network pipe is alive
            model_instance.read()

        logger.debug("SunSpec connection verified active via live read test.")
        return True

    except (ModbusClientError, ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError) as e:
        logger.warning(f"SunSpec server socket failed live health check: {e}")
        # Clean up the dead socket so future connect() calls can bind a new socket
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
            if df_lookup_filtered.loc[idx_para, 'scale_factor'] - 1 > 1e-3:
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
        value = read_value_from_point(conn_obj, model_id, para)
        if not value:
            if is_keep_none:
                logger.warning(
                    f'The sunspec parameter {model_id} - {para} returns None, but still keep it in the list.')
            else:
                logger.warning(
                    f'The sunspec parameter {model_id} - {para} returns None, set it to inactive in the sunspec mapping table.')
                continue

        df.at[idx_para, 'is_delivered'] = True

    return df.loc[df['is_delivered'] == True]



"""
=======================================================================
=================   RUNTIME SUNSPEC FUNCTIONS - READ  =================
=======================================================================
"""

def read_value_from_point(conn_obj: SunSpecModbusClientDeviceTCP,
                          model_id:int, parameter:str) -> any:
    """
    Perform a read value event to get cvalue for a specific sunspec parameter.
    """
    lock = getattr(conn_obj, 'modbus_lock', None)

    try:
        # read the instance to make sure that we are query the latest data
        model_instance = conn_obj.models[model_id][0]
        if lock:
            with lock:  # Strictly serialize network access
                model_instance.read()
        else:
            model_instance.read()

        para_val = getattr(model_instance, parameter).cvalue
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
    return read_value_from_point(conn_obj, model_id, parameter)


"""
=======================================================================
=================   RUNTIME SUNSPEC FUNCTIONS - WRITE =================
=======================================================================
"""


def write_value_to_point(para_obj: SunSpecModbusClientPoint, value: any) -> bool:
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


def write_numeric_value_to_point(conn_obj: SunSpecModbusClientDeviceTCP,
                                 para_obj: SunSpecModbusClientPoint,
                                 value: float | int,
                                 tol: float = 1e-5,
                                 max_retries: int = 3,
                                 retry_delay: float = 0.1) -> bool:
    """
    Write a numeric value to a pre-defined sunspec parameter, and check whether the performed writing operation was
    successful (i.e. diff <= tol.) by examining the difference.

    Compared to the other function :func:´write_value_to_point´, this one requires numeric values as input and will
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

    if hasattr(value, 'item'):
        native_value = value.item()
    else:
        native_value = float(value) if isinstance(value, (float, int)) else value



    lock = getattr(conn_obj, 'modbus_lock', None)
    lock_context = lock if lock is not None else nullcontext()

    try:
        with lock_context:
            para_obj.cvalue = native_value
            # 1. Write the new control value over Modbus
            para_obj.write()

            # 2. Poll for verification with short delay to allow hardware update
            for attempt in range(max_retries):
                time.sleep(retry_delay)  # Yields GIL and gives inverter MCU time to commit registers
                para_obj.read()

                if abs(para_obj.cvalue - native_value) < tol:
                    logger.info(
                        f"Success: Param {getattr(para_obj, 'name', 'DO')} "
                        f"updated to {native_value} on attempt {attempt + 1}."
                    )
                    return True

                # If all retries fail to verify
                logger.error(
                    f"Modbus write failed verification after {max_retries} attempts: "
                    f"Target={native_value}, Retained={para_obj.cvalue}"
                )
                raise ValueError(
                    f"Passing control value {native_value} succeeded on Modbus, but device retained {para_obj.cvalue}"
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
                is_enabled = write_value_to_point(enable_obj, 1)
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
            is_enabled = write_value_to_point(enable_obj, 1)
    return enable_para, is_enabled


def write_value_to_inverter(conn_obj: SunSpecModbusClientDeviceTCP,
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
            return None

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
        is_written = write_numeric_value_to_point(conn_obj, obj, val)

        return is_written

    logger.info('-------------------------------------------------------------------')

    enable_options = init_options()
    for opt in enable_options:
        if _single_value_writer(opt['option']):
            return True
        else:
            logger.warning(opt['msg'])

    logger.warning(
        f"All control attempts failed for '{parameter}' in model {model_id} with value {val}. "
        f"Check inverter or configuration."
    )
    logger.info('-------------------------------------------------------------------\n')
    return False


def find_index_in_df(df: DataFrame, col_name: str, value: any) -> int | None:
    """
    This method attempts to find the index of an IEC 61850 DO in a pre-defined mapping table (should be a
    DataFrame object). The mapping table is supposed to be added as an attribution of the parent class somewhere
    in the runtime operation.

    Parameters
    ----------
    df: pandas DataFrame containing the mapping table
    col_name: target column name for the index search
    value: target value for the index search

    Returns
    -------
    idx_mapping[0], mms_address as a tuple, or None if index not found

    """

    idx = df.loc[df[col_name] == value].index.to_list()

    if not idx:
        logger.warning(f'Something went wrong, can not locate the mapping index with value {value}')
        return None
    else:
        if len(idx) > 1:
            logger.warning(f'Found duplicated entries in the column {col_name}, take the first appearance')
        return idx[0]



