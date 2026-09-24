# -*- coding: utf-8 -*-
"""
A 100-node test network for simple tests.
"""


import pandapower as pp
import numpy as np
import pandas as pd

from settings.helper import rotating_logger

nameLogHandler = 'networkConfigurator'
nameLogger =  f'{nameLogHandler}Logger' 

logger = rotating_logger(nameLogHandler, nameLogger)
logger.info(f'Logger {nameLogger} initialized')


class NetworkParameter(object):
    '''
    A class that stores the configuration of the network, such as component types
    and constraints.
    
    The configuration can be modified before the network initialization.
    TODO: consider move this function somewhere else, like network.parameter
    '''
    
    # bus configuration
    MV_BUS_VOLTAGE = 20  # 20 kV
    LV_BUS_VOLTAGE = 0.4  # 400V
    MIN_BUS_VOLTAGE = 0.95
    MAX_BUS_VOLTAGE = 1.05

    
    # transformator configuration
    MAX_TRAFO_OVERLOADING = 80
    DEFAULT_TRAFO_TYPE = '0.63 MVA 20/0.4 kV'

    
    # line configuration
    DEFAULT_LV_LINE_TYPE = 'NAYY 4x50 SE'  # max I 0.142 kA
    DEFAULT_MV_LINE_TYPE = 'NA2XS2Y 1x95 RM/25 12/20 kV'  # max I 0.252 kA
    MV_LINE_LENGTH_KM = 5
    LV_LINE_LENGTH_KM = 0.01
    MAX_LINE_OVERLOADING = 80
    
    # load configuration
    DEFAULT_LOAD_ACTIVE_POWER = 0.002
    DEFAULT_LOAD_REACTIVE_POWER = 0.0005
    MAX_LOAD_ACTIVE_POWER = 0.05
    MIN_LOAD_ACTIVE_POWER = 0
    MAX_LOAD_REACTIVE_POWER = 0.05
    MIN_LOAD_REACTIVE_POWER = 0
    
    # generator configuration
    DEFAULT_PV_ACTIVE_POWER = 0.015
    DEFAULT_PV_REACTIVE_POWER = 0.005
    DEFAULT_PV_APPARENT_POWER = 0.035
    MAX_PV_ACTIVE_POWER = 0.03  # 30 kW as default
    MIN_PV_ACTIVE_POWER = 0
    MAX_PV_REACTIVE_POWER = 0.005
    MIN_PV_REACTIVE_POWER = -0.005
    
    
    
    
    
    listNumberFeeders = [2, 3, 5]    
    nodePerFeeder = 10  # this should be an integer
    nTransformer = len(listNumberFeeders)
    nFeeder = sum(listNumberFeeders)
    nNode = listNumberFeeders * nodePerFeeder



