# -*- coding: utf-8 -*-
"""
Main module for the organisation of core real-time function blocks and thread workers.

NOTE: the approach of multi-threading is not helping to enhance the processing efficiency. Multi-processing also
couldn't help much because issues might occur due to time management and return values.

IMPORTANT NOTION BEFORE THE CODE REFACTORING:
I've tried different approaches for multithreading handling. In windows OS all of them seems to work
quite fine, but Linux (particularly Docker and raspberry pi) is really a handful. By now, the approach combining
ThreadPoolExecutor() from concurrent.futures for mainThread, and single thread handlers as routine workers turned
out to have relative good performance, in the sense of not getting stuck in main thread stuck just after a few of iterations.
(executor raises a KeyboardInterrupt exception, which is easy to catch and get around).

The other two options (multiprocessing.ThreadPool() and single thread handlers) are not that robust on linux plattfrom
regarding the code structure here. The biggest issue is that the hanging processes returns almost no knowledge about what
is going on.

@author: Chen
"""

# standard built-in lib
import os
import sys
import time
import logging
import threading
from threading import Lock
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from communication.pyiec61850_server import IedServer


# standard lib requiring installation

# local lib
from interface import runtime
from interface.iec61850_mms import IEC61850ServerMMS
from simulation.runtime_manager import IedManager, IedServiceManager
from interface.iec61850_mms import exec_control
from interface import influxdb
from interface.data_buffer import DataBuffer

import settings.helper as helper
import settings.config as config
import interface

iec61850 = helper.import_libiec61850()

logger = logging.getLogger(f"main_logger.{__name__}")
logger.propagate = False

# Use persistent thread pool. Limits max concurrent connections to InfluxDB.
# This prevents thousands of OS threads from bleeding out your system's resources over time.
# TODO: make INFLUX_MAX_WORKERS a parameter in config.yaml or IedManager

# Change max workers to a reasonable size (e.g., 10-20)
INFLUX_MAX_WORKERS = 20
influx_executor = ThreadPoolExecutor(max_workers=INFLUX_MAX_WORKERS, thread_name_prefix="InfluxUpload")

db_ready_event = threading.Event()
db_ready_event.set()  # Start in 'ready' state

"""
=======================================================================
=================   DEFINE THREAD WORKERS FUNCTIONS      ==============
=======================================================================
"""

def upload_to_influxdb(data_buffer):
    """
    Executes concurrently across worker threads.
    Catches errors locally so worker threads don't crash the pool.
    """
    if not data_buffer.is_idle:
        try:
            # Let worker threads upload IN PARALLEL (No lock here!)
            interface.influxdb.perform_upload(data_buffer)
        except Exception as err:
            logger.error(f"Worker upload failed for DO {data_buffer.iec61850_do.name}: {err}")


def trigger_influxdb_upload(ied_server: IEC61850ServerMMS):
    """
    A thread-safe function utilizing a persistent thread pool to safely upload
    databuffer recordings to InfluxDB with a fallback expiration timeout.
    """
    logger.info('Upload data_buffer records to remote database influxdb has been triggered.')

    futures = {}
    for data_buffer in ied_server.data_buffers.values():
        if data_buffer.influx_level > 0:
            # Submit tasks to the reusable global pool instead of initializing new OS threads
            future = influx_executor.submit(upload_to_influxdb, data_buffer)
            futures[future] = data_buffer.iec61850_do.name

    if not futures:
        logger.info('No data_buffers qualified for InfluxDB upload in this cycle.')
        return

    # A short timeout stops late HTTP requests from blocking execution stacks
    UPLOAD_TIMEOUT_SEC = 5.0

    try:
        # Process tasks as they finish, capping at our total timeout cushion
        for future in as_completed(futures.keys(), timeout=UPLOAD_TIMEOUT_SEC):
            do_name = futures[future]
            try:
                future.result()  # Raises exceptions thrown inside upload_to_influxdb
            except Exception as err:
                logger.error(f"InfluxDB upload failed for DO {do_name}: {err}")
    except TimeoutError:
        logger.error(
            f"InfluxDB upload sequence reached strict timeout threshold ({UPLOAD_TIMEOUT_SEC}s). Dropping hung connections.")
        cancelled_count = 0
        for future in list(futures.keys()):
            if future.cancel():
                cancelled_count += 1

        # 2. Log status of dropped tasks
        logger.warning(
            f"Cancelled {cancelled_count} pending InfluxDB upload task(s). "
            f"{len(futures) - cancelled_count} task(s) exceeded the timeout while executing."
        )

    logger.info('Upload data_buffer records to remote database influxdb sequence complete.')


