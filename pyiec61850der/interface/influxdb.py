# -*- coding: utf-8 -*-
"""
Definition of the Influxdb Class and core functions for the influxdb interface.

"""

from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
from pandas import DataFrame
from typing import TYPE_CHECKING
import pandas as pd

from settings import helper

from typing import TYPE_CHECKING
import logging
if TYPE_CHECKING:
    from interface.data_buffer import DataBuffer
    from interface.time_series import TimeSeries
from settings.helper import rotating_logger
logger = logging.getLogger(f"main_logger.{__name__}")


STANDARD_INFLUXDB_TIME_FORMAT: str = '%Y-%m-%dT%H:%M:%SZ'
INFLUXDB_UPLOAD_TIME_FORMAT: str = '%Y-%m-%dT%H:%M:%S.%fZ'

"""
=======================================================================
=================   Begin Essential routine functions =================
=======================================================================
"""

def get_cvalue(data_buffer: 'DataBuffer') -> helper.StdDataType.AllTypes:

    ctime_unix = data_buffer.time_manager.ctime_unix
    val_new = data_buffer.db_timeseries.get_value_in_timeseries(ctime_unix, field_key='value')

    return val_new



class InfluxdbHandler:
    measurement_read: str = 'unknown'  # string of the _measurement for reading from influxdb
    measurement_write: str = 'unknown'  # string of the _measurement for writing to influxdb
    # tags = {}
    read_bucket: str | None = None
    write_bucket: str | None = None
    read_handler: InfluxDBClient | None = None
    write_handler: InfluxDBClient | None = None
    read_token: str | None = None
    write_token: str | None = None
    read_org: str | None = None
    read_url: str | None = None
    write_org: str | None = None
    write_url: str | None = None
    is_secret_loaded: bool = False

    def init_influx_conn_obj(self) -> tuple[bool, bool]:
        """
        Initialize or refresh the influxdb interface object
        """

        # influxdb interface initialisation
        logger.info('-------------------------------------------------------------------')
        logger.info('Start influxdb interface initialisation')

        is_read_success = self.init_read_handler()
        is_write_success = self.init_write_handler()

        logger.info('End of influxdb interface initialisation')
        logger.info('-------------------------------------------------------------------\n')

        return is_read_success, is_write_success

    def init_read_handler(self) -> bool:
        is_success = False
        try:
            logger.info('Try to initialize influxdb handler for data reading')
            read_handler = connect_influxdb(self.read_url, self.read_org, self.read_token)
            self.read_handler = read_handler
            is_success = True
        except Exception as e:
            logger.exception('Connecting to influxdb failed, use local profile instead for loading profiles')
            logger.exception(e)
        return is_success

    def init_write_handler(self) -> bool:
        is_success = False
        try:
            logger.info('Try to initialize influxdb handler for data uploading')
            write_handler = connect_influxdb(self.write_url, self.write_org, self.write_token)
            self.write_handler = write_handler
            is_success = True
        except Exception as e:
            logger.exception('Connecting to influxdb failed, upload data_buffer records may not work properly')
            logger.exception(e)
        return is_success

    def close_influx_conn(self):
        try:
            self.read_handler.close()
            self.write_handler.close()
            logger.info('Successfully closed open influxdb connection')
        except Exception as err:
            logger.exception('Influxdb connection can not be closed as it already had a problem, just refresh it.')
            logger.exception(err)

"""
=======================================================================
=================   End Essential routine functions =================
=======================================================================
"""


