# -*- coding: utf-8 -*-
"""
Definition of two runtime-relevant classes TimeManager and IedManager
"""

import logging
import random
import os
import numpy as np
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import time
import pytz
import pandas as pd
import math
from concurrent.futures import ThreadPoolExecutor

from communication.pyiec61850_server import IedServer, IEC61850ServerMMS
from settings.config import IedConfig
import settings.helper as helper
from settings.helper import rotating_logger
from interface.influxdb import Influxdb
import interface.sunspec as interface_sunspec

from model import IEC61850DataModelGenerator
from communication import pyiec61850_server

logger = rotating_logger(__name__)

class TimeManager(object):
    def __init__(self):
        """
        Initialise an object for global time management. One should have one and only one time_manager object per
        active runtime session.

        When creating instances of time-sensitive classes (e.g. ied_server, data_buffer, ied_manager etc.),
        each one of them should possess an attribute time_manager, which refers to the global time_manager instance.

        FIXME: here things are a little bit nasty. Many value are duplicated from those of the class
         IedConfig.container and IedConfig.ied, due to the usage of a YAML config file. The naming convention is not
         adequate either, as 't' or 'time' are in the var name to indicate time-relevant value.
         The current approach is to copy all time-relevant value from IedConfig, and only use them within TimeManager
         for runtime application. IedConfig will only be used to pass the configuration.

        FIXME: the time string has been used for various purposes, thus they are quite many variants of them appearing.
         Find out which string format is still in use and wrap them up as a method.

        FIXME: there might be a little inconsistency w.r.t the usage of utc and local time. Currently, if the data
         are loaded from a remote database or local csv file, local time must be used. See more in TimeSeries()

        TODO: change static parameters to capital var name
        """

        # value from the class Container
        self.time_start_trigger: str | None = None  # a string of the format YYYY-MM-DD hh:mm:ss
        self.timezone: str = 'Europe/Berlin'  # use 'UTC' as timezone for UTC+0 time
        self.time_mode: str = 'simulation'  # simulation or absolute
        self.time_start_str: str = '2016-07-01 12:00:00'
        self.time_end_str: str = '2016-07-31 23:59:59'
        self.time_str_format: str = '%Y-%m-%d %H:%M:%S'   # TODO:  '%Y-%m-%dT%H:%M:%S.%f' was input for get_ctime_bundles()
        self.time_start_unix: float = 0.0
        self.time_end_unix: float = 0.0
        self.time_accelerator_factor: float = 1.0

        # core time management attr
        self.ctime_unix: float = 0.0
        self.ctime_local_str: str = ''
        self.ctime_utc_str: str = ''
        self.ctime: datetime | None = None
        self.ctime_utc: datetime | None = None
        self.ctime_bundle: tuple[float, str, str, datetime, datetime] | None = None
        self.time_sync_count: int = 0

        # value from the class IED
        self.t_interval_data_update: int = 60  # data update t_interval_data_update in [seconds]
        self.N_CTRL_WD_CYCLES: int = 10
        self.t_monitor_reserve: float = 0.5
        self.t_interval_archive: int = 900
        self.t_interval_data_upload: int = 3600
        self.t_interval_routine: int = 900
        self.t_interval_rt: float = 900.0  # a buffer value due to time mismatch caused by runtime processing
        self.ctime_unix_ied: float = 0.0
        self.ctime_str_round_minute: str | None = None  # round-up time str with full-minute, needed for data query

        self.offset = 0.0

        # some timer for debugging purpose of multithreading
        self.t_dbf_worker = 0.0
        self.t_ctrl_wd_worker = 0.0

        # timer for refreshing service / conn_obj
        self.SUNSPEC_CONN_OBJ_TIMER = 60 * 60 * 2  # restart sunspec connections every 2 hours
        self.INFLUXDB_TIMER = 60 * 60 * 4  # restart influxdb every 4 hours
        self.ROUTINE_MAX_T = 60 * 60 * 24  # one day is considered a routine cycle
        self.SYNC_MAX_T = 60 * 5  # sync time every 5 minutes
        self.DEADLOCK_MAX_T = 60 * 10  # max deadlock time of the thread daemon monitor
        self.TIME_DECIMAL = 5  # precision of time measurements
        self.DEADLOCK_MAX_COUNT = 10  # max number of deadlock iterations to force a routine restart

        # time setting for ied routine restarter
        self.ROUTINE_RESTART_INTERVAL = 60
        self.ROUTINE_RESTART_HOUR = 6  # restart the service at this time [UTC]
        self.ROUTINE_RESTART_MINUTE = 0  # restart the service at this time [UTC]

    def get_ctime_bundles(self, ctime_unix: float | None) -> tuple[float, str, str, datetime, datetime]:

        """
        The function based on the input of a datetime object of timezone UTC, perform a handling of local and UTC
        time conversion, generate time string and unix fload, then returns the tuple composed of all three time objects.
        [Note: if no utc time is given, datetime.now(timezone.utc) will be assumed to be the ctime.


        Alternatively, it is possible to read local time directly using datetime.now(), but we can not always ensure
        that the local machine has a correct local_tz setting, for this reason we always get utc time and set
        local_tz as a default object.

        The parameter self.offset allows you to add some time shift to the local time, it should only be used if a
        time delay is known or has been set in the simulation. Time shift caused by time zones should be handled with
        the self.timezone designator of the parent class, not with offset.

        Clarification of the timezones:
        - UTC: Coordinated Universal Time, which is also the Greenwich Mean Time
        - local time: e.g. CET should handle the time switch between CETS and CETW

        Clarification of the time formats:
        - Unix: the UNIX time as a float number
        - String: the time string in a specific format [e.g., default here: YYYY-mm-ddTHH:MM:SS.XXXX]
        - datetime: the original datetime type object

        ----------

        Parameters
        ----------
        ctime_unix
        dt_local: a predefined utc datetime object passed by external functions

        Returns
        -------
        ctime: a tuple of the current timestamp in all possible format (unix float, String, datetime)
        """


        local_tz: str = self.timezone
        if not ctime_unix:
            logger.warning(f'No unix time is provided, assume current UTC time.')
            dt_local: datetime = datetime.now(timezone.utc) + timedelta(seconds=self.offset)
        else:
            dt_local = datetime.fromtimestamp(self.ctime_unix, tz=ZoneInfo(self.timezone))

        dt_utc = dt_local.astimezone(timezone.utc)

        ctime_local_str: str = datetime.strftime(dt_local, self.time_str_format)
        ctime_utc_str: str = datetime.strftime(dt_utc, self.time_str_format)
        ctime_bundle = (ctime_unix, ctime_local_str, ctime_utc_str, dt_local, dt_utc)

        return ctime_bundle

    def init_ied_time(self):
        """
        Initialise the start and end time for the virtual IED in a specific simulation. Particularly useful for
        simulations in which only historical data sets are used.

        It sets the simulation start time and updates the value self.ctime_unix accordingly, which is then used to
        update the two time relevant objects using self.update_time_by_unix()
        """

        logger.info('=================   Start initialising container time  =================')

        if self.time_mode == 'simulation':
            self.time_start_unix = time.mktime(
                datetime.strptime(self.time_start_str, self.time_str_format).timetuple())
            self.time_end_unix = time.mktime(
                datetime.strptime(self.time_end_str, self.time_str_format).timetuple())

        elif self.time_mode == 'absolute':
            self.time_start_unix = time.time()
            self.time_end_unix = self.time_start_unix + 60 * 60 * 24 * 365
            self.time_start_str = helper.time_unix_to_str(self.time_start_unix)
            self.time_end_str = helper.time_unix_to_str(self.time_end_unix)
        else:
            # TODO: raise time mode error
            logger.warning('Unknown time mode')

        self.ctime_unix = self.time_start_unix

        self.update_time_by_unix()

        if self.t_interval_data_update <= 60:
            self.SYNC_MAX_T = 5 * int(60 / self.t_interval_data_update)
            self.DEADLOCK_MAX_T = 10 * self.t_interval_data_update

        logger.info('=================   End initialising container time  =================\n')



    def get_attr_from_config(self, ied_config: IedConfig):
        """
        TODO: update descr
        TODO: change var name
        copy attributes from the config file

        rename for clarity

        Naming convention was a legacy in old program

        Parameters
        ----------
        ied_config

        Returns
        -------
        """

        self.t_interval_data_update = ied_config.ied.t_interval_data_update
        self.N_CTRL_WD_CYCLES = ied_config.ied.N_CTRL_WD_CYCLES
        self.t_monitor_reserve = ied_config.ied.t_monitor_reserve
        self.t_interval_archive = ied_config.ied.t_interval_archive
        self.t_interval_data_upload = ied_config.ied.t_interval_data_upload

        # time settings
        self.time_mode = ied_config.container.time_mode
        self.time_start_str = ied_config.container.time_start_str
        self.time_end_str = ied_config.container.time_end_str
        self.time_start_unix = ied_config.container.time_start_unix
        self.time_end_unix = ied_config.container.time_end_unix
        self.time_accelerator_factor = ied_config.container.time_accelerator_factor

    def display_ctime(self):
        logger.info(f'Current local time: {self.ctime_local_str}')
        logger.info(f'Current UTC time: {self.ctime_utc_str}')
        logger.info(f'Current UNIX time: {self.ctime_unix}')

    def sync_ied_time(self):
        self.time_sync_count = 0  # reset time sync counter
        self.update_time_by_unix()

    def update_time_by_unix(self):
        """
        Use the current local unix time of float type, to update all time bundle attributes. This method would be a
        great help as operating on float type value is often easier than handling strings or datatime instances.
        -------
        """

        self.ctime_bundle = self.get_ctime_bundles(self.ctime_unix)
        self.ctime_unix = self.ctime_bundle[0]
        self.ctime_local_str = self.ctime_bundle[1]
        self.ctime_utc_str = self.ctime_bundle[2]
        self.ctime = self.ctime_bundle[3]
        self.ctime_utc = self.ctime_bundle[4]

        self.display_ctime()

    def get_runtime_interval(self):
        self.t_interval_rt = round(self.t_interval_data_update - self.offset,
                                           self.TIME_DECIMAL)

    def round_ctime_str_minute(self):
        """
        Take a unix time float value as input, round up the time to full minutes and return the String. This function
        could be used to round up current time before loading time-series profiles. For example, if the profiles come with
        minute resolution, while the current time is 12:05:58.123, then one need to round the time up to 12:06:00, in order
        to query data for the next time step.

        String type time variables might be helpful because the database query language sometimes requires time
        string as input for data query (e.g. in influxdb).
        """

        ctime_str = helper.time_unix_to_str(self.ctime_unix)
        if int(ctime_str[-2:]) == 0:
            pass
        elif int(ctime_str[-2:]) in range(0, 31):
            ctime_str = ctime_str[:-2] + '00'
        elif int(ctime_str[-2:]) in range(31, 60):
            if int(ctime_str[-5:-3]) < 59:
                ctime_str = f'{ctime_str[:-6]}:{int(ctime_str[-5:-3]) + 1}:00'
            else:
                ctime_str = ctime_str[:-2] + '00'

        self.ctime_str_round_minute = ctime_str

    def get_control_watchdog_interval(self):
        CTRL_PERIOD = round((self.t_interval_rt - self.t_monitor_reserve) / self.N_CTRL_WD_CYCLES,
                            self.TIME_DECIMAL)
        return CTRL_PERIOD

