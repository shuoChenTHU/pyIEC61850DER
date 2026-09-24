# -*- coding: utf-8 -*-
"""
A deprecated test script for structured testing on the IED server side

@author: Morris, Chen
"""
import sys
import os

# if os.name != 'nt':  # if not windows os
#     sys.path.append("/work/")
#     listFile = os.listdir("/work/")
#     print("check files in working directory")
#     print(listFile)
#     os.environ["PATH"] = "/work/;" + os.environ["PATH"]

# standard built-in lib
import time
import random
import calendar
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import importlib.util
from settings import helper
from multiprocessing import Process
import multiprocessing
import logging
iec61850 = helper.import_libiec61850()

ifExist = importlib.util.find_spec("pylibiec61850")

# standard lib requiring installation
#import pandas as pd
#from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
#from influxdb_client.client.write_api import SYNCHRONOUS


# # local lib
# import iec61850 as iec

##############################################################################
#####################     service initialization      ########################
##############################################################################

class gvar(object):
    # global counter
    gcount = 0
    # simulation time settings
    pf_time_obj = ""
    pf_timeset_start = ""
    pf_timeset_end = ""
    pf_list_timescale = ""
    pf_timeset_steps = 1.0
    pf_sim_set_flag = False
    # server settings and stats
    port = 61850
    hostname = "127.0.0.1"
    dataSource = 'local'  # local, influxdb or random
    filenameProfile = 'test_PV_profile_summer2016.csv'
    
    # time settings
    timeMode = 'simulation'  # simulation or absolute
    startTime = '2016-07-01T12:00:00'
    endTime = '2016-07-31T23:59:59'
    startTimeUnix = 0
    endTimeUnix = 0
    timeAccelarationFactor = 1
    
    uptime_sec = 0
    uptime_min = 0
    uptime_h = 0
    start_time = 0
    current_time = 0
    cTimeUnix = 0
    cTime = ''
    intrvl_start = 0
    intrvl_duratn = 0.0
    intrvl_table = []
    int_avg_duratn = 0.0
    # Data Model
    iedServer = []
    iedModel = []
    iec_model_dict = {}
    iec_model_dict_callback = {}
    LD_iedModel = []
    app = []
    proj = []
    container_pvsys = []
    container_pvsys_callback = []
    container_load = []
    container_load_callback = []
    container_all_objects = []
#    container_loads = {}
    current_pfObjId = ''
    pvsys_list = []
    pvsys_PFOID_nr_dict = {}
    pvsys_PFOID_pfObj = {}
    pvsys_PFOID_list = []
    load_list = []
    load_PFOID_nr_dict = {}
    load_PFOID_pfObj = {}
    load_PFOID_list = []
    
    
    
    dictUpdateVal = []
    # csv vars
    csv_filename = ""
    
    IedModelName = "demoVirtualCLS"
    DeviceName = "demoProsumerXY"
    scaleFactor = 5
    unitFactor = 1000
    demoProsumerXY_mmxu1_f_current_val = 50
    demoProsumerXY_mmxu1_totw_current_val = 5*unitFactor*scaleFactor
    demoProsumerXY_mmxu1_totvar_current_val = 200
    demoProsumerXY_mmxu1_outwset_current_val = 1.0
    
    demoProsumerXY_mmxu1_totw_mag_f = demoProsumerXY_mmxu1_totw_current_val
    demoProsumerXY_mmxu1_totvar_mag_f = demoProsumerXY_mmxu1_totvar_current_val
    demoProsumerXY_mmxu1_f_mag_f = demoProsumerXY_mmxu1_f_current_val
    demoProsumerXY_mmxu1_outwset_setmag_f = demoProsumerXY_mmxu1_outwset_current_val
    
    derType = 'pv'
    clsGUID = ''
    pvRatedPower = 30*unitFactor  # rated power for random mode
    profileThisDay = None  # a dataFrame to store the profile loaded from influxdb
    
    listValWrite = []
    listControlWrite = []
    listTstmpWrite = []
    measurementInfluxdb = 'unknown'  # string of the _measurement for writing to influxdb
    tagInfluxdb = {}
    bucketRead = '7199_simulation_profile'
    bucketWrite = '7601_virtualCLS_testResults'
        
    clientInfluxdbRead = None
    clientInfluxdbWrite = None
    
    TIME_INTERVAL = 10
    WATCHDOG_ITERATION = 10
    WATCHDOG_SLEEP = 0.5
    
class Profile(object):
    listTimestamp = []
    listTimestampUnix = []
    listVal = []
    
    
def updateJSONConfig():
    nameConfigFile = 'config.json'
    configFile = open(nameConfigFile)
    config = json.load(configFile)
    for key, value in config.items():
        setattr(gvar, key, value)