"""
=======================================================================
=================    ASSIGN THREAD TASK TO WORKERS    =================
=======================================================================
"""


def update_data_buffers_worker(ied_manager: IedManager):
    """
    Thread for updating data buffer instances with safe guard
    """

    # 1. Guard: Skip execution if the server is restarting or shutting down
    if not ied_manager.is_running or ied_manager.is_restart or ied_manager.is_abort:
        logger.debug("Skipping update_data_buffers: IED server is in restart/stop state.")
        return

    # 2. Guard: Verify that ied_server, data_buffers, and time_manager exist and are attached
    ied_server = getattr(ied_manager, 'ied_server', None)
    if not ied_server or not getattr(ied_server, 'data_buffers', None):
        logger.warning("Skipping update_data_buffers: ied_server or data_buffers not initialized.")
        return

    first_buffer = ied_server.data_buffers[0] if len(ied_server.data_buffers) > 0 else None
    if not first_buffer or getattr(first_buffer, 'time_manager', None) is None:
        logger.warning("Skipping update_data_buffers: time_manager in data_buffer is None.")
        return

    # 3. Safe Execution Block
    tic = time.perf_counter()
    logger.info('-------------------------------------------------------------------')
    logger.info('Start the task for updating databuffer instances')

    try:
        runtime.update_data_buffers(ied_manager)
        logger.info('Update measurement was successful.')
    except AttributeError as err:
        logger.exception(f'Update measurement failed, probably bad database handler or unattached manager: {err}')
    except Exception as err:
        logger.exception(f'Unknown error occurred when updating the data_buffer: {err}')

    logger.info('Task for updating data buffer accomplished.')
    logger.info('-------------------------------------------------------------------\n')
    toc = time.perf_counter()

    if getattr(ied_manager, 'time_manager', None):
        ied_manager.time_manager.t_dbf_worker = toc - tic

def periodic_thread(ied_manager: IedManager, next_tick: float) -> float:
    """
    Executes one cycle of the main routine and calculates the sleep requirement
    against an absolute monotonic deadline (`next_tick`) to eliminate drift.

    :param ied_manager: Active IedManager instance
    :param next_tick: Monotonic timestamp target for the completion of this cycle
    :return: The updated `next_tick` timestamp target for the next cycle
    """
    tic_cycle = time.perf_counter()
    time_manager = ied_manager.time_manager

    logger.info('-------------------------------------------------------------------')
    logger.info(
        f"Server running with iteration index {ied_manager.period_idx} "
        f"(Target Interval: {time_manager.t_interval_rt}s)"
    )
    ied_manager.period_idx += 1

    # 1. Update clock
    if time_manager.time_mode == 'absolute':
        time_manager.ctime_unix = time.time()
        time_manager.update_time_by_unix()
    elif time_manager.time_mode == 'simulation':
        # Increment simulated clock by tick interval
        time_manager.ctime_unix += time_manager.t_interval_rt
        time_manager.update_time_by_unix()
    else:
        raise ValueError(f'Wrong time mode: {time_manager.time_mode}')

    time_manager.display_ctime()
    ied_manager.set_routine_time()
    ied_manager.count_routine_time()

    # 2. Update Data Buffers with timing measurement
    t_db_start = time.perf_counter()
    update_data_buffers_worker(ied_manager)
    t_db_duration = time.perf_counter() - t_db_start
    logger.info(f"[TIMING] update_data_buffers_worker took {t_db_duration:.3f} seconds.")

    ied_manager.routine_cycle_count += 1
    ied_manager.time_manager.time_sync_count += 1

    # 3. Periodic Sync Trigger
    if ied_manager.time_manager.time_sync_count >= time_manager.SYNC_MAX_T:
        logger.info('Time synchronisation triggered.')
        time_manager.sync_ied_time()
        time_manager.time_sync_count = 0  # Reset counter

    # Measure total execution work time before sleep calculation
    work_duration = time.perf_counter() - tic_cycle
    logger.info(f"[TIMING] Total cycle work time: {work_duration:.3f}s (Target: {time_manager.t_interval_rt}s).")

    # 4. Cadence Control
    next_tick += time_manager.t_interval_rt
    remaining_sleep = next_tick - time.perf_counter()

    logger.info(f"[TIMING] Computed remaining_sleep: {remaining_sleep:.3f}s (next_tick={next_tick:.3f}).")

    if remaining_sleep > 0:
        logger.info(f"Routine cycle finished in time, sleep for {remaining_sleep:.3f}s!")
        time.sleep(remaining_sleep)
    else:
        logger.warning(f"Routine cycle overran by {-remaining_sleep:.3f}s! Catching up immediately.")
        # Reset alignment if the iteration took significantly longer than one period interval
        next_tick = time.perf_counter()

    # keeps a heartbeat to let the outer container know the state of the program
    ied_manager.heartbeat()

    return next_tick


