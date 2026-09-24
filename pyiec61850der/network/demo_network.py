# -*- coding: utf-8 -*-
"""
A dummy network for test purpose.
"""


import pandapower as pp
import pandapower.networks
import pandapower.topology
import pandapower.plotting
import pandapower.converter
import pandapower.estimation


#%% test kerber networks
import pandapower.networks as pn


net1 = pn.create_kerber_landnetz_freileitung_1()
net2 = pn.create_kerber_landnetz_freileitung_2()
net3 = pn.kb_extrem_dorfnetz_trafo()
net = pn.case118()

res = pp.run.runpp(net1)


net = pp.create_empty_network() 
b1 = pp.create_bus(net, vn_kv=20.)
b2 = pp.create_bus(net, vn_kv=20.)
pp.create_line(net, from_bus=b1, to_bus=b2, length_km=2.5, std_type="NAYY 4x50 SE")   
pp.create_ext_grid(net, bus=b1)
pp.create_load(net, bus=b2, p_mw=1.)




import pandapower as pp
#create empty net
net = pp.create_empty_network() 

#create buses
b1 = pp.create_bus(net, vn_kv=20., name="Bus 1")
b2 = pp.create_bus(net, vn_kv=0.4, name="Bus 2")
b3 = pp.create_bus(net, vn_kv=0.4, name="Bus 3")

#create bus elements
pp.create_ext_grid(net, bus=b1, vm_pu=1.02, name="Grid Connection")
pp.create_load(net, bus=b3, p_mw=0.1, q_mvar=0.05, name="Load")

#create branch elements
tid = pp.create_transformer(net, hv_bus=b1, lv_bus=b2, std_type="0.4 MVA 20/0.4 kV", name="Trafo")
pp.create_line(net, from_bus=b2, to_bus=b3, length_km=0.1, name="Line",std_type="NAYY 4x50 SE") 
pp.run.runpp(net)
pp.run.runopp(net)

#%% state estimation

net = pp.create_empty_network()
b1 = pp.create_bus(net, vn_kv=220)
b2 = pp.create_bus(net, vn_kv=220)
pp.create_ext_grid(net, bus = b1, vm_pu=1)
l1 = pp.create_line_from_parameters(net,from_bus=b1, to_bus=b2, length_km=1, r_ohm_per_km=0, x_ohm_per_km=100, c_nf_per_km=0, max_i_ka= 1)

pp.create_measurement(net, meas_type= "p", element_type= "line", value= 155, std_dev= 1, element=l1, side = b1)
pp.create_measurement(net, meas_type= "q", element_type= "line", value= 22, std_dev= 1, element=l1, side = b1)
pp.create_measurement(net, meas_type= "v", element_type= "bus", value= 210/220, std_dev= 1/220, element=b2)
net.measurement

res = pp.estimation.estimate(net, init= "flat", algorithm= "wls")