def displayConfigInfo():
    logger.info('=================   Begin get DER information   =================')
    listInfo = ['derType', 'pvRatedPower', 'timeMode', 'startTime', 'endTime', 
                'dataSource', 'timeAccelarationFactor', 'scaleFactor','unitFactor',
                'clsGUID', 'hostname', 'port']
    for item in listInfo:
        logger.info(f'{item}: {gvar.__dict__[item]}')
        gvar.tagInfluxdb[item] = gvar.__dict__[item]  # also update the tags for influxDB        
    
    if gvar.timeMode == 'simulation':
        gvar.startTimeUnix = time.mktime(datetime.strptime(gvar.startTime, '%Y-%m-%dT%H:%M:%S').timetuple())
        gvar.endTimeUnix = time.mktime(datetime.strptime(gvar.endTime, '%Y-%m-%dT%H:%M:%S').timetuple())
    elif gvar.timeMode == 'absolute':
        gvar.startTimeUnix = calendar.timegm(datetime.now().utctimetuple())
        gvar.endTimeUnix = gvar.startTimeUnix + 60*60*24*365
    logger.info('=================   End get DER information   =================\n')
  
  
##############################################################################
##################     some supporting functions      ########################
##############################################################################
    
def get_UTC_timestamp_uint64():
    # Get current time and convert to uint64_t
    # Consider correct offset
    # offset_summer_time = 7200000
    offset_summer_time = 0
    current_time = datetime.now()
    current_time_uint64_t = calendar.timegm(current_time.utctimetuple())*1000
    return current_time_uint64_t - offset_summer_time



def get_simulation_timestamp_uint64(unixTime):
    offset_summer_time = 0
    current_time = datetime.utcfromtimestamp(unixTime)
    current_time_uint64_t = calendar.timegm(current_time.utctimetuple())*1000
    return current_time_uint64_t - offset_summer_time

def create_rotating_log():
    """
    Creates a rotating log
    """
    logger = logging.getLogger(gvar.measurementInfluxdb)
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, filemode = 'a')
    path = f'{os.getcwd()}\\{gvar.measurementInfluxdb}_logger.log'
    
    # add a rotating handler
    fh = RotatingFileHandler(path, maxBytes=300*1000*1000,
                                  backupCount=10)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(process)d - %(levelname)s - %(message)s')
    # formatter = logging.Formatter("f'{asctime} - {process} - {levelname} - {message}'")  # new string format for logger
    fh.setFormatter(formatter)
    if (logger.hasHandlers()):
        logger.handlers.clear()
    logger.addHandler(fh)
    return logger

##############################################################################
##################     data profile configuration     ########################
##############################################################################

# def connectInfluxdb():
#     tokenRead = "6Zdpabqp-mvPDsdMnl8pAHAtLfu_dEFZvxBzjwy6rMNuDGzavc6n3jB15S9vJISdNLHLfUeabjdkzoYhY0A09Q=="
#     tokenWrite = 'o2KrflRMacpiSUA1Irdk9SBx1dOlFgMoLYpob6E6Ep38WPcosGg8VMK6EvXl962SejihITaQOtRCNk3sDOrNeQ=='
#     org = "DE-THU-SGFG-KRITIS"
#     url="http://192.168.170.220:8086"
    
#     logger.info('=================   Begin init influxdb connection    =================')
#     gvar.clientInfluxdbRead = InfluxDBClient(url=url, token=tokenRead, org=org) 
#     healthRead = gvar.clientInfluxdbRead.health()
#     if healthRead == 'pass':
#         logger.info('Influxdb read_api client is ready to connect')
#     else:
#         logger.error('Influxdb read_api client has no connection to server')
#         # switch to local mode?
        
#     gvar.clientInfluxdbWrite = InfluxDBClient(url=url, token=tokenWrite, org=org) 
#     healthWrite = gvar.clientInfluxdbWrite.health()
    
#     if healthWrite == 'pass':
#         logger.info('Influxdb read_api client is ready to connect')
#     else:
#         logger.error('Influxdb read_api client has no connection to server')
#         # switch to local mode?
#     logger.info('=================   End init influxdb connection    =================\n')
    