def connect_influxdb(url: str = None,
                     org: str = None,
                     token: str = None, **kwargs) -> InfluxDBClient | None:
    """
    Initialise connection to influxdb, create read or write handlers.

    Currently for all influxdb actions, configuration in data_buffer.influxdb will be used both for read (data
    acquisition) and write (upload records). It is assumed that one organisation would use the same influxdb for the
    storage of historical data and incoming real-time data. Using the influxdb config file in ./secret, different
    read/write handlers could be configured for multiple influxdb urls and orgs using valid tokens.

    NOTE: the write handlers may be associated with a token that only has the access to one specific bucket.
        This limitation is not reflected here. The write_token is only used to establish the writing API service.
    ----------

    Parameters
    ----------
    url: URL of influxdb
    org: to which org are the tokens assigned
    token: token for reading/writing data, left empty will cause returning the client of type None
    **kwargs: place_holder for other supplementary keywords argument

    Returns
    -------
    influxdb_client: reading/writing handler for influxdb API
    """

    logger.info('=================   Begin init influxdb connection    =================')
    logger.info(f"Try to init connection to server {url}")

    INFLUX_CONN_TIMEOUT = 3000

    if token is not None:
        # TODO: add the timeout of influxdb client to config
        influxdb_client = InfluxDBClient(url=url, token=token, org=org, debug=False, timeout=INFLUX_CONN_TIMEOUT)
        # here we set a higher timeout to disable DEBUG:Rx:timeout log message.

        health = influxdb_client.ping()
        if health:
            logger.info('Influxdb client is ready to connect')
        else:
            logger.error('Influxdb client has no connection to server')
    else:
        influxdb_client = None

    logger.info('=================   End init influxdb connection    =================\n')

    return influxdb_client

def convert_influx_time_str(time_str: str) -> str:
    """
    Convert a time string from other format into the time format that influxdb supports.
    
    Parameters
    ----------
    time_str: original time string

    Returns
    -------
    time_str_new: new influxdb compatible time string after conversion
    """
    
    if time_str[-1] != 'Z':
        time_str = time_str + 'Z'
    if helper.time_string_validator(time_str, '%Y-%m-%d %H:%M:%SZ') or \
            helper.time_string_validator(time_str, '%Y-%m-%d %H:%M:%S'):
        time_str_new = time_str.replace(' ', 'T')  # influxdb require a T in the middle!!
        return time_str_new
    else:
        return time_str

def get_end_time_by_range(start_time_str: str, time_range: int|float) -> str:
    """
    A function to create the time string as the end time stamp for an influxdb data query.

    Parameters
    ----------
    start_time_str: start time string (compatible to influxdb time format)
    time_range: numeric value of the time range for query

    Returns
    -------
    end_time_str: end time string for data query
    """

    end_time_str = helper.time_unix_to_str(
        helper.time_utc_str_to_unix(start_time_str, STANDARD_INFLUXDB_TIME_FORMAT) + time_range,
        STANDARD_INFLUXDB_TIME_FORMAT)

    return end_time_str

def validate_influx_time_str(time_str: str) -> bool:
    """
    Validate whether a string is compatible to the influxdb string format.

    Parameters
    ----------
    time_str: target time string to be validated.
    """

    if not helper.time_string_validator(time_str, STANDARD_INFLUXDB_TIME_FORMAT):
        logger.error(f'Time string formats {time_str} and {STANDARD_INFLUXDB_TIME_FORMAT} do not match, \
                     can not proceed to querying data from influxdb'),
        return False
    else:
        return True

