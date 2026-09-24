# -*- coding: utf-8 -*-
'''
A deprecated python script that simulates a virtual SCADA.

@author: Chen, Morris

Essential working steps:
    - initialization of the IED server connections
    - initialization of the pandapower network
    - every 1 minute one iteration of power flow calculation and DER control
    - every 15 minutes, check IED connection and influxdb connection
    - every round hour, upload measurements and records (local or influxdb)

Units of TotW:
    - W in local/influxdb profile, IED server
    - kW in pandapower PF solver

Notes:
    - the timeout of IED connection is permanently set to 1 second, this means each attempt of IED client connection will
        require at least 1 second, too frequent IED reconnection will cause enormous delay.
'''

import sys
import os

# if os.name != 'nt':  # if not windows os
#     sys.path.append("/work/")
#     listFile = os.listdir("/work/")
#     print("check files in working directory")
#     print(listFile)
#     os.environ["PATH"] = "/work/;" + os.environ["PATH"]
# else:
#     os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
# standard built-in lib
import pandapower as pp
import numpy as np
import time
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import copy

# standard lib requiring installation
import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS

# local lib
import iec61850 as iec


##############################################################################
#####################     service initialization      ########################
##############################################################################

class Gvar(object):
    LOGGER_NAME = 'pandapowerRunner'
    MIN_BUS_VOLTAGE = 0.95
    MAX_BUS_VOLTAGE = 1.05
    # LIMIT_MAX_BUS_VOLTAGE  = 1.05
    # LIMIT_MIN_BUS_VOLTAGE = 0.95
    MAX_LINE_OVERLOADING = 80
    MAX_TRAFO_OVERLOADING = 80
    WARNING_BUS_OVERVOLTAGE = 1.10
    WARNING_LINE_OVERLOADING = 90
    WARNING_TRAFO_OVERLOADING = 90
    stdTrafoType = '0.63 MVA 20/0.4 kV'
    stdLineTypeLV = 'NAYY 4x50 SE'  # max I 0.142 kA
    stdLineTypeMV = 'NA2XS2Y 1x95 RM/25 12/20 kV'  # max I 0.252 kA
    
    listNumberFeeders = [2, 3, 5]
    
    pvPerFeeder = 10  # this should be an integer
    ratioLoadToPV = 2  # this should be an integer
    householdPerFeeder = pvPerFeeder * ratioLoadToPV
    nFeeder = sum(listNumberFeeders)
    nPV = nFeeder * pvPerFeeder
    nLoad = nFeeder * householdPerFeeder
    network = None
    
    nameConfigFile = 'config_clsDockerBuilder_update.xlsx'
    sheetNameConfig = 'IedConfig'
    cDir = os.getcwd()
    pathProfile = rf'{cDir}/profiles'
    pathStatistics = rf'{cDir}/records'
    
    dataSource = 'local'  # ied/ influxdb / local / random
    statisticTarget = 'influxdb'  # influxdb / local
    clientInfluxdbRead = None
    clientInfluxdbWrite = None
    bucketWrite = '7602_pandapower_testResults'  # TODO: check this and put the right one here
    simulationIdentifer = f'sim_{datetime.strftime(datetime.fromtimestamp(datetime.today().timestamp()), "%Y%m%d%H%M%S")}'
    os.mkdir(rf'{pathStatistics}/{simulationIdentifer}')
    
    iedHostIP = '192.168.170.220'  # for the realtime simulation with containers
    #iedHostIP = '127.0.0.1'  # for the test on PC localhost
    defaultStartTime = '2016-07-01 08:00:00'
    timeDiff = 934926993.928  # time shift between the libiec61850 server and simulation
    
    cTime = None
    cTimeUnix = None
    
    dfConfig = None
    listNodeInstanceLoad = [None] * nLoad  # use a list to store the load node instances
    listNodeInstancePV = [None] * nPV  # use a list to store the pv node instances
    
    # listNodeLoad = [None] * nLoad  # list storing network information
    # listNodePV = [None] * n_pv  # list storing network information
    
    listNodeAll = []   # list storing network information
    listLineAll = []   # list storing network information
    listLoadAll = []   # list storing network information
    listPVAll = []   # list storing network information
    
    IEC_MX_ADDRESS_PV = 'demoVirtualCLS_demoProsumerXY/PV1_MMXU0.TotW.mag.f'
    IEC_MX_ADDRESS_LOAD = 'demoVirtualCLS_demoProsumerXY/LOAD1_MMXU0.TotW.mag.f'    
    IEC_SP_ADDRESS_PV = 'demoVirtualCLS_demoProsumerXY/PV1_MMXU0.OutWSet.setMag.f'
    IEC_SP_ADDRESS_LOAD = 'demoVirtualCLS_demoProsumerXY/LOAD1_MMXU0.OutWSet.setMag.f'
    IEC_TIME_ADDRESS_PV = 'demoVirtualCLS_demoProsumerXY/PV1_MMXU0.TotW.t'
    IEC_TIME_ADDRESS_LOAD = 'demoVirtualCLS_demoProsumerXY/LOAD1_MMXU0.TotW.t'
    
    listSetpoint = None
    
class Node(object):
    """
    This class stores the essential information of each node in the pandapower network, including configuration, measurements,
    setpoint and local profile.
    The dataframes are for records purpose only (local or influxdb)
    """
    
    def __init__(self, port=None, hostIP=None):
        self.port = port
        self.hostIP = hostIP
    
    idx = 0  # to be changed during initialization of node
    idxInNetwork = 0  # to be changed during initialization of the pandapower network
    labelNetwork = None  # to be changed during initialization, a lable in the pandapower network
    dataSource = 'unknown'
    clsGUID = None  # to be changed during initialization
    objIedClient = None  # keep alive IED connection every 15 minutes
    cValMX = 0
    cValSP = 1.0
    cValSP_write = 1.0
    countUnchangedSP = 0  # count how long has the cValSP_write not been changed
    isIedConnected = 0  # 1 or 0, check IED connection every 5 minutes
    dfProfileLocal = None  # only for the mode with data_source is 'local'
    dfProfileInfluxdb = None  # only for the mode with data_source is 'influxdb'
    dfStatisticsTemplate = pd.DataFrame({'timestamp': [], 'timestampÚnix': [], 'isIedConnected': [],
                                            'valMX': [], 'valSP': [], 'valSP_write': []})
    dfStatistics = copy.deepcopy(dfStatisticsTemplate)
    dfStatisticsNewRow = copy.deepcopy(dfStatisticsTemplate)
    filenameStatistics = None  # define this during the initialization
    
    
    def createCSV(self):
        self.dfStatistics.to_csv(self.filenameStatistics, mode='a', index=False, header=True)
    
    def addNewRow(self):
        """
        Add the new row to dfStatistics, and free the "new row" dataFrame
        This function should be called after each pandapower power flow is done and the new-row df are filled with values        
        """
        
        self.dfStatistics = pd.concat([self.dfStatistics, self.dfStatisticsNewRow], ignore_index=True)
        self.dfStatisticsNewRow = copy.deepcopy(self.dfStatisticsTemplate)
    
    def addValToStatistics(self, key=None, val=None):
        """
        Add a new value to dfNetworkStateNewRow
        """
        
        self.dfStatisticsNewRow.loc[0, key] = val
    
    def exportDfStatistics(self):
        """
        reset the dataframe
        """
        
        isExportSuccess = False
        # try:        
        if gvar.statisticTarget == 'local':
            self.dfStatistics.to_csv(self.filenameStatistics, mode='a', index=False, header=False)
            isExportSuccess = True
        elif gvar.statisticTarget == 'influxdb':
            self.dfStatistics.to_csv(self.filenameStatistics, mode='a', index=False, header=False)  # also export_compose_file a copy of the df
            pushDataToInfluxdb(self.dfStatistics, gvar.simulationIdentifer + '_node')
            
            isExportSuccess = True
        else:
            logger.error(f'Unknown target {gvar.statisticTarget} for the export of records')
        
        # except:
        #     logger.warning('Export of records failed, keep the data in buffer and wait for the next trigger hour')
        
        # if isExportSuccess == True:
        #     self.resetDfStatistics()
    
    def resetDfStatistics(self):
        """
        reset the dataframe
        """
        
        self.dfStatistics = copy.deepcopy(self.dfStatisticsTemplate)
        