#
# def load_profile_local_init():
#     '''
#     This method will get the PV/load profile locally from a pre-configed csv
#     file in the current working directory.
#
#     The profile will be loaded only once by the initialization and will be used
#     throughout the entire simulation.
#     '''
#
#     dfProfile = pd.read_csv(gvar.filenameProfile, sep=',')
#     listTimestamp = list(dfProfile['Datetime'])
#     listTimestampUnix = list(dfProfile['UNIX'])
#     listVal = list(dfProfile['Value'])
#     idxValidVal = [idx for idx,tstmp in enumerate(listTimestampUnix)
#                     if tstmp >=gvar.startTimeUnix and tstmp<=gvar.endTimeUnix]
#
#     Profile.listTimestamp = listTimestamp[idxValidVal[0]:idxValidVal[-1]+1]
#     Profile.listTimestampUnix = listTimestampUnix[idxValidVal[0]:idxValidVal[-1]+1]
#     Profile.listVal = listVal[idxValidVal[0]:idxValidVal[-1]+1]
#     nVal = len(Profile.listVal)
#
#     logger.info('-------------------------------------------------------------------')
#     logger.info('PV feedin profile with 1 minute resolution has been loaded')
#     logger.info(f'The local profile contains {nVal} valid timestamps')
#     logger.info('-------------------------------------------------------------------\n')
#
#     return
#
#
# def load_profile_local():
#     '''
#     This method will get the PV/load profile from local csv file if called.
#     The profile will be queried on a daily basis.
#     '''
#
#     logger.info(f'start profile query for the date {gvar.cTime[0:10]}')
#
#     startTime = f'{gvar.cTime[0:10]} 00:00:00'  # time format in the csv file
#     endTime = f'{gvar.cTime[0:10]} 23:59:00'  # time format in the csv file
#     if Profile.listTimestamp[0][0:10] == gvar.cTime[0:10]:
#         startIdx = 0  # if the simulation begins in the middle of a day
#     else:
#         startIdx = Profile.listTimestamp.index(startTime)
#     if type(startIdx) == list:
#         startIdx = startIdx[0]
#     endIdx = Profile.listTimestamp.index(endTime)
#     if type(endIdx) == list:
#         endIdx = endIdx[0]
#     listProfileVal = Profile.listVal[startIdx:endIdx+1]
#     listProfileTstmp = Profile.listTimestamp[startIdx:endIdx+1]
#     records = pd.DataFrame({'_time': listProfileTstmp,
#                                         '_value': listProfileVal
#                                         })
#     gvar.profileThisDay = records
#     if  len(records) == 0:
#         logger.warning('No data found for this day, the simulation will use profile of the previous day')
#     elif len(records) > 1440:
#         logger.warning('Found some duplicated data, but no problem, we move on')
#     elif len(records) < 1440:
#         logger.warning(f'Found data gap, {1440 - len(records)} data points are missing.')
#         logger.warning('Not a problem, the server will use the previous value in the simulation')
#     else:
#         logger.info('Data query was successfull, profile loaded')
#
# def load_profile_influxdb():
#     '''
#     This method will get the PV/load profile from influxdb if called.
#     The profile will be queried on a daily basis.
#     '''
#
#     logger.info(f'start profile query for the date {gvar.cTime[0:10]}')
#
#     query_api = gvar.clientInfluxdbRead.query_api()
#     startTime = f'{gvar.cTime[0:10]}T00:00:00Z'
#     endTime = f'{gvar.cTime[0:10]}T23:59:00Z'
#     queryFlux = f'from(bucket:"{gvar.bucketRead}") |> range(start: {startTime}, stop: {endTime})\
#             |> filter(fn:(r) => r["GUID"] == "{gvar.clsGUID}")\
#             |> filter(fn:(r) => r["_field"] == "Value")\
#             |> aggregateWindow(every: 1m, fn: last, createEmpty: true)\
#             |> fill(usePrevious: true)'
#     records = query_api.query_data_frame(query=queryFlux)
#     gvar.profileThisDay = records
#
#     if  len(records) == 0:
#         logger.warning('No data found for this day, the simulation will use profile of the previous day')
#     elif len(records) > 1440:
#         logger.warning('Found some duplicated data, but no problem, we move on')
#     elif len(records) < 1440:
#         logger.warning(f'Found data gap, {1440 - len(records)} data points are missing.')
#         logger.warning('Not a problem, the server will use the previous value in the simulation')
#     else:
#         logger.info('Data query was successfull, profile loaded')
#
# def get_val_in_profile():
#     if len(gvar.profileThisDay) == 0:
#         logger.warning('No profile avaialable, set the values to 0')
#         val = None
#     else:
#         idxTstmp = [idx for idx, tstmp in enumerate(list(gvar.profileThisDay['_time']))
#                      if gvar.cTime in str(tstmp)]
#         if idxTstmp == []:
#             val = None
#         else:
#             val = gvar.profileThisDay['_value'][idxTstmp[0]]
#     return val
#
# def push_df_to_influx():
#     '''
#     This method will be called once per hour, it pushes the collected measurements
#     and control set points to the bucket 7601_virtualCLS_testResults.
#     '''
#
#     listRecords = []
#     for idx, val in enumerate(gvar.listValWrite):
#         recordMetrics = {}
#         fields = {'val_MX': val,
#                   'val_SP': gvar.listControlWrite[idx]}
#         recordMetrics['measurement'] = gvar.measurementInfluxdb
#         recordMetrics['tags'] = gvar.tagInfluxdb
#         recordMetrics['fields'] = fields
#         recordMetrics['time'] = gvar.listTstmpWrite[idx]
#         listRecords.append(recordMetrics)
#
#     try:
#         write_api = gvar.clientInfluxdbWrite.write_api(write_options=WriteOptions(batch_size=5000, flush_interval=10_000, jitter_interval=2_000, retry_interval=5_000))
#         write_api.write(bucket=gvar.bucketWrite, record=listRecords)
#         logger.info('Data upload to infludb has been triggered.')
#         logger.info(f'{len(listRecords)} data points were uploaded to infludb bucket {gvar.bucketWrite}.')
#         gvar.listValWrite = []
#         gvar.listControlWrite = []
#         gvar.listTstmpWrite = []
#     except:
#         logger.warning('data upload failed, keep the data list unchanged for the next trigger interval')
#
#
    

