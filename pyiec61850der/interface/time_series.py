# -*- coding: utf-8 -*-
"""
Definition of TimeSeries and Record classes for the handling of time-series data.

"""

from dataclasses import dataclass
from typing import Optional
from pandas import DataFrame
import numpy as np
import uuid
from influxdb_client import InfluxDBClient

from settings.helper import rotating_logger
from settings.helper import KwargsHandler, StdDataType

logger = rotating_logger(__name__)

@dataclass()
class TimeSeries(KwargsHandler):
    """
    The class for storing power/energy data_active data over a specific temporal period. Could be used for local data
    processing or scheduling. The data in the data_active could be historical measurements, forecasts or predicted values
    using other techniques, or scheduled control setpoints.

    In the IEC 61850 context, the TimeSeries instances will be created as attribute(s) at DO level when initialising the
    IEC61850DO() instances. Theoretically, each BDA/DA in the IEC 61850 data model could/should have a data_active
    instance. But some data attributes in the dataframe could be service specific, e.g. in influxdb, columns of the
    data_active should be _time, _value

    NOTE: the initial attributes are kept generic, i.e. they do not pose any implicit relation to a specific
    communication protocol (e.g. IEC 61850 MMS address) or a database type (e.g. influxdb bucket name). Protocol and
    database specific attributes can be added later.

    NOTE: not all attributes are always used when an instance is initialized, e.g. local data doesn't
        imply knowledge about MMS address and guid. If an attributes has value None, most likely it is not
        required for that instance.
    """

    def __init__(self, **kwargs):
        self.uuid: uuid.UUID = uuid.uuid4()  # abuse the term uuid and guid, uuid is the UUID object, guid is str
        self.guid: str = self.uuid.__str__()
        self.timezone: str = 'UTC'  # TODO: use UTC as default, a method is required if local tz shall be used
        self.data_count = None
        self.provider: str | None= None
        self.parent: str = 'unknown'
        self.data_active: DataFrame = DataFrame()
        self.data_archive: DataFrame = DataFrame()
        self.data_all: DataFrame = DataFrame()
        self.time_window_str: tuple[str, str] = ('1970-01-01 01:00:00', '2099-01-01 00:00:00')
        self.time_window_unix: tuple[float, float] = (0.0, 4070908800.0)
        self.data_refresh_trigger: float = 60*60*24  # refresh the data at 00:00:00
        self.offset: float = 0.0  # the offset is to be understood as the unix time diff ahead of or behind UTC
        self.STANDARD_TIME_STRING = '%Y-%m-%d %H:%M:%S'
        self.apply_kwargs(True, **kwargs)


    def __str__(self):
        """
        Use the guid string to represent the TimeSeries object description.
        """

        return self.guid

    def __call__(self):
        """
        Use the guid string to represent the TimeSeries object when it is called.
        """

        return self.guid

    def get_value_in_timeseries(self, ctime_unix: float, field_key: str = 'value') -> (StdDataType.AllTypes) :
        """
        This method captures the corresponding measurement given the current timestamp.
        Currently it only handles single data point.

        For better efficiency we use unix time for fuzzy search, i.e. the data might not be an exact match for the
        given time stamp. But this approach ensures that some data can be found near the desired time.

        TODO: if necessary, add logics to enable the read of multiple columns (fields in influxdb definition)
            in the input data_active instance.

        FIXME: there might be a little inconsistency w.r.t the usage of utc and local time. Currently, if the data
         are loaded from a remote database or local csv file, local time must be used. See more in
         runtime_manager.TimeManager()

        Parameters
        ----------
        ctime_unix: the unix float value of current time
        field_key: the key of the value in the dataframe, for single measurement it takes the default _value

        Returns
        -------
        val: the fuzzy search value, returning None means could not find the proper value

        """

        if self.data_active.empty:
            logger.warning('No data_active available, can not read the new value')
            return None
        elif self.data_count == 0:
            logger.warning('The data_active has length 0, can not read the new value')
            return None
        else:
            # match_idx = next(
            #     (idx for idx, tstmp in enumerate(self.data_active['time']) if ctime_unix in str(tstmp)),
            #     None
            # )
            #
            # if match_idx is not None:
            #     val = self.data_active.loc[match_idx, field_key]
            # else:
            #     logger.warning(f'Timestep {ctime_unix} not found in data_active')

            # Use unix time for fuzzy search
            df_sorted = self.data_active.sort_values('time_unix')
            times = df_sorted['time_unix'].values

            assert np.issubdtype(type(ctime_unix), np.number)
            # find the insertion point
            idx = np.searchsorted(times, ctime_unix, side='left')

            # handle boundary conditions to find the *absolute* nearest
            if idx == 0:
                closest_idx = 0
            elif idx == len(times):
                closest_idx = len(times) - 1
            else:
                # Check if the value before or the value at idx is closer
                before = times[idx - 1]
                after = times[idx]
                if ctime_unix - before < after - ctime_unix:
                    closest_idx = idx - 1
                else:
                    closest_idx = idx

            val = df_sorted.iloc[closest_idx][field_key]

            return val


class Database(KwargsHandler):
    """
    A class that contains information related to database handlers, e.g. the influxdb handler.
    The attribute of an instance could be modified depending on the application scenario.
    """

    def __init__(self, **kwargs):
        self.uuid: uuid.UUID = uuid.uuid4()  # abuse the term uuid and guid, uuid is the UUID object, guid is str
        self.guid: str = self.uuid.__str__()
        self.name: str | None = None
        self.type: str | None = None
        self.parent: str = 'unknown'
        self.query_handler: InfluxDBClient | None = None
        self.write_handler: InfluxDBClient | None = None
        self.query_conn_status: str | bool | int | None = None
        self.write_conn_status: str | bool | int | None = None
        self.id: str | None = None
        self.query_bucket: str | None = None  # this is a name convention intuited by influxdb
        self.write_bucket: str | None = None  # this is a name convention intuited by influxdb
        self.measurement_read: str | None = None
        self.measurement_write: str | None = None

        self.apply_kwargs(True, **kwargs)


@dataclass()
class Record(KwargsHandler):
    """
    Information related to the operation status and records of the runtime service, e.g. the IEC 61850 server or a
    data buffer instance.

    The attributes of this class have generic names, the very first usage is recording of data updates and controls
    of the instances of the class DataBuffer, which makes traces for a specific IEC 61850 DO instance of the class
    IEC61850DO.
    """

    def __init__(self, columns:list[str], **kwargs):
        self.columns: list = columns
        self.integrity_update_count: int = 0
        self.quality_change_count: int = 0
        self.data_update_count: int = 0
        self.control_count: int = 0
        self.data_archive: DataFrame = DataFrame(columns=self.columns)
        self.data_for_upload: DataFrame = DataFrame(columns=self.columns)
        self.create_time: str = 'unknown'
        self.update_time: str = 'unknown'
        self.export_dir: str = './data/archive'
        self.apply_kwargs(True, **kwargs)

    def reset_data_for_upload(self):
        """
        Call after a successful data upload operation. Reset the DataFrame for the attribute data_for_upload to an
        empty DataFrame using prescribed columns during initialisation.
        """
        self.data_for_upload = DataFrame(columns=self.columns)