class RoutineStatistics(object):
    """
    These dataframes are for records purpose only (local or influxdb)
    TODO: implement a class DataStatistics(object) to uniform the collection and export
        of records
    """
    
    dfStatisticsTemplate = pd.DataFrame({'timestamp': [], 'tstmp_unix': [], 'nConnectedPV': [],  'nConnectedLoad': [],
                                         'nSetpoint': [], 'minSetpointW': [], 'maxSetpointW': [], 'meanSetpointW': [], 
                                         'processingTime': [],
                                         }) 
    
    dfNetworkStateTemplate = pd.DataFrame({'timestamp': [], 'tstmp_unix': [],
                                           'minVoltage': [], 'maxVoltage': [], 'meanVoltage': [], 'nNodeOvervoltage': [],
                                           'minLineLoading': [], 'maxLineLoading': [], 'meanLineLoading': [], 'nLineOverloading': [],
                                           'minTrafoLoading': [], 'maxTrafoLoading': [], 'meanTrafoLoading': [], 'nTrafoOverloading': [],
                                           })
    
    dfStatistics = copy.deepcopy(dfStatisticsTemplate)
    dfNetworkState = copy.deepcopy(dfNetworkStateTemplate)
    dfStatisticsNewRow = copy.deepcopy(dfStatisticsTemplate)
    dfNetworkStateNewRow = copy.deepcopy(dfNetworkStateTemplate)
    
    
    def getFileName(self):
        """
        Get the file name of the export data
        """
        self.filenameStatistics = rf'{os.getcwd()}/records/{gvar.simulationIdentifer}/routineStatistics.csv'
        self.filenameNetworkState = rf'{os.getcwd()}/records/{gvar.simulationIdentifer}/networkState.csv'
        
    def createCSV(self):
        self.dfStatistics.to_csv(self.filenameStatistics, mode='a', index=False, header=True)
        self.dfNetworkState.to_csv(self.filenameNetworkState, mode='a', index=False, header=True)
    
    def addNewRow(self):
        """
        Add the new row to dfStatistics and dfNetworkState, and free the two "new row" dataFrame
        This function should be called after each pandapower power flow is done and the new-row df are filled with values        
        """
        
        self.dfStatistics = pd.concat([self.dfStatistics, self.dfStatisticsNewRow], ignore_index=True)
        self.dfNetworkState = pd.concat([self.dfNetworkState, self.dfNetworkStateNewRow], ignore_index=True)
        
        self.dfStatisticsNewRow = copy.deepcopy(self.dfStatisticsTemplate)
        self.dfNetworkStateNewRow = copy.deepcopy(self.dfNetworkStateTemplate)
    
    def addValToStatistics(self, key=None, val=None):
        """
        Add a new value to dfNetworkStateNewRow
        """
        
        self.dfStatisticsNewRow.loc[0, key] = val
        
        
    def addValToNetworkState(self, key=None, val=None):
        """
        Add a new value to dfNetworkStateNewRow
        """
        
        self.dfNetworkStateNewRow.loc[0, key] = val
    
    def exportDfStatistics(self):
        """
        reset the dataframe
        """
        
        isExportSuccess = False
        #try:        
        if gvar.statisticTarget == 'local':
            self.dfStatistics.to_csv(self.filenameStatistics, mode='a', index=False, header=False)
            self.dfNetworkState.to_csv(self.filenameNetworkState, mode='a', index=False, header=False)
            isExportSuccess = True
        elif gvar.statisticTarget == 'influxdb':
            self.dfStatistics.to_csv(self.filenameStatistics, mode='a', index=False, header=False)
            self.dfNetworkState.to_csv(self.filenameNetworkState, mode='a', index=False, header=False)
            pushDataToInfluxdb(self.dfStatistics, gvar.simulationIdentifer + '_statistics')
            pushDataToInfluxdb(self.dfNetworkState, gvar.simulationIdentifer + '_networkState')
            isExportSuccess = True
        else:
            logger.error(f'Unknown target {gvar.statisticTarget} for the export of records')
        
        #except:
        #    logger.warning('Export of records failed, keep the data in buffer and wait for the next trigger hour')
        
        # if isExportSuccess == True:
        #     self.resetDfStatistics()
    
    def resetDfStatistics(self):
        """
        reset the dataframe
        """
        
        self.dfStatistics = copy.deepcopy(self.dfStatisticsTemplate)
        self.dfNetworkState = copy.deepcopy(self.dfNetworkStateTemplate)
        
##############################################################################
##################     some supporting functions      ########################
##############################################################################