##############################################################################
##################     IEC61850 data model service      ######################
##############################################################################
    
def create_IED_model_device(DeviceName):    
    # Logical Device
    gvar.LD_iedModel = iec61850.LogicalDevice_create(DeviceName, gvar.iedModel)
    # LLN0
    LN_LLN0     = iec61850.LogicalNode_create("LLN0", gvar.LD_iedModel)
    # LLN0 - DOs / CDCs
    DO_LLN0_Beh     = iec61850.CDC_ENS_create("Beh", iec61850.toModelNode(LN_LLN0), 0)
    DA_LLN0_Beh_stVal = iec61850.ModelNode_getChild(iec61850.toModelNode(DO_LLN0_Beh), "stVal")
    DO_LLN0_Loc     = iec61850.CDC_ENS_create("Loc", iec61850.toModelNode(LN_LLN0), 0)
    DO_LLN0_Mod     = iec61850.CDC_ENC_create("Mod", iec61850.toModelNode(LN_LLN0), 0, 1)
    DA_LLN0_Mod_stVal = iec61850.ModelNode_getChild(iec61850.toModelNode(DO_LLN0_Mod), "stVal")
    DO_LLN0_NamPlt = iec61850.CDC_DPL_create("NamPlt", iec61850.toModelNode(LN_LLN0), 0)
    # LPHD1
    LN_LPHD1 = iec61850.LogicalNode_create("LPHD1", gvar.LD_iedModel)
    # LPHD1 - DOs / CDCs
    DO_LPHD1_PhyHealth = iec61850.CDC_ENS_create("PhyHealth", iec61850.toModelNode(LN_LPHD1), 0)
    DO_LPHD1_PhyNam = iec61850.CDC_DPL_create("PhyNam", iec61850.toModelNode(LN_LPHD1), 0)
    DO_LPHD1_Proxy = iec61850.CDC_SPS_create("Proxy", iec61850.toModelNode(LN_LPHD1), 0)


def create_IED_model_essential():
    setattr(gvar, "iedModel", 0)
    #setattr(gvar, 'ied_model_dict', {})
        
    IedModelName = gvar.IedModelName
    IedModelName = IedModelName + "_"
        
    gvar.iedModel = iec61850.IedModel_create(IedModelName)
    
    logger.info("Auto generating IED model: %s" %(IedModelName))
    return
    
def create_demo_IED_model():
    '''
    Create LN (pvsys or load) from JSON tag
    '''
    # Def
    dictUpdateVal = dict()
