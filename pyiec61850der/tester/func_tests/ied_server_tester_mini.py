# -*- coding: utf-8 -*-
"""
A test script for running a mini size IED server using only the libIEC61850 server stack

libiec61850 client error code:
ref: https://support.mz-automation.de/doc/libiec61850/net/latest/namespace_i_e_c61850_1_1_client.html
      IedClientError.IED_ERROR_OK = 0
      IedClientError.IED_ERROR_NOT_CONNECTED = 1
      IedClientError.IED_ERROR_ALREADY_CONNECTED = 2
      IedClientError.IED_ERROR_CONNECTION_LOST = 3
      IedClientError.IED_ERROR_SERVICE_NOT_SUPPORTED = 4
      IedClientError.IED_ERROR_CONNECTION_REJECTED = 5
      IedClientError.IED_ERROR_USER_PROVIDED_INVALID_ARGUMENT = 10
      IedClientError.IED_ERROR_ENABLE_REPORT_FAILED_DATASET_MISMATCH = 11
      IedClientError.IED_ERROR_OBJECT_REFERENCE_INVALID = 12
      IedClientError.IED_ERROR_UNEXPECTED_VALUE_RECEIVED = 13
      IedClientError.IED_ERROR_TIMEOUT = 20
      IedClientError.IED_ERROR_ACCESS_DENIED = 21
      IedClientError.IED_ERROR_OBJECT_DOES_NOT_EXIST = 22
      IedClientError.IED_ERROR_OBJECT_EXISTS = 23
      IedClientError.IED_ERROR_OBJECT_ACCESS_UNSUPPORTED = 24
      IedClientError.IED_ERROR_TYPE_INCONSISTENT = 25,
      IedClientError.IED_ERROR_TEMPORARILY_UNAVAILABLE = 26
      IedClientError.IED_ERROR_OBJECT_UNDEFINED = 27
      IedClientError.IED_ERROR_INVALID_ADDRESS = 28
      IedClientError.IED_ERROR_HARDWARE_FAULT = 29
      IedClientError.IED_ERROR_TYPE_UNSUPPORTED = 30
      IedClientError.IED_ERROR_OBJECT_ATTRIBUTE_INCONSISTENT = 31
      IedClientError.IED_ERROR_OBJECT_VALUE_INVALID = 32
      IedClientError.IED_ERROR_OBJECT_INVALIDATED = 33
      IedClientError.IED_ERROR_MALFORMED_MESSAGE = 34
      IedClientError.IED_ERROR_SERVICE_NOT_IMPLEMENTED = 98
      IED_ERROR_UNKNOWN = 99
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import random
import sys
import time
import typing

# Dynamic path resolution prioritizing modern cross-platform compliance
if os.name != 'nt':  # Non-Windows / Containerized targets
    WORK_DIR = Path("/work/")
    sys.path.append(str(WORK_DIR))
    if WORK_DIR.exists():
        print("Checking directory contents in work path...")
        print(os.listdir(str(WORK_DIR)))
        os.environ["PATH"] = f"{WORK_DIR};{os.environ.get('PATH', '')}"

# Third-party performance runtime dependencies
import pandas as pd

# Native C Wrapper Layer Bindings
try:
    import pyiec61850 as iec61850
except:
    try:
        import iec61850
    except:
        from settings import helper
        iec61850 = helper.import_libiec61850()

# Establish structural global basic log pipeline before class declarations
logger = logging.getLogger("iec_simulation")
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


@dataclass
class GlobalRegistry:
    """Core runtime context registry enforcing type constraints across variables."""
    # Simulation operation tracking
    gcount: int = 0
    pf_time_obj: str = ""
    pf_timeset_start: str = ""
    pf_timeset_end: str = ""
    pf_list_timescale: str = ""
    pf_timeset_steps: float = 1.0
    pf_sim_set_flag: bool = False

    # Grid Node Connection Matrix
    port: int = None
    localTcpPort: int = 61850  # Enforce standardized runtime default mapping
    hostname: str = "127.0.0.1"
    dataSource: str = 'random'  # Supported: 'local', 'influxdb', 'random'
    filenameProfile: str = 'test_PV_profile_summer2016.csv'
    INTERVAL = 10

    # Global Temporal Alignment Metrics
    timeMode: str = 'simulation'  # Configurations: 'simulation' or 'absolute'
    startTime: str = '2016-07-01T07:55:00'
    endTime: str = '2016-07-31T23:59:59'
    startTimeUnix: float = 0.0
    endTimeUnix: float = 0.0
    timeAccelarationFactor: int = 1

    # Internal Engine Counters
    uptime_sec: int = 0
    uptime_min: int = 0
    uptime_h: int = 0
    start_time: float = 0.0
    current_time: float = 0.0
    cTimeUnix: float = 0.0
    cTime: str = ''
    intrvl_start: int = 0
    intrvl_duratn: float = 0.0
    intrvl_table: list = field(default_factory=list)
    int_avg_duratn: float = 0.0

    # Active IEC 61850 C Object Interfaces
    iedServer: typing.Any = None
    iedModel: typing.Any = None
    iec_model_dict: dict = field(default_factory=dict)
    iec_model_dict_callback: dict = field(default_factory=dict)
    LD_iedModel: typing.Any = None
    app: list = field(default_factory=list)
    proj: list = field(default_factory=list)
    container_pvsys: list = field(default_factory=list)
    container_pvsys_callback: list = field(default_factory=list)
    container_load: list = field(default_factory=list)
    container_load_callback: list = field(default_factory=list)
    container_all_objects: list = field(default_factory=list)

    current_pfObjId: str = ''
    pvsys_list: list = field(default_factory=list)
    pvsys_PFOID_nr_dict: dict = field(default_factory=dict)
    pvsys_PFOID_pfObj: dict = field(default_factory=dict)
    pvsys_PFOID_list: list = field(default_factory=list)
    load_list: list = field(default_factory=list)
    load_PFOID_nr_dict: dict = field(default_factory=dict)
    load_PFOID_pfObj: dict = field(default_factory=dict)
    load_PFOID_list: list = field(default_factory=list)

    dictUpdateVal: list = field(default_factory=list)
    csv_filename: str = ""

    # Target Application Node Prototyping Defaults
    IedModelName: str = "demoVirtualCLS"
    DeviceName: str = "demoProsumerXY"
    scaleFactor: int = 5
    unitFactor: int = 1000
    demoProsumerXY_mmxu1_f_current_val: float = 50.0
    demoProsumerXY_mmxu1_totw_current_val: float = 25000.0
    demoProsumerXY_mmxu1_totvar_current_val: float = 200.0
    demoProsumerXY_mmxu1_outwset_current_val: float = 1.0

    demoProsumerXY_mmxu1_totw_mag_f: float = 25000.0
    demoProsumerXY_mmxu1_totvar_mag_f: float = 200.0
    demoProsumerXY_mmxu1_f_mag_f: float = 50.0
    demoProsumerXY_mmxu1_outwset_setmag_f: float = 1.0

    derType: str = 'pv'
    clsGUID: str = ''
    pvRatedPower: float = 30000.0
    profileThisDay: pd.DataFrame = None

    # Internal Node Array Output Sinks
    listValWrite: list = field(default_factory=list)
    listControlWrite: list = field(default_factory=list)
    listTstmpWrite: list = field(default_factory=list)
    measurementInfluxdb: str = 'unknown'
    tagInfluxdb: dict = field(default_factory=dict)
    bucketRead: str = '7199_simulation_profile'
    bucketWrite: str = '7601_virtualCLS_testResults'

    clientInfluxdbRead = None
    clientInfluxdbWrite = None

    # Extracted data mapping indicators
    f_index: int = 0
    p_tot_index: int = 0
    q_tot_index: int = 0
    p_pv_max_index: int = 0


@dataclass
class TimeSeriesProfile:
    """Structure isolating localized storage datasets uniformly."""
    listTimestamp: list = field(default_factory=list)
    listTimestampUnix: list = field(default_factory=list)
    listVal: list = field(default_factory=list)


# Instantiate the active registry environment
gvar = GlobalRegistry()
Profile = TimeSeriesProfile()


def update_json_config(config_path: str = 'config.json') -> None:
    """Safely updates registry configuration values while preventing context leaks."""
    path = Path(config_path)
    if not path.exists():
        logger.warning(
            f"Configuration profile path '{config_path}' was not found. Standard initialization defaults applied.")
        return

    with path.open('r', encoding='utf-8') as config_file:
        config = json.load(config_file)
        for key, value in config.items():
            if hasattr(gvar, key):
                setattr(gvar, key, value)


def display_config_info() -> None:
    """Validates configuration parameters directly into system logging pipelines."""
    logger.info('=================   Begin get DER information   =================')
    tracked_parameters = [
        'derType', 'pvRatedPower', 'timeMode', 'startTime', 'endTime',
        'dataSource', 'timeAccelarationFactor', 'scaleFactor', 'unitFactor',
        'clsGUID', 'containerGUID', 'hostname', 'port', 'localTcpPort'
    ]
    for item in tracked_parameters:
        val = getattr(gvar, item, None)
        logger.info(f'{item}: {val}')
        gvar.tagInfluxdb[item] = val

    if gvar.timeMode == 'simulation':
        gvar.startTimeUnix = datetime.fromisoformat(gvar.startTime).replace(tzinfo=timezone.utc).timestamp()
        gvar.endTimeUnix = datetime.fromisoformat(gvar.endTime).replace(tzinfo=timezone.utc).timestamp()
    elif gvar.timeMode == 'absolute':
        gvar.startTimeUnix = datetime.now(timezone.utc).timestamp()
        gvar.endTimeUnix = gvar.startTimeUnix + (60 * 60 * 24 * 365)

    logger.info('=================   End get DER information   =================\n')


def get_UTC_timestamp_uint64() -> int:
    """Returns the unified millisecond timestamp for standard physical profiles."""
    offset_summer_time = 0
    return int(datetime.now(timezone.utc).timestamp() * 1000) - offset_summer_time


def get_simulation_timestamp_uint64(unix_time: float) -> int:
    """Normalizes simulated timeline metrics securely into a standard 64-bit sequence."""
    offset_summer_time = 0
    dt = datetime.fromtimestamp(unix_time, tz=timezone.utc)
    return int(dt.timestamp() * 1000) - offset_summer_time


def create_rotating_log() -> logging.Logger:
    """Builds explicit file rotating systems with standard output fallbacks."""
    active_logger = logging.getLogger(gvar.measurementInfluxdb)
    active_logger.setLevel(logging.DEBUG)

    log_file_path = Path.cwd() / f"{gvar.measurementInfluxdb}_logger.log"

    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=300 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )

    log_formatter = logging.Formatter('%(asctime)s - %(process)d - %(levelname)s - %(message)s')
    file_handler.setFormatter(log_formatter)

    if active_logger.hasHandlers():
        active_logger.handlers.clear()

    active_logger.addHandler(file_handler)
    return active_logger


def load_profile_local_init() -> None:
    """Parses native CSV arrays once, structuring active profiles into global cache frames."""
    profile_path = Path(gvar.filenameProfile)
    if not profile_path.exists():
        logger.error(f"Local mapping context file targets missing: {gvar.filenameProfile}")
        return

    df_profile = pd.read_csv(profile_path, sep=',')
    list_timestamp = list(df_profile['Datetime'])
    list_timestamp_unix = list(df_profile['UNIX'])
    list_val = list(df_profile['Value'])

    idx_valid = [
        idx for idx, tstmp in enumerate(list_timestamp_unix)
        if gvar.startTimeUnix <= tstmp <= gvar.endTimeUnix
    ]

    if not idx_valid:
        logger.warning("No data rows found within specific timeline configurations bounds.")
        return

    Profile.listTimestamp = list_timestamp[idx_valid[0]:idx_valid[-1] + 1]
    Profile.listTimestampUnix = list_timestamp_unix[idx_valid[0]:idx_valid[-1] + 1]
    Profile.listVal = list_val[idx_valid[0]:idx_valid[-1] + 1]

    logger.info('-------------------------------------------------------------------')
    logger.info('PV feedin profile with 1 minute resolution has been loaded')
    logger.info(f'The local profile contains {len(Profile.listVal)} valid timestamps')
    logger.info('-------------------------------------------------------------------\n')


def load_profile_local() -> None:
    """Queries profile timeline metrics on an active daily step slice window securely."""
    logger.info(f'start profile query for the date {gvar.cTime[0:10]}')

    start_time_str = f'{gvar.cTime[0:10]} 00:00:00'
    end_time_str = f'{gvar.cTime[0:10]} 23:59:00'

    try:
        start_idx = 0 if Profile.listTimestamp[0][0:10] == gvar.cTime[0:10] else Profile.listTimestamp.index(
            start_time_str)
        if isinstance(start_idx, list):
            start_idx = start_idx[0]

        end_idx = Profile.listTimestamp.index(end_time_str)
        if isinstance(end_idx, list):
            end_idx = end_idx[0]

        records = pd.DataFrame({
            '_time': Profile.listTimestamp[start_idx:end_idx + 1],
            '_value': Profile.listVal[start_idx:end_idx + 1]
        })
        gvar.profileThisDay = records

        metrics_count = len(records)
        if metrics_count == 0:
            logger.warning('No data found for this day, the simulation will use profile of the previous day')
        elif metrics_count > 1440:
            logger.warning('Found some duplicated data, but no problem, we move on')
        elif metrics_count < 1440:
            logger.warning(f'Found data gap, {1440 - metrics_count} data points are missing.')
        else:
            logger.info('Data query was successful, profile loaded')
    except ValueError as err:
        logger.warning(f"Local parsing window boundary offset configuration mismatch: {err}")


def load_profile_influxdb() -> None:
    """Downloads time-series operational dataset slices across remote target databases."""
    logger.info(f'start profile query for the date {gvar.cTime[0:10]}')

    if not gvar.clientInfluxdbRead:
        logger.error("Database connection session target completely missing.")
        return

    query_api = gvar.clientInfluxdbRead.query_api()
    start_time_iso = f'{gvar.cTime[0:10]}T00:00:00Z'
    end_time_iso = f'{gvar.cTime[0:10]}T23:59:00Z'

    flux_string = (
        f'from(bucket:"{gvar.bucketRead}") |> range(start: {start_time_iso}, stop: {end_time_iso})'
        f' |> filter(fn:(r) => r["GUID"] == "{gvar.clsGUID}")'
        f' |> filter(fn:(r) => r["_field"] == "Value")'
        f' |> aggregateWindow(every: 1m, fn: last, createEmpty: true)'
        f' |> fill(usePrevious: true)'
    )

    try:
        records = query_api.query_data_frame(query=flux_string)
        gvar.profileThisDay = records

        metrics_count = len(records) if records is not None else 0
        if metrics_count == 0:
            logger.warning('No data found for this day, the simulation will use profile of the previous day')
        else:
            logger.info('Data query was successful, profile loaded')
    except Exception as err:
        logger.error(f"Upstream InfluxDB data acquisition failure: {err}")


def get_val_in_profile() -> float:
    """Safely references mapped data intervals from localized runtime slice structures."""
    if gvar.profileThisDay is None or len(gvar.profileThisDay) == 0:
        logger.warning('No profile available, set the values to 0')
        return None

    time_series = list(gvar.profileThisDay['_time'])
    idx_tstmp = [idx for idx, tstmp in enumerate(time_series) if gvar.cTime in str(tstmp)]

    if not idx_tstmp:
        return None

    return gvar.profileThisDay['_value'][idx_tstmp[0]]


def create_IED_model_device(device_name: str) -> None:
    """Registers standard core logic components matching device models."""
    gvar.LD_iedModel = iec61850.LogicalDevice_create(device_name, gvar.iedModel)

    ln_lln0 = iec61850.LogicalNode_create("LLN0", gvar.LD_iedModel)
    iec61850.CDC_ENS_create("Beh", iec61850.toModelNode(ln_lln0), 0)
    iec61850.CDC_ENS_create("Loc", iec61850.toModelNode(ln_lln0), 0)
    iec61850.CDC_ENC_create("Mod", iec61850.toModelNode(ln_lln0), 0, 1)
    iec61850.CDC_DPL_create("NamPlt", iec61850.toModelNode(ln_lln0), 0)

    ln_lphd1 = iec61850.LogicalNode_create("LPHD1", gvar.LD_iedModel)
    iec61850.CDC_ENS_create("PhyHealth", iec61850.toModelNode(ln_lphd1), 0)
    iec61850.CDC_DPL_create("PhyNam", iec61850.toModelNode(ln_lphd1), 0)
    iec61850.CDC_SPS_create("Proxy", iec61850.toModelNode(ln_lphd1), 0)


def create_IED_model_essential() -> None:
    """Configures structural naming roots across the underlying IED library wrappers."""
    gvar.iedModel = 0
    model_name = f"{gvar.IedModelName}_"
    gvar.iedModel = iec61850.IedModel_create(model_name)
    logger.info(f"Auto generating IED model: {model_name}")


def create_demo_IED_model() -> dict:
    """Constructs real-time dataset maps dynamically based on parameter structures."""
    dict_update_val = {}
    pf_attr, iec_da, iec_do_name, iec_da_mag, iec_da_t = [], [], [], [], []

    device_name = gvar.DeviceName
    logger.info(f'LN Name: {device_name}')

    sys_type_prefix = 'PV' if gvar.derType == 'pv' else ('LOAD' if gvar.derType == 'load' else 'UNKNOWN')
    ln_name = f"{sys_type_prefix}1_MMXU0"

    ln_gvar_str = f"{device_name}_LN_{ln_name}"
    setattr(gvar, ln_gvar_str, iec61850.LogicalNode_create(ln_name, gvar.LD_iedModel))
    ln_object = getattr(gvar, ln_gvar_str)

    ds_gvar_str = f"{device_name}_DS_{ln_name}"
    setattr(gvar, ds_gvar_str, iec61850.DataSet_create(ds_gvar_str, ln_object))

    rcb_gvar_str = f"{device_name}_RP_{ln_name}"
    rcb_gvar_id = f"{rcb_gvar_str}_01"
    setattr(gvar, rcb_gvar_str, iec61850.ReportControlBlock_create(rcb_gvar_str, ln_object, rcb_gvar_id, False,
                                                              ds_gvar_str, 1, 31, 233, 0, 10000))

    gvar.DSgvar = getattr(gvar, ds_gvar_str)
    gvar.DSgvarStr = ds_gvar_str
    gvar.RCB_gvar = getattr(gvar, rcb_gvar_str)
    gvar.RCB_gvarStr = rcb_gvar_str

    # Inner Function helper to dynamically bind measurements
    def add_measurement_node(value_tag: str, datatype_path: str, data_attribute: str, mms_type: str) -> None:
        do_gvar = f"{device_name}_DO_{ln_name}_{value_tag}"
        da_gvar = f"{device_name}_DA_{ln_name}_{value_tag}_{datatype_path.replace('.', '_')}"
        da_t_gvar = f"{device_name}_DA_{ln_name}_{value_tag}_t"

        iec_do_name.append(do_gvar)

        if mms_type == "$SP$":
            setattr(gvar, do_gvar,
                    iec61850.CDC_ASG_create(value_tag, iec61850.toModelNode(ln_object), iec61850.CDC_OPTION_UNIT, False))
        else:
            setattr(gvar, do_gvar, iec61850.CDC_MV_create(value_tag, iec61850.toModelNode(ln_object), 0, False))

        do_obj = getattr(gvar, do_gvar)
        setattr(gvar, da_gvar, iec61850.ModelNode_getChild(iec61850.toModelNode(do_obj), datatype_path))

        iec_da.append(getattr(gvar, da_gvar))
        iec_da_mag.append(0)

        if mms_type == "$MX$":
            setattr(gvar, da_t_gvar, iec61850.ModelNode_getChild(iec61850.toModelNode(do_obj), "t"))
            iec_da_t.append(getattr(gvar, da_t_gvar))

        pf_attr.append(data_attribute)

        ds_entry_mms = f"{ln_name}{mms_type}{value_tag}"
        ds_entry_str = f"{device_name}_DS_{ln_name}_{value_tag}"
        setattr(gvar, ds_entry_str, iec61850.DataSetEntry_create(gvar.DSgvar, ds_entry_mms, -1, None))

    # Bind active measurement attributes securely
    add_measurement_node("f", "mag.f", "m:u", "$MX$")
    gvar.f_index = pf_attr.index("m:u")

    add_measurement_node("TotW", "mag.f", "m:P:bus1", "$MX$")
    gvar.p_tot_index = pf_attr.index("m:P:bus1")

    add_measurement_node("TotVar", "mag.f", "m:Q:bus1", "$MX$")
    gvar.q_tot_index = pf_attr.index("m:Q:bus1")

    add_measurement_node("OutWSet", "setMag.f", "Pmax_uc", "$SP$")
    gvar.p_pv_max_index = pf_attr.index("Pmax_uc")

    dict_update_val.update({
        "PF_attr": pf_attr, "Iec_DA": iec_da, "Iec_DO_name": iec_do_name,
        "Iec_DA_mag": iec_da_mag, "Iec_DA_t": iec_da_t
    })

    logger.info(f"Logical Device structure established: {device_name}")
    return dict_update_val


def create_IED_server() -> None:
    gvar.iedServer = iec61850.IedServer_create(gvar.iedModel)
    logger.info("IED server instance created successfully.")


def start_IED_server() -> None:
    iec61850.IedServer_start(gvar.iedServer, gvar.localTcpPort)
    logger.info(f"IED listening network socket online: tcp/{gvar.localTcpPort}")


def init_MX_val() -> None:
    """Pre-populates measurement array baselines based on selected data feeds."""
    gvar.demoProsumerXY_mmxu1_f_mag_f = 50.0
    gvar.demoProsumerXY_mmxu1_totvar_mag_f = 200.0

    if gvar.dataSource == 'random':
        gvar.demoProsumerXY_mmxu1_totw_mag_f = 5000.0
    elif gvar.dataSource in ['local', 'influxdb']:
        if gvar.dataSource == 'local':
            load_profile_local()

        val = get_val_in_profile()
        if val is None:
            gvar.demoProsumerXY_mmxu1_totw_mag_f = 0.0
        else:
            gvar.demoProsumerXY_mmxu1_totw_mag_f = val * gvar.unitFactor * gvar.scaleFactor
    else:
        logger.error(f'Unknown data source target: {gvar.dataSource}')


def update_MX_val() -> None:
    """Mutates simulation metrics tracking physical behaviors iteratively."""
    gvar.demoProsumerXY_mmxu1_f_mag_f += random.randint(-100, 100) / 1000
    gvar.demoProsumerXY_mmxu1_totvar_mag_f += random.randint(-100, 100) / 1000

    if gvar.dataSource == 'random':
        gvar.demoProsumerXY_mmxu1_totw_mag_f += random.randint(-3000, 3000) / 10000
    elif gvar.dataSource in ['local', 'influxdb']:
        try:
            val = get_val_in_profile()
            if val is not None:
                val_profile = val * gvar.unitFactor * gvar.scaleFactor
                val_limit = gvar.demoProsumerXY_mmxu1_outwset_current_val * gvar.pvRatedPower * gvar.unitFactor * gvar.scaleFactor
                gvar.demoProsumerXY_mmxu1_totw_mag_f = min(val_profile, val_limit)
        except Exception as err:
            logger.warning(f'Iterative metric recalculation sequence failed: {err}')
            gvar.demoProsumerXY_mmxu1_totw_mag_f = 0.0


def init_SP_val(val: float) -> None:
    gvar.demoProsumerXY_mmxu1_outwset_setmag_f = val


def update_SP_val(val: float) -> None:
    """Updates server-side operational setpoint boundaries safely."""
    if not gvar.container_pvsys:
        return
    dict_update_val = gvar.container_pvsys[0]
    iec_da = dict_update_val['Iec_DA']
    iec_da_mag = dict_update_val['Iec_DA_mag']

    gvar.demoProsumerXY_mmxu1_outwset_setmag_f = val
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da[gvar.p_pv_max_index]), val)
    iec_da_mag[gvar.p_pv_max_index] = val


def update_IED_attr() -> None:
    """Syncs localized simulator parameters safely down into target C-layer attributes."""
    if not gvar.container_pvsys:
        return

    dict_update_val = gvar.container_pvsys[0]
    iec_da = dict_update_val['Iec_DA']
    iec_da_t = dict_update_val['Iec_DA_t']

    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da[gvar.f_index]),
                                            gvar.demoProsumerXY_mmxu1_f_mag_f)
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da[gvar.q_tot_index]),
                                            gvar.demoProsumerXY_mmxu1_totvar_mag_f)
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da[gvar.p_tot_index]),
                                            gvar.demoProsumerXY_mmxu1_totw_mag_f)

    # Process structured timestamp modifications
    timestamp_func = get_UTC_timestamp_uint64 if gvar.timeMode == 'absolute' else lambda: get_simulation_timestamp_uint64(
        gvar.cTimeUnix)
    current_ts = timestamp_func()

    iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da_t[gvar.q_tot_index]),
                                              current_ts)
    iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da_t[gvar.f_index]), current_ts)
    iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da_t[gvar.p_tot_index]),
                                              current_ts)

    gvar.demoProsumerXY_mmxu1_f_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(
        iec_da[gvar.f_index]))
    gvar.demoProsumerXY_mmxu1_totw_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer,
                                                                                      iec61850.toDataAttribute(
                                                                                          iec_da[gvar.p_tot_index]))
    gvar.demoProsumerXY_mmxu1_totvar_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer,
                                                                                        iec61850.toDataAttribute(
                                                                                            iec_da[gvar.q_tot_index]))
    gvar.demoProsumerXY_mmxu1_outwset_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer,
                                                                                         iec61850.toDataAttribute(iec_da[
                                                                                                                 gvar.p_pv_max_index]))


def get_SP_control() -> bool:
    """Interrogates standard external configuration updates executing remote adjustments."""
    if not gvar.container_pvsys:
        return False

    dict_pvsys = gvar.container_pvsys[0]
    iec_da = dict_pvsys['Iec_DA']
    iec_da_mag = dict_pvsys['Iec_DA_mag']

    outwset_server = iec_da_mag[gvar.p_pv_max_index]
    outwset_client = round(
        iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da[gvar.p_pv_max_index])), 2)

    is_controlled = False
    if outwset_server != outwset_client:
        logger.info(
            '************************************\n***  control command received ******\n************************************')
        logger.info(f"OutWSet changed: {outwset_server} -> {outwset_client}")

        iec_da_mag[gvar.p_pv_max_index] = outwset_client
        gvar.demoProsumerXY_mmxu1_outwset_setmag_f = outwset_client
        is_controlled = True

    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(iec_da[gvar.p_pv_max_index]),
                                            gvar.demoProsumerXY_mmxu1_outwset_setmag_f)
    gvar.demoProsumerXY_mmxu1_outwset_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer,
                                                                                         iec61850.toDataAttribute(iec_da[
                                                                                                                 gvar.p_pv_max_index]))
    return is_controlled


def initialize_iedServer() -> None:
    """Bootstraps data parameters initializing target simulation clusters."""
    logger.info('=================   Begin IEC 61850 server initialization    =================')
    create_IED_model_essential()
    create_IED_model_device(gvar.DeviceName)

    dict_update_val = create_demo_IED_model()
    gvar.container_all_objects.append(dict_update_val)
    gvar.container_pvsys.append(dict_update_val)

    create_IED_server()
    start_IED_server()

    logger.info('IED LD count: {}'.format(iec61850.IedModel_getLogicalDeviceCount(gvar.iedModel)))

    obj_dataset = iec61850.IedModel_lookupDataSet(gvar.iedModel,
                                             f"{gvar.IedModelName}_{gvar.DeviceName}/PV1_MMXU0${gvar.DSgvarStr}")
    if obj_dataset is not None:
        logger.info(f'Found dataset: {obj_dataset.name}. Size: {iec61850.DataSet_getSize(obj_dataset)}')
    else:
        logger.warning('No matching dataset available within structural parameters.')
    logger.info('=================   End IEC 61850 server initialization    =================\n')


def initialize_measurements() -> None:
    """Initializes operational metrics tracking baseline system parameters cleanly."""
    logger.info('=================   Begin measurement initialization    =================')
    init_MX_val()
    init_SP_val(100.0)
    update_SP_val(100.0)
    update_IED_attr()
    logger.info('=================   End measurement initialization    =================\n')


def update_measurements() -> None:
    """Ticks timeline sequences processing active daily profiles iteratively."""
    logger.info(f'Actual current datetime: {gvar.cTime}; current Unix time: {gvar.cTimeUnix}')

    # Establish target daily data boundaries cleanly
    rounded_unix = round(int(gvar.cTimeUnix) / 10) * 10
    ctime_string = datetime.fromtimestamp(rounded_unix, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    seconds_offset = int(ctime_string[-2:])
    if seconds_offset in range(1, 31):
        ctime_string = f"{ctime_string[:-2]}00"
    elif seconds_offset in range(31, 60):
        minutes_offset = int(ctime_string[-5:-3])
        if minutes_offset < 59:
            ctime_string = f'{ctime_string[:-6]}:{minutes_offset + 1:02d}:00'
        else:
            ctime_string = f"{ctime_string[:-2]}00"

    gvar.cTime = ctime_string
    logger.info(f'Current datetime string for data query: {gvar.cTime}')

    logger.info('Update measurement values')
    update_MX_val()
    update_IED_attr()

    logger.info('Current measurements (random/profile/time series database):')
    logger.info('TotW: {} W; TotVAR: {} VAr; f: {} Hz'.format(gvar.demoProsumerXY_mmxu1_totw_mag_f,
                                                              gvar.demoProsumerXY_mmxu1_totvar_mag_f,
                                                              gvar.demoProsumerXY_mmxu1_f_mag_f))

    logger.info('Current measurements IEC 61850:')
    logger.info('TotW: {} W; TotVAR: {} VAr; f: {} Hz'.format(gvar.demoProsumerXY_mmxu1_totw_current_val,
                                                              gvar.demoProsumerXY_mmxu1_totvar_current_val,
                                                              gvar.demoProsumerXY_mmxu1_f_current_val))

    logger.info('Current setpoint value:')
    logger.info('OotWSet: {}'.format(gvar.demoProsumerXY_mmxu1_outwset_current_val))

    if '00:00:00' in gvar.cTime:
        load_profile_local()

    update_MX_val()
    update_IED_attr()


def server_initialization() -> None:
    """Coordinates startup procedures preparing real-time interface engines."""
    gvar.cTime = gvar.startTime
    gvar.cTimeUnix = gvar.startTimeUnix

    if gvar.dataSource == 'local':
        load_profile_local_init()

    initialize_iedServer()
    initialize_measurements()


def server_routine() -> None:
    """Main system execution loop managing dynamic operational phases."""
    while gvar.cTimeUnix < gvar.endTimeUnix:
        timer_start = time.time()
        logger.info('\n--------------------------- Server Sequence Run ---------------------------')
        try:
            update_measurements()
        except Exception as err:
            logger.warning(f'Iterative profile step resolution crashed, skipping step frame: {err}')

        is_controlled = False
        for _ in range(100):
            if get_SP_control():
                is_controlled = True
            time.sleep(gvar.INTERVAL / 100)

        logger.info(
            f"{'Control command executed' if is_controlled else 'No actions required'} during last interval step iteration.")

        gvar.listValWrite.append(gvar.demoProsumerXY_mmxu1_totw_mag_f)
        gvar.listControlWrite.append(gvar.demoProsumerXY_mmxu1_outwset_current_val)
        gvar.listTstmpWrite.append(gvar.cTime)

        timer_end = time.time()
        processing_time = timer_end - timer_start - gvar.INTERVAL
        logger.info(f'Processing footprint load for active iteration: {processing_time:.4f} seconds')

        gvar.cTimeUnix += gvar.INTERVAL - processing_time


if __name__ == '__main__':
    # update_json_config()
    logger = create_rotating_log()
    display_config_info()
    server_initialization()
    server_routine()