def control_watchdog_worker(ied_manager: IedManager):
    logger.info('Event-driven control watchdog worker thread active.')
    ied_config = ied_manager.ied_config
    time_manager = ied_manager.time_manager
    failed_attempts = {}
    MAX_ALLOWED_FAILURES = 5

    while ied_manager.status < 4:
        try:
            # Drop timeout to 0.05s so it reacts instantly when items arrive
            dbf = DataBuffer.control_queue.get(block=True, timeout=0.05)
            tic = time.perf_counter()

            if failed_attempts.get(dbf.id, 0) >= MAX_ALLOWED_FAILURES:
                logger.warning(f"DO {dbf.id} exceeded max failures ({MAX_ALLOWED_FAILURES}). Bypassing.")
                DataBuffer.control_queue.task_done()
                continue

            # Execute control action
            is_success = exec_control(ied_config, dbf)

            if is_success:
                logger.info(f'Successfully applied control action for DO {dbf.id}')
                dbf.records.control_count += 1
                failed_attempts[dbf.id] = 0
            else:
                failed_attempts[dbf.id] = failed_attempts.get(dbf.id, 0) + 1
                logger.error(f'Failed control for DO {dbf.id}. Failure count: {failed_attempts[dbf.id]}')

            DataBuffer.control_queue.task_done()
            time_manager.t_ctrl_wd_worker = time.perf_counter() - tic

        except queue.Empty:
            # Yield CPU briefly so libiec61850 C-callbacks & network threads get GIL access
            time.sleep(0.001)
        except Exception as err:
            logger.exception(f'Control watchdog handler error: {err}')


def ied_routine(ied_manager: IedManager):
    """
    Performs the main execution routine for the IEC 61850 virtual IED application.
        TODO: consider use the parameter time_start_trigger to trigger the server_routine, so that all containers start at the same time.
    """

    time_manager = ied_manager.time_manager

    # 1. Initial Time Synchronization
    if time_manager.time_mode == 'absolute':
        time_manager.ctime_unix = time.time()
        time_manager.sync_ied_time()
    else:
        time_manager.update_time_by_unix()
    time_manager.t_interval_rt = time_manager.t_interval_data_update

    # 2. Instantiate and Launch Background Service Manager
    services = IedServiceManager(
        ied_manager=ied_manager,
        trigger_influxdb_upload_func=trigger_influxdb_upload,
        db_ready_event=db_ready_event  # Shared threading.Event
    )
    services.start_all_services()

    # Start watchdog worker
    watchdog_thread = threading.Thread(name='control_watchdog', target=control_watchdog_worker, args=(ied_manager,),
                                       daemon=True)
    watchdog_thread.start()
    logger.info(f"Daemon thread [control_watchdog] initialized and started.")

    # 3. Core Execution Loop with Precise Cadence Tracking
    next_tick = time.perf_counter()  # Initialized ONCE prior to entering the loop

    try:
        # Exit if is_running becomes False (status % 2 == 0) or abort triggered (status >= 4)
        while ied_manager.status == 1:
            next_tick = periodic_thread(ied_manager, next_tick)
            time_manager.deadlock_count = 0

    except KeyboardInterrupt:
        logger.warning('Caught KeyboardInterrupt in ied_routine, initiating graceful exit...')
        ied_manager.status = 4

    finally:
        # 4. Ensure background workers exit cleanly
        services.stop_all_services()