#    dictUpdateVal["PF_obj"] = device
#    dictUpdateVal["PF_obj_name"] = device.loc_name
    
    PF_attr = []
    Iec_DA = []
    Iec_DO_name = []
    Iec_DA_mag = []
    Iec_DA_t = []
        
    # create_LN
    DeviceName = gvar.DeviceName
    logger.info(f'LN Name: {DeviceName}')
        
    if gvar.derType == 'pv':
        SysTypPref = 'PV'
    elif gvar.derType == 'load':
        SysTypPref = 'LOAD'
    else:
        SysTypPref = 'UNKNOWN'
        
    LNDevInstance = '1'
    logger.info(f'Current LN Dev Instance: {LNDevInstance}')
    
    LNType = "MMXU"
    LNInstance = int(LNDevInstance)-1
    LNName = SysTypPref + str(LNDevInstance) + "_" + LNType + str(LNInstance)
    LNgvarStr = DeviceName + "_LN_" + LNName	
    		
    LNgvar = setattr(gvar, LNgvarStr, 0)
    LNgvar = iec61850.LogicalNode_create(LNName, gvar.LD_iedModel)
    	
    # create_DS 
    DSgvarStr = DeviceName + "_DS_" + LNName	
    DSgvar = setattr(gvar, DSgvarStr, 0)
    DSgvar = iec61850.DataSet_create(DSgvarStr, LNgvar)	
    
    RCB_gvarStr = DeviceName + "_RP_" + LNName
    RCB_gvarStrID = RCB_gvarStr + "_01"
    RCB_gvar = setattr(gvar, RCB_gvarStr, 0)
    RCB_gvar =  iec61850.ReportControlBlock_create(RCB_gvarStr, LNgvar, RCB_gvarStrID, False, DSgvarStr , 1, 8, 0, 0, 10000)
    
    gvar.DSgvar = DSgvar
    gvar.DSgvarStr = DSgvarStr
    gvar.RCB_gvar = RCB_gvar
    gvar.RCB_gvarStr = RCB_gvarStr
    
    # Create Variables
    ### Create Ubb
    Value = "f"	  
    ValueType = "mag_f"
    ValueDataType = "mag.f"
    DA_t = 't'
    DOgvar = DeviceName + "_DO_"  + LNName + "_" + Value
    DAgvar = DeviceName + "_DA_"  + LNName + "_" + Value	+ "_" + ValueType
    DAgvar_t = DeviceName + "_DA_"  + LNName + "_" + Value	+ "_" + DA_t
    Iec_DO_name.append(DOgvar)
    
    
    localgvarDO = setattr(gvar, DOgvar, 0)
    localgvarDO = iec61850.CDC_MV_create(Value, iec61850.toModelNode(LNgvar), 0, False)
    localgvarDA = setattr(gvar, DAgvar, 0)
    localgvarDA = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), ValueDataType)
    localgvarDA_t = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), DA_t)
    
    PF_attr.append("m:u")
    Iec_DA.append(localgvarDA)
    Iec_DA_mag.append(0)
    Iec_DA_t.append(localgvarDA_t)
    setattr(gvar, "f_index", PF_attr.index("m:u"))
    
    #Add DataSet Entry
    DSentryMMS = LNName + "$MX$" + Value
    DSgvarEntryStr = DeviceName + "_DS_" + LNName + "_" + Value
    localgvarDSentry = setattr(gvar, DSgvarEntryStr, 0)
    localgvarDSentry = iec61850.DataSetEntry_create(DSgvar, DSentryMMS, -1, None)
    
    ### Create DO TotW
    Value = "TotW"	
    ValueType = "mag_f"
    ValueDataType = "mag.f"
    DOgvar = DeviceName + "_DO_"	+ LNName + "_" + Value
    DAgvar = DeviceName + "_DA_"  + LNName + "_" + Value	+ "_" + ValueType
    Iec_DO_name.append(DOgvar)
    	
    localgvarDO = setattr(gvar, DOgvar, 0)
    localgvarDO = iec61850.CDC_MV_create(Value, iec61850.toModelNode(LNgvar), 0, False)
    localgvarDA = setattr(gvar, DAgvar, 0)
    localgvarDA = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), ValueDataType)
    localgvarDA_t = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), DA_t)
    
    PF_attr.append("m:P:bus1")
    Iec_DA.append(localgvarDA)
    Iec_DA_mag.append(0)
    Iec_DA_t.append(localgvarDA_t)
    setattr(gvar, "p_tot_index", PF_attr.index("m:P:bus1"))
    
    #Add DataSet Entry
    DSentryMMS = LNName + "$MX$" + Value
    DSgvarEntryStr = DeviceName + "_DS_" + LNName + "_" + Value
    localgvarDSentry = setattr(gvar, DSgvarEntryStr, 0)
    localgvarDSentry = iec61850.DataSetEntry_create(DSgvar, DSentryMMS, -1, None)
    
    ### Create TotVar
    Value = "TotVar"	
    ValueType = "mag_f"
    ValueDataType = "mag.f"
    DOgvar = DeviceName + "_DO_"	+ LNName + "_" + Value
    DAgvar = DeviceName +"_DA_"  + LNName + "_" + Value	+ "_" + ValueType
    Iec_DO_name.append(DOgvar)
    	
    localgvarDO = setattr(gvar, DOgvar, 0)
    localgvarDO = iec61850.CDC_MV_create(Value, iec61850.toModelNode(LNgvar), 0, False)
    localgvarDA = setattr(gvar, DAgvar, 0)
    localgvarDA = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), ValueDataType)
    localgvarDA_t = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), DA_t)
    
    
    PF_attr.append("m:Q:bus1")
    Iec_DA.append(localgvarDA)
    Iec_DA_mag.append(0)
    Iec_DA_t.append(localgvarDA_t)
    setattr(gvar, "q_tot_index", PF_attr.index("m:Q:bus1"))
    
    #Add DataSet Entry
    DSentryMMS = LNName + "$MX$" + Value
    DSgvarEntryStr = DeviceName + "_DS_" + LNName + "_" + Value
    localgvarDSentry = setattr(gvar, DSgvarEntryStr, 0)
    localgvarDSentry = iec61850.DataSetEntry_create(DSgvar, DSentryMMS, -1, None)
    
    ######### DO for control ################################
    Value = "OutWSet"	
    ValueType = "setMag_f"
    ValueDataType = "setMag.f"
    DOgvar = DeviceName + "_DO_"	+ LNName + "_" + Value
    DAgvar = DeviceName + "_DA_"  + LNName + "_" + Value	+ "_" + ValueType
    Iec_DO_name.append(DOgvar)
    	
    localgvarDO = setattr(gvar, DOgvar, 0)
    localgvarDO = iec61850.CDC_ASG_create(Value, iec61850.toModelNode(LNgvar), iec61850.CDC_OPTION_UNIT, False)
    localgvarDA = setattr(gvar, DAgvar, 0)
    localgvarDA = iec61850.ModelNode_getChild(iec61850.toModelNode(localgvarDO), ValueDataType)
    
    PF_attr.append("Pmax_uc")
    Iec_DA.append(localgvarDA)
    Iec_DA_mag.append(0)
    setattr(gvar, "p_pv_max_index", PF_attr.index("Pmax_uc"))
    
    #Add DataSet Entry
    DSentryMMS = LNName + "$SP$" + Value
    DSgvarEntryStr = DeviceName + "_DS_" + LNName + "_" + Value
    localgvarDSentry = setattr(gvar, DSgvarEntryStr, 0)
    localgvarDSentry = iec61850.DataSetEntry_create(DSgvar, DSentryMMS, -1, None)


    # write initial IED data model
    dictUpdateVal["PF_attr"] = PF_attr  
    dictUpdateVal["Iec_DA"] = Iec_DA
    dictUpdateVal["Iec_DO_name"] = Iec_DO_name
    dictUpdateVal["Iec_DA_mag"] = Iec_DA_mag
    dictUpdateVal["Iec_DA_t"] = Iec_DA_t
        
    logger.info("LD created: {}".format(DeviceName))
    return (dictUpdateVal)

