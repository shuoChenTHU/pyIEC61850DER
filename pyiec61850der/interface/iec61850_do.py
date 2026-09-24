# -*- coding: utf-8 -*-
"""
Definition of the IEC61850DO class for the IEC 61850 MMS DO objects.

"""

from dataclasses import dataclass, fields
from typing import Optional, Type, TypedDict
import pandas as pd
from pandas import DataFrame, Series
import numpy as np

from interface.iec61850_da import IEC61850DA
from settings.helper import KwargsHandler
from settings.helper import rotating_logger

logger = rotating_logger(__name__)

DICT_PRIMARY_DA = dict({
    'APC': {'monitor': 'mxVal.f', 'control': 'ctlVal.f'},
    'ASG': {'monitor': 'setMag.f', 'control': 'setMag.f'},
    'BCR': {'monitor': 'actVal', 'control': None},
    'CMV': {'monitor': 'cVal.mag.f', 'control': None},
    'CSG': {'monitor': None, 'control': None},
    'CUG': {'monitor': None, 'control': None},
    'DEL': {'monitor': 'phsAB.cVal.mag.f', 'control': None},
    'DPL': {'monitor': None, 'control': None},
    'ENC': {'monitor': 'stVal', 'control': 'ctlVal'},
    'ENG': {'monitor': 'setVal', 'control': 'setVal'},
    'ENS': {'monitor': 'stVal', 'control': None},
    'LPL': {'monitor': None, 'control': None},
    'INC': {'monitor': 'stVal', 'control': 'ctlVal'},
    'ING': {'monitor': 'setVal', 'control': 'setVal'},
    'INS': {'monitor': 'stVal', 'control': None},
    'MV': {'monitor': 'mag.f', 'control': None},
    'ORG': {'monitor': 'setSrcRef', 'control': 'setSrcRef'},
    'ORS': {'monitor': 'stVal', 'control': None},
    'SPC': {'monitor': 'stVal', 'control': 'ctlVal'},
    'SPG': {'monitor': 'setVal', 'control': 'setVal'},
    'SPS': {'monitor': 'stVal', 'control': None},
    'TCS': {'monitor': 'stVal', 'control': None},
    'TSG': {'monitor': 'setTm', 'control': 'setTm'},
    'VSG': {'monitor': 'setVal', 'control': 'setVal'},
    'WYE': {'monitor': 'phsA.cVal.mag.f', 'control': None},
})

class ObjRefMap(TypedDict):
    """
    Just a dict-safe template for the storage of IEC 61850 communication relevant object references
    TODO: update var types, refs are NOT str!
    """

    ld: str | None
    ln: str | None
    do: str | None
    monitor_da: str | None
    control_da: str | None
    monitor_da_q: str | None
    monitor_da_t: str | None
    monitor_da_mms_addr: str | None
    control_da_mms_addr: str | None
    multi_da: dict  # one placeholder for high-level application of IEC 61850 DA

def init_da_map() -> DataFrame:
    """
    Initialise an empty DA map as a pandas DataFrame object
    NOTE: the column name data_attributes refers to the list containing IEC 61850 DA instances of the type
    IEC61850DA, not the general attributes of a python class.
    """

    columns: list = ['data_attributes', 'da_name', 'da_mms_addr', 'da_obj_ref']
    return DataFrame(columns=columns)  # an empty map to store info relevant to the DAs

def init_obj_ref_map() -> ObjRefMap:
    """
    Initialise an empty obj ref map as a pandas DataFrame object, for object references at different levels.
    Currently, we only consider 4 key DA objects:
        - monitor DA value (e.g. DO.mag)
        - monitor DA quality (DO.q)
        - monitor DA timestamp (DO.t)
        - control DA value (e.g. DO.setMag), use it for both directions (read and write)

    NOTE: if there is the demand of using more sophisticated IEC 61850 CDC types and multiple DA under one DO,
    these can either be done by adding them to the dictionary multi_da, or pass customised attributes using the kwargs.
    """

    obj_ref_map: ObjRefMap = {
        'ld': None,
        'ln': None,
        'do': None,
        'monitor_da': None,
        'control_da': None,
        'monitor_da_q': None,
        'monitor_da_t': None,
        'monitor_da_mms_addr' : None,
        'control_da_mms_addr': None,
        'multi_da': {},
    }

    return obj_ref_map