def build_flux_query(start_time_str: str,
                     measurement: str|None,
                     bucket: str,
                     tags: dict|None,
                     field_key: str = '_value',
                     time_range: int | float = 86400,
                     interval: int | float = 60, **kwargs) -> str:
    """
    This function preps the flux_query for usage in a influxdb query request. Using the default time_range 86400 [s],
    the profile will be queried on a daily basis.

    Influxdb requires the following time string format:
        - '%Y-%m-%dT%H:%M:%S' for local time
        - '%Y-%m-%dT%H:%M:%SZ' for UTC time

    TODO: consider using Unix time to prep the flux_query, converting time string is kind of annoying.

    Parameters
    ----------
    start_time_str: start time string in compliance with influxdb time format
    measurement: name of the influxdb parameter "_measurement"
    bucket: name of the influxdb parameter "bucket" for data query
    tags: a dict object containing key-value pairs that will be used as filter (tags) for influxdb data query.
            Currently we use single keyword value pair.
    field_key: key for the influxdb parameter "_field" localise expected parameter value
    time_range: desired time range for the data query in [seconds]
    interval: t_interval_data_update for data aggregation, could be understood as data resolution in [seconds]
    **kwargs: place_holder for other supplementary keywords argument

    Returns
    -------
    flux_query: a complete string that encodes full information of an influx data query.
    """

    end_time_str = get_end_time_by_range(start_time_str, time_range)
    flux_query = f'from(bucket:"{bucket}") |> range(start: {start_time_str}, stop: {end_time_str})'

    if measurement:
        flux_query += f' |> filter(fn:(r) => r["_measurement"] == "{measurement}")'

    if tags:
        for key, val in tags.items():
            if key == 'guid':
                # special treatment for GUID due to case sensitivity
                flux_query += f' |> filter(fn:(r) => r["guid"] == "{val}" or r["GUID"] == "{val}")'
            else:
                flux_query += f' |> filter(fn:(r) => r["{key}"] == "{val}")'
    else:
        logger.warning(f'Primary tags is None, data query may return multiple data sets')

    if field_key:
        # TODO: consider add the field name as key in the fieldbus_conn_config, but that could be over-engineering
        flux_query += f' |> filter(fn:(r) => r["_field"] == "{field_key}")'
    flux_query += f' |> aggregateWindow(every: {interval}s, fn: last, createEmpty: true) \
                    |> fill(usePrevious: true) \
                    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
    return flux_query

def validate_influx_records(influx_records: DataFrame | list,
                            field_key: str,
                            val_count_ref: int) -> tuple[DataFrame, bool, int]:
    """
    TODO: docstring

    NOTE: this func makes sure that the returend object influx_records is a DataFrame, not a list
    Parameters
    ----------
    influx_records
    field_key
    val_count_ref

    Returns
    -------

    """

    is_records_valid: bool = False
    if isinstance(influx_records, list):
        influx_records = influx_records[0]
        logger.warning('Found multiple data sets in influxdb with given configuration, take the first set')

    num_records: int = influx_records.shape[0]
    # in the last line of query flux, columnKey: ["_field"] causes the original column name to be remained
    if field_key is not None:
        influx_records = influx_records.rename(columns={field_key: 'value'})

    if num_records == 0:
        logger.warning('No data found for this day, the simulation will use profile of the previous day')
    elif num_records > val_count_ref:
        logger.warning('Found some duplicated data, no action, move on to the next timestep')
    elif num_records < val_count_ref:
        logger.warning(f'Found data gap, {val_count_ref - len(influx_records)} data points are missing.')
        logger.info('Not a problem, the server will use the previous value in the simulation')
    else:
        is_records_valid = True
        logger.info('The number of data entries is correct.')

    return influx_records, is_records_valid, num_records


def update_time_series(time_series: 'TimeSeries', influx_records: DataFrame, options: dict) -> 'TimeSeries':
    """
    Initialise an instance of the class TimeSeries, fill the attributes based on the conducted influxdb data query.

    Parameters
    ----------
    time_series: existing time_series instance
    influx_records: the DataFrame instance as output of the influxdb data query
    options: the same options used for the influx data query

    Returns
    -------
    time_series: the TimeSeries instance, which can be directly used to update the value of DataBuffer instances.
    """

    record_count = influx_records.shape[0]
    # TODO: to avoid keeping the para name mapping to influxdb, we just dump field_key if IEC 61850 jargons are used
    #  as tags -> this leads to empty options['field_key']. In this case, we assume the last column is the data column.
    #  this approach might be error-prone,  find a better way to handle this.
    key = options['field_key'] if options['field_key'] else influx_records.columns[-1]
    influx_records = influx_records.rename(columns={'_time': 'time', key: 'value'})
    if 'unix' in influx_records.columns:
        influx_records = influx_records.rename(columns={'unix': 'time_unix'})
    else:
        influx_records['time_unix'] = influx_records['time'].astype('int64') // 10**9
    time_series.data_active = influx_records
    time_series.data_count = record_count
    time_series.provider = options['bucket']
    for k, v in options['tags'].items():
        setattr(time_series, k, v)
    time_series.time_window_str = (influx_records.at[0, 'time'], influx_records.at[record_count - 1, 'time'],)

    return time_series