def create_IED_server():
    gvar.iedServer = iec61850.IedServer_create(gvar.iedModel)
    logger.info("IED server created")

def start_IED_server():
    iec61850.IedServer_start(gvar.iedServer, gvar.port)
    iec61850.IedServer_isRunning(gvar.iedServer)
    iec61850.IedServer_getMmsServer(gvar.iedServer)


    logger.info("IED server started")
    return


##############################################################################
##################     IEC61850 data interface service      ##################
##############################################################################
    
def init_MX_val():
    gvar.demoProsumerXY_mmxu1_f_mag_f = 50
    gvar.demoProsumerXY_mmxu1_totvar_mag_f = 200
    if gvar.dataSource == 'random':   
        gvar.demoProsumerXY_mmxu1_totw_mag_f = 5000
    # elif gvar.dataSource == 'local':
    #     load_profile_local()
    #     val = get_val_in_profile()
    # elif gvar.dataSource == 'influxdb':
    #     load_profile_influxdb()
    #     val = get_val_in_profile()
    #     if val is None:
    #         gvar.demoProsumerXY_mmxu1_totw_mag_f = 0
    #     else:
    #         gvar.demoProsumerXY_mmxu1_totw_mag_f = Profile.listVal[0] * gvar.unitFactor * gvar.scaleFactor
    else:
        logger.error(f'Unknown data source: {gvar.dataSource}, please check the config file.')
    return

def update_MX_val():
    gvar.demoProsumerXY_mmxu1_f_mag_f  += random.randint(-100,100)/1000
    gvar.demoProsumerXY_mmxu1_totvar_mag_f += random.randint(-100,100)/1000
    if gvar.dataSource == 'random':   
        gvar.demoProsumerXY_mmxu1_totw_mag_f += random.randint(-3000,3000)/10000
    # elif gvar.dataSource == 'local' or gvar.dataSource == 'influxdb':
    #     try:
    #         val = get_val_in_profile()
    #         if val is None:
    #             pass  # do nothing, the simulation will use the value from the previous step
    #         else:
    #             valProfile = val * gvar.unitFactor * gvar.scaleFactor  # multiply by 5 to cause overvoltage problems
    #             valLimit = gvar.demoProsumerXY_mmxu1_outwset_current_val * gvar.pvRatedPower * gvar.unitFactor * gvar.scaleFactor
    #             valUpdate = min(valProfile, valLimit)
    #             gvar.demoProsumerXY_mmxu1_totw_mag_f = valUpdate
    #     except:
    #         logger.warning('Update MX values failed, wait for the next iteration')
    #         gvar.demoProsumerXY_mmxu1_totw_mag_f = 0
    return
    

def init_SP_val(val):
    gvar.demoProsumerXY_mmxu1_outwset_setmag_f = val

def update_SP_val(val):
    dictUpdateVal = gvar.container_pvsys[0] # container has only one element with index = 0
    Iec_DA = dictUpdateVal['Iec_DA']
    Iec_DA_mag = dictUpdateVal['Iec_DA_mag']
    gvar.demoProsumerXY_mmxu1_outwset_setmag_f = val
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_pv_max_index]), val)
    Iec_DA_mag[gvar.p_pv_max_index] = val

    
