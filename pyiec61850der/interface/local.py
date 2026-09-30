# -*- coding: utf-8 -*-
"""
Local data processing based on the TimeSeries class.

"""


import logging
import pandas as pd
from pandas import DataFrame

from settings import helper

import copy

from settings.helper import rotating_logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interface.data_buffer import DataBuffer
    from interface.time_series import TimeSeries
logger = logging.getLogger(f"main_logger.{__name__}")

FloatTypes = helper.StdDataType.FloatTypes
IntTypes = helper.StdDataType.IntTypes
BoolTypes = helper.StdDataType.BoolTypes


"""
=======================================================================
=================   Begin Essential routine functions =================
=======================================================================
"""

def get_cvalue(data_buffer: 'DataBuffer') -> helper.StdDataType.AllTypes:
    ctime_unix = data_buffer.time_manager.ctime_unix
    # No need to check field_key by data_buffer configuration, after loading the time-series, the column is
    # automatically renamed to 'value'
    # field_key = data_buffer.data_col if data_buffer.data_col else 'value'
    val_new = data_buffer.local_timeseries.get_value_in_timeseries(ctime_unix, field_key='value')

    return val_new



"""
=======================================================================
=================   End Essential routine functions =================
=======================================================================
"""

# TODO: evaluate whether it is helpful to init the entire profile, maybe it is better
#   to recursively load local profiles in each iteration

def get_dataframe_from_local_file(filename, options:dict, **kwargs:dict) -> DataFrame:
    """
    This method will get the PV/load time series data locally from a pre-configured csv file in the subfolder
    ./time_series, the CSV file could contain more data than required by the simulation time range.

    Input:
        - filename: name of the local csv file, including extension
        - colPara: column name in the csv file that contains the data
        - colTime: column name in the csv file that contains the string timestamps
        - time_str_format: format of time string, default '%Y-%m-%d %H:%M:%S'
        - startTimeStr: start time string of the profile time window, None means starting at the row 0
        - endTimeStr: end time string of the profile time window, None means ending at the last row
        - **kwargs: place_holder for other supplementary keywords argument

    Output;
        - Return the newProfile instance, in which the time column will always have the name '_time'. Additionally
            the unix time (float) will be stored in the column 'UNIX'
    """

    logger.info('=================   Begin local profile initialization    =================')

    para_col_name  = options['para_col_name']
    time_col_name = options['time_col_name']
    time_str_format = options['time_str_format']
    start_time_str = options['start_time_str']
    end_time_str = options['end_time_str']

    # read data
    file_path = f'./data/time_series/{filename}'
    ts_df = pd.read_csv(file_path, sep=kwargs.get('sep', ','))

    # use vectorised datetime conversion for efficiency
    ts_df['dt_internal'] = pd.to_datetime(ts_df[time_col_name], format=time_str_format, errors='coerce')

    # data slicing by time range
    if start_time_str or end_time_str:
        mask = pd.Series([True] * len(ts_df))
        if start_time_str:
            start_dt = pd.to_datetime(start_time_str, format=time_str_format)
            mask &= (ts_df['dt_internal'] >= start_dt)
        if end_time_str:
            end_dt = pd.to_datetime(end_time_str, format=time_str_format)
            mask &= (ts_df['dt_internal'] <= end_dt)
        df_valid = ts_df[mask].copy()
    else:
        df_valid = ts_df.copy()

    if df_valid.empty:
        logger.warning(f"No data found for the specified range in {filename}")
        return df_valid

    if 'unix' in df_valid.columns:
        df_valid = df_valid.rename(columns={'unix': 'time_unix'})
    else:
        df_valid['time_unix'] = (df_valid['dt_internal'] - pd.Timestamp("1970-01-01")) // pd.Timedelta('1s')

    # handle column renaming
    rename_map = {time_col_name: 'time'}
    if isinstance(para_col_name, str):
        rename_map[para_col_name] = 'value'
        selected_cols = ['time', 'value', 'time_unix']
    else:
        selected_cols = ['time'] + list(para_col_name) + ['time_unix']

    df_valid = df_valid.rename(columns=rename_map)

    # final cleanup, keep only relevant columns and reset index
    df_final = df_valid[selected_cols].reset_index(drop=True)

    logger.info(f"Loaded {len(df_final)} rows from {filename}")
    logger.info('=================   End local profile initialization    ================= \n')

    return df_final


def update_time_series(time_series: 'TimeSeries', filename:str, options: dict) -> 'TimeSeries':
    """
    Initialise an instance of the class TimeSeries, fill the attributes based on the data acquired from a local CSV
    file.

    Currently we handle one parameter per profile, in other words, if a csv file containts 10 different measurements,
    then 10 TimeSeries instances need to be initialized separately. Or the other way around, if you need to create 10
    TimeSeries instances, need to prep 10 csv files or one with 10 columns.

    Parameters
    ----------
    filename: filename of the local CSV file
    options: the same options used for the influx data query

    Returns
    -------
    :param time_series: the TimeSeries instance, which can be directly used to update the value of DataBuffer instances.
    """

    logger.info('=================   Begin initialise TimeSeries instance using local CSV  =================')

    local_df = get_dataframe_from_local_file(filename, options)
    time_str_format = options['time_str_format']

    # convert time string to the proper format
    local_df['time'] = pd.to_datetime(local_df['time'], format=time_str_format).dt.strftime(
        time_series.STANDARD_TIME_STRING)

    record_count = local_df.shape[0]
    time_series.data_active = local_df
    time_series.data_count = record_count
    time_series.provider = filename
    time_series.time_window_str = (local_df.at[0, 'time'], local_df.at[record_count - 1, 'time'],)
    time_series.time_window_str = (local_df.at[0, 'time_unix'], local_df.at[record_count - 1, 'time_unix'],)

    if helper.is_valid_guid(filename.replace('.csv', '')):
        time_series.guid = filename.replace('.csv', '')

    logger.info('=================   End initialise TimeSeries instance using local CSV  =================\n')

    return time_series


def refresh_daily_time_series(data_buffer: 'DataBuffer') -> 'DataBuffer':
    time_col = 'datetime' if not data_buffer.time_col else data_buffer.time_col
    data_col = 'value' if not data_buffer.data_col else data_buffer.data_col
    try:
        ctime_unix = data_buffer.time_manager.ctime_unix - data_buffer.time_series.offset
        ctime_str = helper.time_unix_to_str(ctime_unix, time_str_format='%Y-%m-%d %H:%M:%S')

        start_time_str = helper.get_time_str_by_diff(ctime_str, time_str_format='%Y-%m-%d %H:%M:%S', time_diff=-300)
        end_time_str = helper.time_unix_to_str(helper.time_utc_str_to_unix(start_time_str) + 86400)

        options = {"start_time_str": start_time_str,
                   "end_time_str": end_time_str,
                   "para_col_name": data_col,
                   "time_col_name": time_col,
                   "time_str_format": '%Y-%m-%d %H:%M:%S'}

        # 1. Load the new TimeSeries instance OUTSIDE the lock (File/DB I/O)
        new_ts = update_time_series(data_buffer.time_series, data_buffer.local_timeseries.provider, options)

        # 2. Swap the reference under lock protection (Microsecond operation)
        with data_buffer._record_lock:
            data_buffer.time_series = new_ts

    except Exception as e:
        logger.exception('Failed to create new TimeSeries instance by loading data locally in CSV.')
        logger.exception(e)

    return data_buffer