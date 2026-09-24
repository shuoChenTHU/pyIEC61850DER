# -*- coding: utf-8 -*-
"""
Main program for creating IEC 61850 MMS client using the libIEC61850 server stack.

@author: J. Morris; S. Chen

The IedClient() class can be used to initialize IEC 61850 compatible client application, read measured values from
or write control setpoints to an IEC 61850 server via IEC 61850 MMS communication.

It also supports connection status check of the MMS channel and data model scan.

NOTE: implementation of other client side application based on the libIEC61850 client API is possible, such
functionalities might be added here in the future and is also left open for users.

The initialisation for pyiec61850 client object using the libIEC61850 client API
was taken from a test framework as described in:

J. Morris, F. Ebe, J. Pichl, S. Chen, G. Heilscher, and J.-G. Leeser, 
‘Implementation of an automated test bench for monitoring and controlling systems of 
decentralized energy systems through Controller Hardware-In-the-Loop and 
Power Hardware-In-the-Loop methodology’, in 2020 5th IEEE Workshop on the Electronic Grid (eGRID), 
Aachen, Germany: IEEE, Nov. 2020, pp. 1–8. doi: 10.1109/eGRID48559.2020.9330636.

NOTE: libiec61850 client error code:
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

import sys
import os
import time
from typing import Type
from settings import helper
import numpy as np

iec61850 = helper.import_libiec61850()
vprint = helper.vprint


class IedClient(object):
    '''
    This client class is taken from some demo codes in another project, I'm too lazy to update the stuff here.
    It should be able to interact with a static IEC 61850 server, we do not really need that, just ignore the codes if you find them confusing.
    '''

    def __init__(self,
                 ip: str = '127.0.0.1',
                 port: int = 61850):

        """
        Initialising the client object
        Sets connection parameters: TCP Port and host IP address of IEC 61850 Server
        ----------

        Parameters
        ----------
        ip: IP address of the IEC 61850 client
        port: TCP port of the IEC 61850 client
        """

        self.ip: str = ip or self._use_default_ip()
        self.port: int = port or self._use_default_port()

        self.connection: Type["SwigPyObject"] | None = None
        self.conn_timeout: int = 10000
        self.error: int | None = None  # error code as given in libiec61850
        self.status: str | None = None
        self.status_code: bool | None = None

        self.ied_model: dict = {}
        self.all_do: dict = {}
        self.all_da: dict = {}
        self.all_da_mx: dict = {}  # all DA with fc type MX
        self.all_da_sp: dict = {}  # all DA with fc type SP
        self.all_rcb: dict = {}  # all Report Control Blocks
        self.rcb_ref_objs: list = []  # stores the RCB mms address

        # static attributes
        self.SP: int = iec61850.IEC61850_FC_SP
        self.MX: int = iec61850.IEC61850_FC_MX

    def _use_default_ip(self) -> str:
        print('No IP address specified, use localhost as default')
        return '127.0.0.1'

    def _use_default_port(self) -> int:
        print('No TCP port specified, use localhost as default')
        return 61850

    def create_IED_connection(self) -> bool:
        '''
        Creates IED connection with given conncection parameters
        '''

        is_connected: bool = False
        self.connection = iec61850.IedConnection_create()
        iec61850.IedConnection_setConnectTimeout(self.connection, int(self.conn_timeout))
        self.error = iec61850.IedConnection_connect(self.connection, self.ip, self.port)

        error_messages = {
            iec61850.IED_ERROR_OK: ("IEC 61850 connection established", True),
            iec61850.IED_ERROR_CONNECTION_REJECTED: ("IEC 61850 connection rejected", False),
        }

        message, is_connected = error_messages.get(self.error, ("IEC 61850 connection failed", False))

        print(message)

        self.status = 'connected' if is_connected else 'connection error'
        self.status_code = 1 if is_connected else 0

        return is_connected

    def get_ied_conn_state(self) -> str:
        """
        Connection state of the IedConnection instance (either idle, connected or closed)
        Enumeration litervals for IED status:
            - IED_STATE_CLOSED
            - IED_STATE_CONNECTING
            - IED_STATE_CONNECTED
            - IED_STATE_CLOSING
        """

        state_map = {
            iec61850.IED_STATE_CONNECTING: "IED_STATE_CONNECTING",
            iec61850.IED_STATE_CONNECTED: "IED_STATE_CONNECTED",
            iec61850.IED_STATE_CLOSED: "IED_STATE_CLOSED",
            iec61850.IED_STATE_CLOSING: "IED_STATE_CLOSING",
        }

        state = iec61850.IedConnection_getState(self.connection)
        state_string = state_map.get(state, "ERROR")

        return state_string

    def close_ied_connection(self):
        """
        Closes current IED connection
        """

        iec61850.IedConnection_close(self.connection)
        print('IEC 61850 connection closed')

    def terminate_ied_connection(self):
        """
        Terminates current IED connection
        """

        iec61850.IedConnection_destroy(self.connection)
        print('IEC 61850 connection terminated')

    # here begins the definition of conditioners and handlers for data model scan
    @staticmethod
    def rpt_condition(var_name: str):
        return 'RP' in var_name and var_name.count('$') == 1

    @staticmethod
    def do_condition(var_name: str):
        return var_name.count('$') == 1  # fc$DO($SDO)$DA($SDA1)($SDA2)(...)

    @staticmethod
    def da_condition(var_name: str):
        return var_name.count('$') == 2  # fc$DO($SDO)$DA($SDA1)($SDA2)(...)

    @staticmethod
    def sda_condition(var_name: str):
        return var_name.count('$') > 2

    def rpt_handler(self, ld_name: str, ln_name: str, var_name: str, verbose: int):
        """
        Handle IEC 61850 report (RPT) objects during data model scan.
        """

        report_ref = ld_name + '/' + ln_name + '$' + var_name
        self.rcb_ref_objs.append(report_ref)
        report_ref = report_ref.replace('$RP', '')
        report_key = report_ref.replace('$', '.')
        self.all_rcb[report_key] = ''
        vprint(f'Found Report Control Block: {report_key}', verbose)

    def do_handler(self, ld_name: str, ln_name: str, var_name: str, verbose: int):
        """
        Handle IEC 61850 Data Object (DO) objects during data model scan.
        """

        do_ref = ld_name + '/' + ln_name + '$' + var_name
        fc_type = var_name.split('$')[0]
        fc_type_key = getattr(iec61850, f'IEC61850_FC_{fc_type}')
        do_ref = do_ref.replace(f'${fc_type}', '')
        do_key = do_ref.replace('$', '.')
        do_val = iec61850.IedConnection_readFloatValue(self.connection, do_key, fc_type_key)
        self.all_do[do_key] = do_val
        vprint(f'{do_key}: {do_val}', verbose)

    def da_handler(self, ld_name: str, ln_name: str, var_name: str, verbose: int):
        """
        Handle IEC 61850 Data Attribute (DA) objects during data model scan.
        """

        da_ref = ld_name + '/' + ln_name + '$' + var_name
        fc_type = var_name.split('$')[0]
        fc_type_key = getattr(iec61850, f'IEC61850_FC_{fc_type}')
        da_ref = da_ref.replace(f'${fc_type}', '')
        da_key = da_ref.replace('$', '.')
        da_val = iec61850.IedConnection_readFloatValue(self.connection, da_key, fc_type_key)
        self.all_da[da_key] = da_val
        vprint(f'{da_key}: {da_val}', verbose)

    def sda_handler(self, ld_name: str, ln_name: str, var_name: str, verbose: int):
        """
        Handle IEC 61850 Sub Data Attribute (SDA) objects during data model scan.
        """

        sda_ref = ld_name + '/' + ln_name + '$' + var_name
        fc_type = var_name.split('$')[0]
        fc_type_key = getattr(iec61850, f'IEC61850_FC_{fc_type}')
        sda_ref = sda_ref.replace(f'${fc_type}', '')
        sda_key = sda_ref.replace('$', '.')
        if fc_type == 'MX' and '.f' in sda_key:
            sda_val = iec61850.IedConnection_readFloatValue(self.connection, sda_key, fc_type_key)
        elif fc_type == 'SP' and '.f' in sda_key:
            sda_val = iec61850.IedConnection_readFloatValue(self.connection, sda_key, fc_type_key)
        else:
            sda_val = np.nan
            vprint(f'No value available for the SDA {sda_key} of FC type {fc_type}')
        self.all_da_sp[sda_key] = sda_val
        vprint(f'{sda_key}: {sda_val}', verbose)

    def get_data_model(self, verbose: int = 1) -> tuple[dict, bool]:
        """
        Get the IED data model from the IED server
        Returns IED model, MX and SP data attributes with corresponding keys

        MX dictionary: LD/LN$fc$DO($SDO)$DA($SDA1)($SDA2)(...)
        () means without guaranty of appearance
        --> example: {'Relay1/MMXU$MX$TotW$mag$f': '0.01'}

        NOTE: the following logic operator based on number of $ is very floppy, because the existence of SDO
              and SDA will have an impact on this. But it is just a test script anyway...
        ----------

        Parameters
        ----------
        verbose: message level

        Returns
        -------
        self.ied_model: the full data model after scan
        is_success: bool value indicating the data model scan status
        """

        is_success = False

        dispatcher = [
            (self.rpt_condition, self.rpt_handler),
            (self.do_condition, self.do_handler),
            (self.da_condition, self.da_handler),
            (self.sda_condition, self.sda_handler),
        ]

        if self.error == iec61850.IED_ERROR_OK:
            [device_list, error] = iec61850.IedConnection_getLogicalDeviceList(self.connection)
            device = iec61850.LinkedList_getNext(device_list)
            while device:
                ld_name = iec61850.toCharP(device.data)
                print(f"LD: {ld_name}")
                self.ied_model[ld_name] = {}
                [logical_nodes, self.error] = iec61850.IedConnection_getLogicalDeviceDirectory(self.connection, ld_name)
                logical_node = iec61850.LinkedList_getNext(logical_nodes)
                while logical_node:
                    ln_name = iec61850.toCharP(logical_node.data)
                    print(f"LN: {ln_name}")
                    self.ied_model[ld_name][ln_name] = {}
                    [ln_objs, self.error] = iec61850.IedConnection_getLogicalNodeVariables(self.connection,
                                                                                           ld_name + "/" + ln_name)
                    ln_obj = iec61850.LinkedList_getNext(ln_objs)
                    while ln_obj:
                        var_name = iec61850.toCharP(ln_obj.data)
                        vprint(f"VAR: {var_name}", verbose)
                        self.ied_model[ld_name][ln_name][var_name] = {var_name}
                        for conditioner, handler in dispatcher:
                            if conditioner(var_name):
                                handler(ld_name, ln_name, var_name, verbose)
                                break
                        else:
                            vprint(f'Unknown type of MMS reference address: {var_name}', verbose)
                        ln_obj = iec61850.LinkedList_getNext(ln_obj)
                    iec61850.LinkedList_destroy(ln_objs)
                    logical_node = iec61850.LinkedList_getNext(logical_node)
                iec61850.LinkedList_destroy(logical_nodes)
                device = iec61850.LinkedList_getNext(device)

            iec61850.LinkedList_destroy(device_list)

            if self.ied_model != {}:
                print('IEC 61850 server has IED data model')
                print(f'Number of DO in the IED data model: {len(self.all_do)}')
                print(f'Number of DA in the IED data model: {len(self.all_da)}')
                print(f'Number of RCB in the IED data model: {len(self.all_rcb)}')
                is_success = True
            else:
                print('Got empty data model, IED data model transmission failed')
        else:
            print('IEC 61850 connection failed. IED data model transmission failed')

        return self.ied_model, is_success

    def read_float_value(self,
                         obj_ref: str = f'demoIEDPV/MMXU1.TotW.mag.f',
                         fc_type: str = 'MX',
                         round_digits: int = 8) -> tuple[float, int]:
        """
        Simple get function: Get current float from IED server with given number of digits for
        rounding the float value.
        ----------

        Parameters
        ----------
        obj_ref: MMS address as the object reference
        fc_type: fc type of the DA
        round_digits: number of digits for rounding

        Returns
        -------
        value: value of the IEC 61850 DA
        error_code: error code returned by the IEC 61850 client reading handler
        """

        fc_type_key = getattr(iec61850, f'IEC61850_FC_{fc_type}')
        [value, error_code] = iec61850.IedConnection_readFloatValue(self.connection, obj_ref, fc_type_key)

        if error_code == 0:
            assert type(round_digits) is int
            if isinstance(value, (float, int, np.number),):
                value = round(value, round_digits)
                # value = float(format(round(value[0], round_digits)))
                print(f'Measurement (IED server: {obj_ref}): {value}')
            elif isinstance(value, (list, tuple, ),):
                value = round(value[0], round_digits)
                print(f'Measurement (IED server: {obj_ref}): {value}')
            else:
                print('wrong data type, reading failed.')

        else:
            print(f'Reading float value failed, error code: {error_code}')
        return value, error_code

    def write_float_value(self,
                          obj_ref_str: str = f'demoIEDPV/DGEN1.OutWSet.setMag.f',
                          value: float = 1.0,
                          fc_type: str = 'SP') -> int:
        """
        Simple write value function: send a float set point to the defined DA.
        ----------

        Parameters
        ----------
        obj_ref_str: MMS address as the object reference
        fc_type: fc type of the DA
        value: float value for the to be controlled IEC 61850 DA

        Returns
        -------
        error_code: error code returned by the IEC 61850 client reading handler
        """

        assert helper.is_valid_number(value)
        fc_type_key = getattr(iec61850, f'IEC61850_FC_{fc_type}')
        error_code = iec61850.IedConnection_writeFloatValue(self.connection, obj_ref_str, fc_type_key, value)

        return error_code
