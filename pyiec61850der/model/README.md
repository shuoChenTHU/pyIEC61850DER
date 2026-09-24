# IEC 61850 data model generator. More details: https://gitlab.com/thu_smartgrids/iec61850datamodelgenerator

This is the project for the Python toolchain "iec61850DataModelGenerator", which 
automatically generates a template-based IEC 61850 data model for DER.

The model contains almost all possible mandatory and optional Data Objects (DO). The next step
is the implementation of a role-based model reduction approach.

Currently, this python package is consisted of the following scripts:

- [iec61850DataTemplates.py](./iec61850DataTemplates.py): this script generates the default templates for DA, DO, LN and EnumKind types.

- [iec61850DataModelGenerator.py](./iec61850DataModelGenerator.py): this scripts builds the IEC 61850 data model according to an Excel file `config_IEC61850_model.xlsx` or a JSON config `config_JSON.json`.

- [templateCodeGenerator.py](./templateCodeGenerator.py): This is only a supporting script, it defines the to be considered LNs and DOs in each LN according to the Excel file `config_IEC61850_LN_DA.xlsx`.

This model is only a prototype, of course it came to the world with all kinds of limitations. Therefore, please attention to the following notes before using it:

    - we leave out the inlanding parameters, calculation relevant settings and test settings
    - no calculation and data transfer inside the data model
    - Beh, Mod, Health not specified, we don't play around with these settings. These nodes will be automatically created during model generation, as they are mandatory nodes, but they will not be listed in the matching table.
    - no use of mixed DER, if it is the case, consider them separately
    - emergency mode is not considered
    - Autorization and authentification provided by Smart-Meter-Infrastructure
    - All controllable resources are fully controllable
    - DER completely shut down will not be an option in our case, instead use Wmax and other settings to limit the active/reactive power. -> we do not actively connect or disconnect the DER to/from the grid
    - Over-/underexciting ratings and settings are not considered
    - switching between interconnected and not interconnected to the grid is not considered, assume that the DER is always interconnected
    - No autonomous operational functions -> we always assume that Mod.stVal = 1 (On), and Beh in LN also stays at 1
    - possibly reduce the usage of ORG and other reference parameters for simplicity
    - virtual power plant, aggregation is not yet considered (the LN DVER is not in use)
    - not strictly refering to the presece condition defined in IEC-61850
    - most of the DA in LN DINV could be replaced by the same ones in LN DGEN


To convert the generated SCL data model back to C codes, do the following things:
    
go to `./pyiec61850der/pyiec61850der/model/outputs`, find your SCL file and copy it to the model_generator folder of libiec61850: `<your local path>/pyiec61850der/pyiec61850der/linux/libiec61850-1.5.1/tools/model_generator `, then open cmd.

    cd .<your local path>/pyiec61850der/pyiec61850der/linux/libiec61850-1.5.1/tools/model_generator
    java -jar genmodel.jar <your SCL filename>
    java -jar genconfig.jar <your SCL filename> config.cfg

Afterwards, if everything goes well, you will get these 3 files added or updated, they should be ready to use for C application.

    - static_model.h
    - static_model.c
    - config.cfg