def initNetwork():
    """
    This function initializes a pandas network with pre-defined parameter. One can
    always modify the network configuraiton, but the network structure will be fixed.
    
    Each node in the network contains information about consumption and feed-in power,
    which could be communicated with an IEC 61850 server.
    """
    
    para = NetworkParameter()
    
    # TODO: dump list of load and gen, instead use list of nodes, each household is
    # just one node, and the IEC 61850 server takes care of data collection and control
    
    listInstLoad = []
    listInstGen = []
    
    logger.info('=================   Begin network initialization    =================')
    #create empty net
    net = pp.create_empty_network()
    
    #create slack
    bus0 = pp.create_bus(net, vn_kv=para.MV_BUS_VOLTAGE, max_vm_pu=para.MAX_BUS_VOLTAGE, 
                         min_vm_pu=para.MIN_BUS_VOLTAGE, name='Bus slack')
    
    listBusLV = []
    listBusMV = []
    listTransformer = []
    
    # create transformers and MV/LV buses
    for i in range(para.nTransformer): 
        #create bus elements
        busMV = pp.create_bus(net, vn_kv=para.MV_BUS_VOLTAGE, max_vm_pu=para.MAX_BUS_VOLTAGE, 
                              min_vm_pu=para.MIN_BUS_VOLTAGE, name=f'Bus MV {i}')
        busLV = pp.create_bus(net, vn_kv=para.LV_BUS_VOLTAGE, max_vm_pu=para.MAX_BUS_VOLTAGE, 
                              min_vm_pu=para.MIN_BUS_VOLTAGE, name=f'Bus LV {i}')
        loadMV = pp.create_load(net, bus=busMV, p_mw=0.2, q_mvar=0.05, name=f'Load MV {i}')
        listBusLV.append(busLV)
        listBusMV.append(busMV)
        
        #create branch elements
        trafo = pp.create_transformer(net, hv_bus=busMV, lv_bus=busLV, max_loading_percent=para.MAX_TRAFO_OVERLOADING, 
                                      std_type=para.DEFAULT_TRAFO_TYPE, name=f'Trafo MV/LV {i}')
        
    # configure external grid
    pp.create_ext_grid(net, bus=bus0, vm_pu=1.03, name='Grid Connection', va_degree=0.0, in_service=True,
                       max_p_mw=3, min_p_mw=0, max_q_mvar=1, min_q_mvar=0)
    pp.create_poly_cost(net, 0, 'ext_grid', cp1_eur_per_mw=-1)
    
    
    # configure synthetic load on the MV side
    pp.create_load(net, bus=listBusMV[0], p_mw=0.2, q_mvar=0.05, name='Load MV 1')
    pp.create_load(net, bus=listBusMV[1], p_mw=0.5, q_mvar=0.05, name='Load MV 2')
    pp.create_load(net, bus=listBusMV[2], p_mw=0.75, q_mvar=0.05, name='Load MV 3')
    
    # create lines between slack bus and the 3 MV buses
    line1 = pp.create_line(net, from_bus=bus0, to_bus=listBusMV[0], length_km=para.MV_LINE_LENGTH_KM, 
                           max_loading_percent=para.MAX_LINE_OVERLOADING, name='Line MV 1',std_type=para.DEFAULT_MV_LINE_TYPE)
    line2 = pp.create_line(net, from_bus=listBusMV[0], to_bus=listBusMV[1], length_km=para.MV_LINE_LENGTH_KM, 
                           max_loading_percent=para.MAX_LINE_OVERLOADING, name='Line MV 2',std_type=para.DEFAULT_MV_LINE_TYPE)
    line3 = pp.create_line(net, from_bus=listBusMV[1], to_bus=listBusMV[2], length_km=para.MV_LINE_LENGTH_KM,
                           max_loading_percent=para.MAX_LINE_OVERLOADING, name='Line MV 3',std_type=para.DEFAULT_MV_LINE_TYPE)
    
    # create LV branches and elements
    listBusFrom = []
    for idx, val in enumerate(para.listNumberFeeders):
        for j in range(val):
            listBusFrom.append(listBusLV[idx])
    
    idxLoad = 0
    idxPV = 0
    
    listNodeAll = []
    listLineAll = []
    listLoadAll = []
    listPVAll = []   
    
    for k in range(para.nFeeder):
        listNodeLV = []
        listLineLV = []
        listLoad = []
        listPV = []
        busFrom = listBusFrom[k]
        for idxHouse in range(para.nodePerFeeder):    
            busTo = pp.create_bus(net, vn_kv=para.LV_BUS_VOLTAGE, type='m', max_vm_pu=para.MAX_BUS_VOLTAGE, 
                                  min_vm_pu=para.MIN_BUS_VOLTAGE, name=f'Node LV {k},{idxHouse}')
            lineNew = pp.create_line(net, from_bus=busFrom, to_bus=busTo, length_km=para.LV_LINE_LENGTH_KM, 
                                     name=f'Line LV {k},{idxHouse}',std_type=para.DEFAULT_LV_LINE_TYPE)
            listNodeLV.append(busTo)
            listLineLV.append(lineNew)
            busFrom = busTo           
            
            # add load to the household node
            loadNew = pp.create_load(net, bus=busFrom, p_mw=para.DEFAULT_LOAD_ACTIVE_POWER, q_mvar=para.DEFAULT_LOAD_REACTIVE_POWER, 
                                     name=f'name: Load LV {k},{idxHouse}', controllable=False, max_p_mw=para.MAX_LOAD_ACTIVE_POWER, 
                                     min_p_mw=para.MIN_LOAD_ACTIVE_POWER, max_q_mvar=para.MAX_LOAD_REACTIVE_POWER, 
                                     min_q_mvar=para.MIN_LOAD_REACTIVE_POWER)
            pp.create_poly_cost(net, loadNew, 'load', cp1_eur_per_mw=1)
            listLoad.append(busTo)
            idxLoad += 1

            # add PV to the household node
            PVNew = pp.create_sgen(net, bus=busFrom, p_mw=para.DEFAULT_PV_ACTIVE_POWER, q_mvar=para.DEFAULT_PV_REACTIVE_POWER, 
                                   sn_mva=para.DEFAULT_PV_APPARENT_POWER, name=f'PV LV {k},{idxHouse}', index=None, 
                                   max_q_mvar=para.MAX_PV_REACTIVE_POWER, min_q_mvar=para.MIN_PV_REACTIVE_POWER, 
                                   min_p_mw=para.MIN_PV_ACTIVE_POWER, max_p_mw=para.MAX_PV_ACTIVE_POWER, 
                                   min_vm_pu=para.MIN_BUS_VOLTAGE, max_vm_pu=para.MAX_BUS_VOLTAGE, scaling=1.0, type='sync', 
                                   slack=False, controllable=True, in_service=True)
            pp.create_poly_cost(net, PVNew, 'sgen', cp1_eur_per_mw=-1)
            listPV.append(PVNew)
            idxPV += 1
            
        listNodeAll.append(listNodeLV)
        listLineAll.append(listLineLV)
        listLoadAll.append(listLoad)
        listPVAll.append(listPV)            
    
    logger.info('=================   End network initialization    =================\n')
    
    return net, listNodeAll, listLoadAll, listPVAll




def runpp(net):
    # run PF and OPF using default setup
    # perform Power Flow calculation
    pp.runpp(net, algorithm='nr', calculate_voltage_angles='auto', init='auto', 
                     max_iteration=500, tolerance_mva=1e-06, trafo_model='t', 
                     trafo_loading='current', enforce_q_lims=False, check_connectivity=True, 
                     voltage_depend_loads=True, consider_line_temperature=False, run_control=False)

def runopp(net):
    pp.runopp(net, verbose=False, calculate_voltage_angles=True, check_connectivity=True, 
                      suppress_warnings=True, switch_rx_ratio=2, delta=1e-3, init='flat',
                      numba=True, trafo3w_losses='hv', consider_line_temperature=False)


def showRes(net):    
    res_bus = net.res_bus
    res_sgen = net.res_sgen
    res_trafo = net.res_trafo
    res_load = net.res_load
    res_line = net.res_line
    
    print(net.res_bus)
    print(net.res_gen)
    print(net.res_line)
    print(net.res_trafo)

[net, listNodeAll, listLoadAll, listPVAll] = initNetwork()
runpp(net)
showRes(net)
runopp(net)
showRes(net)