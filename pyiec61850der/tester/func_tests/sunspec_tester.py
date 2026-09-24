# -*- coding: utf-8 -*-
"""
A tester script for sunspec functions.

@author: chen
"""

import sunspec2.modbus.client as client

def sunspec_full_scan(ip_addr='192.168.170.78', port=502, slave_id=126):
    d = client.SunSpecModbusClientDeviceTCP(slave_id, ip_addr, port)
    d.scan()
    print(d.models)
    if len(d.models) != 0 or d.models is not None:
        model_names = [key for key, obj in d.models.items() if type(key) is str]
        model_ids = [key for key, obj in d.models.items() if type(key) is int]
        print(f'List of sunspec model names: {model_names}')
        print(f'List of sunspec model ID: {model_ids}')
        for key, obj in d.models.items():
            if type(key) is int:
                print(f'Found Sunspec model {key}')
                model_id = key
                points = getattr(d.models[model_id][0], 'points')
                for name, val in points.items():
                    val = getattr(d.models[model_id][0], name).cvalue
                    print(f'Parameter name {name}, value: {val}')


def control_tester(ip_addr='192.168.170.90', port=502, slave_id=126):
    d = client.SunSpecModbusClientDeviceTCP(slave_id, ip_addr, port)
    d.scan()

    model_id = 123

    obj = getattr(d.models[model_id][0], 'WMaxLim_Ena')
    obj.read()
    obj.cvalue
    obj.cvalue = 1
    obj.write()
    obj.read()
    obj.cvalue

    obj = getattr(d.models[model_id][0], 'WMaxLimPct')
    obj.cvalue = 100
    obj.write()
    obj.read()
    obj.cvalue

    model_id = 704
    obj = getattr(d.models[model_id][0], 'WMaxLimPctEna')
    obj.read()
    obj.cvalue
    obj.cvalue = 1
    obj.write()
    obj.read()
    obj.cvalue

    obj = getattr(d.models[model_id][0], 'WMaxLimPct')
    obj.cvalue = 100  # Attention: the scale factor is probaly not working properly!
    obj.write()
    obj.read()
    obj.cvalue


slave_id = 126
ip_addr = '192.168.170.76'
port = 502

sunspec_full_scan(ip_addr, port, slave_id)
# control_tester(ip_addr, port, slave_id)

#################################################################
#################### IEC 61850 relevante tests  #################
#################################################################

import time
import pandas as pd
from datetime import datetime, timezone
from settings import helper, config
import communication.pyiec61850_server as iec61850Server
import interface
from settings.helper import rotating_logger
import model
import pytz
from simulation.runtime_manager import IedManager
from simulation.virtual_ied import init_virtual_ied_interfaces

helper.set_env_libiec61850()
nameLogger = 'sunspecTester'
logger = rotating_logger(nameLogger)

instConfig = config.IedConfig()
path_config = './settings/config.yaml'
instConfig.update_config(path_config)
# instConfig.display_config_info(instConfig)

# dmGen = model.IEC61850DataModelGenerator(pathConfigFile=instConfig.interface.path_data_model_config,
#                                          nameIED=instConfig.CLS.ied_name)
# [pathOutputSCL, dictOutputSCL] = dmGen.main(readConfigYAML=True, configYAML=instConfig.interface.config_yaml)
# instConfig.interface.path_scl = pathOutputSCL

iedServer = iec61850Server.run_ied_server_mms(instConfig)
iedServer.server_config.container = instConfig.container  # synchronise the server configuration with global config (mainly about the time setting)
iedServer.server_config.der = instConfig.der
# iedServer.server_config.der.der_dicts = dmGen.Config.der_dicts
instConfig.interface.path_lookup = iedServer.path_lookup
instConfig.interface.df_lookup = iedServer.df_lookup

ied_manager = IedManager()
ied_manager.init_ied_service(path_config)
init_virtual_ied_interfaces(ied_manager)

interface.sunspec.init_sunspec_interface(ied_manager)

def routine_reading(config_obj, sunspec_conn):
    """
    This function should perform the sunspec reading for a list of parameters as routine. Currently,
    it is constructed but not used in the runtime environment, only a test function :func:`sunspec_tester` calls it.

    Its functionality could be used to read and process data that are not directly involved in the real-time IEC
    61850 application, e.g. display sunspec values or status check.
    """

    df_lookup = config_obj.interface.df_lookup
    df_lookup_sunspec = df_lookup.loc[df_lookup['data_source'] == 'sunspec']
    df_mapping = config_obj.interface.df_sunspec_mapping

    sunspec_conn.scan()
    df_reading = pd.DataFrame(columns=df_mapping['Name'])
    for idx, parameter in enumerate(list(df_reading)):
        idx_mapping = df_mapping.loc[df_mapping['Name'] == parameter].index.to_list()[0]
        model_id = df_mapping.loc[idx_mapping, 'Model ID']

        if sunspec_conn is None:
            sunspec_conn = df_lookup_sunspec.loc[idx, 'fieldbus_conn_obj']

        val = interface.sunspec.read_value_from_point(sunspec_conn, model_id, parameter)
        df_reading.loc[0, parameter] = val

    return df_reading

def SunspecMonitorIED(ipaddr='192.168.170.90', port=502, slave_id=126):
    d = client.SunSpecModbusClientDeviceTCP(slave_id, ipaddr, port)
    dfLookup = instConfig.interface.df_lookup
    dfMapping = instConfig.interface.df_sunspec_mapping

    dfData = pd.DataFrame(columns=['tstmp', 'Unix'] + list(dfMapping['Name']))

    counter = 0

    for i in range(999999999):

        ctime_utc = datetime.now(timezone.utc)
        ctime_local = ctime_utc.astimezone(pytz.timezone('Europe/Berlin'))
        ctime_local_unix = time.mktime(ctime_local.timetuple())
        time_start = time.perf_counter()

        print(f'Time: {ctime_local}, Unix: {ctime_local_unix}')

        dfNew = interface.sunspec.routine_reading(instConfig, d)
        dfNew['tstmp'] = ctime_local
        dfNew['Unix'] = ctime_local_unix
        dfData = dfData.append(dfNew)
        counter += 1

        if counter % 6 * 15 == 0:
            dfData.to_csv(f'./tester/func_tests/dataRecording_{instConfig.CLS.ied_name}.csv')
        time_end = time.perf_counter()
        processingTime = time_end - time_start

        time.sleep(10 - processingTime)

slave_id = 126
ip_addr = '192.168.170.76'
port = 502
SunspecMonitorIED(ip_addr, port, slave_id)