def update_IED_attr():
    dictUpdateVal = gvar.container_pvsys[0] # container has only one element with index = 0
    Iec_DA = dictUpdateVal['Iec_DA']
    Iec_DA_mag = dictUpdateVal['Iec_DA_mag']
    Iec_DA_t = dictUpdateVal['Iec_DA_t']
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.f_index]), gvar.demoProsumerXY_mmxu1_f_mag_f)
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.q_tot_index]), gvar.demoProsumerXY_mmxu1_totvar_mag_f)      
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_tot_index]), gvar.demoProsumerXY_mmxu1_totw_mag_f)        
    # update all timestamps
    srvTimeSource = gvar.timeMode
    if srvTimeSource == 'absolute':
        iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA_t[gvar.q_tot_index]), get_UTC_timestamp_uint64())
        iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA_t[gvar.f_index]), get_UTC_timestamp_uint64())
        iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA_t[gvar.p_tot_index]), get_UTC_timestamp_uint64())
    elif srvTimeSource == 'simulation':
        iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA_t[gvar.q_tot_index]), get_simulation_timestamp_uint64(gvar.cTimeUnix))
        iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA_t[gvar.f_index]), get_simulation_timestamp_uint64(gvar.cTimeUnix))
        iec61850.IedServer_updateUTCTimeAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA_t[gvar.p_tot_index]), get_simulation_timestamp_uint64(gvar.cTimeUnix))

    gvar.demoProsumerXY_mmxu1_f_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.f_index]))
    gvar.demoProsumerXY_mmxu1_totw_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_tot_index]))
    gvar.demoProsumerXY_mmxu1_totvar_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.q_tot_index]))
    gvar.demoProsumerXY_mmxu1_outwset_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_pv_max_index]))    
    return

def get_SP_control():
    isControlled = False
    dict_pvsys = gvar.container_pvsys[0]
    Iec_DA = dict_pvsys['Iec_DA']
    Iec_DA_mag = dict_pvsys['Iec_DA_mag']
    outwset_server = Iec_DA_mag[gvar.p_pv_max_index]
    outwset_client = round(iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_pv_max_index])), 2) 

    # logger.info('SP value in the IED server: {}'.format(outwset_server))
    # logger.info('SP value from client: {}'.format(outwset_client))
    if outwset_server != outwset_client:
        logger.info('************************************')
        logger.info('***  control command received ******')
        logger.info('************************************')
        logger.info("OutWSet changed: {} -> {}".format(outwset_server, outwset_client))
        Iec_DA_mag[gvar.p_pv_max_index] = outwset_client
        gvar.container_pvsys[0]['Iec_DA_mag'][gvar.p_pv_max_index] = outwset_client
        gvar.demoProsumerXY_mmxu1_outwset_setmag_f = outwset_client
        isControlled = True
    else:
        pass
    iec61850.IedServer_updateFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_pv_max_index]), gvar.demoProsumerXY_mmxu1_outwset_setmag_f)
    gvar.demoProsumerXY_mmxu1_outwset_current_val = iec61850.IedServer_getFloatAttributeValue(gvar.iedServer, iec61850.toDataAttribute(Iec_DA[gvar.p_pv_max_index]))
    return isControlled


##############################################################################
##################     IEC61850 server runtime service      ##################
##############################################################################
def initialize_iedServer():
    '''
    Initialization of the IEC 61850 data model and data server.
    '''
    
    # initialize the data model and IED server
    logger.info('=================   Begin IEC 61850 server initialization    =================')
    listNameLN = ['MMXU']
    create_IED_model_essential()
    create_IED_model_device(gvar.DeviceName)
    for NameLN in listNameLN:                  
        dictUpdateVal = create_demo_IED_model()
        gvar.container_all_objects.append(dictUpdateVal)
        gvar.container_pvsys.append(dictUpdateVal)
    
    create_IED_server()
    start_IED_server()

    logger.info('Verif DO in the IED data model')     
    logger.info(gvar.container_pvsys)
    
    logger.info('verify LD in the IED model')
    logger.info('IED LD count: {}'.format(iec61850.IedModel_getLogicalDeviceCount(gvar.iedModel)))
    
    logger.info('Verif Data Sets in the IED data model') 
    obj_dataset = iec61850.IedModel_lookupDataSet(gvar.iedModel, '{}_{}/PV1_MMXU0${}'.format(gvar.IedModelName, gvar.DeviceName, gvar.DSgvarStr))    
    if obj_dataset != None:
        logger.info('Found data set with name: {}'.format(obj_dataset.name))
    else:
        logger.warning('No data set available')
    logger.info('Data set size: {}'.format(iec61850.DataSet_getSize(obj_dataset)))
    logger.info('=================   End IEC 61850 server initialization    =================\n')
    
def initialize_measurements():
    '''
    Initialization of the measurements for the IEc 61850 server.
    '''
    
    logger.info('=================   Begin measurement initialization    =================')   
    
    init_MX_val()
    init_SP_val(1.0)
    update_SP_val(1.0)
    update_IED_attr()
    
    logger.info('-------------------------------------------------------------------')
    logger.info("Server initializing")
    
    logger.info('Init measurements:')
    logger.info('TotW: {} W; TotVAR: {} VAr; f: {} Hz'.format(gvar.demoProsumerXY_mmxu1_totw_mag_f, gvar.demoProsumerXY_mmxu1_totvar_mag_f, gvar.demoProsumerXY_mmxu1_f_mag_f))
       
    logger.info('Init measurements IEC 61850:')
    logger.info('TotW: {} W; TotVAR: {} VAr; f: {} Hz'.format(gvar.demoProsumerXY_mmxu1_totw_current_val, gvar.demoProsumerXY_mmxu1_totvar_current_val, gvar.demoProsumerXY_mmxu1_f_current_val))

    logger.info('Init setpoint value:')
    logger.info('OutWSet: {}'.format(gvar.demoProsumerXY_mmxu1_outwset_current_val))
    logger.info('-------------------------------------------------------------------\n')
    
    logger.info('=================   End measurement initialization    =================\n')

