# -*- coding: utf-8 -*-
"""
A test script for structured testing on the IED client side

@author: S. Chen

The test script for pyiec61850 client object was taken from a test framework as described in:

J. Morris, F. Ebe, J. Pichl, S. Chen, G. Heilscher, and J.-G. Leeser, 
‘Implementation of an automated test bench for monitoring and controlling systems of 
decentralized energy systems through Controller Hardware-In-the-Loop and 
Power Hardware-In-the-Loop methodology’, in 2020 5th IEEE Workshop on the Electronic Grid (eGRID), 
Aachen, Germany: IEEE, Nov. 2020, pp. 1–8. doi: 10.1109/eGRID48559.2020.9330636.

The test functions are strongly simplised for easy use.

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


import sys
import os
import time
from settings import helper
from communication.pyiec61850_client import IedClient

helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()
    

def init_ied_client(ip_addr:str="127.0.0.1", port:int=61850) -> tuple[bool, IedClient|None]:

    try:
        ied_client = IedClient(ip_addr, port)
        return True, ied_client
    except Exception as e:
        print('Can not initialise the IED client object')
        print(e)
        return is_pass, None


def connect_ied_server(ied_client: IedClient) -> bool:
    """
    This test function can be used to test the connection to a single IED server
    """

    try:
        is_connected = ied_client.create_IED_connection()
        return is_connected
    except Exception as e:
        print('Can not connect to the IED server object')
        print(e)
        return False


def scan_ied_model(ied_client: IedClient) -> bool:

    try:
        data_model, is_success =  ied_client.get_data_model(verbose=0)
        return is_success
    except Exception as e:
        print('Can not load the IED server data model')
        print(e)
        return False


def read_float_value(ied_client_connection, obj_ref:str, fc_type:int=0) -> tuple[bool, float|None]:
    """
    Change the obj_ref_str accordingly for your test!
    :param ied_client_connection:
    :param obj_ref:
    :param fc_type:
    :return:
    """
    
    print(f'ObjRef (MMS address): {obj_ref}')
    try:
        [value, code] = iec61850.IedConnection_readFloatValue(ied_client_connection, obj_ref, fc_type)
        if code == 0:
            print(f'value: {value}')
            return True, value
        else:
            print('Read float value failed.')
            return False, None
    except Exception as e:
        print('Reading float function could not be called, please check syntax error.')
        print(e)
        return False, None

        
def write_float_value(ied_client_connection, obj_ref:str, value:float, fc_type:int=1) -> bool:
    """
    Change the obj_ref_str accordingly for your test!

    :param ied_client_connection:
    :param obj_ref:
    :param value:
    :param fc_type:
    :return:
    """

    print(f'ObjRef (MMS address): {obj_ref}')
    try:
        code = iec61850.IedConnection_writeFloatValue(ied_client_connection, obj_ref, fc_type, value)
        if code == 0:
            print(f'Successfully passed control setpoint value: {value}')
            return True
        else:
            print('Writing setpoint failed.')
            return False
    except Exception as e:
        print('Writing float function could not be called, please check syntax error.')
        print(e)
        return False


def scan_rcb(ied_client_connection, obj_ref:str) -> bool:
    """
    Change the obj_ref_str accordingly for your test!

    :param ied_client_connection:
    :param obj_ref:
    :return:
    """
    
    def get_mms_value(obj_mms_value):
        """
        A helper function to loop through IEC 61850 data structure to extract 
        float MMS values in a Data Set.
        
        It works fine with common cdc types with fc type MX and SP. For complicated
        data structure this function my return error.
        
        q and t of MX may also be considered as a valid MMS value by this function.
        """

        for iteration in range(5):  # search maximum till depth 5
            array_size = iec61850.MmsValue_getArraySize(obj_mms_value)
            if array_size <= 1:
                mms_type = iec61850.MmsValue_getTypeString(obj_mms_value)
                mms_val = iec61850.MmsValue_toFloat(obj_mms_value)
                
                if mms_type in ['float', 'integer', 'boolean']:
                    print(f'MMS object index {i}, current value: {mms_val}')
                    break
                else:
                    mms_value = iec61850.MmsValue_getElement(obj_mms_value, 0)
                    obj_mms_value = mms_value
            elif array_size < 10:
                # assume the data structure containing float is always placed in the first place
                mms_value = iec61850.MmsValue_getElement(obj_mms_value, 0)
                array_size = iec61850.MmsValue_getArraySize(mms_value)
                
                mms_type = iec61850.MmsValue_getTypeString(mms_value)
                mms_val = iec61850.MmsValue_toFloat(mms_value)
                
                if mms_type=='float':
                    print(f'MMS object index {i}, current value: {mms_val}')
                    break
                else:
                    obj_mms_value = mms_value
            else:
                mms_type = iec61850.MmsValue_getTypeString(obj_mms_value)
                mms_val = iec61850.MmsValue_toFloat(obj_mms_value)
                if mms_type in ['float', 'integer', 'boolean']:
                    print(f'MMS object index {i}, current value: {mms_val}')
                    break
                else:
                    print(f'This data structure seems to be a special type with length {array_size}. Skip it.')


    print(f'ObjRef (MMS address): {obj_ref}')
    is_pass = False
    try:
        [new_rcb, code] = iec61850.IedConnection_getRCBValues(ied_client_connection, obj_ref, None)
        rpt_id = iec61850.ClientReportControlBlock_getRptId(new_rcb)
        ds_obj_ref = iec61850.ClientReportControlBlock_getDataSetReference(new_rcb)
        
        if code == 0:
            [new_ds, code] = iec61850.IedConnection_readDataSetValues(ied_client_connection, ds_obj_ref, None)
            
            if code == 0:
                ds_size = iec61850.ClientDataSet_getDataSetSize(new_ds)
                print(f'The DataSet {ds_obj_ref} contains {ds_size} elements. Let us extract the numeric values')
                obj_mms_values = iec61850.ClientDataSet_getValues(new_ds)
                    
                for i in range(ds_size):
                    # for example, each mmsValue of type MX has 3 attributes:
                    #   - structure
                    #   - bit-string
                    #   - utc-time
                    # while mmsValue of type SP has only 1 attribute, either setMag.f or setVal
                    
                    mms_obj = iec61850.MmsValue_getElement(obj_mms_values, i)
                    array_size = iec61850.MmsValue_getArraySize(mms_obj)
                    for n in range(array_size):
                        get_mms_value(mms_obj)
                
                is_pass = True
            else:
                print('Could not find the Data Set with given MMS reference.')
        else:
            print('Could not find the Report Control Block with given MMS reference.')
    
    except Exception as e:
        print('Scan RCB returns error, please check syntax error.')
        print(e)
    return is_pass

def ied_client_test(ip_addr:str= "192.168.170.240", port:int =61850,
                    name_ied: str = 'virtualCLSmini', name_ld: str='PV1') -> float:
    """
    This function performs a simple IED client test. By default the server is supposed to
    be started using the SCL ./tester/func_tests/IEC61850_DER_v1_slim.cid
    """

    read_objs = []
    write_objs = []
    
    read_objs.append(f'{name_ied}{name_ld}/MMXU1.TotW.mag.f')
    read_objs.append(f'{name_ied}{name_ld}/MMXU1.TotVAr.mag.f')
    read_objs.append(f'{name_ied}{name_ld}/MMXU1.TotVA.mag.f')
    read_objs.append(f'{name_ied}{name_ld}/MMXU1.TotPF.mag.f')
    
    write_objs.append({'key': f'{name_ied}{name_ld}/DGEN1.WMax.setMag.f', 'value': 5000})
    write_objs.append({'key': f'{name_ied}{name_ld}/DGEN1.VMax.setMag.f', 'value': 245})
    write_objs.append({'key': f'{name_ied}{name_ld}/DGEN1.VMin.setMag.f', 'value': 215})
    write_objs.append({'key': f'{name_ied}{name_ld}/DGEN1.OutWSet.setMag.f', 'value': 75})
    
    test_count = 0
    pass_count = 0
    
    # Test 01: client object initialisation
    print('------------------------------------------------------------')
    print('Start Test 01 - client object initialisation')
    [is_pass_test, ied_client] = init_ied_client(ip_addr=ip_addr, port=port)
    test_count +=1
    pass_count += is_pass_test
    if is_pass_test:
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')    
    print('------------------------------------------------------------\n')
    
    # Test 02: client-server TCP connection
    print('------------------------------------------------------------')
    print('Starting Test 02 - client-server TCP connection')
    is_pass_test = connect_ied_server(ied_client)
    test_count +=1
    pass_count += is_pass_test
    if is_pass_test:
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')   
    print('------------------------------------------------------------\n')

    # Test 03: data model scan 
    print('------------------------------------------------------------')
    print('Starting Test 03 - data model scan')
    is_pass_test = scan_ied_model(ied_client)
    test_count +=1
    pass_count += is_pass_test
    if is_pass_test:
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')   
    print('------------------------------------------------------------\n')
    
    # Test 04: read different MX float values
    print('------------------------------------------------------------')
    print('Starting Test 04 - read different MX float values')
    test_result = []
    for obj in read_objs:
        [is_pass_read, value] = read_float_value(ied_client.connection, obj, ied_client.MX)
        test_result.append(is_pass_read)
    test_count +=1
    pass_count += min(test_result)
    if min(test_result):
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')   
    print('------------------------------------------------------------\n')
    
    # Test 05: write different SP float values and then read again
    print('------------------------------------------------------------')
    print('Starting Test 05 - write different SP float values and then read again')
    test_result = []
    for item in write_objs:
        is_pass_write = write_float_value(ied_client.connection, item['key'], item['value'], ied_client.SP)
        test_result.append(is_pass_write)
        
        time.sleep(3)
        [is_pass_read, value] = read_float_value(ied_client.connection, item['key'], ied_client.SP)
        
        if is_pass_write:
            if value - item['value'] < 1e-5:
                print('The expected control setpoint has been set.')
                test_result.append(True)
            else:
                print('The control setpoint has been set, but not updated in the server.')
                print(f'Setpoint: {value}, value in the server: {item["value"]}')
        else:
            print('The control setpoint could not be set, can not validate the new value by reading.')

    test_count +=1
    pass_count += min(test_result)
    if min(test_result):
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')  
    print('------------------------------------------------------------\n')
    
    # Test 06: scan MMS elements in a Report Control Block
    print('------------------------------------------------------------')
    print('Starting Test 06 - scan MMS elements in a Report Control Block')
    
    test_result = []
    for objRef in ied_client.rcb_ref_objs:
        is_pass_test = scan_rcb(ied_client.connection, objRef)
        test_result.append(is_pass_test)
    test_count +=1
    pass_count += min(test_result)
    if min(test_result):
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')  
    print('------------------------------------------------------------\n')
    
    # Output the summary of test
    pass_rate_all = round(pass_count/test_count*100, 2)
    print('------------------------------------------------------------')
    print('All tests have been conducted')
    print(f'{test_count} tests in total, {pass_count} passed. Pass rate {pass_rate_all} %')
    
    return pass_rate_all


def connect_multi_server(ied_server_info:dict, ied_name:str, ld_name:str) -> dict:
    """
    This test function can be used to test the parallel connection to multiple IED servers
    Assume all serers use identical IEC 61850 data model

    Each item in the list should have:
                - item['ip_addr'] -> IP address
                - item['port'] -> TCP port

    :param ied_server_info: Server connection information dictionaries
    :param ied_name:
    :param ld_name:
    :return: pyiec61850 client connection objects
    """

    # test multiple servers
    ied_clients = {}

    for idx, item in ied_server_info.items():
        ip_addr = item['ip_addr']
        port = item['port']
        is_success, ied_client = init_ied_client(ip_addr,port)
        is_connected = ied_client.create_IED_connection()
        ied_clients.update({idx: ied_client})

    obj_ref_str = f'{ied_name}_{ld_name}/MMXU0.OutWSet.setMag.f'
    val = 0.95
    for conn_obj in ied_clients.items():
        code = iec61850.IedConnection_writeFloatValue(conn_obj, obj_ref_str, iec61850.IEC61850_FC_SP, val)
        val -= 0.05

    obj_ref_str = f'{ied_name}_{ld_name}/MMXU0.OutWSet.setMag.f'
    for conn_obj in ied_clients.values():
        [sp_val, code] = iec61850.IedConnection_readFloatValue(conn_obj, obj_ref_str, iec61850.IEC61850_FC_SP)
        print(sp_val)


if __name__ == '__main__':
    '''
    This test function is used to test the client connection to a running IEC 61850 server.
    The server could be the virtual CLS initialised by this lib pyiec61850der, or any other
    IEC 61850 compliant device/software/simulator.
    
    For example, one can open the first python console where the virtual CLS runs. Then open
    the second console to observe and validate the interaction with that server.
    Common test cases are:
        - connection status
        - get data model / DO list / DA list....
        - long-term data transmission
        - execution of control commands
    
    Concrete test cases should be defined in the script ./tester/func_tests/iedClientTester.py
    This function only calls the tester and run tests specified there.
    '''

    print('Start the test for pyiec61850 client')
    try:
        pass_rate = ied_client_test(ip_addr="localhost", port =61852, name_ied='virtualCLSmini', name_ld='PV1')
        if abs(pass_rate - 100)< 1e-5:
            is_pass = True
            print('Test of pyiec61850 client has passed.')
        else:
            is_pass = False
            print('A part of pyiec61850 client test has failed.')
    except Exception as e:
        is_pass = False
        print('Test of pyiec61850 client has failed.')
        print(e)