def get_dataframe_from_influxdb(query_handler: InfluxDBClient, options: dict) -> DataFrame:
    """
    This method will get the time series data directly from influxdb using the flux language defined in influxdb.

    Input:
        - query_handler: influxdb reading handler -> read_handler
        - bucket: bucket name for the data query
        - tags: keyword-value pair(s) for the influxdb tags as filter. Currently we use single keyword value pair.
        - field_key: the name of the '_field' to
        - t_interval_data_update: time resolution of the data query, written as string, e.g. '1m', '15m', etc.
        -

    Output:
        - records: take the records in the response of influxdb as output variable
    """

    required_keys = {"start_time_str", "measurement", "bucket", "tags", "field_key", "time_range", "t_interval_data_update", }
    assert required_keys <= options.keys(), f"Unfold missing keys: {required_keys - options.keys()}"

    influx_records: DataFrame | None = None

    start_time_str = options["start_time_str"]
    measurement = options["measurement"]
    bucket = options["bucket"]
    tags = options["tags"]
    field_key = options["field_key"]
    time_range = options["time_range"]

    start_time_str = convert_influx_time_str(start_time_str)
    
    logger.info('=================   Begin query data from influxdb   =================')
    logger.info(f'Start profile query, start time stamp {start_time_str}, time range {time_range} seconds')

    is_valid_time_str = validate_influx_time_str(start_time_str)

    if is_valid_time_str:
        flux_query =  build_flux_query(start_time_str, None, bucket, tags, field_key,
                                       time_range)

        try:
            influx_records = query_handler.query_api().query_data_frame(query=flux_query)
        except Exception as exc:
            logger.exception('Getting profile from influxdb has failed.')
            logger.exception(exc)
    logger.info('=================   End query data from influxdb   =================\n')

    return influx_records

def update_time_series_by_dataframe(time_series: 'TimeSeries', query_handler: InfluxDBClient,
                                    options: dict) -> 'TimeSeries':
    logger.info('=================   Begin initialise TimeSeries instance using influxdb data  =================')
    influx_records = get_dataframe_from_influxdb(query_handler, options)

    time_range = options["time_range"]
    interval = options["t_interval_data_update"]
    field_key = options["field_key"]

    val_count_ref = int(time_range / interval)
    influx_records, is_records_valid, num_records  = validate_influx_records(influx_records, field_key, val_count_ref)
    if num_records > 0:
        time_series = update_time_series(time_series, influx_records, options)
        time_series.STANDARD_TIME_STRING = STANDARD_INFLUXDB_TIME_FORMAT
    else:
        logger.warning('Influxdb returned an empty list, check the data query construction again.')

    logger.info('=================   End initialise TimeSeries instance using influxdb data   =================\n')

    return time_series


def refresh_daily_time_series(data_buffer: 'DataBuffer') -> 'DataBuffer':
    """
    TODO: add docstring
    86400 corresponds to total seconds of a day

    TODO: make the time range and interval parameters/options

    Parameters
    ----------
    data_buffer

    Returns
    -------

    """

    try:
        ctime_unix = data_buffer.time_manager.ctime_unix - data_buffer.time_series.offset

        ctime_str = helper.time_unix_to_str(ctime_unix, time_str_format='%Y-%m-%d %H:%M:%S')
        start_time_str = helper.get_time_str_by_diff(ctime_str, time_str_format='%Y-%m-%d %H:%M:%S', time_diff=-300)
        kw_tag = build_query_tags(data_buffer)

        # NOTE: _value is the default field key in influxdb data structure, this does not guarantee that the data
        # records can be found!
        field_key = data_buffer.fieldbus_conn_config.get('field_key', '_value')
        # NOTE: only use the default _value if IEC 61850 tags are not in use
        if field_key == '_value' and data_buffer.is_iec61850_tag:
            field_key = None

        options = {"start_time_str": start_time_str,
                   "measurement": data_buffer.influxdb.measurement_read,
                   "bucket": data_buffer.influxdb.read_bucket,
                   "tags": kw_tag,
                   "field_key": field_key,
                   "time_range": 86400, "t_interval_data_update": 60, }
        data_buffer.time_series = update_time_series_by_dataframe( data_buffer.time_series,
                                                                   data_buffer.influxdb.read_handler, options)
    except Exception as e:
        logger.exception('Failed to create new TimeSeries instance by querying influxdb data.')
        logger.exception(e)

    return data_buffer