def createRotatingLog():
    """
    Creates a rotating log
    """
    logger = logging.getLogger(gvar.LOGGER_NAME)
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, filemode = 'a')
    path = rf'{os.getcwd()}/{gvar.LOGGER_NAME}_logger.log'
    
    # add a rotating handler
    fh = RotatingFileHandler(path, maxBytes=300*1000*1000,
                                  backupCount=10)
    logger.setLevel(logging.DEBUG)
    logging.disable(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(process)d - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    if (logger.hasHandlers()):
        logger.handlers.clear()
    logger.addHandler(fh)
    return logger


##############################################################################
##################     pyiec61850 API configuration     ######################
##############################################################################

class pyiec61850client(object):    
    def __init__(self, port=None, hostIP=None):
        self.port = port
        self.hostIP = hostIP
        self.iedState = None
        self.iedConnection = None
        self.iedConnectError = None
 
    def createIedConnection(self):
        '''
        Creates IED connection with given conncection parameters
        '''
        
        self.iedConnection = iec.IedConnection_create()
        iec.IedConnection_setConnectTimeout(self.iedConnection, int(1000))  # set timeout to 1s to speed up the initialization
        
        type(self.port)
        iedError = iec.IedConnection_connect(self.iedConnection, self.hostIP, int(self.port))

        if (iedError == iec.IED_ERROR_OK):
            logger.info('IEC 61850 connection established')
        elif iedError == iec.IED_ERROR_CONNECTION_REJECTED:
            logger.error('IEC 61850 connection rejected')		
        else:
            logger.error('IEC 61850 connection failed')
        
        self.iedConnectionError = iedError

        
    def getStateIedConnection(self):
        '''
        Querry State of current IED connection
        
        IED_STATE_CLOSED 
        
        IED_STATE_CONNECTING 

        IED_STATE_CONNECTED 

        IED_STATE_CLOSING 
        
        '''
        
        logger.info(f'test IEC 61850 connection to {self.hostIP}:{self.port}')
        state = iec.IedConnection_getState(self.iedConnection)

        if state == iec.IED_STATE_CONNECTING:
            logger.warning('IED state: IED_STATE_CONNECTING')
        elif state == iec.IED_STATE_CONNECTED:
            logger.info('IED state: IED_STATE_CONNECTED')
        elif state == iec.IED_STATE_CLOSED:
            logger.warning('IED state: IED_STATE_CLOSED')
        elif state == iec.IED_STATE_CLOSING:
            logger.warning('IED state: IED_STATE_CLOSING')
        else:
            logger.error('IED state: unknown ERROR')
        
        self.iedState = state
        return state
        
def createIedClient(port=None, hostIP=None):
    logger.info('-------------------------------------------------------------------')
    logger.info(f'Init IEC 61850 connection to {hostIP}:{port}')
    newIedClient = pyiec61850client(port, hostIP)
    newIedClient.createIedConnection()
    newIedClient.getStateIedConnection()
    logger.info(f'IED Client state: {newIedClient.iedState}')
    logger.info('-------------------------------------------------------------------')
    return newIedClient

def keepAliveIedConnection(objIedClient):
    state = objIedClient.getStateIedConnection()
    if state != iec.IED_STATE_CONNECTED:
        logger.info(f'Reconnecting IED server {objIedClient.hostIP}:{objIedClient.port}')
        for i in range(10):  # reconnect 10 times
            objIedClient.createIedConnection()  # try reconnect
            logger.info(f'Reconnection attempt {i}, iedState: {objIedClient.iedState}')
            if objIedClient.iedState == iec.IED_STATE_CONNECTED:
                logger.info(f'IED server {objIedClient.hostIP}:{objIedClient.port} sucessfully reconnected')
                break
    else:
        logger.info(f'Connection to IED server {objIedClient.hostIP}:{objIedClient.port} is ok')
                
    return objIedClient

def getIedTimeUTC(objIedClient=None, derType='pv'):
    if derType == 'pv':
        [valTstmp, error] = iec.IedConnection_readTimestampValue(objIedClient.iedConnection, gvar.IEC_TIME_ADDRESS_PV, iec.IEC61850_FC_MX, None)
    elif derType == 'load':
        [valTstmp, error] = iec.IedConnection_readTimestampValue(objIedClient.iedConnection, gvar.IEC_TIME_ADDRESS_LOAD, iec.IEC61850_FC_MX, None)

    tstmpUnix = int(valTstmp.val)/1000 - gvar.timeDiff  # this is just used to synchronize the time with the IED servers
    tstmp = datetime.strftime(datetime.fromtimestamp(round(int(tstmpUnix)/10)*10), '%Y-%m-%d %H:%M:%S')
    
    return tstmp, tstmpUnix

def getIedVal(objIedClient=None, FC='MX', derType='pv'):
    if FC == 'MX' and derType == 'pv':
        [val, error] = iec.IedConnection_readFloatValue(objIedClient.iedConnection, gvar.IEC_MX_ADDRESS_PV, iec.IEC61850_FC_MX)
    elif FC == 'MX' and derType == 'load':
        [val, error] = iec.IedConnection_readFloatValue(objIedClient.iedConnection, gvar.IEC_MX_ADDRESS_LOAD, iec.IEC61850_FC_MX)
    elif FC == 'SP' and derType == 'pv':
        [val, error] = iec.IedConnection_readFloatValue(objIedClient.iedConnection, gvar.IEC_SP_ADDRESS_PV, iec.IEC61850_FC_SP)
    elif FC == 'SP' and derType == 'load':
        [val, error] = iec.IedConnection_readFloatValue(objIedClient.iedConnection, gvar.IEC_SP_ADDRESS_LOAD, iec.IEC61850_FC_SP)
    else:
        logger.warning(f'Unknown FC type {FC} or derType {derType}')
    
    return val, error

def writeIedValSP(objIedClient=None, valSP=None):
    """
    In current version only pv are controllable.
    """
    
    error = iec.IedConnection_writeFloatValue(objIedClient.iedConnection, gvar.IEC_SP_ADDRESS_PV, iec.IEC61850_FC_SP, valSP)
    
    return error

##############################################################################
#################     pandapower related functions    ########################
##############################################################################

def getNetworkConfig():
    """
    get network configuration and init
    """
    logger.info('=================   Begin load network config    =================')
    gvar.dfConfig = pd.read_excel(gvar.nameConfigFile, gvar.sheetNameConfig)
    logger.info('=================   End load network config     =================\n')

def initIedClients():
    """
    """
    
    logger.info('=================   Begin IED client initialization    =================')    
    dfConfig = gvar.dfConfig    
    listKey = list(dfConfig.keys())
    listIdx = list(range(len(dfConfig)))
    idxPV = 0
    idxLoad = 0
    nIedPV = 0
    nIedLoad = 0
    nIedConnectedPV = 0
    nIedConnectedLoad = 0
    while listIdx != []:
        idxCLS = listIdx.pop()
        thisNode = Node(port=dfConfig['port'][idxCLS], hostIP=gvar.iedHostIP)
        for item in listKey:
            setattr(thisNode, item, dfConfig.loc[idxCLS, item])        

        isIedConnected = 0
        if thisNode.dataSource == 'ied':
            thisNode.objIedClient = createIedClient(thisNode.port, thisNode.hostIP)
            if thisNode.objIedClient.iedState == iec.IED_STATE_CONNECTED:
                isIedConnected = 1    
                thisNode.isIedConnected = 1
        elif thisNode.dataSource in ['local', 'influxdb']:
            loadNodeProfile(thisNode)  # export_compose_file data in profile, meanwhile node.objIedClient == None and node.isIedConnected == 0
        else:
            pass
            logger.error(f'Unknown data source {thisNode.dataSource}, no profile available for this node')
            
        # insert thisNode into the node list
        if thisNode.derType == 'pv': 
            thisNode.idx = idxPV
            gvar.listNodeInstancePV[idxPV] = thisNode
            idxPV += 1  
            nIedPV += 1
            nIedConnectedPV += isIedConnected
        elif thisNode.derType == 'load':
            thisNode.idx = idxLoad
            gvar.listNodeInstanceLoad[idxLoad] = thisNode
            idxLoad += 1
            nIedLoad += 1
            nIedConnectedLoad += isIedConnected

        thisNode.filenameStatistics = rf'{os.getcwd()}/records/{gvar.simulationIdentifer}/{thisNode.derType}_{thisNode.idx}.csv'
        thisNode.createCSV()
        
    if idxPV == 0:
        idxPV = -1
    if idxLoad == 0:
        idxLoad = -1
    logger.info(f'IedConfig file loaded, {len(dfConfig)} data sets for measurments available')
    logger.info(f'{nIedPV} PV IED servers in the list, {nIedConnectedPV} of them are connected')
    logger.info(f'{nIedLoad} Load IED servers in the list, {nIedConnectedLoad} of them are connected')
    
    routineStatistics.addValToStatistics('nConnectedPV', nIedConnectedPV)
    routineStatistics.addValToStatistics('nConnectedLoad', nIedConnectedLoad)

    logger.info('=================   End IED client initialization     =================\n')

def initNetwork():
    """
    """
    
    logger.info('=================   Begin network initialization    =================')
    #create empty net
    net = pp.create_empty_network()
    
    #create buses
    bus0 = pp.create_bus(net, vn_kv=20., max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus slack')
    busMV1 = pp.create_bus(net, vn_kv=20., max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus MV 1')
    busMV2 = pp.create_bus(net, vn_kv=20., max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus MV 2')
    busMV3 = pp.create_bus(net, vn_kv=20., max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus MV 3')
    
    busLV1 = pp.create_bus(net, vn_kv=0.4, max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus LV 1')
    busLV2 = pp.create_bus(net, vn_kv=0.4, max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus LV 2')
    busLV3 = pp.create_bus(net, vn_kv=0.4, max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name='Bus LV 3')
    
    #create bus elements
    pp.create_ext_grid(net, bus=bus0, vm_pu=1.03, name='Grid Connection', va_degree=0.0, in_service=True,
                       max_p_mw=3, min_p_mw=0, max_q_mvar=1, min_q_mvar=0)
    pp.create_poly_cost(net, 0, 'ext_grid', cp1_eur_per_mw=-1)
    
    pp.create_load(net, bus=busMV1, p_mw=0.2, q_mvar=0.05, name='Load MV 1')
    pp.create_load(net, bus=busMV2, p_mw=0.5, q_mvar=0.05, name='Load MV 2')
    pp.create_load(net, bus=busMV3, p_mw=0.75, q_mvar=0.05, name='Load MV 3')
    
    #create branch elements
    trafo1 = pp.create_transformer(net, hv_bus=busMV1, lv_bus=busLV1, max_loading_percent=gvar.MAX_TRAFO_OVERLOADING, std_type=gvar.stdTrafoType, name='Trafo MV/LV 1')
    trafo2 = pp.create_transformer(net, hv_bus=busMV2, lv_bus=busLV2, max_loading_percent=gvar.MAX_TRAFO_OVERLOADING, std_type=gvar.stdTrafoType, name='Trafo MV/LV 2')
    trafo3 = pp.create_transformer(net, hv_bus=busMV3, lv_bus=busLV3, max_loading_percent=gvar.MAX_TRAFO_OVERLOADING, std_type=gvar.stdTrafoType, name='Trafo MV/LV 3')
    
    line1 = pp.create_line(net, from_bus=bus0, to_bus=busMV1, length_km=5, max_loading_percent=gvar.MAX_LINE_OVERLOADING, name='Line MV 1',std_type=gvar.stdLineTypeMV)
    line2 = pp.create_line(net, from_bus=busMV1, to_bus=busMV2, length_km=5, max_loading_percent=gvar.MAX_LINE_OVERLOADING, name='Line MV 2',std_type=gvar.stdLineTypeMV)
    line3 = pp.create_line(net, from_bus=busMV2, to_bus=busMV3, length_km=5, max_loading_percent=gvar.MAX_LINE_OVERLOADING, name='Line MV 3',std_type=gvar.stdLineTypeMV)
    

    listNodePrevious = [busLV1, busLV1, busLV2, busLV2, busLV2, busLV3, busLV3, busLV3, busLV3, busLV3]
    idxLoad = 0
    idxPV = 0
    for k in range(gvar.nFeeder):
        listNodeLV = []
        listLineLV = []
        listLoad = []
        listPV = []
        nodePrevious = listNodePrevious[k]
        for idxHouse in range(gvar.householdPerFeeder):
            if gvar.listNodeInstanceLoad[idxHouse] is None:
                guidLoad = 'none'
            else:
                guidLoad = gvar.listNodeInstanceLoad[idxHouse].clsGUID
            
            nodeNew = pp.create_bus(net, vn_kv=0.4, type='m', max_vm_pu=gvar.MAX_BUS_VOLTAGE, min_vm_pu=gvar.MIN_BUS_VOLTAGE, name=f'Node LV {k},{idxHouse}')
            lineNew = pp.create_line(net, from_bus=nodePrevious, to_bus=nodeNew, length_km=0.01, name=f'Line LV {k},{idxHouse}',std_type=gvar.stdLineTypeLV)
            listNodeLV.append(nodeNew)
            listLineLV.append(lineNew)
            nodePrevious = nodeNew           
            
            loadNew = pp.create_load(net, bus=nodePrevious, p_mw=0.002, q_mvar=0.0005, name=f'name: Load LV {k},{idxHouse}, guid: {guidLoad}',
                                     controllable=False, max_p_mw=0.05, min_p_mw=0, max_q_mvar=0.005, min_q_mvar=0)
            listLoad.append(loadNew)
            gvar.listNodeInstanceLoad[idxLoad].idxInNetwork = loadNew
            idxLoad += 1

            if idxHouse % gvar.ratioLoadToPV==0:  # insert PV into the household nodes
                if gvar.listNodeInstancePV[idxHouse] is None:
                    guidPV = 'none'
                    max_p_mw = 0.03
                else:
                    guidPV = gvar.listNodeInstancePV[idxHouse].clsGUID
                    max_p_mw = gvar.listNodeInstancePV[idxHouse].pvRatedPower / gvar.listNodeInstancePV[idxHouse].unitFactor
                    
                PVNew = pp.create_sgen(net, bus=nodePrevious, p_mw=0.015, q_mvar =0.005, sn_mva=0.035, name=f'PV LV {k},{idxHouse}, guid: {guidPV}', 
                                    index=None, max_q_mvar=0.005, min_q_mvar=-0.005, min_p_mw=0, max_p_mw=0.03, 
                                    min_vm_pu=gvar.MIN_BUS_VOLTAGE, max_vm_pu=gvar.MAX_BUS_VOLTAGE, scaling=1.0, type='sync', 
                                    slack=False, controllable=True, in_service=True)
                pp.create_poly_cost(net, PVNew, 'sgen', cp1_eur_per_mw=-1)
    
                listPV.append(PVNew)
                gvar.listNodeInstancePV[idxPV].idxInNetwork = PVNew
                idxPV += 1
            
        gvar.listNodeAll.append(listNodeLV)
        gvar.listLineAll.append(listLineLV)
        gvar.listLoadAll.append(listLoad)
        gvar.listPVAll.append(listPV)            
    
    logger.info('=================   End network initialization    =================\n')
    
    return net


##############################################################################
###################     data interface functions    ##########################
##############################################################################
def connectInfluxdb():
    """
    Initialize the influxdb read_api client and write_api client
    """
    
    # TODO: change tokens
    tokenRead = "9pZMKEV8nLOVkdNHkfrzVd5fO5kueSkRpg3zsu3zzcIDulP7QqUWhnAS7o1bY_qWrs-8S_LCo4imrHNgj5ZAiQ=="
    tokenWrite = 'ryinIWoofyCgcPuQCTL4K0Utb7XcEQBtXH6PwuF4eBxdAodceO_o4yD0QzV7rhFIcEbS_RZL8iQRTMScOAdk9A=='
    org = "DE-THU-SGFG-KRITIS"
    url="http://192.168.170.220:8086"
    
    logger.info('=================   Begin init influxdb connection    =================')
    gvar.clientInfluxdbRead = InfluxDBClient(url=url, token=tokenRead, org=org) 
    healthRead = gvar.clientInfluxdbRead.health()
    if healthRead.status == 'pass':
        logger.info('Influxdb read_api client is ready to connect')
    else:
        logger.error('Influxdb read_api client has no connection to server')
        # switch to local mode?
        
    gvar.clientInfluxdbWrite = InfluxDBClient(url=url, token=tokenWrite, org=org) 
    healthWrite = gvar.clientInfluxdbWrite.health()
    
    if healthWrite.status == 'pass':
        logger.info('Influxdb write_api client is ready to connect')
    else:
        logger.error('Influxdb write_api client has no connection to server')
        # switch to local mode?
    logger.info('=================   End init influxdb connection    =================\n')
    

def loadNodeProfile(node=None):
    """
    Load profile for the nodes with data_source 'local' or 'influxdb'
    """
    
    if node.data_source == 'local':
        filename = rf'{gvar.pathProfile}/{node.ied_guid}.csv'
        node.dfProfileLocal = pd.read_csv(filename, sep=',')
    elif node.data_source == 'influxdb':
        pass  # TODO: implement this later
    else:
        logger.warning(f'Unknown data source for node {node.ied_guid}')
        
def getMeasurementLocal(node=None):
    """
    Iteratively get current measurement from local profile, use the guid in the node instance to navigate.
    When this function is called, use gvar.ctime_local_str to localize the desired value.
    
    If the data query failed, use the last valid value.
    """
    if node.der_type == 'pv':
        try:  # compare the smaller value of cValMX and valLimit w.r.t. rated power
            idxTstmp = node.dfProfileLocal.loc[node.dfProfileLocal['Datetime']==gvar.cTime].index.values[0]
            valMX = node.dfProfileLocal.loc[idxTstmp, 'Value'] * node.unit_factor * node.scaling_factor
            valLimit = node.cValSP * node.pvRatedPower * node.unit_factor * node.scaling_factor
            valUpdate = min(valMX, valLimit)
    
        except:
            valUpdate = node.cValMX
            logger.warning(f'Value update failed for node {node.container_name}, use the val from last iteration')
    
        node.cValMX = valUpdate
        node.addValToStatistics('timestamp', gvar.cTime)
        node.addValToStatistics('tstmp_unix', gvar.cTimeUnix)
        node.addValToStatistics('valMX', valUpdate)
        node.addValToStatistics('valSP', node.cValSP)
        node.addValToStatistics('valSP_write', node.cValSP_write)
        node.addValToStatistics('isIedConnected', node.isIedConnected)

    elif node.der_type == 'load':
        try:
            idxTstmp = node.dfProfileLocal.loc[node.dfProfileLocal['Datetime']==gvar.cTime].index.values[0]
            valMX = node.dfProfileLocal.loc[idxTstmp, 'Value'] * node.unit_factor * node.scaling_factor
    
        except:
            valMX = node.cValMX
            logger.warning(f'Value update failed for node {node.container_name}, use the val from last iteration')
    
        node.cValMX = valMX
        node.addValToStatistics('timestamp', gvar.cTime)
        node.addValToStatistics('tstmp_unix', gvar.cTimeUnix)
        node.addValToStatistics('valMX', valMX)
        node.addValToStatistics('valSP', 1.0)  # loads are considered not controllable
        node.addValToStatistics('valSP_write', 1.0)  # loads are considered not controllable
        node.addValToStatistics('isIedConnected', node.isIedConnected)

    else:
        logger.error(f'Unknown der type of node {node.container_name}, proceed to the next node')
        
def getMeasurementIED(node=None):
    """
    Iteratively get current measurement from active IED connection. When this function is called, safari through all
    PV and load in the list, as long as an IED connection is marked as "avaialbe" (IED_State == 2 after initialization), 
    try to get the value using libiec client API.
    
    If the data query failed, use the last valid value and mark the IED_connection status as "disconnected".
    
    TODO: add the possibility to use local profile or predicted value instead
    """
    
    if node.isIedConnected == 0:
        valMX = node.cValMX
        valSP = node.cValSP
        logger.warning(f'IED server disconnected for node {node.container_name}, use the val from last iteration')
    else:
        try:  # compare the smaller value of cValMX and valLimit w.r.t. rated power
            [valMX, error] = getIedVal(node.objIedClient, FC='MX', derType=node.der_type)
            [valSP, error] = getIedVal(node.objIedClient, FC='SP', derType=node.der_type)
        except:
            valMX = node.cValMX
            valSP = node.cValSP
            node.isIedConnected = 0
            logger.warning(f'Value update failed for node {node.container_name}, use the val from last iteration')

    node.cValMX = valMX
    node.cValSP = valSP
    node.addValToStatistics('timestamp', gvar.cTime)
    node.addValToStatistics('tstmp_unix', gvar.cTimeUnix)
    node.addValToStatistics('valMX', valMX)
    node.addValToStatistics('valSP', valSP)
    node.addValToStatistics('valSP_write', node.cValSP_write)
    node.addValToStatistics('isIedConnected', node.isIedConnected)

def getMeasurementInfluxdb(node=None):
    """
    Currently no need to implement this mode.
    """
    pass

def getMeasurementRandom(node=None):
    """
    Currently no need to implement this mode.
    """
    pass


def pushDataToInfluxdb(dataframe=None, measurement=None, **kwargs):
    '''
    This method will be called once per hour, it pushes the collected measurements,
    records and control set points to the bucket 7602_pandapower_testResults.
    '''
    
    listKeys = list(dataframe.keys())
    listRecords = []
    for idx in range(len(dataframe)):
        recordMetrics = {}       
        fields = {}
        tags = {}
        recordMetrics['measurement'] = measurement
        
        for key, item in kwargs:
            tags[key] = item
        recordMetrics['tags'] = tags
        
        for key in listKeys:
            if key == 'timestamp':
                recordMetrics['time'] = dataframe.loc[idx, key]
            else:
                fields[key] = dataframe.loc[idx, key]
        recordMetrics['fields'] = fields
        
        listRecords.append(recordMetrics)
                        
    # TODO: put write_api out of the loop??
    write_api = gvar.clientInfluxdbWrite.write_api(write_options=WriteOptions(batch_size=5000, flush_interval=10_000, jitter_interval=2_000, retry_interval=5_000))
    write_api.write(bucket=gvar.bucketWrite, record=listRecords)
    #logger.info('Data upload to infludb has been triggered.')
    #logger.info(f'{len(listRecords)} data points were uploaded to infludb bucket {gvar.write_bucket}.')
   


def updateMeasurement():
    """
    In each iteration, update measurements of all PV and load node instances.
    """
    
    logger.info('-------------------------------------------------------------------')
    logger.info("Start update measurements of all PV and loads")    
    
    for nodePV in gvar.listNodeInstancePV:
        if nodePV.dataSource == 'ied':
            getMeasurementIED(nodePV)
        elif nodePV.dataSource == 'local':
            getMeasurementLocal(nodePV)
        elif nodePV.dataSource == 'influxdb':
            getMeasurementInfluxdb(nodePV)
        elif nodePV.dataSource == 'random':
            getMeasurementRandom(nodePV)
        else:
            pass
            #logger.error(f'Unknown data_source {nodePV.data_source} for PV node {nodePV.container_name}')
            
    for nodeLoad in gvar.listNodeInstanceLoad:
        if nodeLoad.dataSource == 'ied':
            getMeasurementIED(nodeLoad)
        elif nodeLoad.dataSource == 'local':
            getMeasurementLocal(nodeLoad)
        elif nodeLoad.dataSource == 'influxdb':
            getMeasurementInfluxdb(nodeLoad)
        elif nodeLoad.dataSource == 'random':
            getMeasurementRandom(nodeLoad)
        else:
            pass
            #logger.error(f'Unknown data_source {nodePV.data_source} for load node {nodeLoad.container_name}')
    
    logger.info("End update measurements of all PV and loads")  
    logger.info('-------------------------------------------------------------------\n')
    
def updateValInNetwork():
    """
    Update the values in the pandapower network for the next iteration of power flow calculation.
    """
    for nodePV in gvar.listNodeInstancePV:
        if np.isnan(nodePV.cValMX):  # replace nan with 0
            gvar.network.sgen.loc[nodePV.idxInNetwork, 'p_mw'] = 0
        else:
            gvar.network.sgen.loc[nodePV.idxInNetwork, 'p_mw'] = nodePV.cValMX / nodePV.unitFactor / 1000  # attention, convert W to MW here
    
    for nodeLoad in gvar.listNodeInstanceLoad:
        if np.isnan(nodeLoad.cValMX):  # replace nan with 0
            gvar.network.load.loc[nodeLoad.idxInNetwork, 'p_mw'] = 0
        else:
            gvar.network.load.loc[nodeLoad.idxInNetwork, 'p_mw'] = nodeLoad.cValMX / nodePV.unitFactor / 1000  # attention, convert W to kW here


def updateStatics():
    """
    Update all statistic dataframes, get prepared for statistic export or upload.
    Note that this function can only update a part of the parameters in the dataFrame, mainly the timestamps and conection
    status. The other parameters need to be passed to the dataframe when other functions or methods are called
    """
    
    logger.info('-------------------------------------------------------------------')
    logger.info("Start update records dataFrames")
    
    listConnectedPV = [node.isIedConnected for node in gvar.listNodeInstancePV]
    listConnectedLoad = [node.isIedConnected for node in gvar.listNodeInstanceLoad]
    nConnectedPV = sum(listConnectedPV)
    nConnectedLoad = sum(listConnectedLoad)
    logger.info(f'Number of connected PV IED: {nConnectedPV}')
    logger.info(f'Number of connected Load IED: {nConnectedLoad}')
    routineStatistics.addValToStatistics('nConnectedPV', nConnectedPV)
    routineStatistics.addValToStatistics('nConnectedLoad', nConnectedLoad)
    routineStatistics.addValToStatistics('timestamp', gvar.cTime)
    routineStatistics.addValToStatistics('tstmp_unix', gvar.cTimeUnix)

    routineStatistics.addValToNetworkState('timestamp', gvar.cTime)
    routineStatistics.addValToNetworkState('tstmp_unix', gvar.cTimeUnix)
    logger.info("End update records dataFrames")
    logger.info('-------------------------------------------------------------------\n')


def exportStatistics():
    """
    This function is triggered each hour. For all nodes and simulation records, always update the local csv file as copy.
    If gvar.statisticTarget is set to influxdb, then try to push the data collected from the last hour to influxdb.
    
    """
    
    logger.info('Data upload to infludb for routine records has been triggered.')
    routineStatistics.exportDfStatistics()
    
    listNode = gvar.listNodeInstancePV + gvar.listNodeInstanceLoad
    
    logger.info('Data upload to infludb for node records has been triggered.')
    for node in listNode:
        node.exportDfStatistics()
        
    
##############################################################################
##################     runtime simulation fucntions     ######################
##############################################################################

def initSimulationStartTime():
    isActiveConnection = False
    # TODO: find a way to get the UNIX time from libiec server properly
    
    # if gvar.listNodeInstancePV[0] is not None:
    #     for idxConn, itemNode in enumerate(gvar.listNodeInstancePV):  # go through the ied list, get one timestamp and quit
    #         if itemNode.objIedClient is not None:
    #             if itemNode.objIedClient.iedState == iec.IED_STATE_CONNECTED:
    #                 gvar.ctime_local_str, gvar.ctime_unix = getIedTimeUTC(itemNode.objIedClient, 'pv')
    #                 isActiveConnection = True
    #                 break
    # if isActiveConnection == False and gvar.listNodeInstanceLoad[0] is not None:
    #     for idxConn, itemNode in enumerate(gvar.listNodeInstanceLoad):  # if still no start time fetched, then go through the load list
    #         if itemNode.objIedClient is not None:
    #             if itemNode.objIedClient.iedState == iec.IED_STATE_CONNECTED:
    #                 gvar.ctime_local_str, gvar.ctime_unix = getIedTimeUTC(itemNode.objIedClient, 'load')
    #                 isActiveConnection = True
    #                 break
    
    if isActiveConnection == False: 
        gvar.cTime = gvar.defaultStartTime
        gvar.cTimeUnix = time.mktime(datetime.strptime(gvar.cTime, '%Y-%m-%d %H:%M:%S').timetuple())
        logger.warning('Currently no active IED connection, use default start time in gvar')
    
    logger.info(f'Simulation start time initalized, datetime string: {gvar.cTime}, UNIX time: {gvar.cTimeUnix}')


def runPP(net):

    # perform Power Flow calculation
    logger.info('Starting pandapower load flow calculation')
    
    try:
        pp.runpp(net, algorithm='nr', calculate_voltage_angles='auto', init='auto', 
                         max_iteration=50, tolerance_mva=1e-06, trafo_model='t', 
                         trafo_loading='current', enforce_q_lims=False, check_connectivity=True, 
                         voltage_depend_loads=True, consider_line_temperature=False, run_control=False)
    except pp.OOPFNotConverged:
        logger.error('The power flow is not converged in this iteration, check possible topo or data error')
        # TODO: add records on convergence
    
    res_bus = net.res_bus
    res_trafo = net.res_trafo
    res_line = net.res_line

    isControlRequired = False
    
    listIdxBusOvervoltage = [idx for idx in list(res_bus.index) if res_bus['vm_pu'][idx] > gvar.MAX_BUS_VOLTAGE]
    listIdxLineOverloading = [idx for idx in list(res_line.index) if res_line['loading_percent'][idx] > gvar.MAX_LINE_OVERLOADING]
    listIdxTrafoOverloading = [idx for idx in list(res_trafo.index) if res_trafo['loading_percent'][idx] > gvar.MAX_TRAFO_OVERLOADING]

    if listIdxBusOvervoltage != []:
        logger.info(f'Busbar overvoltage detected: {len(listIdxBusOvervoltage)} busbars have overvoltage')
        isControlRequired = True
        for idx in listIdxBusOvervoltage:
            if res_bus["vm_pu"][idx] > gvar.WARNING_BUS_OVERVOLTAGE:  # only log warning events
                logger.warning(f'Bus {idx} showed overvoltage problem, bus voltage: {res_bus["vm_pu"][idx]}')
    else:
        logger.info('No busbar overvoltage problem')
    
    if listIdxLineOverloading != []:
        logger.info(f'Line overloading detected: {len(listIdxLineOverloading)} lines have overloading')
        isControlRequired = True
        for idx in listIdxLineOverloading:
            if res_line["loading_percent"][idx] > gvar.WARNING_LINE_OVERLOADING:  # only log warning events
                logger.warning(f'Line {idx} showed overloading problem, line overloading: {res_line["loading_percent"][idx]}')
    else:
        logger.info('No line overloading problem')
    
    if listIdxTrafoOverloading != []:
        logger.info(f'Trafo overloading detected: {len(listIdxTrafoOverloading)} trafos have overloading')
        isControlRequired = True
        for idx in listIdxTrafoOverloading:
            if res_trafo["loading_percent"][idx] > gvar.WARNING_TRAFO_OVERLOADING:  # only log warning events
                logger.warning(f'Trafo {idx} showed overloading problem, trafo overloading: {res_trafo["loading_percent"][idx]}')
    else:
        logger.info('No transformer overloading problem')
        
    if isControlRequired:
        logger.info('Measures must be taken to ensure the grid stability.')        
    else:
        logger.info('No network problem detected, no action necessary within this iteration')
        
    isConverged = net.converged
    if isConverged == False:
        logger.warning('Power flow simulation was not converged, no action can be taken within this iteration')
        
    
    # update the records
    routineStatistics.addValToNetworkState('minVoltage', np.min(res_bus['vm_pu']))
    routineStatistics.addValToNetworkState('maxVoltage', np.max(res_bus['vm_pu']))
    routineStatistics.addValToNetworkState('meanVoltage', np.mean(res_bus['vm_pu']))
    routineStatistics.addValToNetworkState('nNodeOvervoltage', len(listIdxBusOvervoltage))
    routineStatistics.addValToNetworkState('minLineLoading', np.min(res_line['loading_percent']))
    routineStatistics.addValToNetworkState('maxLineLoading', np.max(res_line['loading_percent']))
    routineStatistics.addValToNetworkState('meanLineLoading', np.mean(res_line['loading_percent']))
    routineStatistics.addValToNetworkState('nLineOverloading', len(listIdxLineOverloading))
    routineStatistics.addValToNetworkState('minTrafoLoading', np.min(res_trafo['loading_percent']))
    routineStatistics.addValToNetworkState('maxTrafoLoading', np.max(res_trafo['loading_percent']))
    routineStatistics.addValToNetworkState('meanTrafoLoading', np.mean(res_trafo['loading_percent']))
    routineStatistics.addValToNetworkState('nTrafoOverloading', len(listIdxTrafoOverloading))    
    
    return isConverged, isControlRequired, listIdxBusOvervoltage, listIdxLineOverloading, listIdxTrafoOverloading


def computeControlSP(network, listIdxBusOvervoltage, listIdxLineOverloading, listIdxTrafoOverloading):
    """
    Localize the PV systems that are connected to the lines/busbar nodes/trafo, which are tending to suffer from overloading 
    or overvoltage problems, and then limits the PV infeed power in proportion to the level of problem.
    
    principle:
        - overvoltage: each 0.01 pu -> reduce PV active power by 10%, 1.10 pu leads to shutdown of the PV inverter
        - line overloading: each 2% of the exceeded line loading -> reduce the active power by 10% of the connected node that is near the trafo 
        - trafo overloading: each 2% of exceeded trafo loading -> reduce the active power of all PV at the underlying feeders by 5% 
    
    Priority:
        1 - trafo overloading
        2 - line overloading
        3 - busbar overvoltage
    Perform the control reversely.
    
    All performed setpoint curtailment will be reduced by 10% for each hour, as long as no further limitation has been applied
    in the last half hour.
    
    One concrete example:
    For one PV system, the curtailment is 0.8 at 13:00, in one hour at 14:00 the situation is not getting worse, 
    
    """
    
    logger.info('-------------------------------------------------------------------')
    logger.info('Start computing DER active power control on the simulated PV systems')
    
    # TODO: implemente some logic to harmonize the duplicate codes here
    # TODO: check if pandapower provide topology check

    
    listValSP = [nodePV.cValSP for nodePV in gvar.listNodeInstancePV]
    listValOV = [0] * gvar.nPV
    listValTrafoOL = [0] * gvar.nPV
    listValLineOL = [0] * gvar.nPV
    
    logger.info('Compute setpoint values to solve overvoltage issues')
    for idxBus in listIdxBusOvervoltage:
        listIdxNetworkPV = network.sgen.loc[network.sgen['bus'] == idxBus].index.values # find the idx of PV in the pp network
        valSP = (network.res_bus.loc[idxBus, 'vm_pu'] - gvar.MAX_BUS_VOLTAGE) / 0.01 * -0.1
        for idxPV in listIdxNetworkPV:
            idxIedPV = [idx for idx, item in enumerate(gvar.listNodeInstancePV) if item.idxInNetwork == idxPV]  # this should return a single element
            if idxIedPV == []:
                logger.info(f'Can not find PV system with index {idxPV}')
            else:
                listValOV[idxIedPV[0]] = np.min([listValOV[idxIedPV[0]], valSP])
    
    logger.info('Compute setpoint values to solve line overloading issues')
    for idxLine in listIdxLineOverloading:
        idxBus = network.line.loc[idxLine, 'from_bus']
        listIdxNetworkPV = list(network.sgen.loc[network.sgen['bus'] == idxBus].index.values)  # find the idx of PV in the pp network
        if listIdxNetworkPV == []:
            idxBus = network.line.loc[idxLine, 'to_bus']
            listIdxNetworkPV = list(network.sgen.loc[network.sgen['bus'] == idxBus].index.values)  # find the idx of PV in the pp network
        if listIdxNetworkPV == []: 
            logger.warning(f'No PV system connected directly on line {idxLine}, observe whether the overloading can be resolved by other measures')
            continue
        valSP = (network.res_line.loc[idxLine, 'loading_percent'] - gvar.MAX_LINE_OVERLOADING) / 2 * -0.1
        for idxPV in listIdxNetworkPV:
            idxIedPV = [idx for idx, item in enumerate(gvar.listNodeInstancePV) if item.idxInNetwork == idxPV]  # this should return a single element
            if idxIedPV == []:
                logger.info(f'Can not find PV system with index {idxPV}')
            else:
                listValLineOL[idxIedPV[0]] = np.min([listValLineOL[idxIedPV[0]], valSP])
   
    logger.info('Compute setpoint values to solve trafo overloading issues')  
    for idxTrafo in listIdxTrafoOverloading:
        idxBusLV = network.trafo.loc[idxTrafo,'lv_bus']
        # TODO: the following code is static, implement dynamic logic later
        if idxBusLV == 4:  # feeder group 1, 2
            listIdxPV = gvar.listPVAll[0] + gvar.listPVAll[1]
        elif idxBusLV == 5:
            listIdxPV = gvar.listPVAll[2] + gvar.listPVAll[3] + gvar.listPVAll[4]
        elif idxBusLV == 6:
            listIdxPV = gvar.listPVAll[5] + gvar.listPVAll[6] + gvar.listPVAll[7]+ gvar.listPVAll[8] + gvar.listPVAll[9]
        
        valSP = (network.res_trafo.loc[idxTrafo, 'loading_percent'] - gvar.MAX_TRAFO_OVERLOADING) / 2 * -0.05
        for idxPV in listIdxPV:
            listValTrafoOL[idxPV] = np.min([listValTrafoOL[idxPV], valSP])
    
    # determine setpoint values & check unchanged setpoint duration
    logger.info('Determine final setpoint values for all PV systems')  
    for idx, nodePV in enumerate(gvar.listNodeInstancePV):
        valSP_reduce = np.min([listValOV[idx], listValLineOL[idx], listValTrafoOL[idx]])
        if valSP_reduce < 0:  # valSP_reduce is a negative value, so the operator must be plus
            cValSP_write =  np.max([listValSP[idx] + valSP_reduce, 0])
            nodePV.cValSP_write =  np.min([cValSP_write, 1.0]) # the setpoint can not be less than 0, can not be larger than 1
        elif valSP_reduce > 0:
            logger.info('A negative curtailment has been calculated, can not execute, pass')
        else:  # val == 0, value type not clear, so we use else to avoid error
            nodePV.countUnchangedSP += 1
            if nodePV.countUnchangedSP == 30:  # recover the limitation by 10% if no further limitation in the past 30 iterations
                nodePV.cValSP_write = np.min([listValSP[idx] + 0.1, 1.0])
                nodePV.countUnchangedSP = 0
                
    listSetpoint = [nodePV.cValSP_write for nodePV in gvar.listNodeInstancePV if nodePV.cValSP_write != 1.0]
    
    # check abnormal setpoint values
    listCValSP_write = [nodePV.cValSP_write for nodePV in gvar.listNodeInstancePV]
    if np.max(listCValSP_write) <= 1.0:
        logger.info('All setpoint are ok, be ready for the curtailment execution')
    else:
        for idx, nodePV in enumerate(gvar.listNodeInstancePV):
            if nodePV.cValSP_write > 1:  # if detect
                logger.warning('Found abnormal setpoint value, set it to 1')
                gvar.listNodeInstancePV[idx].cValSP_write = 1.0     
    
    routineStatistics.addValToStatistics('nSetpoint', len(listSetpoint))
    routineStatistics.addValToStatistics('minSetpointW', np.min(listSetpoint))
    routineStatistics.addValToStatistics('maxSetpointW', np.max(listSetpoint))
    routineStatistics.addValToStatistics('meanSetpointW', np.mean(listSetpoint))
    
    logger.info('PV active power curtailments haven been calculated.')
    logger.info(f'Number of to be performed setpoints: {len(listSetpoint)}.')
    logger.info(f'Minimum setpoints: {np.min(listSetpoint)}.')
    logger.info(f'Mean setpoints: {np.mean(listSetpoint)}.')

    logger.info('End computing DER active power control on the simulated PV systems')
    logger.info('-------------------------------------------------------------------\n')
    
    return listSetpoint

def performControlSP():
    """
    Perform computed control SP
    """
    
    logger.info('-------------------------------------------------------------------')
    logger.info('Start performing DER active power control on the simulated PV systems')
    for idx, nodePV in enumerate(gvar.listNodeInstancePV):
        if nodePV.dataSource == 'ied':
            error = writeIedValSP(nodePV.objIedClient, nodePV.cValSP_write)
        elif nodePV.dataSource == 'local':
            nodePV.cValSP = nodePV.cValSP_write
        elif nodePV.dataSource == 'influxdb':
            pass
        elif nodePV.dataSource == 'random':
            pass
        else:
            pass
    
    logger.info('End performing DER active power control on the simulated PV systems')
    logger.info('-------------------------------------------------------------------\n')
    
def keepAliveAllIED():
    """
    Keep alive IED connections every 15 minutes
    """
    
    for node in gvar.listNodeInstancePV:
        if node.objIedClient is not None:
            node.objIedClient = keepAliveIedConnection(node.objIedClient)
    
    for node in gvar.listNodeInstanceLoad:
        if node.objIedClient is not None:
            node.objIedClient = keepAliveIedConnection(node.objIedClient)
    

def serviceInitialization():
    """
    Initalization of mandatory services, get prepared for the service routine.
    """

    getNetworkConfig() 
    initIedClients()      
    gvar.network = initNetwork()
    initSimulationStartTime()
    try:
        connectInfluxdb()
    except:
        logger.error('No connection to influxdb')
        
def updateSimulationTime():
    """
    here do a round_digits trick to make sure the time will be HH:MM:SS
    """
    # 
    logger.info(f'Actual current datetime: {gvar.cTime}; current Unix time: {gvar.cTimeUnix}')
    cTimeString = datetime.strftime(datetime.fromtimestamp(round(int(gvar.cTimeUnix)/10)*10), '%Y-%m-%d %H:%M:%S')
    if int(cTimeString[-2:]) == 0:
        pass
    elif int(cTimeString[-2:]) in range(0,31):
        cTimeString = cTimeString[:-2] + '00'
    elif int(cTimeString[-2:]) in range(31,60):
        if int(cTimeString[-5:-3]) < 59:
            cTimeString = f'{cTimeString[:-6]}:{int(cTimeString[-5:-3])+1}:00'
        else:
            cTimeString = cTimeString[:-2] + '00'
    
    gvar.cTime = cTimeString
    logger.info(f'Current datetime string for data query: {gvar.cTime}')
    
    # also update the timestamps in the records dataframes
    routineStatistics.addValToNetworkState('timestamp', gvar.cTime)
    routineStatistics.addValToNetworkState('tstmp_unix', gvar.cTimeUnix)
    routineStatistics.addValToStatistics('timestamp', gvar.cTime)
    routineStatistics.addValToStatistics('tstmp_unix', gvar.cTimeUnix)
    
    listNode = gvar.listNodeInstanceLoad + gvar.listNodeInstancePV
    for node in listNode:
        node.addValToStatistics('timestamp', gvar.cTime)
        node.addValToStatistics('tstmp_unix', gvar.cTimeUnix)
        
    
def serviceRoutine():
    """
    Main thread of the simulation
    """
    logger.info('=================   Begin pyiec61850panda simulation   =================')
    logger.info(f'Start server routine, the current simulation has the identifier: {gvar.simulationIdentifer}')
    iterRoutine = 0
    iterRoutineMax = 100000
    while iterRoutine < iterRoutineMax:       
        timerStart = time.time()  # use this time to compensate the processing time in each iteration.        
        logger.info('-------------------------------------------------------------------')
        updateSimulationTime()
        
        logger.info(f'Current datetime: {gvar.cTime}; current Unix time: {gvar.cTimeUnix}')
        logger.info("Pandapower grid operator running")    
        
        updateMeasurement()
        updateValInNetwork()
        
        [isConverged, isControlRequired, listIdxBusOvervoltage, listIdxLineOverloading, listIdxTrafoOverloading] = runPP(gvar.network)
        
        if isConverged == False or isControlRequired == False:
            logger.info('No control required, proceed to the next iteration')
        else:
            gvar.listSetpoint = computeControlSP(gvar.network, listIdxBusOvervoltage, listIdxLineOverloading, listIdxTrafoOverloading)
            performControlSP()
            
        if gvar.cTime[-5:] in ['00:00', '15:00', '30:00', '45:00']:  # if the time is XX:00:00
            try:    
                keepAliveAllIED()
            except:
                logger.warning('Keep alive of all IED connections failed, manual interfere may be necessary!')  
        
        if gvar.cTime[-5:] == '00:00':  # if the time is XX:00:00
            exportStatistics()
        
                
        # add the new row of measurements within this iteration to the dataframes 
        routineStatistics.addNewRow()
        for nodePV in gvar.listNodeInstancePV:
            nodePV.addNewRow()
        for nodeLoad in gvar.listNodeInstanceLoad:
            nodeLoad.addNewRow()
            
        timerEnd = time.time()
        processingTime = timerEnd - timerStart
        routineStatistics.addValToStatistics('processingTime', processingTime)
        
        logger.info(f'Processing time for the current iteration: {processingTime} seconds')      
        logger.info('-------------------------------------------------------------------\n')
        
        iterRoutine += 1
        if processingTime <= 60:
            time.sleep(60-processingTime)
            gvar.cTimeUnix += 60
        else:
            logger.warning('This iteration took longer than 60 second, round up to the next possible trigger time')
            
            nMinutes = int(np.ceil(processingTime/60))
            bufferTime = processingTime % 60
            time.sleep(60-bufferTime)
            gvar.cTimeUnix += 60*(nMinutes+1)
            
            
if __name__ == '__main__':
    gvar = Gvar()
    routineStatistics = RoutineStatistics()
    routineStatistics.getFileName()
    routineStatistics.createCSV()
    logger = createRotatingLog() 
    serviceInitialization()
    serviceRoutine()