def init_virtual_ied_interfaces(ied_manager: IedManager):
    ied_config = ied_manager.ied_config
    ied_server = ied_manager.ied_server

    ied_manager.distribute_time_manager()

    # read influxdb secrete
    ied_manager.influxdb_handler.is_secret_loaded = config.read_secret(ied_config, filename='influxdb.json')

    if not ied_manager.influxdb_handler.is_secret_loaded:
        logger.warning('Loading influxdb secret config file failed, probably cannot init the influxdb interface!')
        logger.info('One could use local time-series data instead, this requires modification of the lookup table.')
        # TODO: currently no logic is inplace for switching data_source to local, implementing it if necessary
    else:
        logger.info('Influxdb configuration successfully loaded, now check the connection to db')
        is_read_success, is_write_success = ied_manager.influxdb_handler.init_influx_conn_obj()

    # sunspec interface
    interface.sunspec.init_sunspec_interface(ied_manager)

    # distribute the influxdb handler despite the configured data_source
    ied_manager.distribute_influxdb_handler()

    # initialising the values of all DataBuffer instances
    runtime.init_data_buffers(ied_config, ied_server, verbose=True)

    # NOTE: update data_buffer once to avoid unexpected control immediately after the initialization
    runtime.update_data_buffers(ied_manager, verbose=True)

    # unmute the silent control executors by setting is_initialized True
    for dbf in ied_server.data_buffers.values():
        dbf.is_initialized = True


def run_virtual_ied(path_config: str) -> IedManager:
    """
        We use this function to initialise a virtual CLS application (IED server) using only the SCL file.
        Further configuration can be and should be done by modifying the config YAML file.

        0 means no routine number limits, otherwise the main CLS app will exit after the maximal number of
        routines has been reached.

        -------------------------------------------------------------------
        IedManager routine status indicators:
            0 - isRunning
            1 - isRestart
            2 - isAbort

        status = isRunning*2^0 + isRestart*2^1 + isAbort*2^2
            0 - not running
            1 - running
            2 - not running -> restarting
            3 - running -> restarting
            4 - not running, not restarting, aborted
            5 - running, not restarting, directly aborted
            6 - running, restart triggered and also aborted
        -------------------------------------------------------------------

    """

    # helper.set_env_libiec61850()

    ied_manager = IedManager()
    ied_manager.init_ied_service(path_config)
    init_virtual_ied_interfaces(ied_manager)

    # Continue running as long as is_running is True or restart/abort flags allow
    while ied_manager.status % 2 or ied_manager.status <= 3:
        logger.info(f'Start routine with index {ied_manager.routine_cycle_count}')

        # 1. Run main routine block until is_running is False or status >= 4
        ied_routine(ied_manager)

        # 2. Handle Abort/Destroy
        if ied_manager.status >= 4:
            logger.warning("Destroying IED server connection...")
            ied_manager.destroy_ied_server()
            sys.exit(1)  # Non-zero exit code indicates aborted state

        # 3. Handle Restart
        if ied_manager.is_restart:
            # Force teardown of C-level IED server object & threads
            if hasattr(ied_manager, 'service_manager') and ied_manager.service_manager:
                try:
                    ied_manager.service_manager.flush_all_workers()
                except Exception as e:
                    logger.error(f"Error during service manager pre-restart flush: {e}")

            logger.info("Executing clean process exit for Docker container restart...")

            # Force teardown of C-level IED server object & threads
            try:
                ied_manager.destroy_ied_server()
            except Exception as e:
                logger.error(f"Error while destroying C IED server during soft restart: {e}")

            # Give TCP sockets 2 seconds to release from TIME_WAIT state
            time.sleep(2)

            # FIXME: the trigger_restarter_worker is doing fine mostly, but it leads to incomplete data upload in
            #   influxdb. So, the restart mechanism is rolled back to the scheduled container restart by exiting the
            #   Python program and forcing the container to restart automatically.

            # # Re-initialize fresh C server & virtual interfaces
            # ied_manager.restart_ied_server(path_config)
            # init_virtual_ied_interfaces(ied_manager)
            #
            # # Reset status flags for next while-loop iteration
            # ied_manager.is_running = True
            # ied_manager.is_restart = False
            # ied_manager.update_status()

            # as mentioned above, just exit with code 0
            sys.exit(0)

        ied_manager.routine_cycle_count += 1

        print('*******************************************')
        print('*******************************************')
        print('*******************************************')

        # 4. Check Cycle Limits
        if 0 < ied_manager.MAX_CYCLE_COUNT_RESTART <= ied_manager.routine_cycle_count:
            ied_manager.is_running = False
            ied_manager.is_restart = True
            ied_manager.update_status()
            logger.warning('Server restart triggered by maximum routine cycle count.')

        if 0 < ied_manager.MAX_CYCLE_COUNT_DESTROY <= ied_manager.routine_cycle_count:
            ied_manager.ied_config = config.IedConfig()
            ied_manager.is_running = False
            ied_manager.is_abort = True
            ied_manager.update_status()
            logger.warning('Server destroy triggered by maximum routine cycle count.')

    return ied_manager