def build_iec61850_tags(data_buffer: 'DataBuffer', **kwargs) -> dict:
    """
    This method maps the IEC 61850 information to a dictionary object as required by the write handler of
    influxdb API, and then return the dict for further use by the influxdb write handler.

    Parameters
    ----------
    data_buffer: the DataBuffer instance that requires influxdb write action.
    kwargs: keyword args passed from the upper level function, if any exists.

    Returns
    -------
    tags: a dictionary composing all IEC 61850 relevant attributes, can be used by influxdb write handler
    """



    tags = {'LD': data_buffer.iec61850_do.obj_ref_map['ld'].name,
            'LN': data_buffer.iec61850_do.obj_ref_map['ln'].name[:4],  # dump the suffix of LN name
            'DO': data_buffer.iec61850_do.name,
            'DA': data_buffer.iec61850_do.get_monitor_da_name(),
            'CDC': data_buffer.iec61850_do.cdc,
            'FC': data_buffer.iec61850_do.fcda,
            }
    tags.update(kwargs)

    return tags

def build_generic_tags(data_buffer: 'DataBuffer', **kwargs) -> dict:
    """
    This method maps only generic information to a dictionary object as required by the write handler of
    influxdb API, and then return the dict for further use by the influxdb write handler.

    Parameters
    ----------
    data_buffer: the DataBuffer instance that requires influxdb write action.
    kwargs: keyword args passed from the upper level function, if any exists.

    Returns
    -------
    tags: a dictionary composing generic attributes, can be used by influxdb write handler
    """

    tags = {'guid': data_buffer.guid,
            'container': data_buffer.container_name,  # container name may be redundant to guid
            }
    tags.update(kwargs)

    return tags

def build_query_tags(data_buffer: 'DataBuffer', **kwargs) -> dict:
    """
    It turned the guid would be enough to locate the data points in influxdb. So keep the query text simple.

    Parameters
    ----------
    data_buffer
    kwargs

    Returns
    -------

    """

    tags = {k: v for k, v in data_buffer.fieldbus_conn_config.items() if k.lower() == 'guid'}
    if tags =={} or data_buffer.is_iec61850_tag:
        tags.update(build_iec61850_tags(data_buffer, **kwargs))

    tags.update(kwargs)
    return tags