@dataclass()
class IEC61850DO(KwargsHandler):
    """
    This class is subject to creation and maintenance of information associated to an IEC 61850 Data Object (DO). It
    is the vital data interface for instances of the class DataBuffer.

    Basic idea behind it: since many DA do not need integrity update, it is not always necessary to step one level
    downwards to fetch DA information. So we use the instances of IEC61850DO to store all information beneath this
    information level (this includes Sub-DO, DA, Sub-DA and multiple Sub-DAs). The instances of this class have job
    to interact with other services through the parent class DataBuffer, i.e. each instance of DataBuffer must
    contain one and only one instance of this class IEC61850DO.

    Filtering of DA information is done by selecting maximal one primary monitor DA and maximal one primary control DA.
    The following 4 attributes determine the primary monitoring and control parameter of a DO.
        - self.DO.obj_ref_map['monitor_da_mms_addr']
        - self.DO.obj_ref_map['control_da_mms_addr']
        - self.OO.obj_ref_map['monitor_da']
        - self.DO.obj_ref_map['control_da']

    With help of these prescribed dictionary map for object references, other functions and modules need not access the
    DA attributes at a deeper level to perform reading or sending controls. These concept only works for simple CDC
    types such as measurements and control. For more complicated settings, see the doc of init_obj_ref_map().

    To determine the monitor and control DA under each DO, we make use of the data structure given in the IEC 61850
    data models. For this purpose, some hard coding logics are necessary, they are implemented in the method
    select_primary_da().

    To avoid information loss, the data class IEC61850DA is still available, in the prototype phase we store all
    the information anyway, so the private attribute da_map should contain information of all IEC61850DA instances.
    Functions and methods from outside can see these instances of IEC61850DA, but do not have to operate on them.

    NOTE: a DA can also have more child-objects, this is currently not being handled

    =================================================================================================
    IEC 61850 specific information:
        Without further notion, MMS address (mms_addr) of a DO refers to a string following this scheme:
            <IED_name>_<LD name>/<LN_name>.<DO name>.<DA name>.<SDA name>
        In addition, a communication address (comm_addr) is also designed following this scheme:
            <IED_name>$<LD name>$<LN_name>$<DO name>$<DA name>$<SDA name>
        The MMS address is a backup plan in case some application can not process the separators (_, / or .) properly.
    =================================================================================================-
    """

    def __init__(self, **kwargs):
        self.level: str = 'DO'  # BDA/SDA, DA, DO, ...
        self.id: str | None = None  # currently the same as mms_addr, this attribute could be used for other type of id
        self.mms_addr: str | None = None
        self.comm_addr: str | None = None
        self.name: str | None = None
        self.type: str | None = None
        self.guid: str | None = None
        self.cdc: str | None = None
        self.fcda: str | None = None
        self.description: Optional[str] = None  # currently not used

        self._da_objs: list = []  # a list of DA object instances of the class IEC61850DA
        self.da_map: DataFrame = init_da_map()  # map for essential DA attributes
        self.obj_ref_map: ObjRefMap = init_obj_ref_map()  # map for IEC 61850 object references

        self.idx_monitor_da: int | None = None  # the index corresponding to the primary monitor DA in da_map
        self.idx_control_da: int | None = None  # the index corresponding to the primary control DA in da_map

        self.apply_kwargs(False, **kwargs)


    def __str__(self):
        """
        Use the DO id to represent the DO object description.
        """
        return f'{self.id}'

    def __call__(self):
        """
        Use the DO id to represent the DO object when it is called.
        """
        return self.id

    def add_iec61850_da(self, new_da:Type[IEC61850DA]=None):
        """
        Create a new IEC61850DA instance and update the relevant attributes in IEC61850DO
        accordingly.
        """

        assert isinstance(new_da, IEC61850DA)
        new_row = {'data_attributes': new_da,
                   'da_name': new_da.name,
                   'da_mms_addr': new_da.mms_addr,
                   'da_obj_ref': new_da.da_obj_ref
                   }
        self.da_map = pd.concat([self.da_map, pd.DataFrame([new_row])], ignore_index=True)


    def select_primary_da(self):
        """
        It should be clear that each IEC 61850 DO would contain a bunch of different DA, but in many cases one of them would
        be the most frequently used parameter for monitoring and control. Therefore, this method will be called after all DA
        instances of the class IEC61850DA are initialized, it selects one (if there exists any) primary DA for the monitoring
        as well as control direction, note the address and reference object and add them to the lists in the DataBuffer instances.

        These primary DA ref is only a short cut for simply application. For complexer application you may consider get a deeper
        insight into the IEC61850DA instances.

        Theoretically one can dynamically assign primary DA names based on cdc type, but for this prototype we go wild by using
        a fix coded dictionary.

        Mapping is defined as following:
            cdc Type		monitoring DA	 	control DA
            -----------------------------------------------
            APC				mxVal.f				ctlVal.f
            ASG				setMag.f			setMag.f
            BCR				actVal				--
            CMV				cVal.mag.f			--
            CSG				--					--
            CUG				--					--
            DEL				phsAB.cVal.mag.f	--				(Currently take phaseAB)
            DPL				--					--
            ENC				stVal				ctlVal
            ENG				setVal				setVal
            ENS				stVal				--
            LPL				--					--
            INC				stVal				ctlVal
            ING				setVal				setVal
            INS				stVal				--
            MV				mag.f				--
            ORG				setSrcRef			setSrcRef
            ORS				stVal				--
            SPC				stVal				ctlVal
            SPG				setVal				setVal
            SPS				stVal				--
            TCS				stVal				--
            TSG				setTm				setTm
            VSG				setVal				setVal
            WYE				phsA.cVal.mag.f		--				(Currently take phaseA)
        """

        if not self.get_da_instances():
            logger.info(f'There is no DA in the list of DO {self.name}, can not proceed.')
            pass
        elif self.cdc not in DICT_PRIMARY_DA:
            logger.info(f'The cdc type {self.cdc} is not yet supported.')
            pass
        else:
            if DICT_PRIMARY_DA[self.cdc]['monitor'] is not None:
                self.select_primary_monitor_da()
            if DICT_PRIMARY_DA[self.cdc]['control'] is not None:
                self.select_primary_control_da()

    def select_primary_monitor_da(self):
        mms_id = f'{self.mms_addr}.{DICT_PRIMARY_DA[self.cdc]["monitor"]}'
        row = self.loc_da_in_map('da_mms_addr', mms_id)
        if row is not None:
            assert isinstance(row.name, (np.int64, int, np.int32))
            idx = int(row.name)  # the name of the row Series should be the row index in the DataFrame da_map
            self.idx_monitor_da = idx
            self.fcda = self.da_map.loc[idx, 'data_attributes'].fc
            self.obj_ref_map['monitor_da_mms_addr'] = mms_id
            self.obj_ref_map['monitor_da'] = getattr(self.da_map.at[idx, 'data_attributes'], 'da_obj_ref', None)

            # only monitoring DA can provide info about q and t
            row_q = self.loc_da_in_map('da_name', 'q', False)
            if row_q is not None:
                self.obj_ref_map['monitor_da_q'] = row_q['da_obj_ref']

            row_t = self.loc_da_in_map('da_name', 't', False)
            if row_t is not None:
                self.obj_ref_map['monitor_da_t'] = row_t['da_obj_ref']

    def select_primary_control_da(self):
        mms_id = f'{self.mms_addr}.{DICT_PRIMARY_DA[self.cdc]["control"]}'
        row = self.loc_da_in_map('da_mms_addr', mms_id)
        if row is not None:
            assert isinstance(row.name, (np.int64, int, np.int32))
            idx = int(row.name)  # the name of the row Series should be the row index in the DataFrame da_map
            self.idx_control_da = idx
            self.obj_ref_map['control_da_mms_addr'] = mms_id
            self.obj_ref_map['control_da'] = getattr(self.da_map.at[idx, 'data_attributes'], 'da_obj_ref', None)

    def get_monitor_da_name(self) -> str:
        """
        A simple method to find DA name based on index of monitor DA
        """

        return self.da_map.at[self.idx_monitor_da, 'da_name']

    def get_da_instances(self) -> list:
        """
        A simple method to get a list  DA name based on index of monitor DA
        """

        return self.da_map['data_attributes'].values.tolist()

    def loc_da_in_map(self, key: str, value: any, is_report_none: bool = True) -> Series | None:
        """
        A supporting method to locate the row in da_map containing a specific key value.
        Parameters
        ----------
        key: column name of the target object
        value: specific value of the key
        is_report_none: whether report in log in case the desired kw pair is not found

        Returns
        -------
        Either the 1-d DataFrame row if the key-value pair exists, or a None object
        """

        res = self.da_map.loc[self.da_map[key] == value]
        if not res.empty:
            if res.shape[0] > 1:
                logger.warning(f'Found more than one entry with kw pair {key}:{value}, double check is required.')
            return res.iloc[0]
        else:
            if is_report_none:
                logger.info(f'The DA entry with kw pair {key}:{value} not found in the DA map.')
            return None