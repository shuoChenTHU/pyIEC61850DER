# -*- coding: utf-8 -*-
"""
Data processing logics for local data calculation inside the data buffers.

"""

import logging
import numpy as np
import settings.helper as helper

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface.data_buffer import DataBuffer
    from communication.pyiec61850_server import IEC61850ServerMMS

from settings.helper import rotating_logger
import interface

logger = rotating_logger(__name__)


"""
=======================================================================
=================   Begin Essential routine functions =================
=======================================================================
"""

def get_cvalue(data_buffer: 'DataBuffer') -> helper.StdDataType.AllTypes:
    # TODO: here it will not be checked whether the associated values have been updated at current timestep
    #       i.e. the "calculation" might be delayed, implement a method to update DO with priority

    '''
    One old example of the bounds for calculator is like this:
    {'lower': {'idxBuffer':317,'functionHandler':'', 'args':[]}, 'upper': {'idxBuffer':304,'functionHandler':'', 'args':[]}}
    '''

    if hasattr(data_buffer, 'handler'):
        if hasattr(interface.calculator, data_buffer.handler):
            if hasattr(data_buffer, 'args'):
                args = data_buffer.args
            else:
                args = []
            func_handler = getattr(interface.calculator, data_buffer.handler)
            # FIXME: if the function handler requires more than just the data_buffer obj, we have a problem.
            #    find a way out!
            # val = func_handler(ied_server, data_buffer, *args)


"""
=======================================================================
=================   End Essential routine functions =================
=======================================================================
"""



'''
##################################################################
##########     some dummy functions for tests  ###################
##################################################################
'''


def set_one():
    return 1.0

def counter(val):
    val += 1.0
    return val

def double_value(val):
    return val*2.0

'''
##################################################################
##########     IEC 61850 oriented calculation  ###################
##################################################################
'''

'''
For all calculation methods, we assume ied_server, df_lookup_active, and the current data_buffer instance
are passed as default input args, even if they might not be used.

In this way, in the CSV lookup table, one only needs to define functionHandler and args,
args should be the integer index of a data_buffer instance


'''


def aggregate_pcc(ied_server: 'IEC61850ServerMMS', data_buffer: 'DataBuffer', *args):
    '''
    This function scans all active logical nodes in the data model, aggregates the
    sum of all TotW.mag.f and write it to the DO TotW of the LN "PCC".

    The input addressMmsPCC is the MMS address of to be calculated aggregator parameters, e.g.
    active / reactive / apparent power of different DER behind a PCC.

    Currently we use simple logic, just iterate over the df_lookup_active dataframe and sum up the values
    of all DO that have the same LN_DO_DA id.

    TODO: check if LN should be removed because the suffix integer might not always be 1.

    TODO: all values are positive, find a way to determine the direction (absorption or injection)

    TODO: pass index of target DataBuffer instances as *args?
    '''

    df_lookup_active = ied_server.df_lookup_active
    pcc_mms_addr = data_buffer.iec61850_do.obj_ref_map['monitor_da_mms_addr']
    identifier = pcc_mms_addr.split('/')[1]
    val_agg = 0
    for i in range(len(df_lookup_active)):
        if pcc_mms_addr == df_lookup_active.loc[i, 'monitorDA']:
            pass
        elif identifier in df_lookup_active.loc[i, 'monitorDA']:
            idx = df_lookup_active.loc[i, 'idxBuffer']
            [idx, val] = interface.runtime.get_external_value_by_idx(ied_server.data_buffers, idx)

            if not val:
                logger.warning(
                    f'Value of DA {ied_server.data_buffers[idx].iec61850_do.obj_ref_map['monitor_da_mms_addr']} is None, skip it')
            elif not helper.is_valid_number(val):
                logger.warning(f'Value of DA {ied_server.data_buffers[idx].iec61850_do.obj_ref_map['monitor_da_mms_addr']} is not a number, skip it')
            elif 'PV' in df_lookup_active.loc[i, 'monitorDA']:
                val_agg += -1 * val
            else:
                val_agg += val

    return val_agg


def multiplication(ied_server: 'IEC61850ServerMMS', data_buffer: 'DataBuffer', *args: int | list[int]):
    '''
    This function takes the index of data_buffer instances and performs a simple multiplication of them all.
    TODO: outsource the lookup process to a method of data buffer
    '''

    df_lookup_active = ied_server.df_lookup_active
    val_multi = None
    first_arg = None
    for idx_buffer in args:
        [idx, val] = interface.runtime.get_external_value_by_idx(ied_server.data_buffers, idx)

        if not val:
            logger.warning(
                f'Value of DA {ied_server.data_buffers[idx].iec61850_do.obj_ref_map['monitor_da_mms_addr']} is None, skip it')
        elif not helper.is_valid_number(val):
            logger.warning(
                f'Value of DA {ied_server.data_buffers[idx].iec61850_do.obj_ref_map['monitor_da_mms_addr']} is not a number, skip it')
        else:
            if not first_arg:
                first_arg = val
                val_multi = val
            else:
                val_multi *= val

    return val_multi


def solarCurtailment():
    '''
    In case no PV inverter is availalbe, this function can be called to represent
    the effect of PV curtailment. It compares the "measured" value and threhold given
    by the curtailment and take the smaller one as "actual" PV active feed-in power.

    '''

    # only a place_holder, this functionality is currently implemented as limits.

    pass