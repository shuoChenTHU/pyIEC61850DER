# -*- coding: utf-8 -*-
"""
Created on Tue Apr 19 09:15:26 2022

@author: chen
"""

# TODO: add some general documentation here
"""
Doc xxxx

"""

# standard python libs
import xmltodict
from collections import OrderedDict
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import logging

# project relevant libs
import model.iec61850DataTemplates as iec61850DataTemplates
from settings.helper import rotating_logger


# TODO: No except handling is implemented, for this moment it is not necessary. As the scope grows, consider using
#  explicit exception handlers to catch errors.
# TODO: consider use some unittest to reduce error
# TODO: implement __repr__() and __str__() in all classes
# TODO: consider turn some of the attributes in the classes into properties and implement setter, getter and deleter

"""
###############################################################################
#############   Pre-Configuration and function declaration   ##################
###############################################################################
"""

from settings.helper import rotating_logger
logger = rotating_logger(__name__)

class IEC61850DataModelGenerator(object):
    """ The entire framework is defined as a class """

    def __init__(self, pathConfigFile=None, nameIED=None, nameExportFile=None):
        """
        Initialize the class
            Input:
                - pathConfigFile: the config file (most likely an Excel table) containing the data model selection

            Output:
                - one SCL file (in XML format) in the project directory
        """

        # create an empty class to store important configuration variables
        class Config:
            pathConfigFile = None
            nameIED = None
            pathOutputSCL = None
            apName = 'processLabSGFG'
            nameExportFile = None
            dictListDER = {'PV': ['PV'], 
                          'LOAD': ['LOAD'],
                          'STO': ['STO'],
                          }

        class Templates:
            DOTemplates = None
            DATemplates = None
            LNTemplates = None
            EnumTemplates = None
            
        class DataModel:
            dictModelTopo = None  # this dict will be a normal Python dictionary, not OrderedDict!
            dictDS = OrderedDict()
            dictRCB = OrderedDict()

        self.Config = Config
        self.Templates = Templates
        self.DataModel = DataModel

        self.Config.nameIED = nameIED
        self.Config.pathConfigFile = pathConfigFile
        if not nameExportFile:
            logger.info('File name of export SCL not given, use current time and IED name to construct export file name')
            self.Config.nameExportFile = '{}_{}.cid'.format(datetime.now().strftime('%Y-%m-%dT%H%M%S'), nameIED)
        else:
            self.Config.nameExportFile = nameExportFile  # use the extension .cid for the first draft
        self.Config.pathOutputSCL = f'./model/outputs/{self.Config.nameExportFile}' # for debugger: this fixed working dir could be a bug maker
        self.dictOutputSCL = OrderedDict()

    """
    ###############################################################################
    #################  Define methods for dynamic modelling  ######################
    ###############################################################################
    
    As the IEC 61850 objects will be called dynamically in other functions, it's hard to add too much dynamics to the
    dictionary structure itself, therefore we try to keep the structure for these classes consistent, to preserve
    unified topology in the IEC61850 modelling context. 
    This means, directly using a method to create OrderedDict storing information, reserve spaces for unknown
    information with None. 
    """

    # TODO: check if it could be better to use classes and instances representing LD and LN, I suppose not!

    # noinspection PyMethodMayBeStatic
    def createDictLD(self, inst=None, dictLN0=None, listDictLN=None):
        """
        This function takes following input parameters, build an Ordered dict for one LD and return it as output
            Input:
                - inst: instance of the LD, i.e. LD name in the IEC 61850 data model
                - dictLN0: dictionary representing the structure of LN LLN0, each LD must have one and only one LLN0
                - listDictLN: a list containing the dictionary of other LNs in this LD, it could also be one
            Output:
                - ld_model: the dictionary that represents the data structure of the LD
        """

        dictLD = OrderedDict([('@inst', inst),
                              ('LN0', dictLN0),
                              ('LN', listDictLN),
                              ])
        return dictLD

    # noinspection PyMethodMayBeStatic
    def createDictLLN0(self, lnType=None, desc=None, listDictDS=None, listDictRPT=None, **kwargs):
        """
        This function takes following input parameters, build an Ordered dict for the LN LLN0 and return it as output
            Input:
                - lnType: type of the LN, if not specified, the method takes the default type LLN0_0
                - desc: description of the LN
                - listDictDS: a list containing the dictionary of Data Sets for one LD, it could also be one or empty
                - listDictRPT: a list containing the dictionary of Reports for one LD, it could also be one or empty
            Output:
                - dictLLN0: the dictionary that represents the data structure of LLN0
        """
        if not lnType:
            lnType = 'LLN0_0'
        if not desc:
            desc = ''  # just leave it empty
        dictLLN0 = OrderedDict([('@desc', desc),
                                ('@inst', ''),  # assuming LLN0 always has empty instance
                                ('@lnType', lnType),
                                ('@lnClass', 'LLN0'),  # this is fixed, can not be other values
                                ])
        if listDictDS is not None:
            dictLLN0['DataSet'] = listDictDS
        if listDictRPT is not None:
            dictLLN0['ReportControl'] = listDictRPT

        # TODO: check if there is any other possible kwargs

        return dictLLN0

    # noinspection PyMethodMayBeStatic
    def createDictLN(self, lnClass=None, lnType=None, desc=None, inst=None, prefix=None, **kwargs):
        """
        This function takes following input parameters, build an Ordered dict for the LN LLN0 and return it as output
            Input:
                - lnType: type of the LN, if not specified, the method takes the default type LLN0_0
                - inst: instance of the LN, usually left empty
                - desc: description of the LN
            Output:
                - dictLLN0: the dictionary that represents the data structure of LLN0
        """

        if not lnClass:
            logger.error('Value of "lnClass" shall not be empty, double-check the inputs or change it manually')
            lnClass = ''  # just leave it empty, but it has to be changed
        if not lnType:
            lnType = '{}_0'.format(lnClass)  # if not specified, take the default lnType from template
        if not desc:
            desc = ''  # just leave it empty
        if not inst:
            # TODO: add a function to record the numbers of LN with the same lnType and change the inst, maybe not here
            logger.error('Value of "inst" shall not be empty, double-check the inputs or change it manually')
            inst = ''  # just leave it empty, but it has to be changed
        if not prefix:
            prefix = ''  # just leave it empty
        dictLN = OrderedDict([('@desc', desc),
                              ('@inst', inst),
                              ('@lnType', lnType),
                              ('@lnClass', lnClass),
                              ('@prefix', prefix),
                              ])

        # TODO: check if there is any other possible kwargs
        # TODO: check if it is required to define DOI, SDI, DAI and Val at this step

        return dictLN

    # TODO: add RPT and DS later

    def createDictDS(self, dictLD):
        """
        This function takes the dictionary of a LD as input and build the DataSets based on it.
        Note that all DS are stored in the LN LLN0.
        Here we make use of the <DO Template>.listFC provided by the method DOType.organizeDictDO.

        TODO: check if this is a good approach
        TODO: consider categorizing the DA according to use case (e.g. operation, eco, ...)
        TODO: or divide huge DS into sub-DS, each has an index
        Principles:
            - per LN a set of DS
            - Parameter of the same fc type in one DS
            - Naming convention: <LD>_<fc>_<LN/ALL>
            - Divide the Datasets into the following categories
                * per LD one <LD>_ST_General (containing Beh, Health, loc and other general DA)
                * per LD one <LD>_ST_ALL (containing all other status DA)
                * per LD one <LD>_DC_ALL (containing all descriptive DA)
                * per LD one <LD>_CF_ALL (containing all configuration DA)
                * per LN one <LD>_MX_<LN> (containing all measured values from that LN)
                * per LN one <LD>_SP_<LN> (containing all settings from that LN)
            - the following DA/SDA shall be excluded:
                * Unit
                * d

            Input:
                - ld_model: a dictionary representing the topology of a LD
            Output:
                - ld_model: a updated dictionary containing DataSets
        """

        # TODO: some methods are required to decide which DA shall be included, otherwise the model size will explode
        #   using something like a JSON file might be an option
        # TODO: the codes in this function are not good, repeating all the time. Find a way to reconstruct

        # TODO: prepare a list for excluding specific DO
        listDOGeneral = ['Beh', 'Health', 'Loc', 'LocKey']  # general DO refers to ST type
        listDOExcluded = []  # this is only a place_holder, update it based on practical experience

        nameLD = dictLD['@inst']
        self.DataModel.dictDS[nameLD]['listDS'] = []  # make a list to store the DS in this LD

        listDictDS = []  # initialize an empty list to store all DS
        dict_ST_General = OrderedDict([('@name', '{}_ST_General'.format(nameLD)),
                                       ('fcda', []),  # init a list and add DO latter
                                       ])
        dict_ST_ALL = OrderedDict([('@name', '{}_ST_ALL'.format(nameLD)),
                                   ('fcda', []),  # init a list and add DO latter
                                   ])
        dict_DC_ALL = OrderedDict([('@name', '{}_DC_ALL'.format(nameLD)),
                                   ('fcda', []),  # init a list and add DO latter
                                   ])
        dict_CF_ALL = OrderedDict([('@name', '{}_CF_ALL'.format(nameLD)),
                                   ('fcda', []),  # init a list and add DO latter
                                   ])

        # starting with LLN0
        # TODO: the codes for LLN0 are more or less duplicated, consider generalize them
        dictLLN0 = dictLD['LN0']
        for DO in self.Templates.LNTemplates.__dict__[dictLLN0['@lnType']].dict['DO']:
            typeDO = DO['@type']
            listFC = self.Templates.DOTemplates.__dict__[typeDO].listFC
            dictFCDA = OrderedDict([('@doName', DO['@name']),
                                    ('@fc', None),
                                    ('@ldInst', nameLD),
                                    ('@lnClass', dictLLN0['@lnClass'])
                                    ])
            if DO['@name'] in listDOExcluded:
                continue
            elif DO['@name'] in listDOGeneral:
                dictFCDA['@fc'] = 'ST'
                dict_ST_General['fcda'].append(dictFCDA.copy())
            else:
                if 'CF' in listFC:
                    dictFCDA['@fc'] = 'CF'
                    dict_CF_ALL['fcda'].append(dictFCDA.copy())
                if 'DC' in listFC:
                    dictFCDA['@fc'] = 'DC'
                    dict_DC_ALL['fcda'].append(dictFCDA.copy())
                if 'ST' in listFC:
                    dictFCDA['@fc'] = 'ST'
                    dict_ST_ALL['fcda'].append(dictFCDA.copy())

        # Then proceed to all other LNs in the LD
        for dictLN in dictLD['LN']:
            nameDS = '{}_MX_{}{}{}'.format(nameLD, dictLN['@prefix'], dictLN['@lnClass'], dictLN['@inst'])
            dict_MX_LN = OrderedDict([('@name', nameDS),
                                      ('fcda', []),  # init a list and add DO latter
                                      ])
            nameDS = '{}_SP_{}{}{}'.format(nameLD, dictLN['@prefix'], dictLN['@lnClass'], dictLN['@inst'])
            dict_SP_LN = OrderedDict([('@name', nameDS),
                                      ('fcda', []),  # init a list and add DO latter
                                      ])
            for DO in self.Templates.LNTemplates.__dict__[dictLN['@lnType']].dict['DO']:
                typeDO = DO['@type']
                listFC = self.Templates.DOTemplates.__dict__[typeDO].listFC
                dictFCDA = OrderedDict([('@doName', DO['@name']),
                                        ('@fc', None),
                                        ('@ldInst', nameLD),
                                        ('@lnClass', dictLN['@lnClass']),
                                        ('@lnInst', dictLN['@inst']),
                                        ('@prefix', dictLN['@prefix'])
                                        ])
                if DO['@name'] in listDOExcluded:
                    continue
                elif DO['@name'] in listDOGeneral:
                    dictFCDA['@fc'] = 'ST'
                    dict_ST_General['fcda'].append(dictFCDA.copy())
                else:
                    if 'CF' in listFC:
                        dictFCDA['@fc'] = 'CF'
                        dict_CF_ALL['fcda'].append(dictFCDA.copy())
                    if 'DC' in listFC:
                        dictFCDA['@fc'] = 'DC'
                        dict_DC_ALL['fcda'].append(dictFCDA.copy())
                    if 'ST' in listFC:
                        dictFCDA['@fc'] = 'ST'
                        dict_ST_ALL['fcda'].append(dictFCDA.copy())
                    if 'MX' in listFC or 'SDO' in listFC:
                        # TODO: assume DO containing SDO are of MX types (e.g. DEL, WYE has CMV), this might be wrong
                        dictFCDA['@fc'] = 'MX'
                        dict_MX_LN['fcda'].append(dictFCDA.copy())
                    if 'SP' in listFC:
                        dictFCDA['@fc'] = 'SP'
                        dict_SP_LN['fcda'].append(dictFCDA.copy())

            if dict_MX_LN['fcda']:
                listDictDS.append(dict_MX_LN)
                self.DataModel.dictDS[nameLD]['listDS'].append(dict_MX_LN)
            if dict_SP_LN['fcda']:
                listDictDS.append(dict_SP_LN)
                self.DataModel.dictDS[nameLD]['listDS'].append(dict_SP_LN)
        if dict_ST_General['fcda']:
            listDictDS.append(dict_ST_General)
            self.DataModel.dictDS[nameLD]['listDS'].append(dict_ST_General)
        if dict_ST_ALL['fcda']:
            listDictDS.append(dict_ST_ALL)
            self.DataModel.dictDS[nameLD]['listDS'].append(dict_ST_ALL)
        if dict_CF_ALL['fcda']:
            listDictDS.append(dict_CF_ALL)
            self.DataModel.dictDS[nameLD]['listDS'].append(dict_CF_ALL)
        if dict_DC_ALL['fcda']:
            listDictDS.append(dict_DC_ALL)
            self.DataModel.dictDS[nameLD]['listDS'].append(dict_DC_ALL)

        # add the DS list to ld_model['LN0']
        dictLD['LN0']['DataSet'] = listDictDS

        return dictLD

    def createDictRCB(self, dictLD):
        """
        This function takes the dictionary of a LD as input and build the RCB based on the DS.
        Note that all RCB are stored in the LN LLN0.
        Here we define the RCB configuration based on the fc of the included DA.

        # TODO: check if this is a feasible approach

        RCB types (fc types):
            - MX: measurements, most frequently transmitted, transmisstion by integrity
            - ST: status, less often transmitted, update on data change/ quality change
            - SP: control settings, update only on data change/ quality change
            - DC: Description, initial read, then only update on data change
            - CF: Configuration, initial read, then only update on data change

        Default integrity period 10 seconds for MX, 900 seconds for ST
        Principles:
                    intgPd      dchg        dupd        gi          period      qchg
            MX      10000       false       true        false       true        false
            ST      900000      true        true        false       false       true
            SP      1440000     true        true        false       false       true
            DC      99999999    true        true        false       false       true
            CF      99999999    true        true        false       false       true

            Input:
                - ld_model: a dictionary representing the topology of a LD
            Output:
                - ld_model: a updated dictionary containing Report Control Blocks
        """

        # active all optional fields, let the client side decide what to transmit
        # set RptEnabled to 3, allow max. 3 active RPT connections
        dictRCBTemplate = OrderedDict([('@confRev', 1),
                                       ('@datSet', None),
                                       ('@intgPd', None),
                                       ('@name', None),
                                       ('@rptID', None),
                                       ('TrgOps', OrderedDict([('@dchg', 'false'),
                                                               ('@dupd', 'false'),
                                                               ('@gi', 'false'),
                                                               ('@period', 'false'),
                                                               ('@qchg', 'false'),
                                                               ])),
                                       ('OptFields', OrderedDict([('@configRef', 'true'),
                                                                  ('@dataRef', 'true'),
                                                                  ('@dataSet', 'true'),
                                                                  ('@entryID', 'true'),
                                                                  ('@reasonCode', 'true'),
                                                                  ('@seqNum', 'true'),
                                                                  ('@timeStamp', 'true'),
                                                                  ])),
                                       ('RptEnabled', 3),
                                       ])

        nameLD = dictLD['@inst']
        listDictRCB = []  # initialize an empty list to store all RCB
        listDS = self.DataModel.dictDS[nameLD]['listDS']
        self.DataModel.dictRCB[nameLD]['listRCB'] = []
        # TODO: find a better way to determine the DS/RCB name and ID
        for DS in listDS:
            nameDS = DS['@name']
            dictRCB = dictRCBTemplate.copy()
            dictRCB['@datSet'] = nameDS  # DataSet name
            dictRCB['@name'] = nameDS  # use DataSet name as Report name
            dictRCB['@rptID'] = 'RCB_{}'.format(nameDS)  # RCB_ + dataset name
            if 'MX' in nameDS:
                dictRCB['@intgPd'] = 10000
                dictRCB['TrgOps']['@dupd'] = 'true'
                dictRCB['TrgOps']['@period'] = 'true'
            elif 'ST' in nameDS:
                dictRCB['@intgPd'] = 900000
                dictRCB['TrgOps']['@dupd'] = 'true'
                dictRCB['TrgOps']['@dchg'] = 'true'
                dictRCB['TrgOps']['@qchg'] = 'true'
            elif 'SP' in nameDS:
                dictRCB['@intgPd'] = 1440000
                dictRCB['TrgOps']['@dupd'] = 'true'
                dictRCB['TrgOps']['@dchg'] = 'true'
                dictRCB['TrgOps']['@qchg'] = 'true'
            elif 'DC' in nameDS or 'CF' in nameDS:
                dictRCB['@intgPd'] = 99999999
                dictRCB['TrgOps']['@dupd'] = 'true'
                dictRCB['TrgOps']['@dchg'] = 'true'
                dictRCB['TrgOps']['@qchg'] = 'true'
            else:
                logger.warning('Dataset {} has an unknown type, cannot proceed, \
                               RCB will have invalid configuration'.format(nameDS))

            listDictRCB.append(dictRCB)
            self.DataModel.dictRCB[nameLD]['listRCB'].append(dictRCB)

        # add the RCB list to ld_model['LN0']
        dictLD['LN0']['ReportControl'] = listDictRCB

        return dictLD

    """
    ###############################################################################
    #################  Dynamically generate the data model  #######################
    ###############################################################################
    """

    def parseConfigFile(self):
        """ Load the config file and get the desired data model structure """

        # TODO: consider enable the initialization of model topology by JSON file
        # TODO: consider combine the config file and JSON file
        # TODO: role-based model reduction must be implemented later

        dfModel = pd.read_excel(self.Config.pathConfigFile, sheet_name='data_model_config')
        listLN = list(dfModel['LN'])
        listPrefix = list(dfModel['Prefix'])
        listLD = list(dfModel['LD'])

        # Filter the LN and LD, only keep rows that have val for LD and LN
        listValidIdx = [idx for idx, val in enumerate(list(dfModel['LN'].isnull()) or list(dfModel['LD'].isnull())) if
                        not val]

        # reconstruct prefix
        for idx, val in enumerate(listPrefix):
            if type(val) is not str:
                listPrefix[idx] = ''
            elif '_' in val:
                listPrefix[idx] = listPrefix[idx].strip('_')

        # build list of Logical Device and store the info in a dictionary
        listLDUnique = list(set(listLD))
        listLDUnique.remove(np.nan)
        # TODO: here a normal dict is used instead of an OrderedDict, check if this could be an issue
        dictModelTopo = dict()
        for LD in listLDUnique:
            dictModelTopo[LD] = []
            listLNInLD = list(
                set(['{}_{}'.format(listPrefix[idx], listLN[idx]) for idx in listValidIdx if listLD[idx] == LD]))
            for item in listLNInLD:
                [prefix, ln] = item.split('_')
                dictModelTopo[LD].append({'prefix': prefix,
                                          'nameLN': ln
                                          })
            # TODO: here a place_holder for createDS and createRPT
        self.DataModel.dictModelTopo = dictModelTopo
    
    def updateModelTopo(self, configYAML=None):
        """
        This method can be used to update the IED topology based on e.g. contents of the global YAMl config file.
        This possiblity is essential when it comes to complicated IED data model with more than 1 PV/LOAD/STO.
        
        According to the configuration, the default LD for PV/LOAD/STO will be deleted or renamed or duplicated with extending LD names.
        Before calling this method, make sure that the 
        """
        
        if configYAML is None:
            logger.warning('YAML config file is empty, can not proceed, no change in the IED topology will be made.')
        elif type(configYAML) is not dict:
            logger.warning('YAML config has unknown type, can not proceed, no change in the IED topology will be made.')
        else:
            for key in ['PV', 'LOAD', 'STO']:
                listUpdate = [item for item in configYAML if key in item]
                if len(listUpdate) > 0:
                    for item in listUpdate:
                        self.DataModel.dictModelTopo[item] = self.DataModel.dictModelTopo[key]
                    self.DataModel.dictModelTopo.pop(key)
                    self.Config.dictListDER[key] = listUpdate
                
    def genSCL(self):
        """
        Generate the entire "SCL" dictionary.
        Nothing charming here, just take the standard XML section and use it as a static template here.
        """

        dictSCL = OrderedDict([('@xmlns', 'http://www.iec.ch/61850/2003/SCL'),
                               ('@xmlns:xsd', 'http://www.w3.org/2001/XMLSchema'),
                               ('@xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance'),
                               ('@revision', 'B'),
                               ('@version', '2007'),
                               ('@xsi:schemaLocation', 'http://www.iec.ch/61850/2003/SCL SCL.xsd')
                               ])
        self.dictOutputSCL["SCL"] = dictSCL

    def genHeader(self):
        """
        Generate the "Header" dictionary.
        Nothing charming here, just take the standard XML section and use it as a static template here.
        """

        dictHeader = OrderedDict([('@id', '0'),
                                  ('@version', "3"),  # make this dynamic later
                                  ])
        self.dictOutputSCL["SCL"]["Header"] = dictHeader

    def genCommunication(self):
        """
        Generate the "Header" dictionary.
        It is based on a standard XML section, use it as a static template here and change some import configuration.
        Things to be modified (most likely coming from the config Excel file):
              - IP
              - IP-SUBNET
              - IP-GATEWAY
              - MAC-Address
        """
        # TODO: read the settings from the config file and make them dynamic here

        dictP = list([OrderedDict([('@type', 'OSI-AP-Title'),
                                   ('#text', '1,1,9999,1')]),
                      OrderedDict([('@type', 'OSI-AE-Qualifier'),
                                   ('#text', '12')]),
                      OrderedDict([('@type', 'OSI-PSEL'),
                                   ('#text', '00000001')]),
                      OrderedDict([('@type', 'OSI-SSEL'),
                                   ('#text', '0001')]),
                      OrderedDict([('@type', 'OSI-TSEL'),
                                   ('#text', '0001')]),
                      OrderedDict([('@type', 'IP'),
                                   ('#text', '192.168.168.168')]),
                      OrderedDict([('@type', 'IP-SUBNET'),
                                   ('#text', '255.255.255.0')]),
                      OrderedDict([('@type', 'IP-GATEWAY'),
                                   ('#text', '192.168.168.1')]),
                      OrderedDict([('@type', 'MAC-Address'),
                                   ('#text', '00-01-02-03-04-05')])
                      ])

        dictConnectedAP = OrderedDict([('@apName', self.Config.apName),  # apName must be the same as in the IED
                                       ('@iedName', self.Config.nameIED),  # iedName must be the same as in the IED
                                       ('Address', OrderedDict([('P', dictP)]))
                                       ])
        dictSubNetwork = OrderedDict([('@name', 'processTHU'),
                                      ('ConnectedAP', dictConnectedAP)
                                      ])
        dictCommunication = OrderedDict([('SubNetwork', dictSubNetwork)])
        self.dictOutputSCL["SCL"]["Communication"] = dictCommunication

    def initDataTypeTemplates(self):
        """ Init the Templates, store them in the function class for further use """

        [EnumTemplates, DATemplates, DOTemplates, LNTemplates] = iec61850DataTemplates.genIEC61850Templates()
        self.Templates.DATemplates = DATemplates
        self.Templates.DOTemplates = DOTemplates
        self.Templates.LNTemplates = LNTemplates
        self.Templates.EnumTemplates = EnumTemplates

    def genDataTypeTemplates(self):
        """
        Generate the "Header" dictionary. Everything will be automatically generated by the script
        iec61850DataTemplates.py and returned as instances.
        For instances will be needed here, and they must be added following this order:
            - LNTemplates
            - DOTemplates
            - DATemplates
            - EnumTemplates
        Each of them contains several templates as attributes, generate a list of them using the following syntax:
            listAttributes = LNTemplates.__dict__.keys()
        In case needed for debugging, this allows you to iterate through all attributes and get the dictionaries:
                for item in listAttributes:
                    dictLN = LNTemplates.__dict__[item].dict
        Nothing charming here, just take the standard XML section and use it as a static template here.
        """

        # init the dictionary
        dictDataTypeTemplates = OrderedDict()
        # Theoretically one can iterate these for class instances in a loop. But there are only four of them, so we
        # handle them one by one to make the structure more clear

        # add LNTemplates to the data model
        listNameLN = self.Templates.LNTemplates.__dict__.keys()
        listDictLN = []
        for item in listNameLN:
            dictLN = self.Templates.LNTemplates.__dict__[item].dict
            listDictLN.append(dictLN)
        dictDataTypeTemplates['LNodeType'] = listDictLN

        # add DOTemplates to the data model
        listNameDO = self.Templates.DOTemplates.__dict__.keys()
        listDictDO = []
        for item in listNameDO:
            # TODO: I decided to keep the PseudoEnumKind in the data model, just to avoid validation error.
            #   A method is needed to pass the correct EnumType (e.g. the schedules) to the DO accordingly.
            # if item not in ['ENC_0', 'ENG_0', 'ENS_0']:  # dump the Enum template with PseudoEnumKind
            dictDO = self.Templates.DOTemplates.__dict__[item].dict
            listDictDO.append(dictDO)
        dictDataTypeTemplates['DOType'] = listDictDO

        # add DATemplates to the data model
        listNameDA = self.Templates.DATemplates.__dict__.keys()
        listDictDA = []
        for item in listNameDA:
            dictDA = self.Templates.DATemplates.__dict__[item].dict
            listDictDA.append(dictDA)
        dictDataTypeTemplates['DAType'] = listDictDA

        # add EnumTemplates to the data model
        listNameEnum = self.Templates.EnumTemplates.__dict__.keys()
        listDictEnum = []
        for item in listNameEnum:
            dictEnum = self.Templates.EnumTemplates.__dict__[item].dict
            listDictEnum.append(dictEnum)
        dictDataTypeTemplates['EnumType'] = listDictEnum

        self.dictOutputSCL["SCL"]["DataTypeTemplates"] = dictDataTypeTemplates

    def genIED(self):
        """ Generate the "IED" dictionary based on the topology of the dictionary dictModelTopo """

        # prepare the "IED" dictionary, update Services and AccessPoint later
        # TODO: make "manufacturer", "name", "type" dynamic later
        dictIED = OrderedDict([('@manufacturer', 'THU_SGFG'),
                               ('@name', self.Config.nameIED),
                               ('@type', 'demoType'),
                               ('Services', None),
                               ('AccessPoint', None),
                               ])
        # prepare the "Services" sub-dictionary
        # TODO: check if the dictionary Services should include more parameters
        dictServices = OrderedDict([('@nameLength', 64),
                                    ('ClientServices', None),
                                    ])
        dictIED['Services'] = dictServices

        # prepare the "AccessPoint" sub-dictionary, update Server later
        # TODO: check if the dictionary AccessPoint should include more parameters
        dictAccessPoint = OrderedDict([('@name', self.Config.apName),
                                       ('@router', 'false'),
                                       ('Server', None),
                                       ])
        dictServer = OrderedDict([('@timeout', 30),
                                  ('Authentication', None),  # TODO: check if any authentication is necessary
                                  ('LDevice', None),  # update the LDevice list dynamically
                                  ])

        # Now we use the dict built by the method parseConfigFile to dynamically create DO and underlying LN
        listDictLD = []
        if self.DataModel.dictModelTopo is None:
            logger.error('Dictionary of model topology is empty, cannot proceed')
        else:
            # TODO: here we assume each LN type only occur once, which is definitely not the reality
            #   consider implementing a method to enable multiple LN of the same type
            listLDKeys = list(self.DataModel.dictModelTopo.keys())  # get a list of all LD
            # prepare for Datasets and Reports
            for key in listLDKeys:
                self.DataModel.dictDS[key] = OrderedDict()
                self.DataModel.dictRCB[key] = OrderedDict()

            # Iterate through all LDs and generate the default topology
            for key in listLDKeys:  # for each LD get the list of LN
                listLNinLD = []
                dictLLN0 = None
                for item in self.DataModel.dictModelTopo[key]:
                    prefix = item['prefix']
                    if prefix != '':
                        prefix = prefix + '_'  # add the _ to the prefix as separator
                    typeLN = item['nameLN']  # TODO: this might be confusing, unify the usage of type and name
                    if typeLN == 'LLN0':
                        dictLLN0 = self.createDictLLN0(lnType=None, desc='Default LLN0',
                                                       listDictDS=None, listDictRPT=None)
                    elif typeLN in ['FSCH', 'FSCC']:  # TODO: here first use ASG(MV), consider extension to all 4 types
                        desc = 'Default {} template for ASG control'.format(typeLN)
                        lnType = typeLN + '_MV0'
                        listLNinLD.append(self.createDictLN(lnClass=typeLN, lnType=lnType, desc=desc,
                                                            inst=1, prefix=prefix))
                    else:
                        desc = 'Default {} template'.format(typeLN)
                        listLNinLD.append(self.createDictLN(lnClass=typeLN, lnType=None, desc=desc,
                                                            inst=1, prefix=prefix))
                dictLD = self.createDictLD(inst=key, dictLN0=dictLLN0, listDictLN=listLNinLD)

                # at last create DataSet and Report
                dictLD = self.createDictDS(dictLD)
                dictLD = self.createDictRCB(dictLD)
                listDictLD.append(dictLD)



        # now update the parent dictionaries
        dictServer['LDevice'] = listDictLD
        dictAccessPoint['Server'] = dictServer
        dictIED['AccessPoint'] = dictAccessPoint

        # pass the completed dictionary object to the root dictionary dictOutputSCL
        self.dictOutputSCL["SCL"]["IED"] = dictIED

    def exportSCL(self):
        """ Export the dictionary into an XML file """

        with open(self.Config.pathOutputSCL, 'wt', encoding='utf-8') as fo:
            xmltodict.unparse(self.dictOutputSCL, fo, pretty=True)
        
        logger.info(f'The SCL has been exported to {self.Config.pathOutputSCL}')
        dictOutputSCL = self.dictOutputSCL
        pathOutputSCL = self.Config.pathOutputSCL
        
        return pathOutputSCL, dictOutputSCL

    def main(self, readConfigYAML=False, configYAML=None):
        self.parseConfigFile()
        if readConfigYAML:
            self.updateModelTopo(configYAML)
        self.initDataTypeTemplates()
        self.genSCL()
        self.genHeader()
        self.genCommunication()
        self.genIED()
        self.genDataTypeTemplates()
        [pathOutputSCL, dictOutputSCL] = self.exportSCL()
        
        return pathOutputSCL, dictOutputSCL
    
if '__name__' == '__main__':
    pathConfigFile = './model/config_IEC61850_model.xlsx'
    dmGen = IEC61850DataModelGenerator(pathConfigFile=pathConfigFile, nameIED='demoAutoGenCLS')
    [pathOutputSCL, dictOutputSCL] = dmGen.main()