def update_measurements():
    '''
    Iteratively update the measurements for the IEc 61850 server.
    '''
    
    # here do a rounding trick to make sure the time will be HH:MM:SS
    logger.info(f'Actual current datetime: {gvar.cTime}; current Unix time: {gvar.cTimeUnix}')
    cTimeString = datetime.strftime(datetime.fromtimestamp(gvar.cTimeUnix), '%Y-%m-%d %H:%M:%S')
    # cTimeString = datetime.strftime(datetime.fromtimestamp(round(int(gvar.cTimeUnix)/10)*10), '%Y-%m-%d %H:%M:%S')
    # if int(cTimeString[-2:]) == 0:
    #     pass
    # elif int(cTimeString[-2:]) in range(0,31):
    #     cTimeString = cTimeString[:-2] + '00'
    # elif int(cTimeString[-2:]) in range(31,60):
    #     if int(cTimeString[-5:-3]) < 59:
    #         cTimeString = f'{cTimeString[:-5]}:{int(cTimeString[-5:-3])+1}:00'
    #     else:
    #         cTimeString = cTimeString[:-2] + '00'
    
    gvar.cTime = cTimeString
    logger.info(f'Current datetime string for data query: {gvar.cTime}')
    
    # if gvar.dataSource == 'influxdb' and '00:00:00' in gvar.cTime:
    #     load_profile_influxdb()  # if a new day starts, update the profile dataFrame for this day
    # elif gvar.dataSource == 'local' and '00:00:00' in gvar.cTime:
    #     load_profile_local()  # if a new day starts, update the profile dataFrame for this day
    logger.info('Update measurement values')
    update_MX_val()
    update_IED_attr()
    
    logger.info('Current measurements (random/profile/time series database):')
    logger.info('TotW: {} W; TotVAR: {} VAr; f: {} Hz'.format(gvar.demoProsumerXY_mmxu1_totw_mag_f, gvar.demoProsumerXY_mmxu1_totvar_mag_f, gvar.demoProsumerXY_mmxu1_f_mag_f))
    
    logger.info('Current measurements IEC 61850:')
    logger.info('TotW: {} W; TotVAR: {} VAr; f: {} Hz'.format(gvar.demoProsumerXY_mmxu1_totw_current_val, gvar.demoProsumerXY_mmxu1_totvar_current_val, gvar.demoProsumerXY_mmxu1_f_current_val))
    
    logger.info('Current setpoint value:')
    logger.info('OotWSet: {}'.format(gvar.demoProsumerXY_mmxu1_outwset_current_val))

def server_initialization():
    gvar.cTime = gvar.startTime
    gvar.cTimeUnix = gvar.startTimeUnix
    
    # if gvar.dataSource == 'influxdb':
    #     try:
    #         connectInfluxdb()
    #     except:
    #         logger.warning('Connecting to influxdb failed')
    # elif gvar.dataSource == 'local':
    #     load_profile_local_init()
    
    initialize_iedServer()
    initialize_measurements()
    
def server_routine():
    # start the server routine loop
    while gvar.cTimeUnix < gvar.endTimeUnix:        
        timerStart = time.time()  # use this time to compensate the processing time in each iteration.        
        logger.info('-------------------------------------------------------------------')
        logger.info("Server running")
        try:
            update_measurements() 
        except:
              logger.warning('Update measurement failed, wait for the next iteration')  
        isControlled = False
        for i in range(gvar.WATCHDOG_ITERATION):
            isControlled = get_SP_control()
            time.sleep(gvar.WATCHDOG_SLEEP)
        if isControlled is True:
            logger.info('Control command is executed in the last interval')
        else:
            logger.info('No control command is executed in the last interval')
        
        gvar.listValWrite.append(gvar.demoProsumerXY_mmxu1_totw_mag_f)
        gvar.listControlWrite.append(gvar.demoProsumerXY_mmxu1_outwset_current_val)
        gvar.listTstmpWrite.append(gvar.cTime)
        
        timerEnd = time.time()
        processingTime = timerEnd - timerStart - gvar.WATCHDOG_ITERATION*gvar.WATCHDOG_SLEEP
        logger.info(f'Processing time for the current iteration: {processingTime} seconds')
        gvar.cTimeUnix += gvar.TIME_INTERVAL - processingTime
        logger.info('-------------------------------------------------------------------\n')
        
        # if gvar.dataSource == 'influxdb' and gvar.cTime[-5:] == '00:00':  # if the time is XX:00:00
        #     try:
        #         push_df_to_influx()
        #     except:
        #         logger.warning('Data upload to influxdb failed, wait for the next hour')

if __name__ == '__main__':
    # updateJSONConfig()    
    logger = create_rotating_log()
    displayConfigInfo()
    server_initialization()
    server_routine()