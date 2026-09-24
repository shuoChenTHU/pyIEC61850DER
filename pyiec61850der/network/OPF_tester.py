# -*- coding: utf-8 -*-
"""
A test script to validate the OPF results.
"""

import pandapower.networks as pn
import pandapower as pp
import numpy as np
import pandas as pd


def add_poly_cost(net, identical_cost:bool):
    n_gen = len(net.gen)
    n_sgen = len(net.sgen)
    n_load = len(net.load)
    if identical_cost:
        p_gen = np.linspace(10,10,n_gen)
        p_sgen = np.linspace(10,10,n_sgen)
        p_load = np.linspace(1,1,n_load)
    else:
        p_gen = np.linspace(10,10+n_gen-1,n_gen)
        p_sgen = np.linspace(10,10+n_sgen-1,n_sgen)
        p_load = np.linspace(1,1+n_load-1,n_load)
            
    for i in range(len(net.gen)):
        pp.create_poly_cost(net, i, 'gen', cp1_eur_per_mw=-1*p_gen[i])
        
    for i in range(len(net.sgen)):
        pp.create_poly_cost(net, i, 'sgen', cp1_eur_per_mw=-1*p_sgen[i])
    
    # for i in range(len(net.load)):
    #     pp.create_poly_cost(net, i, 'load', cp1_eur_per_mw=-1*p_load[i])
    
def get_elements(net, is_display:bool):
    # res_bus = net.res_bus
    # res_sgen = net.res_sgen
    # res_trafo = net.res_trafo
    # res_load = net.res_load
    # res_line = net.res_line
    
    if is_display:
        print('################ Start show network elements  ###################')
        print('------- Display bus elements (default) ------------')
        print(net.bus)
        print('\n')
        
        print('------- Display generator elements (default) ------------')
        print(net.gen)
        print('\n')
        
        print('------- Display static generator elements (default) ------------')
        print(net.sgen)
        print('\n')
        
        print('------- Display load elements (default) ------------')
        print(net.load)
        print('\n')
        
        print('------- Display line elements (default) ------------')
        print(net.line)
        print('\n')
        
        print('------- Display transformer elements (default) ------------')
        print(net.trafo)
        print('\n')
        print('################ End show network elements  ################### \n')
    
    return net.gen, net.sgen


def get_elements_res(net, is_display:bool):
    # res_bus = net.res_bus
    # res_sgen = net.res_sgen
    # res_trafo = net.res_trafo
    # res_load = net.res_load
    # res_line = net.res_line
    
    if is_display:
        print('################ Start show OPF results  ###################')
        print('------- Display bus elements (OPF results) ------------')
        print(net.res_bus)
        print('\n')
        
        print('------- Display generator elements (OPF results) ------------')
        print(net.res_gen)
        print('\n')
        
        print('------- Display static generator elements (OPF results) ------------')
        print(net.res_sgen)
        print('\n')
        
        print('------- Display load elements (OPF results) ------------')
        print(net.res_load)
        print('\n')
        
        print('------- Display line elements (OPF results) ------------')
        print(net.res_line)
        print('\n')
        
        print('------- Display transformer elements (OPF results) ------------')
        print(net.res_trafo)
        print('\n')
        
        print('################ End show OPF results  ################### \n')
    
    return net.res_gen, net.res_sgen

def show_gen_controll(net):
    diff_gen = net.gen- net.res_gen
    diff_sgen = net.sgen - net.res_sgen
    
    print('------- Display differences of gen power after OPF ------------')
    print(diff_gen[['p_mw', 'vm_pu']])
    
    print('------- Display differences of sgen power after OPF  ------------')
    print(diff_sgen[['p_mw', 'q_mvar']])

# def runopp(net):
#     # perform Power Flow calculation
#     pp.runopp(net, verbose=False, calculate_voltage_angles=True, check_connectivity=True, 
#                       suppress_warnings=True, switch_rx_ratio=2, delta=1e-3, init='flat',
#                       numba=True, trafo3w_losses='hv', consider_line_temperature=False)

#%% IEEE test case 24 bus
net = pn.case24_ieee_rts()
[gen, sgen] = get_elements(net, False)
pp.runopp(net)
[gen_opf, sgen_opf] = get_elements_res(net, False)
show_gen_controll(net)


#%% CIGRE MV network
# Medium voltage distribution network with PV and Wind DER
net = pn.create_cigre_network_mv(with_der="all")
add_poly_cost(net, False)
[gen, sgen] = get_elements(net, False)
pp.runopp(net)
[gen_opf, sgen_opf] = get_elements_res(net, False)
show_gen_controll(net)



#%% CIGRE network
# Low voltage distribution network --> no generator

net = pn.create_cigre_network_lv()
add_poly_cost(net, False)
[gen, sgen] = get_elements(net, False)
pp.runopp(net)
[gen_opf, sgen_opf] = get_elements_res(net, False)
show_gen_controll(net)



#%% Dickert LV Networks
# Low voltage distribution network --> no generator
net = pn.create_dickert_lv_network('middle', 'cable', 'multiple', 'good')
# add_poly_cost(net, False)
[gen, sgen] = get_elements(net, False)
pp.runopp(net)
[gen_opf, sgen_opf] = get_elements_res(net, False)
show_gen_controll(net)



