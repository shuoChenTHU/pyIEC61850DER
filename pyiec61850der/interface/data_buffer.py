# -*- coding: utf-8 -*-
"""
Definition of the DataBuffer class and its attributes, essential for the runtime functions.

"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Optional, Type, TypedDict
import uuid
import json
import os
from datetime import datetime
from pandas import DataFrame
import random
import queue
import threading

from settings.helper import KwargsHandler
import settings.helper as helper
from interface.iec61850_do import IEC61850DO
from interface.time_series import TimeSeries, Database, Record
from settings.helper import rotating_logger, is_valid_number


import interface.randomisor as interface_random
import interface.number as interface_number
import interface.calculator as interface_calculator
import interface.local as interface_local
import interface.influxdb as interface_influxdb
import interface.sunspec as interface_sunspec


# type hints
from typing import Optional, Type, TypedDict
FloatTypes = helper.StdDataType.FloatTypes
IntTypes = helper.StdDataType.IntTypes
BoolTypes = helper.StdDataType.BoolTypes



logger = logging.getLogger(f"main_logger.{__name__}")

@dataclass()
class DataBuffer(KwargsHandler):
    """
    TODO: refine the documentation here after the refactoring is finished.
    An inner-class containing properties that specify the data interfaces between the IED server and other data
    service providers, such as local data files, timeseries database, metadata database, SCADA and the simulation
    environment.

    This data class is very important! It is the interface between the runtime environment and the simulated IEC 61850
    services. It connects the IEC 61850 application to the data pool, local DER units and controller interfaces. It passes
    the measurements collected during the simulation to the IED server and react to the control commands performed by the
    IED clients.

    After an DataBuffer instance has been initialised (most likely by the service module communication._swig_obj),
    it is barely empty, it contains only the default setup except that some specific configurations are passed by kwargs.
    While the configuration of data points are stored in the CSV lookup table. The user specified configuration  will be
    transferred to the attributes of DataBuffer instances by the function communication._swig_obj.read_lookup_csv(
    columns).

    So the attributes here should contain required information for:
        - detailed IEC 61850 description (MMS address, parent DO)
        - current values of the parameter, both on the server and client sides
        - place_holder for profiles, if load/gen data_active or prediction is available,
        - time series database connection (for profiles), i.e. the data entries in a database and database handlers
        - meta connection (for registration), i.e. the data entries in a database and database handlers


    NOTE: some thoughts here
        - lowest level is DO DataBuffer
        - generate data_buffers only for DO or also for DA?
        - write d, q, t, units as attributes?
        - Use IEC server shadow?
        - or initialize for each DataBuffer a sub data buffer for the DAs?
        - or should we handle the DO by cdc type?

    IEC 61850 data quality flags:
        - QUALITY_VALIDITY_GOOD   0
        - QUALITY_VALIDITY_INVALID   2
        - QUALITY_VALIDITY_RESERVED   1
        - QUALITY_VALIDITY_QUESTIONABLE   3
        - ..
    TODO: some attributes could be configured by IEC 61850 parameters, double-check and implement


    TODO: add description of data_source:
        - disabled
        - random
        - local
        - influxdb
        - processed
        - DER
        - ... ...
    NOTE: here we use value_external instead of value_source to avoid confusion

    FIXME: because the attrs are iteratively updated while reading the lookup CSV as a dataframe, all None values are
        presented as np.nan, which has the wrong data type. -> Fix it!
    """

    # the attr control_queue is SHARED across ALL instances of DataBuffer automatically.
    control_queue = queue.Queue()

    def __init__(self, **kwargs):
        # 1. Initialize a Reentrant Lock per buffer instance
        self._record_lock = threading.RLock()

        # meta data
        self.index: int | None = None
        self.data_source: str = 'disabled'
        self.id: str | None = None  # currently use the IEC 61850 MMS address as id
        self.uuid: uuid.UUID = uuid.uuid4()  # abuse the term uuid and guid, uuid is the UUID object, guid is str
        self.guid: str = self.uuid.__str__()
        self.container_guid: str | None = None  # TODO: check the var name, is container_guid correct?
        self.container_name: str | None = None  # TODO: check the var name, is container_name correct?

        # time manger (all DataBuffer instances will later refer to the same time manager)
        self.time_manager = None

        # IEC 61850
        self.iec61850_do = IEC61850DO()

        # measurement and control values
        # NOTE: this value name could be generalised for all types of communication protocols, not just IEC 61850
        self.value_external: float | int | str| None = None
        self._value_iec61850: float | int | None = None  # make value_iec61850 a property
        self.value_quality: int = 2  # see quality flags in docstring, use invalid state unless valid value available
        self.is_monitor: bool = False
        self.is_control: bool = False
        self.is_idle: bool = False  # data_buffer is considered idle, if neither monitoring nor controlling

        # NOTE: limits may contain function handlers and other info, numeric_limits are two numerical values
        self.limits = dict({'lower': -np.inf,
                            'upper': np.inf})  # now make it a mutable list instead of tuple for runtime processing
        self.numeric_limits: tuple = (-np.inf, np.inf)
        self.rated_value: float | None = None  # rating value on the nameplate, such as rated power
        self.unit_factor: float = 1.0  # scaling by unit often occurs, we distinguish it with other scaling methods
        self.scaling_factor: float = 1.0
        self.unit: str = 'unknown'

        # data_active
        self.local_timeseries: TimeSeries = TimeSeries()  # time series data provided in local data files
        self.db_timeseries: TimeSeries = TimeSeries()  # time series data provided by a remote database
        self.time_series: TimeSeries | None = None
        self.time_col: str | None = None  # column name for datetime when querying data
        self.data_col: str | None = None  # column name for the target data column when querying data

        # records
        columns = ['t', 't_unix', 'q', 'value_iec61850', 'value_external', 'integrity_update_count', 'control_count']
        self.records: Record = Record(columns)
        self.records.create_time = 'create_time_' + datetime.today().strftime('%Y%m%d%H%M')

        # database interface
        self.influxdb = Database()
        self.influxdb.parent = self.iec61850_do.name
        self.meta = Database()  # NOTE: placeholder for a metadata database, which is relevant for the registration
        self.is_iec61850_tag: bool = True  # True by default, so that the influxdb records contains IEC 61850 tags
        self.influx_level = 0  # indicator for influx query/upload operation

        # communication connection object
        self.fieldbus_conn_config = None  # intermediate storage for the config JSON string
        self.fieldbus_conn_obj = None  # local communication object, e.g. the client API for SunSPEC interface
        self.fieldbus_conn_mapping = None  # local communication mapping table, e.g. IEC 61850 <---> SunSPEC
        self.id_map = None  # local map for the mapping between data_buffer index and IEC 61850 MMS attr
        self.apply_kwargs(False, **kwargs)

        # track initialization state. Controls are muted until True.
        self.is_initialized = False

    def __str__(self):
        """
        Use the DataBuffer id to represent the DataBuffer object description.
        """
        return f'{self.id}'

    def __call__(self):
        """
        Use the DataBuffer id to represent the DataBuffer object when it is called.
        """
        return self.id

    @property
    def value_iec61850(self):
        return self._value_iec61850

    @value_iec61850.setter
    def value_iec61850(self, new_val):
        old_val = self._value_iec61850
        self._value_iec61850 = new_val

        if not self.is_control or not self.is_initialized:
            return

        # Explicitly check for data differences
        if self.check_value_change(self.value_external, new_val):
            logger.info('************************************')
            logger.info('***  control command received ******')
            logger.info('************************************')
            logger.info(
                f'The value of control parameter {self.id} has been changed: {self.value_external,} -> {new_val}')
            self.value_external = new_val
            self.control_queue.put(self)

    @property
    def time_series(self):
        """
        A getter to access the current time series object depending on data_source type.
        """

        mapping = {
            'local': getattr(self, 'local_timeseries', None),
            'influxdb': getattr(self, 'db_timeseries', None)
        }

        source = str(self.data_source).lower()
        return mapping.get(source)

    @time_series.setter
    def time_series(self, value):
        """
        This setter allows direct assignment to self.time_series.
        Note: Calling this setter will overwrite the reference in the active source! Be careful when assigning
        a completely new instance of TimeSeries.
        """

        if self.data_source == 'local':
            self.local_timeseries = value
        elif self.data_source == 'influxdb':
            self.db_timeseries = value

    @property
    def timeseries_offset(self):
        # This just asks the current time_series for its offset
        return self.time_series.offset if self.time_series else 0

    @timeseries_offset.setter
    def timeseries_offset(self, value):
        """
        This setter method was intended to compute the time difference between the simulation time and local time of
        the data (in case they are not UTC time). It reaches inside the instance of TimeSeries and changes the 'offset'
        attribute.

        However, since we use unix time anyway, the attr self.time_series.offset is not really being used right now.
        """

        if self.time_series:
            self.time_series.offset = value
        elif self.data_source == 'disabled':
            pass
        else:
            logger.debug("Cannot set offset: No active TimeSeries found.")

    def update_attribute_kwargs(self, **kwargs):
        """
        This method takes a dictionary **kwargs as input parameter, parse the parameters stored in the
        dict and update the attributes of the DataBuffer instances accordingly. Of course, one can also
        pass single kwargs without adding the **.
        """

        if kwargs is not None:
            for key, value in kwargs.items():
                if key not in dir(self):
                    setattr(self, key, value)
                    logger.warning(f'Unknown attribute {key} has been added and set, this may cause inconsistency')
                else:
                    setattr(self, key, value)

    def update_child_attr_kwargs(self, child: str, **kwargs):
        """
        This method allows the user to configure the influxdb handler individually for each single data buffer instance.
        The method only overwrites existing attributes, unknown keys will be ignored.

        :param child: name of the child value
        :param kwargs: key-values pairs for update
        :return:
        """

        if child not in dir(self):
            pass
        else:
            if kwargs is not None:
                for key, val in kwargs.items():
                    obj = getattr(self, child)
                    if key in obj.keys():
                        setattr(self, f'{child}.{key}', val)
                    else:
                        logger.warning(f'The given key {child}.{key} does not exist, it will be ignored.')

    def update_records(self, new_data: DataFrame):
        """
        This method is called during each iteration of the IEC 61850 server, it writes the last valid value of active
        DO into the data_buffer.records attribute.

        Parameters
        ----------
        new_data: new data since the last update in the DataFrame format
        """


        try:
            with self._record_lock:
                self.records.data_archive = pd.concat([self.records.data_archive, new_data], ignore_index=True)
                self.records.data_for_upload = pd.concat([self.records.data_for_upload, new_data], ignore_index=True)
                self.records.integrity_update_count += 1
        except Exception as exc:
            logger.exception(exc)


    def get_id_map(self, required_cols: list, attr: str = 'fieldbus_conn_mapping'):
        """
        Note: this method is actually explicitly for sunspec data mapping, but it could also work for other interfaces.
        Important is that a sort of mapping table is stored as an attr of the data_buffer instance.
        """

        df_mapping = getattr(self, attr, None)
        if df_mapping is None:
            logger.warning(f'The data_buffer does not have attr {attr}, please check it manually.')
        elif not all(col in df_mapping.columns.tolist() for col in required_cols):
            logger.warning(f'Not all required columns are contained in the mapping table. Check it manually')
        else:
            self.id_map = df_mapping.groupby('mms_addr').groups


    def export_records_locally(self) -> bool:
        """
        This method exports the Attribute data_buffer.records to a local csv file. The attribute is a pandas DataFrame,
        and the file name is its DO.id, the slash "/" is replaced by an underscore "_". It only takes data_buffer
        instances with is_monitor == True into account.

        NOTE: this method exports all historical values in the data_archive in an incremental manner.
        Currently, there is no version control and file size management implemented.

        flag:
            - 0: not under monitoring, no export required
            - 1: export success
            - 99: export failed
        """

        if not self.is_monitor:
            return 0

            # Initialize tracking index if not already set
        if not hasattr(self, "_last_exported_index"):
            self._last_exported_index = 0

        try:
            # Create continuous target directory
            export_dir = f"{self.records.export_dir}/{self.records.create_time}"
            os.makedirs(export_dir, exist_ok=True)

            filepath = f"{export_dir}/{self.iec61850_do.id.replace('/', '_')}.csv"

            # 1. Take a quick thread-safe snapshot slice of unexported data
            # Lock ONLY while creating the memory slice snapshot
            with self._record_lock:
                total_rows = len(self.records.data_archive)
                if total_rows <= self._last_exported_index:
                    return 0
                # Quick RAM slice under lock protection
                new_data = self.records.data_archive.iloc[self._last_exported_index:total_rows].copy(deep=True)

            # 2. Append incremental records to disk
            # File I/O runs completely UNLOCKED (MainThread is free to update other attributes)
            os.makedirs(export_dir, exist_ok=True)
            file_exists = os.path.isfile(filepath)
            new_data.to_csv(filepath, mode='a', header=not file_exists, index=True)

            # 3. Advance pointer only upon successful write
            self._last_exported_index = total_rows
            logger.debug(f"Appended {len(new_data)} records to {filepath}")
            return 1

        except PermissionError as e:
            logger.exception("Cannot write export CSV file; file may be open by another process!")
            logger.exception(e)
            return 99
        except Exception as exc:
            logger.exception(f"Error occurred during CSV export for {self.iec61850_do.id}: {exc}")
            logger.exception(exc)
            return 99

    def get_current_source_value(self):
        """
        This function passes actual values of those parameters that have been controlled by IEC 61850 clients to the corresponding data_buffer instances.
        """

        try:
            v = self.value_external / (self.unit_factor * self.scaling_factor)
            if not is_valid_number(v):
                logger.warning(
                    'Got invalid data after internal processing, please double check the data type of new value, '
                    'scaling_factor, and unit_factor')
                logger.warning(
                    'Set data_buffer.data_source to valWrite directly instead, without multiplicating scaling_factor and unit_factor, this could cause error')
                v = self.value_external
        except Exception as e:
            v = self.value_external
            logger.exception('Wrong data type. Check the data type of new value, scaling_factor and unit_factor')
            logger.exception(e)

        return v

    def update_external_value(self, val: np.number, is_init:bool=False):
        """
        This function helps to calculate the actual value of a parameter that is frequently read from a data source. It takes the
        scaling_factor and unit_factor of the pre-configuration into account, based on that it generate the scaled value and write it to
        the data_buffer instance -> data_buffer.value_external.

        If there is anything wrong with the factors, it just ignores the scale factors and write the fresh fetched value
        directly to the
        data_buffer, which may cause unplausible values in the IED server. In such a case, the unit and scale of a DA might be messed up,
        but the server can still run. Just pay attention to the unscaled values!

        Besides, if the limits is set to some wrong data types, this function will reactivate the default value, which equals to no limits.
        """

        lb, ub = self.numeric_limits

        if pd.isna(val):
            if is_init:
                self.value_external = 0.0
                self.value_quality = 2  # QUALITY_VALIDITY_INVALID
                logger.warning(f'Write invalid value 0.0 to DO {self.iec61850_do.id}.')
                logger.warning('Because IEC 61850 requires numeric value, can not pass None. This value could be '
                               'misleading, attention.')
            elif self.value_quality == 2:
                pass
            else:
                # Preserve the old value for self.value_external, only change quality flag
                self.value_quality = 3  # QUALITY_VALIDITY_QUESTIONABLE
                logger.debug('Got nan value from the external source, no action.')
        else:
            try:
                val_scaled = val * self.unit_factor * self.scaling_factor

                if not is_valid_number(val_scaled):
                    logger.warning(f'{val_scaled} is not a number! Double check the data type, scaling_factor and unit_factor')
                    self.value_quality = 3  # QUALITY_VALIDITY_QUESTIONABLE
                    raise ValueError
                else:
                    self.value_external = max(min(val_scaled, ub), lb)
                    self.value_quality = 0 # QUALITY_VALIDITY_GOOD
            except Exception as e:
                self.value_quality = 3  # QUALITY_VALIDITY_QUESTIONABLE
                logger.exception(e)

    def init_single_value(self):
        """
        This function iterates over the list object ied_server.data_buffers and generate an initial value
        for each of the parameters in the list as configured. (each parameter can have a different data source)

        When starting a simulation, this fucntion only has to be called once per IEC 61850 Data Attribute during the initialization.

        For parameters that is using a local data_active, data_buffer.local_timeseries must have been set before the initialization.
        Calling this function triggers the methode interface_local/influxdb.get_dataframe_from_influxdb given current
        timestamp, then it takes the first value as the init value.

        Usage:
            processing.routine.init_single_value(ied_config, ied_server, data_buffer, data_source, ctime_local_str, verbose)

        Input:
            - ied_config: instance of the global configuration, containing interface config and mapping tables
            - ied_server: instance of the running ied_server, containing IEC 61850 and communication entries
            - data_buffer: one instance of the class DataBuffer
            - ctime_local_str: current timestamp in string format, e.g. '%Y-%m-%d %H:%M:%S'
            - value: only applicable for the data_source "random", a user defined random value

        Output:
            The function has no return value, the instance data_buffer will be updated dynamically.

        """

        val_new = None
        if self.data_source == 'disabled':
            logger.info(f'No data source configured for the DA {self.id}, skip it')
        elif self.data_source == 'number':
            # if 'value' in data_buffer.fieldbus_conn_config.keys():
            #     val = data_buffer.fieldbus_conn_config['value']
            if self.value_external is not None:
                val_new = self.value_external
            elif 'value' in self.fieldbus_conn_config.keys():
                val_new = self.fieldbus_conn_config['value']
        elif self.data_source == 'random':
            if self.value_external is not None:
                val_new = self.value_external
            else:
                val_new = interface_random.get_cvalue(random.randint(-5000, 5000) / 10000)
        elif self.data_source == 'local':
            try:
                val_new = interface_local.get_cvalue(self)
            except Exception as e:
                logger.exception(
                    f'Can not find valid data for the parameter {self.id} in local data data_active')
                logger.exception(e)
        elif self.data_source == 'influxdb':
            try:
                val_new = interface_influxdb.get_cvalue(self)
            except Exception as e:
                logger.exception(f'Can not find valid data for the parameter {self.id} in influxdb')
                logger.exception(e)
        elif self.data_source == 'sunspec':
            # Note: the value returned by this func can be None
            val_new = interface_sunspec.read_single_value(self)
        elif self.data_source == 'calculation':
            logger.info(
                f'Data source for the DA {self.id} configured to be calculated, no initialisation required.')
        else:
            logger.warning(f'Unknown data source: {self.data_source}, please check the config file.')

        self.update_external_value(val_new, True)

    def update_buffer_single_val(self):
        """
        This function iterates over the list object ied_server.data_buffers and update the current values
        for each of the parameters in the list according to the pre-configured data source.
        (each parameter can have a different data source)

        For parameters that is using a local data_active, data_buffer.data_active must have been set before the initialization.
        (which is done by calling the other function init_single_value)

        For parameters that is using a influxdb data_active, it requires the attributes unit_factor, scaling_factor and limits
        to be set during the server or interface initialization.

        Usage:
            processing.routine.update_buffer_single_val(ied_config, ied_server, data_buffer, ctime_local_str)

        Input:
            - ied_config: instance of the global configuration, containing interface config and mapping tables
            - ied_server: instance of the running ied_server, containing IEC 61850 and communication entries
            - data_buffer: one instance of the class DataBuffer
            - ctime_local_str: current timestamp in string format, e.g. '%Y-%m-%d %H:%M:%S'

        Output:
            The function has no return value, the instance data_buffer will be updated dynamically.
        """

        val_new = None

        if not self.value_external:
            logger.debug(f'No initial value configured for the DO {self.id}')
        else:
            ext_val = self.value_external
            if self.data_source == 'disabled':
                logger.warning(f'No data source configured for the DA {self.id}, skip it')
            elif self.data_source == 'number':
                val_new = interface_number.get_cvalue(ext_val)
            elif self.data_source == 'random':
                val_new = interface_random.get_cvalue(ext_val)
            elif self.data_source == 'local':
                if self.local_timeseries.data_active.empty:
                    logger.warning(f'No time series available for the DA {self.id}')
                    logger.info(f'Try to load the time-series data from local CSV.')
                    interface_local.refresh_daily_time_series(self)
                val_new = interface_local.get_cvalue(self)
            elif self.data_source == 'influxdb':
                if self.db_timeseries.data_active.empty:
                    logger.warning(f'No time series available for the DA {self.id}')
                    logger.info(f'Try to load the time-series data from influxdb')
                    interface_influxdb.refresh_daily_time_series(self)
                val_new = interface_influxdb.get_cvalue(self)
            elif self.data_source == 'sunspec':
                val_new = interface_sunspec.get_cvalue(self)
            elif self.data_source == 'calculator':
                val_new = interface_calculator.get_cvalue(self)
            else:
                logger.error(f'Unknown data source: {self.data_source}, please check the config file.')

        self.update_external_value(val_new)

    def create_single_record(self):
        """
        Create a single dataframe record for the current time step in the simulation.
        Time info is taken from time_manager.

        :return:
        """

        with self._record_lock:
            archive_keys = list(self.records.data_archive.keys())
        df_new = pd.DataFrame(columns=archive_keys)
        df_new.at[0, 't'] = self.time_manager.ctime_utc_str
        df_new.at[0, 't_unix'] = self.time_manager.ctime_unix
        df_new.at[0, 'value_external'] = self.value_external
        df_new.at[0, 'value_iec61850'] = self.value_iec61850
        df_new.at[0, 'integrity_update_count'] = self.records.integrity_update_count
        df_new.at[0, 'control_count'] = self.records.control_count
        return df_new

    ##################################################################################################################
    #################################     FUNCTIONS FOR RUNTIME PROCESSING   ########################################
    ##################################################################################################################

    @staticmethod
    def check_nan_value(external_val: float, iec61850_val: float) -> tuple[int, dict]:
        """
        Check whether any of the source value or current IEC 61850 value of the server delivers nan. Return the integer
        checker as a bitmap flag and the dict of message map for logger.

        Parameters
        ----------
        external_val: newly acquired value from the data source
        iec61850_val: currently valid value in the IEC 61850 server

        Returns
        -------
        flag: an integer value indicating nan status map
        msg_map: corresponding message for the logger
        """

        msg_map = {0: '',
                   3: 'Both source and IEC 61850 are None, can not proceed',
                   2: 'The IEC 61850 server has received a None value, considered as no control',
                   1: 'The source value is nan, assign a 0 to it for computation. This might cause inconsistency!',
                   }

        flag: int = 0
        if pd.isna(external_val):
            flag += 1
            # external_val = 0  # TODO: check if removing the 0 assignment would have any side effect
        if pd.isna(iec61850_val):
            flag += 2

        return flag, msg_map

    @staticmethod
    def check_float_change(source_val: FloatTypes, iec61850_val: FloatTypes) -> bool:
        """
        Detect value update of the type float or other numpy float types triggered by external control.

        Parameters
        ----------
        source_val: newly acquired value from the data source
        iec61850_val: currently valid value in the IEC 61850 server

        Returns
        -------
        is_updated: boolean indicator, True if a value update could be detected
        """

        is_updated = False
        source_val_round = helper.round_up_val(source_val, 4)
        iec61850_val_round = helper.round_up_val(iec61850_val, 4)

        if not np.isnan(source_val_round * iec61850_val_round):
            if abs(iec61850_val - source_val) > 1e-6:
                # logger.info(f'Detected change in the control value; valSource: {valSource}, valIEC61850 {valIEC61850}')
                is_updated = True
        else:
            logger.warning('Either the source value or IEC 61850 is not a numeric value, can not compare')

        return is_updated

    @staticmethod
    def check_int_change(source_val: IntTypes, iec61850_val: IntTypes) -> bool:
        """
        Detect value update of the type int or other numpy int types triggered by external control.

        Parameters
        ----------
        source_val: newly acquired value from the data source
        iec61850_val: currently valid value in the IEC 61850 server

        Returns
        -------
        is_updated: boolean indicator, True if a value update could be detected
        """

        is_updated = False
        if helper.is_valid_number(source_val) * helper.is_valid_number(iec61850_val):
            logger.warning('Either the source value or IEC 61850 is not a numeric value, can not compare')
        elif int(source_val) != int(iec61850_val):
            is_updated = True

        return is_updated

    def check_value_change(self, source_val: any, iec61850_val: any) -> bool:
        """
        By simply comparing the current IEC 61850 value of a parameter / data attribute to the value last recorded as
        source value, this method checks whether a value update in the IEC 61850 server could be detected. It works only
        if the value change acknowledgement is not required immediately. For fast response control such as inverter
        power setpoint, it is recommended to use a

        TODO: implement a fast response value change detector for the DER.

        The change in the parameter value is most likely triggered by an external control (e.g. from an IEC 61850
        client), or internal calculation logics.

        Once a value change is detected, the corresponding DataBuffer instance need to acknowledge a write or control
        action and respond to it accordingly.

        Note: there is a bug in the libIEC61850 server, sometimes iec61850_val returns a 0 as value when it is  supposed
        to be a None or nan. Currently the following check is removed. Need to check if is necessary to take it back.
        if iec61850_val == 0:
            pass

        TODO: find out why would the IED server deliver a 0 in that case; Use other methods to handle 0 values in server
         for None, we can not just write 0 everywhere.
        """

        is_updated = False
        flag, msg_map = self.check_nan_value(source_val, iec61850_val)

        if flag >= 1:
            logger.warning(msg_map.get(flag, 'Unknown message.'))
        elif all(isinstance(v, IntTypes) for v in (source_val, iec61850_val,)):
            is_updated = self.check_int_change(source_val, iec61850_val)
        elif all(isinstance(v, FloatTypes) for v in (source_val, iec61850_val,)):
            is_updated = self.check_float_change(source_val, iec61850_val)
        else:
            # TODO: add other handlers for boolean, string, and others
            # TODO: add an operation to overwrite iec61850 value by the source value if source is numeric
            logger.warning('Either source or IEC 61850 value is non-numeric, can not compare')
        return is_updated