class IedManager(object):
    """
    This class handles the runtime operations such as IEC 61850 server, server configuration, time management,
    data update and ied routine.

    -------------------------------------------------------------------
    IedManager routine status indicators:
        - is_running: 0, 1
        - is_restart: 0, 1
        - is_abort:   0, 1

    status = is_running*2^0 + is_restart*2^1 + is_abort*2^2
        0 - not running
        1 - running
        2 - not running -> restarting
        3 - running -> restarting
        4 - not running, not restarting, aborted
        5 - running, not restarting, directly aborted
        6 - not running, not restarting, not abort -> same action as 2
        7 - running, restart triggered and also aborted

    NOTE: the difference between restart and abort is, restart only affects the IED server, while abort requires
    termination of all services.

    NOTE: the state abort can be tricky here, occasionally the abort will not be performed as a python function,
    but rather triggered by the container management.

    TODO: check all occurrences of status change, are they correctly implemented? is it too complex?
    -------------------------------------------------------------------

    TODO: share those time related value with TimeManager
    """

    def __init__(self):
        self.ied_config: IedConfig | None = None
        self.time_manager: TimeManager | None = TimeManager()
        self.ied_server: IEC61850ServerMMS | None = None
        self.data_model_generator: IEC61850DataModelGenerator | None = None
        self.influxdb: Influxdb = Influxdb()

        self.allowed_threads: list = []
        self.routine_cycle_count: int = 0
        self.db_conn_count: int = 0  # count of database connections, will be used for conn_obj obj refreshing
        self.period_idx: int = 0

        self.status: int = 0
        self.is_running: bool = False
        self.is_restart: bool = False
        self.is_abort: bool = False

        self.is_start_new_routine: bool = False  # a flag to indicate whether a new routine should start
        self.deadlock_count: int = 0
        self.seconds_in_routine: int | float = 999999  # abs. time [seconds] at the beginning of this routine cycle
        self.seconds_in_routine_next: int | float = 999999  # abs. time [seconds] at the end of this routine cycle
        self.routine_agg_duration: int | float = 0  # aggregated (relative) duration since the start of the routine
        self.logged_errors: set = set()  # TODO: add a method to flush logged_errors regularly

        # ONLY FOR DEBUG PURPOSE
        self.MAX_CYCLE_COUNT_DESTROY: int = 0  # max. number of routine cycles before forcing a server termination
        self.MAX_CYCLE_COUNT_RESTART: int = 0  # max. number of routine cycles before forcing a server restart
        self.CTRL_PERIOD: float = 1.0



    def update_status(self):
        """
        status = is_running*2^0 + is_restart*2^1 + is_abort*2^2
        """

        self.status = self.is_running * 2**0 + self.is_restart * 2**1  + self.is_abort * 2**2

    #################################################################
    #######  Methods related to initialising IEC 61850 IED   ########
    #################################################################

    def init_ied_service(self, path_config: str):
        self.setup_runtime_components(path_config)

    def init_time_manager(self):
        self.time_manager.get_attr_from_config(self.ied_config)
        self.time_manager.init_ied_time()
        self.is_running = True
        self.update_status()
        self.routine_cycle_count = 0

    def init_ied_config(self, config_filepath: str | None):
        """
        Initialise the IED configuration from a prescribed config file.
        If the case file does not exist, or could not be found, then use default configuration to start the IED.

        Parameters
        ----------
        config_filepath: the filepath of the customised config.

        Returns
        -------
        ied_config: an instance of the type IedConfig that encompasses all the customised or default IED config.
        """

        # init config
        self.ied_config = IedConfig()
        is_config_updated = self.ied_config.update_config(config_filepath)


        # distribute secrets to other
        # FIXME: the instance influxdb of the class Influxdb() used to be an attr of IedConfig, because of the storage
        #  of influx secrets and other config. So it is essential to pass the same reference to self.ied_config. This
        #  have the implication, or the question: where should any new secret configs be stored? -> Find an answer to
        #  this question

        self.ied_config.influxdb = self.influxdb
        self.display_config_info()


    def attach_container_time_to_tm(self):
        """
        This method is crucial!
        Later in the runtime environment, the DataBuffer instances wouldn't be able to access all attributes of
        TimeManager, but the attr ied_config is always passed to the containers, they must use the same time as time
        manager.
        """

        self.ied_config.container.ctime = self.time_manager.ctime
        self.ied_config.container.ctime_utc = self.time_manager.ctime_utc
        self.ied_config.container.ctime_unix = self.time_manager.ctime_unix
        self.ied_config.container.ctime_local_str = self.time_manager.ctime_local_str
        self.ied_config.container.ctime_utc_str = self.time_manager.ctime_utc_str
        self.ied_config.container.ctime_bundle = self.time_manager.ctime_bundle

    def init_thread_whitelist(self):
        self.allowed_threads = [threading.current_thread().ident, ]

    def init_routine_time(self):
        self.seconds_in_routine = self.time_manager.ctime_unix % self.time_manager.ROUTINE_MAX_T

    def init_ied_app(self):
        """
        Initialize the CLS application (aka the virtual IEC 61850 IED Server)
        """

        ied_config = self.ied_config
        time_manager = self.time_manager

        logger.info(f'Initialise the IEC 61850 server with the start Time {time_manager.time_start_str}')
        logger.info(f'Current local time: {time_manager.ctime_local_str}, unix local time: {time_manager.ctime_unix}')
        logger.info(f'Current UTC time: {time_manager.ctime_utc_str}, unix UTC time: {time_manager.ctime_unix}')

        self.gen_iec61850_data_model()
        self.init_ied_server()
        self.is_running = True
        self.is_abort = False
        self.is_restart = False
        self.update_status()



    def gen_iec61850_data_model(self):
        """
        TODO: add desc

        """

        ied_config = self.ied_config

        if not ied_config.interface.path_scl:
            # dynamic IEC 61850 data model generation
            self.data_model_generator = IEC61850DataModelGenerator(
                pathConfigFile=ied_config.interface.path_data_model_config,
                nameIED=ied_config.ied.ied_name)
            [path_output_scl, dict_output_scl] = self.data_model_generator.main(readConfigYAML=True,
                                               configYAML=ied_config.interface.config_yaml)
            ied_config.interface.path_scl = path_output_scl
        else:
            # config.update_der_dicts(ied_config)
            name_scl = os.path.basename(ied_config.interface.path_scl)
            ied_config.container.service_name = name_scl.split('.')[0]
            ied_config.container.container_name = name_scl.split('.')[0]

    def init_ied_server(self):
        """
        IEC 61850 communication server initialisation.

        Note that the instance of class IEC61850ServerMMS has no connection to instances of IedConfig. But they can
        exchange information within ied_manager.

        TODO: improve sloppy var names and info storage
        """

        self.ied_server = pyiec61850_server.run_ied_server_mms(self.ied_config)
        self.ied_server.server_config.container = self.ied_config.container  # sync the server config with the global one
        self.ied_server.server_config.der = self.ied_config.der
        if not self.ied_config.interface.path_scl:
            self.ied_server.server_config.der.der_dicts = self.data_model_generator.Config.der_dicts

        self.ied_config.interface.path_lookup = self.ied_server.path_lookup
        self.ied_config.interface.df_lookup = self.ied_server.df_lookup
        self.ied_config.interface.df_lookup_active = self.ied_server.df_lookup_active

        # add the unique data source to the server
        self.data_sources = list(self.ied_server.df_lookup['data_source'].unique())

    #################################################################
    #######      Methods related to runtime IED services     ########
    #################################################################

    def set_routine_time(self):
        self.seconds_in_routine_next = self.time_manager.ctime_unix % self.time_manager.ROUTINE_MAX_T

    def count_routine_time(self):
        if self.seconds_in_routine_next < self.seconds_in_routine:  # indicates the start of a new day
            logger.info(
                f'Accumulated time in the current routine changed from {self.seconds_in_routine} s -> {self.seconds_in_routine_next} s')
            self.is_start_new_routine = True
        else:
            logger.info(
                f'Accumulated time in the current routine increased {self.seconds_in_routine} s -> {self.seconds_in_routine_next} s')
            logger.info('Still in the same processing routine.')
        self.seconds_in_routine = self.seconds_in_routine_next

    def destroy_ied_server(self):
        logger.info('-------------------------------------------------------------------\n')
        logger.info('Destroy running ied_server and the ied_config instance.')
        self.ied_config = IedConfig()
        self.ied_server.destroy_ied_server()
        self.ied_server = None
        self.is_abort = True
        self.update_status()
        logger.info('-------------------------------------------------------------------\n')

    def setup_runtime_components(self, config_filepath: str | None):
        """Executes the full initialization chain for config, time management, and IEC 61850 app."""
        self.init_ied_config(config_filepath)
        self.init_time_manager()
        self.init_routine_time()
        self.init_ied_app()
        self.init_thread_whitelist()
        self.attach_container_time_to_tm()
        self.CTRL_PERIOD = self.time_manager.get_control_watchdog_interval()

    def restart_ied_server(self, config_filepath: str | None):
        logger.info('-------------------------------------------------------------------\n')
        logger.info('Re-initialise the ied_config and restart the IEC 61850 server.')
        self.is_restart = True
        self.is_abort = False
        self.update_status()

        logger.info('First terminate the running server.')
        self.destroy_ied_server()

        logger.info('Now restart all runtime services and the server.')
        self.setup_runtime_components(config_filepath)

        logger.info('Start a new virtual IED routine.')
        logger.info('-------------------------------------------------------------------\n')

    def display_config_info(self):
        """
        This method can display the current configuration of a running virtual CLS.
        """

        logger.info('=================   Begin get IED information   =================')
        # listInfo = ['der_type', 'pvRatedPower', 'time_mode', 'time_start_str', 'time_end_str',
        #             'data_source', 'time_accelerator_factor', 'scaling_factor','unit_factor',
        #             'ied_guid', 'container_guid', 'host_name', 'port', 'tcp_port']

        for key in vars(self.ied_config).keys():
            item = self.ied_config.__dict__[key]
            logger.info(f'-------------  Display <{key}> configuration  -------------')
            for k, v in vars(item).items():
                logger.info(f'{k}: {v}')
        logger.info('=================   End get IED information   =================\n')

    def display_worker_process_time(self):
        try:
            t_buffer_worker = round(self.time_manager.t1, self.time_manager.TIME_DECIMAL)
            t_controller_worker = round(self.time_manager.t_ctrl_wd_worker, self.time_manager.TIME_DECIMAL)
            logger.info(f'This iteration started with an offset of: {self.time_manager.offset} seconds')
            logger.info(f'Time consumed by the subprocess update data buffer: {t_buffer_worker} seconds')
            logger.info(f'Time consumed by the subprocess control watchdog: {t_controller_worker} seconds')
        except Exception as err:
            logger.exception(f'Failed to determine the processing time of this iteration: {err}')

    def distribute_time_manager(self):
        assert self.ied_server, 'The IEC61850 MMS Server must not be None'

        # distribute the same time manager to all data buffer instances
        for dbf in self.ied_server.data_buffers.values():
            dbf.time_manager = self.time_manager

        # in case of using data from influx or local file, we must determine the time offset between data and simulation
        active_buffers = [dbf for dbf in self.ied_server.data_buffers.values() if dbf.data_source
                          in ('influxdb', 'local')]

        # also calc time offset between simulation time and time series data
        # NOTE: this time offset is not particularly required since we use unix time to get data
        tz_sim = self.time_manager.timezone
        for dbf in active_buffers:
            tz_data = self.time_manager.timezone if not dbf.time_series else dbf.time_series.timezone
            if tz_data == tz_sim:  # if the time zone is the same as simulation time zone
                dbf.timeseries_offset = 0
            else:
                dbf.timeseries_offset = helper.get_tz_diff_seconds(tz_sim, tz_data, self.time_manager.ctime)


    def distribute_influxdb_handler(self):
        """
        This method is used to allow the data buffer instances share a single influxdb handler.

        influx level:
            0 - no monitoring, no control
            1 - only monitoring
            2 - only control
            3 - monitoring + control
        """

        assert self.ied_server, 'The IEC61850 MMS Server must not be None'

        for dbf in self.ied_server.data_buffers.values():
            # passing influxdb configuration including the handler
            keys = [item for item in dir(self.ied_config.influxdb) if '__' not in item]
            dbf.influx_level = dbf.is_monitor + 2 * dbf.is_control

            if dbf.influx_level < 1:
                dbf.is_idle = True

            # whether the DB requries influxdb handler depends on if it reads profile data from influxdb
            # so is_passing=True if data_buffer.is_monitor = True and data_buffer.data_source = 'influxdb',
            # otherwise the influxdb handler will not be assigned to that dataBuffer instance.
            for key in keys:
                is_assign_handler = True
                if key == 'read_handler':
                    if not dbf.is_monitor or dbf.data_source != "influxdb":
                        is_assign_handler = False
                if key == 'write_handler' and dbf.influx_level == 0:
                    is_assign_handler = False

                if is_assign_handler:
                    setattr(dbf.influxdb, key, getattr(self.ied_config.influxdb, key))
                else:
                    setattr(dbf.influxdb, key, None)

            # if measurement_write is not given in the config.yaml, use <container_name>
            # this is for pushing data and records to influxdb write bucket.
            if not dbf.influxdb.measurement_write:
                dbf.influxdb.measurement_write = self.ied_config.container.container_name

            # double check whether the lookup CSV contains influxdb related configuration for this DO
            if dbf.data_source == 'influxdb' and not pd.isna(dbf.fieldbus_conn_obj):
                for keyJSON in dbf.fieldbus_conn_obj.keys():
                    setattr(dbf.influxdb, keyJSON, dbf.fieldbus_conn_obj[keyJSON])