def prep_records(data_buffer: 'DataBuffer', df: DataFrame = None, **kwargs) -> list:
    """
    This method helps to prepare a well-constructed data object that will be passed to the influxdb write handler.

    Currently we rebuild the dataframe into a list of dictionaries, during the process it is also easy to define
    influxdb data tags using standardised IEC 61850 naming convention. This approach works well when the batch
    for writing is not huge. However, with large data amounts, this process could consume much more time than
    directly dealing the DataFrame objects.

    IMPORTANT NOTIONS:
     - adding tags should not be protocol specific, but now we specify some IEC 61850 tags. In future
     developments, we need to find a way to generalise it.
     - the attr data_buffer.is_iec61850_tag decides whether IEC 61850 specific tags should be added to the query.
     Those tags are particularly useful when the guid of a data entry refers to data with underlying sub-structure.
     - the time format conversion using STANDARD_INFLUXDB_TIME_FORMAT could cause error! Need to find a solution to deal with it.
     - always use UTC time for data upload into influxdb for consistency

    Parameters
    ----------
    data_buffer: the DataBuffer instance that requires influxdb write action.
    df: Optional DataFrame snapshot to process. If None, defaults to reading data_buffer.records.data_for_upload.
    kwargs: keyword args passed from the upper level function, if any exists.

    Returns
    -------
    influx_records: a list containing all influx records for the next write handler operation.
    """

    # 1. Capture source DataFrame
    source_df = df if df is not None else data_buffer.records.data_for_upload

    if source_df is None or source_df.empty:
        logger.debug(
            f"[prep_records] DO '{getattr(data_buffer, 'id', 'unknown')}': source_df is empty or None. Returning 0 records.")
        return []

    initial_row_count = len(source_df)
    logger.debug(
        f"[prep_records] DO '{getattr(data_buffer, 'id', 'unknown')}': Input DataFrame row count = {initial_row_count}")

    # Log raw sample timestamps from column 't' to inspect decimal vs integer format
    if 't' in source_df.columns:
        sample_raw_t = source_df['t'].head(5).tolist()
        sample_raw_v = source_df['value_iec61850'].head(5).tolist()
        logger.debug(f"[prep_records] First 5 raw 't' values: {sample_raw_t}")
        logger.debug(f"[prep_records] First 5 raw IEC61850 DA values: {sample_raw_v}")
    else:
        logger.warning("[prep_records] Column 't' not found in source_df!")

    # 2. Reset index & convert numeric columns
    data: DataFrame = source_df.reset_index(drop=True)

    # 1. Drop rows where timestamp 't' is missing or invalid
    data = data.dropna(subset=['t'])
    if data.empty:
        return []

    # 2. Handle numeric columns: convert to float and replace NaN with None/0 or drop
    num_cols = data.select_dtypes(include=["number", "object"]).columns
    for col in num_cols:
        if col != 't':
            # Convert numeric columns to float, coercion handles invalid strings/NaNs
            data[col] = pd.to_numeric(data[col], errors='coerce')

    # Replace NaN/NaT with None so dict conversion excludes them or handles them cleanly
    data = data.where(pd.notnull(data), None)

    influx_fields: list = data.to_dict(orient='records')
    influx_records = []
    generated_timestamps = []

    # 3. Format records and capture output time strings
    for idx, field in enumerate(influx_fields):
        # Clean fields: remove key-values that are None so InfluxDB doesn't throw type errors
        cleaned_fields = {k: v for k, v in field.items() if k != 't' and v is not None}

        if not cleaned_fields:
            continue  # Skip empty points when inverter is offline

        if data_buffer.is_iec61850_tag:
            tags = build_iec61850_tags(data_buffer, **kwargs)
            tags.update(build_generic_tags(data_buffer, **kwargs))
        else:
            tags = build_generic_tags(data_buffer, **kwargs)

        # Ensure ISO format with sub-second resolution (nanoseconds/microseconds)
        raw_time = data.loc[idx, 't']
        formatted_time = pd.to_datetime(raw_time, utc=True).strftime(INFLUXDB_UPLOAD_TIME_FORMAT)

        generated_timestamps.append(formatted_time)

        record: dict = {
            'tags': tags,
            'time': formatted_time,
            'measurement': data_buffer.influxdb.measurement_write,
            'fields': cleaned_fields,
        }
        influx_records.append(record)

    # 4. Diagnostic Logging: Compare input vs output record counts & timestamp uniqueness
    final_record_count = len(influx_records)
    unique_timestamps_count = len(set(generated_timestamps))

    logger.debug(f"[prep_records] Completed formatting for DO '{getattr(data_buffer, 'id', 'unknown')}':")
    logger.debug(f"  • Input rows: {initial_row_count}")
    logger.debug(f"  • Formatted records generated: {final_record_count}")
    logger.debug(f"  • Unique formatted timestamps: {unique_timestamps_count}")

    if unique_timestamps_count < final_record_count:
        duplicates_lost = final_record_count - unique_timestamps_count
        logger.error(
            f"  ⚠️ TIMESTAMP COLLISION DETECTED! {duplicates_lost} out of {final_record_count} "
            f"records generated identical timestamp strings! InfluxDB will overwrite these points, "
            f"causing missing rows in database."
        )
        logger.error(f"  • Sample generated timestamps: {generated_timestamps[:5]}")

    return influx_records

