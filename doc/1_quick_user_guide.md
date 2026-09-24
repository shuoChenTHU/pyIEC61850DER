## Quick user guide for the vIED on Windows OS

The configuration of the IEC 61850 virtual IED consists of the following steps:

### To configure a vIED server

0. Preparation work
    
   - Prepare your IEC 61850 data model (SCL file) along with a lookup table
   - If the lookup table is not yet available, it will be generated when starting the server for the first time
   - Prepare the data required for simulation (local csv files or influxdb data)
   - (when using a physical inverter) Prepare the modbus setting of the sunspec inverter for real-time communication
   
1. Configure IED hyper-parameters
   
   - open the `config.yaml` file declared in your `main.py` script, e.g. `'./settings/config.yaml'`
   - Check the entries of each section, refer to the inline comments for more details
   - Make sure you are using the right SCL file, sunspec mapping table, and the right lookup table.
   - If a physical inverter is planned, double-check the modbus TCP settings, it must be in the same network
   
2. Configure the lookup table
   
   For each data buffer instance (each row in the lookup table), as soon as it is supposed to be active, manually 
   configure the entries, which should not using default values. Whenever a dict type parameter (JSON tag) is 
   involved, use [this file](../pyiec61850der/settings/IEC61850_DA_lookup_mini_mega.csv) as a reference. For each 
   new key in the JSON dict, a method for the corresponding processing logic must be implemented as well.

   **_Explanation of all columns:_**

      | Parameter Name | Data Type | Description                                                                                    |
      |---|---|------------------------------------------------------------------------------------------------|
      | mms_addr | string | MMS address of the DO associated to the data buffer                                            |
      | monitor_da | string | MMS address of the monitor DA associated to the data buffer (maximal one)                      |
      | control_da | string | MMS address of the control DA associated to the data buffer (maximal one)                      |
      | data_source | string | The data source in real-time (disabled, local, influxdb, sunspec, random, number, calculation) |
      | fieldbus_conn_config | dict | A JSON tag for the communication partner in Home Area Network                                  |
      | conn_obj | Not configurable | A placeholder to store the python object for the HAN communication                             |
      | guid | Not configurable | Automatically generated GUID for this data buffer                                              |
      | is_monitor | bool | Should this DO be monitored?                                                                   |
      | is_control | bool | Should this DO be controlled?                                                                  |
      | limits | dict | Upper & lower bounds of the physical quantity                                                  |
      | rated_value | float / int | Rated value of the physical quantity, e.g. rated power                                         |
      | unit_factor | float / int | Scaling factor for unit conversion (e.g. required by sunspec)                                  |
      | scaling_factor | float / int | Scaling factor in addition to unit conversion                                                  |
      | unit | str | SI unit of the physical quantity                                                               |

3. If using `influxdb`, check its config in `./secret/influxdb.json` or another file as configured in `config.yaml`
4. Start the vIED server by executing `main.py`
5. Check the IEC 61850 server and data archive
   
   - use IEC 61850 client tools like IEDExplorer to connect to the running server and read data or send control
   - To verify the data after the simulation, check the local data archive in ./data/archive
   - or check time-series data stored in influxdb according to the config in `./secret/influxdb.json`

### To run a tester vIED server
You can execute the tester script to test some basic functions of this module.

Minimal example:
    
    ./tester/module_tests/minimal_example.py


To start an IEC 61850 server according to your configuration in `./tester/func_tests/config_tester.yaml`, use the other 
test script:

    ./tester/func_tests/ied_server_tester.py

which initialises the IEC 61850 server using the SCL data model.