class IedServiceManager:
    """
    Manages the lifecycle and execution of all persistent asynchronous
    background daemon tasks for the Virtual IED server.
    """

    def __init__(self, ied_manager: IedManager, trigger_influxdb_upload_func=None, db_ready_event=None):
        self.ied_manager = ied_manager
        self.trigger_influxdb_upload_func = trigger_influxdb_upload_func
        self.db_ready_event = db_ready_event or threading.Event()

        # Ensure db_ready_event is set initially
        self.db_ready_event.set()

        self.stop_event = threading.Event()
        self.threads = []

        # Initialize the CSV Executor bound to this service manager instance
        self.csv_writer_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="csv_writer"
        )

    # =========================================================================
    # Task 1: Local CSV Archive Worker
    # =========================================================================
    def csv_archive_worker(self):
        time_manager = self.ied_manager.time_manager
        interval = time_manager.t_interval_archive
        logger.info(f"CSV Archive Worker started (Interval: {interval}s).")

        while not self.stop_event.is_set() and self.ied_manager.status < 4:
            tic = time.perf_counter()
            try:
                logger.info("Exporting CSV records to local storage...")

                # Shallow list snapshot to prevent dict mutation issues during iteration
                data_buffers = list(self.ied_manager.ied_server.data_buffers.values())
                monitored_buffers = [db for db in data_buffers if getattr(db, 'is_monitor', False)]

                def _write_buffer_to_csv(data_buffer):
                    """Helper function executed asynchronously in the thread pool for disk I/O."""
                    try:
                        flag = data_buffer.export_records_locally()
                        if flag == 1:
                            logger.debug(f"Export CSV completed for DO {data_buffer.iec61850_do.name}.")
                        elif flag == 99:
                            logger.warning(f"Export CSV failed for DO {data_buffer.iec61850_do.name}!")
                    except Exception as err:
                        logger.error(f"Failed to export CSV for DO {data_buffer.iec61850_do.name}: {err}")

                # Offload file writing asynchronously without holding GIL / locking the worker thread
                for db in monitored_buffers:
                    self.csv_writer_executor.submit(_write_buffer_to_csv, db)

                logger.info("CSV archiving tasks successfully offloaded to disk executor.")

            except Exception as err:
                logger.exception(f"Error in CSV Archive Worker: {err}")

            elapsed = time.perf_counter() - tic
            if self.stop_event.wait(timeout=max(0.1, interval - elapsed)):
                break

        logger.info("CSV Archive Worker stopped cleanly.")

    # =========================================================================
    # Task 2: InfluxDB Upload Worker
    # =========================================================================
    def influx_upload_worker(self):
        time_manager = self.ied_manager.time_manager
        interval = time_manager.t_interval_data_upload
        update_interval = time_manager.t_interval_rt

        # Timeout set to 2.0s so connection check fails fast if DB is reconnecting
        WAIT_TIMEOUT = min(2.0, update_interval / 2.0)

        logger.info(f"InfluxDB Upload Worker started (Interval: {interval}s).")

        next_tick = time.perf_counter()

        while not self.stop_event.is_set() and self.ied_manager.status < 4:
            next_tick += interval

            # Wait if the database connection is currently being refreshed
            if self.db_ready_event.wait(timeout=WAIT_TIMEOUT):
                try:
                    if self.trigger_influxdb_upload_func:
                        self.trigger_influxdb_upload_func(self.ied_manager.ied_server)
                        logger.debug("InfluxDB upload completed.")
                except Exception as err:
                    logger.exception(f"Error in InfluxDB Upload Worker: {err}")
            else:
                logger.warning("InfluxDB upload skipped: Connection refresh in progress.")

            # Compute remaining sleep against absolute target
            remaining_sleep = next_tick - time.perf_counter()

            if remaining_sleep > 0:
                if self.stop_event.wait(timeout=remaining_sleep):
                    break
            else:
                logger.warning(
                    f"InfluxDB upload cycle overran by {-remaining_sleep:.3f}s! "
                    f"Catching up to next interval."
                )
                # Re-align next_tick to prevent compounding delays
                now = time.perf_counter()
                while next_tick <= now:
                    next_tick += interval

        logger.info("InfluxDB Upload Worker stopped cleanly.")

    # =========================================================================
    # Task 3: InfluxDB Connection Maintenance Worker
    # =========================================================================
    def influx_connection_refresher_worker(self):
        time_manager = self.ied_manager.time_manager
        refresh_interval = time_manager.INFLUXDB_TIMER  # e.g., 14400s (4 hours)
        logger.info(f"InfluxDB Connection Refresher Worker started (Interval: {refresh_interval}s).")

        while not self.stop_event.is_set() and self.ied_manager.status < 4:
            # Interruptible sleep until the next 4-hour cycle
            if self.stop_event.wait(timeout=refresh_interval):
                break

            logger.info("Re-establishing InfluxDB connection object...")
            self.db_ready_event.clear()  # Block uploads during socket teardown
            try:
                self.ied_manager.db_conn_count += 1
                self.ied_manager.influxdb.close_influx_conn()

                if self.ied_manager.influxdb.is_secret_loaded:
                    is_read_success, is_write_success = self.ied_manager.influxdb.init_influx_conn_obj()
                    self.ied_manager.distribute_influxdb_handler()
                    logger.info("InfluxDB connection object successfully refreshed.")
                else:
                    logger.warning("InfluxDB secret file is not loaded!")
            except Exception as err:
                logger.exception(f"Failed to refresh InfluxDB connection: {err}")
            finally:
                self.db_ready_event.set()  # Unblock uploads
        logger.info("InfluxDB Connection Refresher Worker stopped cleanly.")

    def get_sunspec_conn_objs(self) -> list:
        """
        Dynamically fetches the latest active SunSpec connection objects from ied_manager.
        Returns an empty list if ied_server or df_lookup_active is not yet initialized.
        """
        ied_server = getattr(self.ied_manager, 'ied_server', None)
        if ied_server is None:
            return []

        # Dynamically pull the live df_lookup_active DataFrame
        df_lookup_active = getattr(ied_server, 'df_lookup_active', None)
        if df_lookup_active is None or df_lookup_active.empty:
            return []

        # Check if 'data_source' and 'fieldbus_conn_obj' columns exist
        if 'data_source' not in df_lookup_active.columns or 'fieldbus_conn_obj' not in df_lookup_active.columns:
            return []

        # Filter active SunSpec entries
        df_lookup_sunspec = df_lookup_active.loc[df_lookup_active['data_source'] == 'sunspec']

        # Drop NA / None connection objects
        conn_objs = df_lookup_sunspec['fieldbus_conn_obj'].dropna().unique().tolist()
        return conn_objs

    def sunspec_conn_obj_refresher_worker(self):
        """
        Periodically triggers a full SunSpec connection object scan in the background.
        Default interval: 7200 seconds (2 hours).
        """

        time_manager = self.ied_manager.time_manager
        refresh_interval_sec = time_manager.SUNSPEC_CONN_OBJ_TIMER

        logger.info(f"SunSpec Connection Refresher Worker active (Interval: {refresh_interval_sec}s).")

        # Track the last refresh execution time
        last_refresh_time = 0.0

        while not self.stop_event.is_set() and self.ied_manager.status < 4:
            try:
                # Yield if server is stopped or transitioning through a restart
                if not self.ied_manager.is_running or self.ied_manager.is_restart:
                    if self.stop_event.wait(timeout=5.0):
                        break
                    continue

                now = time.monotonic()
                if now - last_refresh_time >= refresh_interval_sec:
                    logger.info("Triggering periodic SunSpec connection object health check and scan...")

                    conn_objs = self.get_sunspec_conn_objs()

                    logger.info(f"Found {len(conn_objs)} unique SunSpec connection objects to check.")

                    for idx, conn_obj in enumerate(conn_objs):
                        if self.stop_event.is_set() or not self.ied_manager.is_running:
                            logger.info("Abort signal received during SunSpec scan cycle.")
                            break

                        if conn_obj is None:
                            continue

                        # 1. Reconnection Handler Guard
                        is_healthy = interface_sunspec.keep_alive(conn_obj)

                        if is_healthy:
                            # Check if models dictionary is empty or unpopulated
                            has_models = hasattr(conn_obj, 'models') and bool(conn_obj.models)

                            if not has_models:
                                logger.info(f"No active SunSpec models found for index {idx}. Running scanner...")
                                try:
                                    interface_sunspec.sunspec_scanner(idx, conn_obj)
                                except Exception as err:
                                    logger.error(f"Error scanning SunSpec connection object index {idx}: {err}")
                            else:
                                logger.debug(
                                    f"Connection object index {idx} is healthy and models are already populated. Skipping scan.")
                        else:
                            logger.warning(
                                f"Skipping SunSpec scan for connection object at index {idx}: "
                                f"Server unreachable after reconnection attempt."
                            )

                    last_refresh_time = time.monotonic()
                    logger.info("SunSpec connection object refresh cycle completed.")

            except Exception as err:
                logger.exception(f"Error in SunSpec Connection Refresher Worker: {err}")

            if self.stop_event.wait(timeout=1.0):
                break

        logger.info("SunSpec Connection Refresher Worker stopped cleanly.")

    def service_restarter_worker(self):
        """
        Monitors operational time (real or simulated) via time_manager.ctime_unix
        and triggers a server restart whenever time_manager.ROUTINE_RESTART_HOUR AM UTC is crossed.
        """

        time_manager = self.ied_manager.time_manager
        check_interval_sec = time_manager.ROUTINE_RESTART_INTERVAL
        hour = time_manager.ROUTINE_RESTART_HOUR
        minute =  time_manager.ROUTINE_RESTART_MINUTE
        OFFSET_TRIGGER_SEC = hour * 3600 + minute * 60
        SECONDS_PER_DAY = 24 * 3600

        logger.info(f"Service restarter worker active (Targeting daily {hour}:{minute} UTC restart).")

        # Initialize the current day index based on initial time
        # Subtracting 8 hours shifts the rollover boundary to the restart time
        initial_unix = time_manager.ctime_unix
        last_day_index = math.floor((initial_unix - OFFSET_TRIGGER_SEC) / SECONDS_PER_DAY)

        while not self.stop_event.is_set() and self.ied_manager.status < 4:
            try:
                # Read current Unix time (handles both absolute and simulation modes)
                current_unix = time_manager.ctime_unix

                # Compute current day index relative to 08:00 AM UTC
                current_day_index = math.floor((current_unix - OFFSET_TRIGGER_SEC) / SECONDS_PER_DAY)

                # If the integer day index incremented, we crossed 08:00 AM UTC
                if current_day_index > last_day_index:
                    # Update time bundle to reflect the exact state at trigger
                    time_manager.update_time_by_unix()

                    logger.warning(
                        f"UTC boundary crossed at timestamp {time_manager.ctime_utc_str}. "
                        f"Service restarter workerTriggering full IEC 61850 server restart."
                    )
                    self.ied_manager.is_restart = True
                    self.ied_manager.is_running = False
                    self.ied_manager.update_status()
                    break  # Exit worker once restart sequence is initiated

            except Exception as err:
                logger.exception(f"Error in Service Restarter Worker: {err}")

            if self.stop_event.wait(timeout=check_interval_sec):
                break

            logger.info("Service restarter worker stopped cleanly.")

    # =========================================================================
    # Service Lifecycle Controls
    # =========================================================================
    def start_all_services(self):
        """Launches all 5 worker methods as daemon threads."""
        self.stop_event.clear()

        workers = [
            ("csv_archive_worker", self.csv_archive_worker),
            ("influx_upload_worker", self.influx_upload_worker),
            ("influx_connection_refresher", self.influx_connection_refresher_worker),
            ("sunspec_connection_refresher", self.sunspec_conn_obj_refresher_worker),
            ("service_restarter_worker", self.service_restarter_worker),
        ]

        for name, target_method in workers:
            th = threading.Thread(target=target_method, name=name, daemon=True)
            th.start()
            self.threads.append(th)
            logger.info(f"Daemon worker [{name}] initialized and started.")

    def stop_all_services(self):
        """Signals all worker threads to stop and waits for their termination."""
        logger.info("Signaling all background worker threads to stop...")
        self.stop_event.set()

        # Safely shut down the CSV thread pool without blocking application cleanup
        if hasattr(self, 'csv_writer_executor'):
            logger.info("Shutting down CSV writer executor pool...")
            self.csv_writer_executor.shutdown(wait=False, cancel_futures=True)

        for th in self.threads:
            if th.is_alive():
                th.join(timeout=2.0)

        self.threads.clear()
        logger.info("All service workers stopped.")