def write_records(write_handler: InfluxDBClient,
                  influx_records: DataFrame | list,
                  bucket: str,
                  options: WriteOptions | None = None) -> bool:
    """
    This method simply performs a write action to upload data to influxdb. Write handler should have been created
    during the service initialisation.

    NOTE: To distinguish from the class Record and its instances, we use the var name influx_records to denote any
    data (either a DataFrame or a list of DataFrame instances) that are transferred between any function module and the
    influxdb.

    Parameters
    ----------
    write_handler: influxdb client object as the write handler
    influx_records: data records to be writen
    bucket: bucket name in the influxdb instance
    options: options for writing data to influxdb using the handler of influxdb API

    Returns
    -------
    A boolean value to determine whether the write action was successful (it does not necessarily mean that the data
    have been written to the right buckets under the correct _measurement! )
        True -> writing action was successful
#       False -> writing to influxdb failed, the process should wait for the next trigger
    """

    if not options:
        options = WriteOptions(batch_size=5000, flush_interval=10_000, jitter_interval=2_000, retry_interval=5_000,
                               max_close_wait=30_000)

    assert [isinstance(item, list) for item in influx_records]
    try:
        write_api = write_handler.write_api(write_options=options)
        write_api.write(bucket=bucket, record=influx_records)
        return True
    except Exception as exc:
        logger.warning('Something went wrong when writing data to influxdb.')
        logger.exception(exc)
        return False

def _extract_and_snapshot_buffers(data_buffers):
    """
    Extracts pending data snapshots for a group of data_buffers under lock.
    Returns: list of tuples (data_buffer, pending_df)
    """
    snapshots = []
    for db in data_buffers:
        with db._record_lock:
            if not db.records.data_for_upload.empty:
                pending_df = db.records.data_for_upload.copy()
                snapshots.append((db, pending_df))
    return snapshots


def _rollback_snapshots(snapshots, max_retry_rows=1000):
    """
    Restores captured data snapshots back to their respective data_buffers if upload fails.
    """
    for db, pending_df in snapshots:
        with db._record_lock:
            combined_df = pd.concat([pending_df, db.records.data_for_upload], ignore_index=True)
            db.records.data_for_upload = combined_df.tail(max_retry_rows).reset_index(drop=True)


def _clear_snapshots(snapshots):
    """
    Clears data_for_upload ONLY after a successful batch upload.
    """
    for db, pending_df in snapshots:
        with db._record_lock:
            # Drop the rows that were successfully transmitted
            # keeping any newly accumulated rows during the HTTP POST
            db.records.reset_data_for_upload()

