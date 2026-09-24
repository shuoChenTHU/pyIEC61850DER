## Build the vIED containers in batch for a large scale virtual simulation

A short instruction for preparing a virtual simulation with a batch of IEC 61850 compatible DER containers.

The ultimate objective of such a virtual simulation is to use the real-time IEC 61850 interface to represente DER 
communication between network operators and DER devices/controllers, and incorporating time-series data for 
quasi-static simulation.

Key components:
- (Optimal) power flow calculation with pandapower or other solver tools
- virtual container representing DER controller incl. config files
- data storage, either local or remote database (e.g. influxdb) incl. mapping onto the network model

Major working steps:
0. (optional) upload the data onto influxdb the influxdb interface will be used
	- The data uploader script is not a part of this project as the process highly depends on the data structure
    - We expect per bus node (each bus node is considered one PCC) exactly one IEC 61850 container; hence also 
	  exactly one set of data accordingly
    - Case 1: data search by unique (container) guid:
      - After the uploader process, at least one mapping table should be in presence to indicate the data location in 
        influxdb, e.g. the file named data_mapping.csv. 
      - This file must contain the columns filename, _measurement and guid
      - If one container requires multiple data sets from influxdb for Data Attributes at one particular node, this 
		approach would have very restricted application. This is because the container guid only help to find the 
		container but not the underlying data fields. In this case, inflxudb may return a list of data records, 
		without specifying the IEC 61850 MMS address, the influxdb interface will just naively take the first item 
		out of the list.
	- Case 2: data search by IEC 61850 address
      - If the data query is based on the IEC 61850 nomenclature, make sure you have a mapping table named
		iec61850_definition.csv, such that your data uploader will be capable of converting column names in the raw 
		data file into influxdb tags.
      - The container guid may still be required to allocate the node in influxdb
      - In the best case the data structure in influxdb meets the IEC 61850 definition, then such a 
		mapping file would not be necessary in the runtime virtual simulation.
      - If the uploaded data in influx do not preserve the IEC 61850 data structure, then the users must implement  
		parsing logics for the influxdb interface and for the runtime application.
    - After the data upload is accomplished, double check in your influxdb instance to make sure that the 
	  required data are indeed accessible
1. Preparing Network model 
	- Prepare the network model in pandapower
    - Make sure that the columns in the data files / data records from remote database can be uniquely identified by 
	  a bus node in the network model.
    - Multiple loads or generators per bus node is allowed, one would have to adjust the IEC 61850 data model 
	  accordingly.
2. Preparing time-series data
    - Prepare time-series data required for the simulation (i.e. load data and PV data), either as local data files 
	  in `./data/time_series/batch` or stored in an influxdb bucket (step 0)
    - For local data, each node is supposed to pose an individual CSV file, the column names may be some customised 
	  strings coming from the raw data; for the conversion into IEC 61850 jargons during the runtime virtual 
	  simulation, the file `iec61850_definition.csv` can be used again. The critical point is: one must adjust the 
	  items in `fieldbus_conn_config` accordingly for each associated row (DA).
    - To some extent, the columns in the raw data files need to be reorganised such that each new csv file contains 
	  only data of data attributes subject to one single bus node.
    - Node-wise aggregation is managed by `interface.calculator` depending on the defined function handler on the 
	  column `fieldbus_conn_config` in the lookup table.
    - Make sure the file data_mapping.csv is available and contains correct information.
3. Preparing DER data model
	- We use one data model and the associated lookup table as template. For each individual containers, only the 
	  configuration of data_source differ.
    - One must first generate the following files if not yet available using scripts in the module `./model`
      - IEC 61850 data model (the so-called SCL file)
      - lookup CSV (particularly the configuration of data_source)
	- If both the IEC 61850 data model and the lookup CSV are available, double-check the contents in the lookup CSV 
	  template; plenty of rows may need modification depending on the use case.
4. Create docker-compose files for the batch
	- If not specified, the Dockerfile, docker-compose.yaml and requirements.txt in `./container/build/linux` will 
	  be used as templates. It is recommended to configure your own docker-compose project.
	- Run `builder.py` to generate the docker-compose files for the current batch. For efficiency concerns, one
	  batch of containers can be split in small groups, per group one docker-compose.yaml.
	- It is not possible to directly change the lookup CSV once the docker image has been created. A 
	  workaround is to mount the config.yaml and the lookup CSV using the _volumn_ syntax in the docker-compose file.
5. Copy the docker project to the container platform and start containers
	- After everything has been successfully generated, copy all files to your platform
    - First start the builder, make sure everything is as expected, and the docker 
	  image is properly created, stop the builder container.
	- Then copy all grouped container files into the container software and start them all at once.
