# -*- coding: utf-8 -*-
"""
A deprecated test script for structured testing on the IED client side

@author: S. Chen

The test script for pyiec61850 client object was taken from a test framework as described in:

J. Morris, F. Ebe, J. Pichl, S. Chen, G. Heilscher, and J.-G. Leeser, 
‘Implementation of an automated test bench for monitoring and controlling systems of 
decentralized energy systems through Controller Hardware-In-the-Loop and 
Power Hardware-In-the-Loop methodology’, in 2020 5th IEEE Workshop on the Electronic Grid (eGRID), 
Aachen, Germany: IEEE, Nov. 2020, pp. 1–8. doi: 10.1109/eGRID48559.2020.9330636.

The test functions are strongly simplified for easy use.

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
import importlib.util
from settings import helper

helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()
ifExist = importlib.util.find_spec("pylibiec61850")



class Pyiec61850Client(object):
    '''
    This client class is taken from some demo codes in another project, I'm too lazy to update the stuff here.
    It should be able to interact with a static IEC 61850 server, we do not really need that, just ignore the codes if you find them confusing.
    '''
    
    def __init__(self, ip_address: str | None, port: str | None):
        '''
        Initialsing the cleint object
        Sets connection parameters: TCP Port and host IP address of IEC 61850 Server
        '''

        if not ip_address:
            print('No IP address specified, use localhost as default')
            self.ipAddress = '127.0.0.1'
        else:
            self.ipAddress = ip_address

        if not port:
            print('No TCP port specified, use localhost as default')
            self.port = 61850
        else:
            self.port = port

        self.connection = None
        self.connTimeout = 10000
        self.error = None
        self.status = None

        self.iedModel = None
        self.allDO = {}
        self.allDA = {}
        self.allDA_MX = {}  # all DA with FC type MX
        self.allDA_SP = {}  # all DA with FC type SP
        self.allDS = {}  # all Report Control Blocks
        self.allRCB = {}  # all Report Control Blocks
        self.listRefRCB = []  # stores the RCB mms address
        self.listRefDS = []  # stores the RCB mms address

        self.SP = iec61850.IEC61850_FC_SP
        self.MX = iec61850.IEC61850_FC_MX


    def create_IED_connection(self):
        '''
        Creates IED connection with given conncection parameters
        '''

        isConnected = False
        self.connection = iec61850.IedConnection_create()
        iec61850.IedConnection_setConnectTimeout(self.connection, int(self.connTimeout))
        
        self.error = iec61850.IedConnection_connect(self.connection, self.ipAddress, self.port)

        if self.error == iec61850.IED_ERROR_OK:
            print('IEC 61850 connection established')
            isConnected = True
        elif self.error == iec61850.IED_ERROR_CONNECTION_REJECTED:
            print('IEC 61850 connection rejected')
        else:
            print('IEC 61850 connection failed')

        if isConnected:
            self.status = 'connected'
        else:
            self.status = 'connection error'

        return isConnected


    def getState_IED_connection(self):
        '''
        Connection state of the IedConnection instance (either idle, connected or closed)
        Enumeration litervals for IED status:
            - IED_STATE_IDLE
            - IED_STATE_CONNECTED
            - IED_STATE_CLOSED
        
        Querry State of current IED connection:
            - IED_STATE_CLOSED
            - IED_STATE_CONNECTING
            - IED_STATE_CONNECTED
            - IED_STATE_CLOSING
        '''

        state = iec61850.IedConnection_getState(self.connection)
        stateString = None

        if state == iec61850.IED_STATE_IDLE:
            stateString = "IED_STATE_IDLE"
        elif state == iec61850.IED_STATE_CONNECTED:
            stateString = "IED_STATE_CONNECTED"
        elif state == iec61850.IED_STATE_CLOSED:
            stateString = "IED_STATE_CLOSED"
        else:
            stateString = "ERROR"

        return stateString

    def close_IED_connection(self):
        '''
        Closes current IED connection
        '''

        iec61850.IedConnection_close(self.connection)
        print('IEC 61850 connection closed')

    def terminate_IED_connection(self):
        '''
        Terminates current IED connection
        '''

        iec61850.IedConnection_destroy(self.connection)
        print('IEC 61850 connection terminated')

    def get_srv_model(self, verbose=False):
        '''
        Get the IED data model from the IED server
        Returns IED model, MX and SP data attributes with corresponding keys
        
        TODO: the following logic operator based on number of $ is very floppy, because the existence of SDO 
              and SDA will have an impact on this. But it is just a test script right, why would we care? 
                        
        '''

        isSuccess = False
        self.iedModel = {}
        # MX dictionary: LD/LN$FC$DO($SDO)$DA($SDA1)($SDA2)(...) 
        # () means without garanty of appearance
        # --> example: {'Relay1/MMXU$MX$TotW$mag$f': '0.01'}

        if self.error == iec61850.IED_ERROR_OK:
            [deviceList, error] = iec61850.IedConnection_getLogicalDeviceList(self.connection)
            device = iec61850.LinkedList_getNext(deviceList)
            while device:
                LD_name = iec61850.toCharP(device.data)
                print("LD: %s" % LD_name)
                self.iedModel[LD_name] = {}
                [logicalNodes, self.error] = iec61850.IedConnection_getLogicalDeviceDirectory(self.connection, LD_name)
                logicalNode = iec61850.LinkedList_getNext(logicalNodes)
                while logicalNode:
                    LN_name = iec61850.toCharP(logicalNode.data)
                    if verbose:
                        print(" LN: %s" % LN_name)
                    self.iedModel[LD_name][LN_name] = {}
                    [LNobjects, self.error] = iec61850.IedConnection_getLogicalNodeVariables(self.connection, LD_name+"/"+LN_name)
                    LNobject = iec61850.LinkedList_getNext(LNobjects)
                    while LNobject:
                        VAR_name = iec61850.toCharP(LNobject.data)
                        if verbose:
                            print("  VAR: %s" % VAR_name)
                        self.iedModel[LD_name][LN_name][VAR_name] = {VAR_name}

                        if 'RP' in VAR_name and VAR_name.count('$') == 1:
                            RP_MMS = LD_name+'/'+LN_name+'$'+VAR_name
                            self.listRefRCB.append(RP_MMS)
                            RP_MMS = RP_MMS.replace('$RP', '')
                            RP_key = RP_MMS.replace('$', '.')
                            self.allRCB[RP_key] = RP_MMS
                            print(f'Found Report Control Block: {RP_key}')

                        elif 'DS' in VAR_name and VAR_name.count('$') == 1:
                            DS_MMS = LD_name+'/'+LN_name+'$'+VAR_name
                            self.listRefDS.append(DS_MMS)
                            DS_MMS = DS_MMS.replace('$RP', '')
                            DS_key = DS_MMS.replace('$', '.')
                            self.allDS[DS_key] = DS_MMS
                            print(f'Found Report Control Block: {DS_key}')
                        elif VAR_name.count('$') == 1:  # FC$DO($SDO)$DA($SDA1)($SDA2)(...) 
                            DO_MMS = LD_name+'/'+LN_name+'$'+VAR_name
                            FCType = VAR_name.split('$')[0]
                            FCTypeKey = getattr(iec61850, f'IEC61850_FC_{FCType}')
                            DO_MMS = DO_MMS.replace(f'${FCType}', '')
                            DO_key = DO_MMS.replace('$', '.')
                            #DO_val = iec61850.IedConnection_readFloatValue(self.connection, DO_key, FCTypeKey)
                            self.allDO[DO_key] = None
                        
                        elif VAR_name.count('$') == 2:  # FC$DO($SDO)$DA($SDA1)($SDA2)(...)
                            DA_MMS = LD_name+'/'+LN_name+'$'+VAR_name
                            FCType = VAR_name.split('$')[0]
                            FCTypeKey = getattr(iec61850, f'IEC61850_FC_{FCType}')
                            DA_MMS = DA_MMS.replace(f'${FCType}', '')
                            DA_key = DA_MMS.replace('$', '.')
                            #DA_val = iec61850.IedConnection_readFloatValue(self.connection, DA_key, FCTypeKey)
                            self.allDA[DA_key] = None
                            
                        elif VAR_name.count('$') > 2:
                            SDA_MMS = LD_name+'/'+LN_name+'$'+VAR_name
                            FCType = VAR_name.split('$')[0]
                            FCTypeKey = getattr(iec61850, f'IEC61850_FC_{FCType}')
                            SDA_MMS = SDA_MMS.replace(f'${FCType}', '')
                            SDA_key = SDA_MMS.replace('$', '.')
                            if FCType == 'MX' and '.f' in SDA_MMS:
                                SDA_val = iec61850.IedConnection_readFloatValue(self.connection, SDA_key, FCTypeKey)
                                self.allDA_MX[SDA_key] = SDA_val
                                if verbose:
                                    print(f'{SDA_key}: {SDA_val}')
                            elif FCType == 'SP' and '.f' in SDA_MMS:
                                SDA_val = iec61850.IedConnection_readFloatValue(self.connection, SDA_key, FCTypeKey)
                                self.allDA_SP[SDA_key] = SDA_val
                                if verbose:
                                    print(f'{SDA_key}: {SDA_val}')
                            
                        
                            
                        LNobject = iec61850.LinkedList_getNext(LNobject)
                    iec61850.LinkedList_destroy(LNobjects)
                    logicalNode = iec61850.LinkedList_getNext(logicalNode)
                iec61850.LinkedList_destroy(logicalNodes)
                device = iec61850.LinkedList_getNext(device)

            iec61850.LinkedList_destroy(deviceList)

            if self.iedModel != {}:
                print('IEC 61850 server has IED data model')
                print(f'Number of DO in the IED data model: {len(self.allDO)}')
                print(f'Number of DA in the IED data model: {len(self.allDA)}')
                print(f'Number of RCB in the IED data model: {len(self.allRCB)}')
                isSuccess = True
            else:
                print('IED data model transmission failed')
        else:
            print('IEC 61850 connection failed. IED data model transmission failed')

        return isSuccess


    def readFloatValue(self, objRef, fcType='MX', rounding=None):
        '''
        Simple get function: Get current float set point from IED server
        rounding
        '''
        
        fcTypeKey = getattr(iec61850, f'IEC61850_FC_{fcType}')
        [value, errorCode] = iec61850.IedConnection_readFloatValue(self.connection, objRef, fcTypeKey)
        
        if errorCode == 0:
            if type(rounding) is int:
                value = float(format(round(value[0], rounding)))
            print(f'Measurement (IED serve: {objRef}): {value}')
        else:
            print(f'Reading float value failed, error code: {errorCode}')
        return value, errorCode


    def writeFloatValue(self, objRef=None, value=None, fcType=None):
        '''
        Simple write function
        '''
        
        fcTypeKey = getattr(iec61850, f'IEC61850_FC_{fcType}')
        errorCode = iec61850.IedConnection_writeFloatValue(self.connection, objRef, fcTypeKey, value)
        
        return errorCode
    

def testInitIedClient(ipAddress="127.0.0.1", port=61850):
    isPass = False
    
    try:
        iedClient = Pyiec61850Client(ipAddress, port)
        isPass = True
    except:
        print('Can not initialise the IED client object')
        iedClient = None
        
    return isPass, iedClient

def testConnectIedServer(iedClient):
    '''
    This test function can be used to test the connection to a single IED server
    '''
    
    isPass = False
    try:
        isConnected = iedClient.create_IED_connection()
        isPass = isConnected
    except:
        print('Can not connect to the IED server object')
    
    return isPass


def testScanIedModel(iedClient):
    
    isPass = False
    try:
        isSuccess= iedClient.get_srv_model(verbose=False)
        isPass = isSuccess
    except:
        print('Can not load the IED server data model')
    
    return isPass


def testReadFloatValue(iedClientConnection=None, objRef=None, fcType=0):
    '''
    Change the obj_ref accordingly for your test!
    '''
    
    print(f'ObjRef (MMS address): {objRef}')
    isPass = False
    try:
        [value, errorCode] = iec61850.IedConnection_readFloatValue(iedClientConnection, objRef, fcType)
        if errorCode == 0:     
            print(f'value: {value}')
            isPass = True
        else:
            print('Read float value failed.')
    except:
        print('Reading float function could not be called, please check syntax error.')
        
    return isPass, value   
        
def testWriteFloatValue(iedClientConnection=None, objRef=None, value=None, fcType=1):
    '''
    Change the obj_ref accordingly for your test!
    '''
    
    print(f'ObjRef (MMS address): {objRef}')
    isPass = False
    try:
        errorCode = iec61850.IedConnection_writeFloatValue(iedClientConnection, objRef, fcType, value)
        if errorCode == 0:
            print(f'Successfully passed control setpoint value: {value}')
            isPass = True
        else:
            print('Writting setpoint failed.')
    except:
        print('Writing float function could not be called, please check syntax error.')

    return isPass

def testScanRCB(iedClientConnection=None, objRef=None):
    '''
    Change the obj_ref accordingly for your test!
    '''
    
    def getMmsValue(objMmsValue):
        '''
        A helper function to loop through IEC 61850 data structure to extract 
        float MMS values in a Data Set.
        
        It works fine with common CDC types with FC type MX and SP. For complicated
        data structure this function my return error.
        
        q and t of MX may also be considered as a valid MMS value by this function.
        '''
        
        
        for iteration in range(5):  # search maximum till depth 5
            arraySize = iec61850.MmsValue_getArraySize(objMmsValue)
            if arraySize <= 1:
                mmsType = iec61850.MmsValue_getTypeString(objMmsValue)
                mmsVal = iec61850.MmsValue_toFloat(objMmsValue)
                
                if mmsType in ['float', 'integer', 'boolean']:
                    print(f'MMS object index {i}, current value: {mmsVal}')
                    break
                else:
                    mmsValue = iec61850.MmsValue_getElement(objMmsValue, 0)
                    objMmsValue = mmsValue
            elif arraySize < 10:
                # assume the data structure containing float is always placed in the first place
                mmsValue = iec61850.MmsValue_getElement(objMmsValue, 0)  
                arraySize = iec61850.MmsValue_getArraySize(mmsValue)
                
                mmsType = iec61850.MmsValue_getTypeString(mmsValue)
                mmsVal = iec61850.MmsValue_toFloat(mmsValue)
                
                if mmsType=='float':
                    print(f'MMS object index {i}, current value: {mmsVal}')
                    break
                else:
                    objMmsValue = mmsValue
            else:
                mmsType = iec61850.MmsValue_getTypeString(objMmsValue)
                mmsVal = iec61850.MmsValue_toFloat(objMmsValue)
                if mmsType in ['float', 'integer', 'boolean']:
                    print(f'MMS object index {i}, current value: {mmsVal}')
                    break
                else:
                    print(f'This data structure seems to be a special type with length {arraySize}. Skip it.')

                
        
    
    print(f'ObjRef (MMS address): {objRef}')
    isPass = False
    try:
        [newRCB, errorCode] = iec61850.IedConnection_getRCBValues(iedClientConnection, objRef, None)
        rptID = iec61850.ClientReportControlBlock_getRptId(newRCB)
        refDS = iec61850.ClientReportControlBlock_getDataSetReference(newRCB)
        
        if errorCode == 0:
            [newDS, errorCode] = iec61850.IedConnection_readDataSetValues(iedClientConnection, refDS, None)
            
            if errorCode == 0:
                lenDS = iec61850.ClientDataSet_getDataSetSize(newDS)
                print(f'The DataSet {refDS} contains {lenDS} elements. Let us extract the numeric values')
                objMmsValues = iec61850.ClientDataSet_getValues(newDS)
                    
                for i in range(lenDS):
                    # for example, each mmsValue of type MX has 3 attributes:
                    #   - structure
                    #   - bit-string
                    #   - utc-time
                    # while mmsValue of type SP has only 1 attribute, either setMag.f or setVal
                    
                    mmsObj = iec61850.MmsValue_getElement(objMmsValues, i)
                    arraySize = iec61850.MmsValue_getArraySize(mmsObj)
                    for n in range(arraySize):
                        getMmsValue(mmsObj)

                
                isPass = True
            else:
                print('Could not find the Data Set with given MMS reference.')
        else:
            print('Could not find the Report Control Block with given MMS reference.')
    
    except:
        print('Scan RCB returns error, please check syntax error.')

    return isPass
        
    
def iedClientTest():
    '''
    This function performs a simple IED client test. By default the server is supposed to
    be started using the SCL ./tester/func_tests/IEC61850_DER_v1_slim.cid
    '''
    

    nameIED = 'virtualCLSmini'
    nameLD = 'PV1'
    listObjRead = []
    listObjWrite = []
    
    listObjRead.append(f'{nameIED}{nameLD}/MMXU1.TotW.mag.f')
    listObjRead.append(f'{nameIED}{nameLD}/MMXU1.TotVAr.mag.f')
    listObjRead.append(f'{nameIED}{nameLD}/MMXU1.Hz.mag.f')
    
    listObjWrite.append({'key': f'{nameIED}{nameLD}/DGEN1.OutWSet.setMag.f', 'value': 0.75})
    
    nTest = 0
    nPass = 0
    
    # Test 01: client object initialisation
    print('------------------------------------------------------------')
    print('Start Test 01 - client object initialisation')
    [isPass, iedClient] = testInitIedClient(ipAddress="127.0.0.1", port=61850)
    nTest +=1
    nPass += isPass
    if isPass:
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')    
    print('------------------------------------------------------------\n')
    
    # Test 02: client-server TCP connection
    print('------------------------------------------------------------')
    print('Starting Test 02 - client-server TCP connection')
    isPass = testConnectIedServer(iedClient)
    nTest +=1
    nPass += isPass
    if isPass:
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')   
    print('------------------------------------------------------------\n')

    # Test 03: data model scan 
    print('------------------------------------------------------------')
    print('Starting Test 03 - data model scan')
    isPass = testScanIedModel(iedClient)
    nTest +=1
    nPass += isPass
    if isPass:
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')   
    print('------------------------------------------------------------\n')
    
    # Test 04: read different MX float values
    print('------------------------------------------------------------')
    print('Starting Test 04 - read different MX float values')
    testResult = []
    for obj in listObjRead:
        [isPassRead, value] = testReadFloatValue(iedClient.connection, obj, iedClient.MX)
        testResult.append(isPassRead)
    nTest +=1
    nPass += min(testResult)
    if min(testResult):
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')   
    print('------------------------------------------------------------\n')
    
    # Test 05: write different SP float values and then read again
    print('------------------------------------------------------------')
    print('Starting Test 05 - write different SP float values and then read again')
    testResult = []
    for item in listObjWrite:
        isPassWrite = testWriteFloatValue(iedClient.connection, item['key'], item['value'], iedClient.SP)
        testResult.append(isPassWrite)
        
        time.sleep(3)
        [isPassRead, value] = testReadFloatValue(iedClient.connection, item['key'], iedClient.SP)
        
        if isPassWrite:
            if value - item['value'] < 1e-5:
                print('The expected control setpoint has been set.')
                testResult.append(True)
            else:
                print('The control setpoint has been set, but not updated in the server.')
                print(f'Setpoint: {value}, value in the server: {item["value"]}')
        else:
            print('The control setpoint could not be set, can not validate the new value by reading.')

    nTest +=1
    nPass += min(testResult)
    if min(testResult):
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')  
    print('------------------------------------------------------------\n')
    
    # Test 06: scan MMS elements in a Report Control Block
    print('------------------------------------------------------------')
    print('Starting Test 06 - scan MMS elements in a Report Control Block')
    
    testResult = []
    for objRef in iedClient.listRefRCB:
        isPass = testScanRCB(iedClient.connection, objRef)
        testResult.append(isPass)
    nTest +=1
    nPass += min(testResult)
    if min(testResult):
        print('++++++++++++++++++   test passed   +++++++++++++++++++++++++++')
    else:
        print('!!!!!!!!!!!!!!!!!!   test failed    !!!!!!!!!!!!!!!!!!!!!!!!!!')  
    print('------------------------------------------------------------\n')
    
    # Output the summary of test
    passRate = round(nPass/nTest*100, 2)
    print('------------------------------------------------------------')
    print('All tests have been conducted')
    print(f'{nTest} tests in total, {nPass} passed. Pass rate {passRate} %')
    
    return passRate

def testIedClient():
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
        passRate = iedClientTest()    
        if abs(passRate - 100)< 1e-5:
            isPass = True
            print('Test of pyiec61850 client has passed.')
        else:
            isPass = False
            print('A part of pyiec61850 client test has failed.')
    except:
        isPass = False
        print('Test of pyiec61850 client has failed.')

    return isPass

if __name__ == '__main__':
    passRate = testIedClient()

# def connect_multi_server(ied_servers=None):
#     '''
#     This test function can be used to test the parallel connection to multiple IED servers
#     Input:
#         - ied_servers: a list of Server connection information dictionaries
#             each item in the list should have:
#                 - item['ip_address'] -> IP address
#                 - item['port'] -> TCP port
#     Output:
#         - listServerConnection: a list of pyiec61850 client connection objects
#     '''

#     # test multiple servers
#     listServerConnection = []

#     for port in range(43001, 43011):
#         pyiec61850.set_connection_parms(port, "127.0.0.1")
#         pyiec61850.create_IED_connection()
#         pyiec61850.get_srv_model()
#         listServerConnection.append(gvar.client_connection)

#     obj_ref = f'{nameIED}_{nameLD}/PV1_MMXU0.OutWSet.setMag.f'
#     val = 0.95
#     for conn_obj in listServerConnection:
#         error = iec61850.IedConnection_writeFloatValue(conn_obj, obj_ref, iec61850.IEC61850_FC_SP, val)
#         val -= 0.05

#     obj_ref = f'{nameIED}_{nameLD}/PV1_MMXU0.OutWSet.setMag.f'
#     for conn_obj in listServerConnection:
#         [valSP, error] = iec61850.IedConnection_readFloatValue(conn_obj, obj_ref, iec61850.IEC61850_FC_SP)
#         print(valSP)
    
