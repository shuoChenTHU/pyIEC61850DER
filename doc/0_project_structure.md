```
pyiec61850der\
├── communication  # Sub-module for IEC 61850 telecommunication
│   ├── README.md
│   ├── iec61850_dynamic_model_builder.py  # Build the IEC 61850 data model inside the IEC 61850 MMS server.
│   ├── pyiec61850_client.py  # Main program for creating IEC 61850 MMS client using the libIEC61850 server stack.
│   └── pyiec61850_server.py  # Main program for creating IEC 61850 MMS server using the libIEC61850 server stack.
├── container  # Sub-module for docker container configuration and batch generation
│   ├── README.md
│   ├── batch
│   ├── build
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   ├── docker-compose_mount.yml
│   │   └── requirements.txt
│   └── builder.py  # Build docker container configuration files in batch.
├── data  # Local time-series data pool and data archive
├── docker-compose.yml
├── interface  # Real-time communication and data processing interfaces
│   ├── README.md
│   ├── calculator.py  # Data processing logics for local data calculation inside the data buffers.
│   ├── data_buffer.py  # Definition of the DataBuffer class and its attributes, essential for the runtime functions.
│   ├── iec61850_da.py  # Definition of the IEC61850DA class for the IEC 61850 MMS DA objects.
│   ├── iec61850_do.py  # Definition of the IEC61850DO class for the IEC 61850 MMS DO objects.
│   ├── iec61850_mms.py  # Core functions for the data operations in terms of a real-time IEC 61850 MMS interface.
│   ├── influxdb.py  # Definition of the Influxdb Class and core functions for the influxdb interface.
│   ├── interface_SunSpec.xlsx
│   ├── interface_SunSpec_export.xlsx
│   ├── interface_SunSpec_export_0.xlsx
│   ├── local.py  # Local data processing based on the TimeSeries class.
│   ├── number.py  # Initialise data buffer instances with dummy data for test purpose.
│   ├── randomisor.py  # Initialise data buffer instances with random data for test purpose.
│   ├── runtime.py  # Supporting functions for runtime data processing routines.
│   ├── sunspec.py  # Real-time functions for the Sunspec - IEC 61850 interface, incl. a Sunspec client.
│   └── time_series.py  # Definition of TimeSeries and Record classes for the handling of time-series data.
├── logs  # loggers will write log files here!
├── main.py  # Main program of the virtual IED for real-time simulation or emulation.
├── model  # IEC 61850 data model generator. More details: https://gitlab.com/thu_smartgrids/iec61850datamodelgenerator
├── network  # pandapower networks for real-time testing
│   ├── OPF_tester.py  # A test script to validate the OPF results.
│   ├── README.md
│   ├── demo_100nodes.py  # A 100-node test network for simple tests.
│   └── demo_network.py  # A dummy network for test purpose.
├── pylibiec61850  # A collection of available libIEC61850 python bindings
│   ├── README.md
│   ├── __init__.py
│   ├── linux  # A placeholder for the linux python binding of libIEC61850 stack
│   ├── source  # Source library of the libIEC61850 python binding
│   └── windows  # A placeholder for the windows python binding of libIEC61850 stack
├── secret  # Sub-folder for storing confidential information, e.g. influxdb tokens
│   ├── README.md
│   ├── influxdb.json
│   └── influxdb_template.json
├── settings  # Submodule for the configuration of the vIED runtime service
│   ├── IEC61850_DA_lookup_demoAutoGenCLS.csv  # returned by pyiec61850_server.py containing a parameter lookup table
│   ├── IEC61850_DA_lookup_miniPV.csv
│   ├── IEC61850_DA_lookup_mini_mega.csv
│   ├── IEC61850_DA_lookup_tester_DER_comprehensive.csv
│   ├── IEC61850_DA_lookup_tester_DER_mini.csv
│   ├── IEC61850_DA_lookup_tester_DER_slim.csv
│   ├── IEC61850_DA_lookup_tester_DER_slim2.csv
│   ├── IEC61850_da_guid_virtualCLSmini.csv  # returned by pyiec61850_server.py containing the GUIDs
│   ├── README.md
│   ├── config.py  # Definition of the class IedConfig and core functions for config file I/O
│   ├── config.yaml
│   ├── helper.py  # General helper functions for all submodules.
│   └── third_party.py  # Storage of functions and implementations provided by a third party.
├── simulation  # Submodule for the real-time operation of the vIED
│   ├── README.md
│   ├── pandapower61850  # pandapower61850
│   ├── runtime_manager.py  # Definition of two runtime-relevant classes TimeManager and IedManager
│   ├── virtual_ied.py  # Main module for the organisation of core real-time function blocks and thread workers.
│   └── virtual_scada_old.py  # A deprecated python script that simulates a virtual SCADA.
└── tester  # Submodule for tester scripts.
    ├── README.md
    ├── func_tests
    │   ├── config_tester.yaml
    │   ├── ied_client_tester.py  # A test script for structured testing on the IED client side
    │   ├── ied_client_tester_old.py  # A deprecated test script for structured testing on the IED client side
    │   ├── ied_server_tester.py  # A test script for structured testing on the IED server side
    │   ├── ied_server_tester_old.py  # A deprecated test script for structured testing on the IED server side
    │   ├── lookup_mpc.csv
    │   ├── sunspec_tester.py  # A tester script for sunspec functions.
    │   └── vIED_function_tester_old.py  # A deprecated testing script for some core functions, no longer in deployment.
    └── module_tests
        ├── cprofile_tester.py  # A tester script to perform a profiling of the vIED to detect performance bottlenecks.
        ├── minimal_example.py  # A minimal example of the IEC 61850 server for test purpose.
        ├── pyiec61850_function_tester.py  # A dummy test script for simple functional testing of the libIEC61850 python binding
        └── pyiec61850_import_tester.py  # This testing script can be used in the docker container to locate module import errors.
```