def _bulk_upload_per_connection(write_handler, bucket_name, data_buffers) -> bool:
    """
    Prepares records from all data_buffers sharing the same connection,
    performs a SINGLE ping check, and transmits a single batch write payload.
    """
    if not write_handler:
        logger.warning("InfluxDB write handler does not exist. Skipping bulk upload.")
        return False

    # 1. Single ping check per connection (NOT per DO)
    if not write_handler.ping():
        logger.warning("InfluxDB connection ping failed. Aborting bulk upload.")
        return False

    # 2. Extract snapshots from all buffers under their individual locks
    snapshots = _extract_and_snapshot_buffers(data_buffers)
    if not snapshots:
        return True  # Nothing pending

    # 3. Concatenate all influx points into a single batch list
    all_influx_records = []
    for db, pending_df in snapshots:
        try:
            records = prep_records(db, pending_df)
            if records:
                all_influx_records.extend(records)
        except Exception as prep_err:
            logger.error(f"Failed to prepare influx records for DO {db.iec61850_do.name}: {prep_err}")

    if not all_influx_records:
        return True

    # 4. Perform SINGLE HTTP POST call for all data records
    try:
        is_written = write_records(write_handler, all_influx_records, bucket_name)

        if is_written:
            # SUCCESS: Clear the uploaded snapshots
            _clear_snapshots(snapshots)
            logger.info(
                f"Successfully uploaded batch of {len(all_influx_records)} records "
                f"across {len(snapshots)} data buffers to InfluxDB."
            )
            return True
        else:
            # FAILURE: Roll back all snapshot data safely to original data buffers
            _rollback_snapshots(snapshots)
            logger.warning(
                f"Batch write returned False. Safely restored snapshots to {len(snapshots)} data buffers."
            )
            return False

    except Exception as exc:
        # EXCEPTION: Ensure complete rollback on network/timeout error
        _rollback_snapshots(snapshots)
        logger.warning(f"Failed to transmit bulk upload to InfluxDB: {exc}. Rolled back all snapshots.")
        return False

def perform_upload(data_buffer: 'DataBuffer', MAX_RETRY_ROWS=1000, **kwargs) -> bool:
    """
    NOTE: deprecated method for uploading data to influxdb on DataBuffer basis. Use _bulk_upload_per_connection for
    efficient operation on edge devices.

    This method uploads the latest measurements to the pre-configured influxdb regularly.
    It requires the influxdb write handler.

    MAX_RETRY_ROWS = 1000 accounts for data in queue of 2.77 hours with update interval of 10s.

    Parameters
    ----------
    data_buffer: the data_buffer instance that contains data for
        - influxdb: the influxdb interface instance of the class Database
        - records: the time series data instance of the class Record
    kwargs: keyword args passed from the upper level function, if any exists.

    Returns
    -------
    is_written: a boolean value indicating whether the write action was successful.
    """

    is_written = False

    if not data_buffer.influxdb.write_handler:
        logger.warning(
            f'Influxdb write handler for DO {data_buffer.influxdb.parent} does not exist, can not upload data')
        return False
    elif not data_buffer.influxdb.write_handler.ping():
        logger.warning(f'Influxdb write handler for DO {data_buffer.influxdb.parent} has a bad connection')
        return False

    try:
        # 1. Safely snapshot and clear pending upload records under thread lock
        with data_buffer._record_lock:
            if data_buffer.records.data_for_upload.empty:
                return True  # Nothing new to upload

            # Make a copy of the current pending data
            pending_df = data_buffer.records.data_for_upload.copy()
            # Reset immediately so new updates in the next 10s accumulate cleanly
            data_buffer.records.reset_data_for_upload()

        # 2. Prepare influx records from the captured snapshot
        influx_records = prep_records(data_buffer, pending_df, **kwargs)

        if influx_records:
            is_written = write_records(
                data_buffer.influxdb.write_handler,
                influx_records,
                data_buffer.influxdb.write_bucket
            )
            if is_written:
                logger.info(f'Data upload to influx was successful for DO {data_buffer.iec61850_do.name}')
            else:
                # If write failed, restore unsent records back to data_for_upload safely
                with data_buffer._record_lock:
                    combined_df = pd.concat([pending_df, data_buffer.records.data_for_upload], ignore_index=True)
                    # Keep only the most recent N rows to prevent memory saturation
                    data_buffer.records.data_for_upload = combined_df.tail(MAX_RETRY_ROWS).reset_index(drop=True)
                logger.warning(f'Influxdb data upload failed for DO {data_buffer.iec61850_do.name}')
        else:
            logger.warining(f'The method prep_records returned empty list for DO {data_buffer.iec61850_do.name}')
    except Exception as exc:
        logger.warning(f'Failed to write DO {data_buffer.influxdb.parent} to influxdb, wait for the next iteration.')
        logger.exception(exc)
        return False

    return is_written