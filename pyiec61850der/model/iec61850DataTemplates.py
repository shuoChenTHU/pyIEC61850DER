# -*- coding: utf-8 -*-
"""
Created on Tue Apr 19 11:33:50 2022
@author: chen

# TODO: add some general documentation here

Usage:
    [EnumTemplates, DATemplates, DOTemplates, LNTemplates] = genIEC61850Templates()

"""

import xmltodict
from collections import OrderedDict
import sys
import os
import copy
# import json
import logging

# project relevant libs
from settings.helper import rotating_logger




# TODO: No except handling is implemented, for this moment it is not necessary. As the scope grows, consider using
#  explicit exception handlers to catch errors.
# TODO: consider use some unittest to reduce error
# TODO: implement __repr__() and __str__() in all classes
# TODO: consider turn some of the attributes in the classes into properties and implement setter, getter and deleter


class Config:
    """ This class stores some global variables and constants"""
    nGeneratedDO = 0
    nGeneratedDA = 0
    nGeneratedEnum = 0
    nGeneratedLN = 0
    nTotalDO = 0
    nTotalDA = 0
    nTotalEnum = 0
    nTotalLN = 0
    listTemplateEnum = None
    listTemplateDA = None
    listTemplateDO = None
    listTemplateLN = None


from settings.helper import rotating_logger
logger = rotating_logger(__name__)

"""
###############################################################################
######################   Define classes for templates  ########################
###############################################################################
"""


class Templates:
    """ An empty class prepared for template initialization"""
    def __init__(self, *args):
        pass  # this is an empty class, we will dynamically add new templates to it during the template initialization


class EnumerationKind:
    """Use this class to store all necessary enumeration kind in IEC61850"""

    # TODO: if the enum list is very long, separate the values and items might not be a good idea. Consider providing
    #  another possibility for such enum template (e.g. SIUnit)

    def __init__(self, nameEnum=None, nVal=None, listNum=None, listItem=None, **kwargs):
        self.name = nameEnum  # the name should be the same as the instance name!!
        self.nVal = nVal  # input of data_count is not necessary, it is used to remind raise the awareness of the user
        self.listNum = listNum
        self.listItem = listItem
        self.isValid = False
        self.dict = None
        self.isDictCreated = False

    def checkVal(self):
        """check if the initial setup of the instance is valid"""

        if len(self.listNum) != self.nVal:
            logger.warning('Enum {}: The value of data_count and the list length of '
                           'enumerated values are inconsistent'.format(self.name))
        elif len(self.listItem) != self.nVal:
            logger.warning('ENum {}: The value of data_count and the list length of '
                           'value descriptions are inconsistent'.format(self.name))
        else:
            self.isValid = True
        for idx, num in enumerate(self.listNum):
            if type(num) is not str:
                self.listNum[idx] = str(
                    num)  # convert the enum val to string, in case the number is given as an integer
            if not num.isdigit():
                logger.warning('ENum {}: List of enumerated values contains non-integer value, '
                               'please check the input.'.format(self.name))

    def createDictEnum(self):
        """ Create the enumeration dictionary for later use"""

        if self.isValid is not True:
            self.nVal = min(len(self.listNum), len(self.listItem), self.nVal)
            logger.warning('Enum {}: data_count changed to {} due to inconsistency'.format(self.name, self.nVal))
            logger.warning('double check the input lists to make sure the matching is correct')

        # go create a dictionary for the enum template

        try:
            dictEnum = OrderedDict()
            dictEnumVal = [OrderedDict([('@ord', self.listNum[idx]),
                                        ('#text', self.listItem[idx])]) for idx in range(self.nVal)]
            dictEnum['@id'] = self.name
            dictEnum['EnumVal'] = dictEnumVal
            self.dict = dictEnum
            self.isDictCreated = True
            Config.nGeneratedEnum += 1
            logger.info('The dictionary for Enum Kind {} has been successfully created.'.format(self.name))
        except:
            logger.error('The dictionary for {} could not be created, please check the input again.'.format(self.name))


class DAType:
    """
       We use this class to define default DO data object according to the given cdc structure.
       Here are some important notes:
    """

    # TODO: pycharm claims that the usage of type and id shadow built-in names, this seems to be an invalid warning.
    #   Double check whether it is true.

    def __init__(self, typeDA=None, idDA=None, **kwargs):
        """ Initialize the DA instance """
        if not typeDA:
            self.type = 'unknown'
            self.isValid = False
            logger.error('id is not given, set id to unknown and skip this one')
            logger.warning('check the DA templates in the output SCL to avoid error')
        else:
            self.type = typeDA
            self.isValid = True
        if not idDA:
            # TODO: check whether it is a good idea to use '_0' in the id to indicate default
            self.id = '{}_0'.format(typeDA)  # default DA dict
        else:
            self.id = idDA  # the id should be unique and descriptive
        self.listBDA = []
        self.dict = None
        self.isDictCreated = False

    def createDictDA(self):
        """ Create the DA dictionary for later use"""

        try:
            dictDA = OrderedDict([('@id', self.id),
                                  ('BDA', []),  # leave the BDA list empty, update BDA list in addBDAToDAType
                                  ])
            self.dict = dictDA
            self.isDictCreated = True
            logger.info('The dictionary for DA instance {} has successfully been created.'.format(self.id))
            Config.nGeneratedDA += 1
        except:
            logger.error('The dictionary for {} could not be created, please check the input again.'.format(self.id))

    def addBDAToDAType(self, bType=None, nameBDA=None, typeBDA=None, **kwargs):
        """ Use this method to add default BDA to the DA data structure"""

        dictBDA = OrderedDict([('@bType', bType),
                               ('@name', nameBDA),
                               ])
        if typeBDA is not None:
            dictBDA['@type'] = typeBDA
        if kwargs is not None:
            for idx, key in enumerate(kwargs):
                dictBDA['@{}'.format(key)] = kwargs[key]
        self.dict['BDA'].append(dictBDA)
        self.listBDA.append(nameBDA)


class DOType:
    """
    We use this class to define default DO data object according to the given cdc structure.
    Here are some important notes:
        1. a DO dictionary contains a list of DA and keys: cdc, desc, id
        2. the key "id" should follow the form <cdc>_default
        3. one DA sub-dict in the list contains following mandatory keys: bType, fc, name
        4. optional keys could be added later by other modules
        5. optional keys include: dchg, qchg, type, desc, .... (e.g. all Enum DO needs the type item to
            specify the enum literals)
    """

    def __init__(self, cdc=None, idDO=None, descDO=None, **kwargs):
        """ Initialize the DO instance """
        if not cdc:
            self.cdc = 'unknown'
            self.isValid = False
            logger.error('cdc is not given, set cdc to unknown and skip this one')
            logger.warning('check the DO templates in the output SCL to avoid error')
        else:
            self.cdc = cdc  # the name should be the same as the instance name!!
            self.isValid = True
        if not descDO:
            self.desc = 'Default DO templates for the cdc type {}'.format(cdc)
        else:
            self.desc = descDO  # input of data_count is not necessary, it is used to remind raise the awareness of the user
        if not idDO:
            # TODO: check whether it is a good idea to use '_0' in the id to indicate default
            self.id = '{}_0'.format(cdc)  # default cdc dict
        else:
            self.id = idDO
        self.listDA = []
        self.listSDO = []
        self.dict = None
        self.isDictCreated = False
        self.listFC = []

    def createDictDO(self):
        """ Create the DO dictionary for later use"""

        try:
            dictDO = OrderedDict([('@cdc', self.cdc),
                                  ('@id', self.id),
                                  ('@desc', self.desc),
                                  ('DA', []),  # leave the DA list empty, update DA list using addDAToDOType
                                  ('SDO', []),  # leave the SDO list empty, update DA list using addSDOToDOType
                                  ])
            self.dict = dictDO
            self.isDictCreated = True
            Config.nGeneratedDO += 1
            logger.info('The dictionary for DO instance {} has successfully been created.'.format(self.id))
        except:
            logger.error('The dictionary for {} could not be created, please check the input again.'.format(self.id))

    def addDAToDOType(self, bType=None, fc=None, nameDA=None, **kwargs):
        """ Use this method to add default DA to the DO data structure"""

        dictDA = OrderedDict([('@bType', bType),
                              ('@fc', fc),
                              ('@name', nameDA),
                              ])
        if kwargs is not None:
            for idx, key in enumerate(kwargs):
                # here the input argument should be typeXXX, like typeDA, otherwise var name shadows the system variable
                # we need a var name check to convert the type argument in kwargs back to just "type"
                if 'type' in key:
                    dictDA['@type'] = kwargs[key]
                else:
                    dictDA['@{}'.format(key)] = kwargs[key]
        self.dict['DA'].append(dictDA)
        self.listDA.append(nameDA)

    def addSDOToDOType(self, nameSDO=None, typeSDO=None, descSDO=None, **kwargs):
        """ Use this method to add default DA to the DO data structure"""

        if not descSDO:
            descSDO = 'Default SDO templates for the type {}'.format(typeSDO)
        dictSDO = OrderedDict([('@desc', descSDO),
                               ('@name', nameSDO),
                               ('@type', typeSDO),
                               ])
        if kwargs is not None:
            for idx, key in enumerate(kwargs):
                dictSDO['@{}'.format(key)] = kwargs[key]
        self.dict['SDO'].append(dictSDO)
        self.listSDO.append(nameSDO)

    def organizeDictDO(self):
        """
        Do something to make the DO dict clean and descriptive.
            - Check if the dict contains empty item (DA or SDO), if so, remove it to avoid modelling error
            - Generate a list of fc from all underlying DA
        """
        if not self.dict['DA']:
            del self.dict['DA']  # delete sub dict if no DA detected
        else:  # otherwise update fc list, this list will be very useful for the generation of DS and RPT!!!
            # TODO: units and d are basically in each DA dict, so these two don't count; but there should be a better
            #   way to obtain the DA fc
            listFCAll = [item['@fc'] for item in self.dict['DA'] if item['@name'] not in ['units', 'd']]
            listFCAll = list(set(listFCAll))
            self.listFC = self.listFC + listFCAll

        if not self.dict['SDO']:  # delete sub dict if no SDO detected
            del self.dict['SDO']
        else:  # otherwise update fc list, this list will be very useful for the generation of DS and RPT!!!
            # TODO: this process is risky, because SDO templates do not exist before the class is defined
            # Now we know CMV is a SDO type, WYE and DEL will call it, but we can not take it for granted. So we just
            # put 'SDO' into the list to command the module for DS/RPT creation go examine the fc list of SDO.
            self.listFC.append('SDO')

            # listTypeSDO = list(set([item['@type'] for item in self.dict['SDO']]))
            # for item in listTypeSDO:
            #     if item not in DOTemplates.__dict__:
            #         logger.warning('The target SDO type template {} is not yet created, '
            #                        'we cannot obtain the fc types'.format(item))
            #     else:
            #         listFCAll = [item['@fc'] for item in DOTemplates.__dict__[item].dict['DA']]
            #         listFCAll = list(set(listFCAll))
            #         self.listFC = self.listFC + listFCAll


class LNType:
    """
    We use this class to define default LN Logical Nodes according to the cdc structure and user selection.
    Here are some important notes:
    """

    def __init__(self, lnClass=None, idLN=None, **kwargs):
        """ Initialize the LN instance """
        if not lnClass:
            self.lnClass = 'unknown'
            self.isValid = False
            logger.error('lnClass is not given, set lnClass to unknown and skip this one')
            logger.warning('check the LNode templates in the output SCL to avoid error')
        else:
            self.lnClass = lnClass  # the name should be a standard IEC 61850 LN class
            self.isValid = True
            # TODO: add a IEC61850 LN list and validate the LN class against the entries in the list at each time
        if not idLN:
            # TODO: check whether it is a good idea to use '_0' in the id to indicate default
            self.id = '{}_0'.format(lnClass)  # default cdc dict
        else:
            self.id = idLN
        self.listDO = []
        self.dict = None
        self.isDictCreated = False

    def createDictLN(self):
        """ Create the LN dictionary for later use"""

        try:
            dictLN = OrderedDict([('@lnClass', self.lnClass),
                                  ('@id', self.id),
                                  ('DO', []),  # leave the DA list empty, update DA list using the method addDAToDOType
                                  ])
            self.dict = dictLN
            self.isDictCreated = True
            Config.nGeneratedLN += 1
            logger.info('The dictionary for DO instance {} has successfully been created.'.format(self.id))
        except:
            logger.error('The dictionary for {} could not be created, please check the input again.'.format(self.id))

    # noinspection PyMethodMayBeStatic
    def createDOTemplateEnum(self, typeDO=None):
        """ Use this function to create customized EnumTemplate (ENS, ENC, ENG)"""
    
        logger.info('Undefined DO template of type {} detected, now start creating it'.format(typeDO))
        if not typeDO:
            logger.warning('Type not given, cannot create the template, skip this function')
        elif len(typeDO.split('_')) != 2:
            logger.warning('Format of the type is incorrect, please use "<cdc>_<EnumKind>", '
                           'cannot proceed, skip this function')
        else:
            [typeCDC, nameEnumKind] = typeDO.split('_')
    
            if typeCDC[0] != 'E':
                logger.warning('Non-enumeration type is given, no logic implemented yet,'
                               ' cannot proceed, skip this function')
            elif typeCDC not in ['ENC', 'ENS', 'ENG']:
                logger.warning('Type is not a standard cdc type, please check typo, '
                               'cannot proceed, skip this function')
            elif nameEnumKind not in Config.listTemplateEnum:
                logger.warning('Enum type {} undefined, consider create a Enum template first'.format(nameEnumKind))
            else:  # if everything is fine, copy the default Enum instance and change the EnumKind accordingly
                customizedEnum = copy.deepcopy(DOTemplates.__dict__['{}_0'.format(typeCDC)])  # copy the right template
                customizedEnum.dict['@id'] = typeDO  # set the id to the correct one
                # try update the information in the customized DO template for enumeration
                try:
                    idxEnum = [idx for idx, item in enumerate(customizedEnum.dict['DA']) if item['@bType'] == 'Enum'
                               and item['@type'] == 'PseudoEnumKind']
                    for idx in idxEnum:
                        customizedEnum.dict['DA'][idx]['@type'] = nameEnumKind  # set the EnumKind to the correct one
                    customizedEnum.dict['@desc'] = 'Default DO Template for enuemration {}'.format(typeDO)
                    customizedEnum.id = typeDO  # update id
                    customizedEnum.desc = 'Default DO Template for enumeration {}'.format(typeDO)
                    DOTemplates.customizedEnum = customizedEnum  # add the Enum to the EnumTemplate instance
                    DOTemplates.__dict__[typeDO] = DOTemplates.__dict__.pop('customizedEnum')  # change attribute name
                    Config.listTemplateDO.append(typeDO)
                    Config.nGeneratedDO += 1
                    logger.info('DO template of type {} successfully created'.format(typeDO))
                except:
                    logger.error('DA of the enum type can not be found in DO dictionary, check the default DO')

    def addDOToLNType(self, typeDO=None, nameDO=None, descDO=None, **kwargs):
        """ Use this method to add default DO to the LN data structure"""

        # TODO: check whether it is necessary and possible to include other keys
        if not descDO:
            descDO = ''  # leave the desc empty due to model size concern, if not specified
        if typeDO not in Config.listTemplateDO:  # create a new DO of cdc type Enum
            self.createDOTemplateEnum(typeDO)
        dictDO = OrderedDict([('@desc', descDO),
                              ('@type', typeDO),
                              ('@name', nameDO),
                              ])
        # TODO: check whether it is necessary to address the presence condition PresCond (cond='M' or cond='O')
        if kwargs is not None:
            for idx, key in enumerate(kwargs):
                dictDO['@{}'.format(key)] = kwargs[key]
        self.dict['DO'].append(dictDO)
        self.listDO.append(nameDO)

    
 
                   
"""
###############################################################################
#################   Initialize the IEC 61850 data templates  ##################
###############################################################################
"""

"""
Since most of the IEC 61850 data objects have unique name, we shall assume that using their names directly as 
variable names would not cause any naming conflict.
"""


def initEnumTemplates():
    """
    Init templates for enumerated values.
    Note that each enum kind is a class instance, use XXX.dict to access the dictionary object of that enum kind.
    """

    EnumTemplates = Templates()  # init the template instance for enumeration

    # TODO: check whether it is totally okay to categorize different templates of one particular type into one class
    # Now start to create templates and add them to the instance EnumTemplates

    # We start with general IEC 61850 enumerations

    # BehaviourModeKind
    listNum = [str(i) for i in range(1, 6)]
    listItem = ['on', 'on-blocked', 'test', 'test/blocked', 'off']
    BehaviourModeKind = EnumerationKind(nameEnum='BehaviourModeKind', nVal=5, listNum=listNum, listItem=listItem)
    BehaviourModeKind.checkVal()
    BehaviourModeKind.createDictEnum()
    EnumTemplates.BehaviourModeKind = BehaviourModeKind

    # CoolingMethodKind
    listNum = [str(i) for i in range(1, 5)] + ['98']
    listItem = ['Passive air cooling (heatsink)', 'Forced air cooling (fan + heatsink)', 'Fluid cooling (water)',
                'Heat pipe', 'Not applicable or not known']
    CoolingMethodKind = EnumerationKind(nameEnum='CoolingMethodKind', nVal=5, listNum=listNum, listItem=listItem)
    CoolingMethodKind.checkVal()
    CoolingMethodKind.createDictEnum()
    EnumTemplates.CoolingMethodKind = CoolingMethodKind


    # CtlModelKind
    listNum = [str(i) for i in range(0, 5)]
    listItem = ['status-only', 'direct-with-normal-security', 'sbo-with-normal-security',
                'direct-with-enhanced-security', 'sbo-with-enhanced-security']
    CtlModelKind = EnumerationKind(nameEnum='CtlModelKind', nVal=5, listNum=listNum, listItem=listItem)
    CtlModelKind.checkVal()
    CtlModelKind.createDictEnum()
    EnumTemplates.CtlModelKind = CtlModelKind

    # HealthKind
    listNum = [str(i) for i in range(1, 4)]
    listItem = ['OK', 'Warning', 'Alarm']
    HealthKind = EnumerationKind(nameEnum='HealthKind', nVal=3, listNum=listNum, listItem=listItem)
    HealthKind.checkVal()
    HealthKind.createDictEnum()
    EnumTemplates.HealthKind = HealthKind

    # MonthKind
    listNum = [str(i) for i in range(0, 13)]
    listItem = ['reserved', 'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December']
    MonthKind = EnumerationKind(nameEnum='MonthKind', nVal=13, listNum=listNum, listItem=listItem)
    MonthKind.checkVal()
    MonthKind.createDictEnum()
    EnumTemplates.MonthKind = MonthKind

    # OccurrenceKind
    listNum = [str(i) for i in range(0, 5)]
    listItem = ['Time', 'WeekDay', 'WeekOfYear', 'DayOfMonth', 'DayOfYear']
    OccurrenceKind = EnumerationKind(nameEnum='OccurrenceKind', nVal=5, listNum=listNum, listItem=listItem)
    OccurrenceKind.checkVal()
    OccurrenceKind.createDictEnum()
    EnumTemplates.OccurrenceKind = OccurrenceKind

    # PeriodKind
    listNum = [str(i) for i in range(0, 5)]
    listItem = ['Hour', 'Day', 'Week', 'Month', 'Year']
    PeriodKind = EnumerationKind(nameEnum='PeriodKind', nVal=5, listNum=listNum, listItem=listItem)
    PeriodKind.checkVal()
    PeriodKind.createDictEnum()
    EnumTemplates.PeriodKind = PeriodKind

    # SIUnitKind
    # TODO: since SIUnitKind contains to many items, I just copied them out of the SCL XML and convert the XML to dict
    # Note: the items with ord larger than 87 are customized units, necessary for the project, but not really SI Units.
    XML_STR = '''<EnumType id="SIUnitKind">
         <EnumVal ord="1">null</EnumVal>
         <EnumVal ord="2">m</EnumVal>
         <EnumVal ord="3">kg</EnumVal>
         <EnumVal ord="4">s</EnumVal>
         <EnumVal ord="5">A</EnumVal>
         <EnumVal ord="6">K</EnumVal>
         <EnumVal ord="7">mol</EnumVal>
         <EnumVal ord="8">cd</EnumVal>
         <EnumVal ord="9">deg</EnumVal>
         <EnumVal ord="10">rad</EnumVal>
         <EnumVal ord="11">sr</EnumVal>
         <EnumVal ord="21">Gy</EnumVal>
         <EnumVal ord="22">Bq</EnumVal>
         <EnumVal ord="23">°C</EnumVal>
         <EnumVal ord="24">Sv</EnumVal>
         <EnumVal ord="25">F</EnumVal>
         <EnumVal ord="26">C</EnumVal>
         <EnumVal ord="27">S</EnumVal>
         <EnumVal ord="28">H</EnumVal>
         <EnumVal ord="29">V</EnumVal>
         <EnumVal ord="30">ohm</EnumVal>
         <EnumVal ord="31">J</EnumVal>
         <EnumVal ord="32">N</EnumVal>
         <EnumVal ord="33">Hz</EnumVal>
         <EnumVal ord="34">lx</EnumVal>
         <EnumVal ord="35">Lm</EnumVal>
         <EnumVal ord="36">Wb</EnumVal>
         <EnumVal ord="37">T</EnumVal>
         <EnumVal ord="38">W</EnumVal>
         <EnumVal ord="39">Pa</EnumVal>
         <EnumVal ord="41">m²</EnumVal>
         <EnumVal ord="42">m³</EnumVal>
         <EnumVal ord="43">m/s</EnumVal>
         <EnumVal ord="44">m/s²</EnumVal>
         <EnumVal ord="45">m³/s</EnumVal>
         <EnumVal ord="46">m/m³</EnumVal>
         <EnumVal ord="47">M</EnumVal>
         <EnumVal ord="48">kg/m³</EnumVal>
         <EnumVal ord="49">m²/s</EnumVal>
         <EnumVal ord="50">W/m K</EnumVal>
         <EnumVal ord="51">J/K</EnumVal>
         <EnumVal ord="52">ppm</EnumVal>
         <EnumVal ord="53">1/s</EnumVal>
         <EnumVal ord="54">rad/s</EnumVal>
         <EnumVal ord="55">W/m²</EnumVal>
         <EnumVal ord="56">J/m²</EnumVal>
         <EnumVal ord="57">S/m</EnumVal>
         <EnumVal ord="58">K/s</EnumVal>
         <EnumVal ord="59">Pa/s</EnumVal>
         <EnumVal ord="60">J/kg K</EnumVal>
         <EnumVal ord="61">VA</EnumVal>
         <EnumVal ord="62">Watts</EnumVal>
         <EnumVal ord="63">VAr</EnumVal>
         <EnumVal ord="64">phi</EnumVal>
         <EnumVal ord="65">cos(phi)</EnumVal>
         <EnumVal ord="66">Vs</EnumVal>
         <EnumVal ord="67">V²</EnumVal>
         <EnumVal ord="68">As</EnumVal>
         <EnumVal ord="69">A²</EnumVal>
         <EnumVal ord="70">A²t</EnumVal>
         <EnumVal ord="71">VAh</EnumVal>
         <EnumVal ord="72">Wh</EnumVal>
         <EnumVal ord="73">VArh</EnumVal>
         <EnumVal ord="74">V/Hz</EnumVal>
         <EnumVal ord="75">Hz/s</EnumVal>
         <EnumVal ord="76">char</EnumVal>
         <EnumVal ord="77">char/s</EnumVal>
         <EnumVal ord="78">kgm²</EnumVal>
         <EnumVal ord="79">dB</EnumVal>
         <EnumVal ord="80">J/Wh</EnumVal>
         <EnumVal ord="81">W/s</EnumVal>
         <EnumVal ord="82">l/s</EnumVal>
         <EnumVal ord="83">dBm</EnumVal>
         <EnumVal ord="84">h</EnumVal>
         <EnumVal ord="85">min</EnumVal>
         <EnumVal ord="86">Ohm/m</EnumVal>
         <EnumVal ord="87">percent/s</EnumVal>
         <EnumVal ord="88">%</EnumVal>
         <EnumVal ord="89">Ah</EnumVal>
      </EnumType>'''
    XML_DICT = xmltodict.parse(XML_STR, dict_constructor=OrderedDict)  # note we set the constructor to OrderedDict
    # manually change the value Null to '' to solve the empty entry parsing problematic
    XML_DICT['EnumType']['EnumVal'][0]['#text'] = ''
    listNum = [val['@ord'] for val in XML_DICT['EnumType']['EnumVal']]
    listItem = [val['#text'] for val in XML_DICT['EnumType']['EnumVal']]
    SIUnitKind = EnumerationKind(nameEnum='SIUnitKind', nVal=79,
                                 listNum=listNum, listItem=listItem)  # to perseve the unified format
    SIUnitKind.checkVal()
    SIUnitKind.createDictEnum()
    EnumTemplates.SIUnitKind = SIUnitKind

    # WeekdayKind
    listNum = [str(i) for i in range(0, 8)]
    listItem = ['reserved', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    WeekdayKind = EnumerationKind(nameEnum='WeekdayKind', nVal=8, listNum=listNum, listItem=listItem)
    WeekdayKind.checkVal()
    WeekdayKind.createDictEnum()
    EnumTemplates.WeekdayKind = WeekdayKind

    # Now we move to some DER specific enumeration, the instances are alphabetically sorted

    # ACSystemKind
    listNum = [str(i) for i in range(1, 4)]
    listItem = ['Single phase', 'Two phases', 'Three phases']
    ACSystemKind = EnumerationKind(nameEnum='ACSystemKind', nVal=3, listNum=listNum, listItem=listItem)
    ACSystemKind.checkVal()
    ACSystemKind.createDictEnum()
    EnumTemplates.ACSystemKind = ACSystemKind

    # ChargeSourceKind
    listNum = [str(i) for i in range(1, 4)]
    listItem = ['Mode A - Storage may not export to grid, but may charge',
                'Mode B - Storage may export to grid, but not charge',
                'Mode C - Storage may both charge or discharge from the grid']
    ChargeSourceKind = EnumerationKind(nameEnum='ChargeSourceKind', nVal=3, listNum=listNum, listItem=listItem)
    ChargeSourceKind.checkVal()
    ChargeSourceKind.createDictEnum()
    EnumTemplates.ChargeSourceKind = ChargeSourceKind

    # DERStateKind
    listNum = [str(i) for i in range(1, 12)] + ['98']
    listItem = ['on but disconnected and not ready', 'starting up', 'disconnected and available',
                'disconnected and authorized', 'synchronizing', 'running',
                'stopping and disconnecting under emergency conditions',
                'stopping', 'disconnected and blocked', 'disconnected and in maintenance', 'failed',
                'Not applicable or not known']
    DERStateKind = EnumerationKind(nameEnum='DERStateKind', nVal=12, listNum=listNum, listItem=listItem)
    DERStateKind.checkVal()
    DERStateKind.createDictEnum()
    EnumTemplates.DERStateKind = DERStateKind

    # DERStateTransitionKind
    listNum = [str(i) for i in range(1, 11)]
    listItem = ['Start', 'Connect', 'Disconnect', 'Disconnect under emergency conditions', 'Get blocked',
                'Get unblocked', 'Go to maintenance', 'Go out of maintenance', 'Stop', 'Turn off controller']
    DERStateTransitionKind = EnumerationKind(nameEnum='DERStateTransitionKind', nVal=10,
                                             listNum=listNum, listItem=listItem)
    DERStateTransitionKind.checkVal()
    DERStateTransitionKind.createDictEnum()
    EnumTemplates.DERStateTransitionKind = DERStateTransitionKind

    # DERSynchronizationKind
    listNum = [str(i) for i in range(1, 8)] + ['98']
    listItem = ['Unavailable to connect', 'Notsynchronized, available to connect', 'In synchronization process',
                'Synchronized and not connected', 'Synchronized and connected', 'Synchronization failure',
                'Disconnecting from grid', 'Not applicable or not known']
    DERSynchronizationKind = EnumerationKind(nameEnum='DERSynchronizationKind', nVal=8,
                                             listNum=listNum, listItem=listItem)
    DERSynchronizationKind.checkVal()
    DERSynchronizationKind.createDictEnum()
    EnumTemplates.DERSynchronizationKind = DERSynchronizationKind

    # DERUnitKind
    listNum = [str(i) for i in range(1, 14)] + ['50', '98']
    listItem = ['Diesel / gas engine', 'Gas Turbine engine', 'PV', 'PV plus Storage', 'Lithium Ion Battery Storage',
                'Fuel cell', 'Hydro generator', 'Wind turbine', 'Flow battery storage', 'Air compression storage',
                'Flywheel storage', 'Capacitor storage', 'Vehicle-to-Grid (V2G)', 'Mixed, hybrid DER',
                'Not applicable or not known']
    DERUnitKind = EnumerationKind(nameEnum='DERUnitKind', nVal=15, listNum=listNum, listItem=listItem)
    DERUnitKind.checkVal()
    DERUnitKind.createDictEnum()
    EnumTemplates.DERUnitKind = DERUnitKind

    # ECPConnKind
    listNum = [str(i) for i in range(1, 10)] + ['98']
    listItem = ['PoC: Electric point positioned at the connection of the DER to its local EPS',
                'IntDER: Electric point positioned internally to the DER',
                'PCC: Electric point positioned at the connection of local EPS to area EPS, the EPS contains DERs including local loads',
                'PCCD: specific PCC when the EPS contains only DERs with no loads',
                'PoCoL: Electric point positioned at the connection of load within the DER local EPS',
                'ExtPCC: Electric point positioned at the connection to a PCC external to the area EPS',
                'ExtPoC: Electric point positioned at the connection of DER within local EPS outside of the DER local EPS',
                'AuxLoad: Connection of auxilliary load to DER',
                'PoCG: Connection of group of possibly different types of DERs to local EPS',
                'Not applicable or not known']
    ECPConnKind = EnumerationKind(nameEnum='ECPConnKind', nVal=10, listNum=listNum, listItem=listItem)
    ECPConnKind.checkVal()
    ECPConnKind.createDictEnum()
    EnumTemplates.ECPConnKind = ECPConnKind

    # InverterControlSourceKind
    listNum = [str(i) for i in range(1, 4)] + ['98']
    listItem = ['Current-source inverter (CSI)',
                'Voltage-controlled voltage-source inverter (VCVSI)',
                'Current-controlled voltage-source inverter (CCVSI)',
                'Not applicable or not known']
    InverterControlSourceKind = EnumerationKind(nameEnum='InverterControlSourceKind', nVal=4,
                                                listNum=listNum, listItem=listItem)
    InverterControlSourceKind.checkVal()
    InverterControlSourceKind.createDictEnum()
    EnumTemplates.InverterControlSourceKind = InverterControlSourceKind

    # IsolationKind
    listNum = [str(i) for i in range(1, 5)] + ['98']
    listItem = ['Low frequency transformer isolated', 'Hi frequency transformer isolated', 'Non-isolated, grounded',
                'Non-isolated, isolated DC source', 'Not applicable or not known']
    IsolationKind = EnumerationKind(nameEnum='IsolationKind', nVal=5, listNum=listNum, listItem=listItem)
    IsolationKind.checkVal()
    IsolationKind.createDictEnum()
    EnumTemplates.IsolationKind = IsolationKind

    # OrCatKind
    listNum = [str(i) for i in range(0, 9)]
    listItem = ['not-supported', 'bay-control', 'station-control', ' remote-control', 'automatic-bay',
                'automatic-station', 'automatic-remote', 'maintenance', 'process']
    OrCatKind = EnumerationKind(nameEnum='OrCatKind', nVal=9, listNum=listNum, listItem=listItem)
    OrCatKind.checkVal()
    OrCatKind.createDictEnum()
    EnumTemplates.OrCatKind = OrCatKind

    # PhaseKind
    listNum = [str(i) for i in range(1, 7)] + ['9', '98']
    listItem = ['Single phase to neutral', 'Split phase', '2-phase', '3-phase delta', '3-phase wye / 4-wires',
                '3-phase wye / 5-wires', 'DC', 'Not applicable or not known']
    PhaseKind = EnumerationKind(nameEnum='PhaseKind', nVal=8, listNum=listNum, listItem=listItem)
    PhaseKind.checkVal()
    PhaseKind.createDictEnum()
    EnumTemplates.PhaseKind = PhaseKind

    # QuadrantRunningStateKind
    listNum = [str(i) for i in range(1, 10)]
    listItem = ['P greater than zero, Q greater than zero', 'P less than zero, Q greater than zero',
                'P less than zero, Q less than zero', 'P greater than zero, Q less than zero',
                'P equals zero, Q greater than zero', 'P equals zero, Q less than zero',
                'P greater than zero, Q equals zero', 'P less than zero, Q equals zero', 'P equals zero, Q equals zero']
    QuadrantRunningStateKind = EnumerationKind(nameEnum='QuadrantRunningStateKind', nVal=9,
                                               listNum=listNum, listItem=listItem)
    QuadrantRunningStateKind.checkVal()
    QuadrantRunningStateKind.createDictEnum()
    EnumTemplates.QuadrantRunningStateKind = QuadrantRunningStateKind

    # ReactivePowerRefParamKind
    listNum = [str(i) for i in range(1, 4)] + ['98']
    listItem = ['Reactive power in percent of WMax', 'Reactive power in percent of VArMax',
                'Reactive power in percent of VArAvl', 'Not applicable or not known']
    ReactivePowerRefParamKind = EnumerationKind(nameEnum='ReactivePowerRefParamKind', nVal=4,
                                                listNum=listNum, listItem=listItem)
    ReactivePowerRefParamKind.checkVal()
    ReactivePowerRefParamKind.createDictEnum()
    EnumTemplates.ReactivePowerRefParamKind = ReactivePowerRefParamKind

    # ScheduleEnablingErrorKind
    listNum = [str(i) for i in range(1, 7)] + ['99']
    listItem = ['None', 'Missing valid NumEntr', 'Missing valid SchdIntv',
                'Missing valid schedule values', 'Inconsistent values cdc', 'Missing valid StrTm', 'Other']
    ScheduleEnablingErrorKind = EnumerationKind(nameEnum='ScheduleEnablingErrorKind', nVal=7,
                                                listNum=listNum, listItem=listItem)
    ScheduleEnablingErrorKind.checkVal()
    ScheduleEnablingErrorKind.createDictEnum()
    EnumTemplates.ScheduleEnablingErrorKind = ScheduleEnablingErrorKind

    # ScheduleStateKind
    listNum = [str(i) for i in range(1, 5)]
    listItem = ['Not ready', 'Start Time required', 'Ready', 'Running']
    ScheduleStateKind = EnumerationKind(nameEnum='ScheduleStateKind', nVal=4,
                                        listNum=listNum, listItem=listItem)
    ScheduleStateKind.checkVal()
    ScheduleStateKind.createDictEnum()
    EnumTemplates.ScheduleStateKind = ScheduleStateKind

    # At last, add one Pseudo Enum EnumDA to avoid model validation error
    # PseudoEnumKind
    listNum = [str(i) for i in range(1, 4)]
    listItem = ['Pseudo state on', 'Pseudo state off', 'Pseudo state unknown']
    PseudoEnumKind = EnumerationKind(nameEnum='PseudoEnumKind', nVal=3, listNum=listNum, listItem=listItem)
    PseudoEnumKind.checkVal()
    PseudoEnumKind.createDictEnum()
    EnumTemplates.PseudoEnumKind = PseudoEnumKind

    Config.listTemplateEnum = list(EnumTemplates.__dict__)

    return EnumTemplates


def initDATemplates():
    """
    Initialize templates for Data Attributes containing BDA (Basic Data Attribute)
    Here are some important notes:
        - for the DA with type MX, only float type is considered in the BDA lists, integer is excluded
        - the usage of _0 for default DAs is inspired by the XML schema in the IEC 61850 engineering tool
            ICD Designer
    """

    DATemplates = Templates()  # init the template instance for DA

    # AnalogueValue_0
    AnalogueValue_0 = DAType(typeDA='AnalogueValue')
    AnalogueValue_0.createDictDA()
    AnalogueValue_0.addBDAToDAType(bType='FLOAT32', nameBDA='f')
    DATemplates.AnalogueValue_0 = AnalogueValue_0

    # AnalogueValueCtl_0
    AnalogueValueCtl_0 = DAType(typeDA='AnalogueValueCtl')
    AnalogueValueCtl_0.createDictDA()
    AnalogueValueCtl_0.addBDAToDAType(bType='FLOAT32', nameBDA='f')
    DATemplates.AnalogueValueCtl_0 = AnalogueValueCtl_0

    # Unit_0
    Unit_0 = DAType(typeDA='Unit')
    Unit_0.createDictDA()
    Unit_0.addBDAToDAType(bType='Enum', nameBDA='SIUnit', typeBDA='SIUnitKind')
    DATemplates.Unit_0 = Unit_0

    # Vector_0
    Vector_0 = DAType(typeDA='Vector')
    Vector_0.createDictDA()
    Vector_0.addBDAToDAType(bType='Struct', nameBDA='mag', typeBDA='AnalogueValue_0')
    # TODO: check if adding a DA as SDA to another DA would work
    DATemplates.Vector_0 = Vector_0

    # Originator_0
    Originator_0 = DAType(typeDA='Originator')
    Originator_0.createDictDA()
    Originator_0.addBDAToDAType(bType='Enum', nameBDA='orCat', typeBDA='OrCatKind')
    Originator_0.addBDAToDAType(bType='Octet64', nameBDA='orIdent')
    DATemplates.Originator_0 = Originator_0

    # Point_0
    Point_0 = DAType(typeDA='Point')
    Point_0.createDictDA()
    Point_0.addBDAToDAType(bType='FLOAT32', nameBDA='xVal')
    Point_0.addBDAToDAType(bType='FLOAT32', nameBDA='yVal')
    Point_0.addBDAToDAType(bType='FLOAT32', nameBDA='zVal')  # optional DA
    DATemplates.Point_0 = Point_0

    # CalendarTime_0
    CalendarTime_0 = DAType(typeDA='CalendarTime')
    CalendarTime_0.createDictDA()
    CalendarTime_0.addBDAToDAType(bType='INT16U', nameBDA='occ')
    CalendarTime_0.addBDAToDAType(bType='Enum', nameBDA='occType', typeBDA='OccurrenceKind')
    CalendarTime_0.addBDAToDAType(bType='Enum', nameBDA='occPer', typeBDA='PeriodKind')
    CalendarTime_0.addBDAToDAType(bType='Enum', nameBDA='weekDay', typeBDA='WeekdayKind')
    CalendarTime_0.addBDAToDAType(bType='Enum', nameBDA='month', typeBDA='MonthKind')
    CalendarTime_0.addBDAToDAType(bType='INT8U', nameBDA='day')
    CalendarTime_0.addBDAToDAType(bType='INT8U', nameBDA='hr')
    CalendarTime_0.addBDAToDAType(bType='INT8U', nameBDA='mn')
    DATemplates.CalendarTime_0 = CalendarTime_0

    Config.listTemplateDA = list(DATemplates.__dict__)

    return DATemplates


def initDOTemplates():
    """
    Init templates for Data Objects.
    Following IEC 61850 cdc types are currently supported as DO Templates:
        - Status Info:      SPS, INS, ENS; BCR, ORS, TCS
        - Analogue Info:    MV, CMV, WYE, DEL
        - Control:          SPC, INC, ENC, APC
        - Status Set:       SPG, ING, ENG, ORG, TSG, CUG, VSG
        - Description:      DPL, LPL
    Here are some important notes:
        - Note that each DOTemplates is a class instance, use XXX.dict to access the dictionary object
            of that DOTemplates;
        - Default DO instances take the cdc as instance name. Later when using non-standard DO,
            please follow the naming convention <cdc>_<customized instance name>, e.g. ASG_noQuality
        - For the enumeration DO (ENG, ENS, ENC), each kind needs a separate template as they all have different enum
            kinds. So we use a for loop here to get them all at once.
        - currently only consider mandatory DAs, only important optional DA such as d and units are included
            wheverver applicable, the other optional DAs can be added later in customized DA objects
            according to user demand
        - IEC 61850-7-3 defines 3 dedicated types for Status Settings DO (SP, SG, SE), here only SP is considered.
        - the usage of _0 for default DOs is inspired by the XML schema in the IEC 61850 engineering tool
            ICD Designer
        - Description of the DA is only optional, most of the information is to be derived from the standard documents,
            thus, only critical information is required here, otherwise leave out the item "desc"
    Two prerequisite for the execution of this function:
         1. EnumTemplates successfully initialized (to dynamically initialize ENum DOs)
         2. DATypeTemplates for commonly used DA successfully initialized (since many DA in DO refer to
            a certain DA type, e.g. mag.f, cVal.mag.f)
    """

    DOTemplates = Templates()  # init the template instance for DO

    # TODO: check whether it is totally okay to categorize different templates of one particular type into one class
    # Now start to create templates and add them to the instance DOTemplates, alphabetically sorted
    # First generate default DO (for all cdc types that are not enumeration)

    # APC_0
    APC_0 = DOType(cdc='APC')
    APC_0.createDictDO()
    APC_0.addDAToDOType(bType='Struct', fc='MX', nameDA='origin', typeDA='Originator_0')  # optional DA
    APC_0.addDAToDOType(bType='INT8U', fc='MX', nameDA='ctlNum')  # optional DA
    APC_0.addDAToDOType(bType='Struct', fc='MX', nameDA='mxVal', dchg='true', typeDA='AnalogueValue_0')
    APC_0.addDAToDOType(bType='Quality', fc='MX', nameDA='q', qchg='true')
    APC_0.addDAToDOType(bType='Timestamp', fc='MX', nameDA='t')
    APC_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    APC_0.addDAToDOType(bType='Enum', fc='CF', nameDA='ctlModel', typeDA='CtlModelKind')
    APC_0.addDAToDOType(bType='Struct', fc='CO', nameDA='ctlVal', typeDA='AnalogueValueCtl_0')
    APC_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    APC_0.organizeDictDO()
    DOTemplates.APC_0 = APC_0

    # ASG_0
    ASG_0 = DOType(cdc='ASG')
    ASG_0.createDictDO()
    ASG_0.addDAToDOType(bType='Struct', fc='SP', nameDA='setMag', typeDA='AnalogueValueCtl_0')
    ASG_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    ASG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ASG_0.organizeDictDO()
    DOTemplates.ASG_0 = ASG_0

    # BCR_0
    BCR_0 = DOType(cdc='BCR')
    BCR_0.createDictDO()
    BCR_0.addDAToDOType(bType='INT64', fc='ST', nameDA='actVal', dchg='true')
    BCR_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    BCR_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    BCR_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    BCR_0.addDAToDOType(bType='FLOAT32', fc='CF', nameDA='pulsQty', dchg='true')
    BCR_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    BCR_0.organizeDictDO()
    DOTemplates.BCR_0 = BCR_0

    # CMV_0
    # instCVal is not included, as we do not calculate deadband
    CMV_0 = DOType(cdc='CMV')
    CMV_0.createDictDO()
    CMV_0.addDAToDOType(bType='Struct', fc='MX', nameDA='cVal', dchg='true', dupd='true', typeDA='Vector_0')
    CMV_0.addDAToDOType(bType='Quality', fc='MX', nameDA='q', qchg='true')
    CMV_0.addDAToDOType(bType='Timestamp', fc='MX', nameDA='t')
    CMV_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    CMV_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    CMV_0.organizeDictDO()
    DOTemplates.CMV_0 = CMV_0

    # CSG_0
    # Note the DA crvPts is an arroy of points, the count is set to 100 for default, this corresponds to profiles or
    # settings with 92/96/100 vals per day, under the assumption of data transmission by 15 min t_interval_data_update.
    # Change this value when calling DO of typeDA CSG!!
    CSG_0 = DOType(cdc='CSG')
    CSG_0.createDictDO()
    CSG_0.addDAToDOType(bType='Struct', fc='SP', nameDA='crvPts', dchg='true', typeDA='Point_0', count=100)
    CSG_0.addDAToDOType(bType='FLOAT32', fc='SP', nameDA='pointZ', dchg='true')  # optional DA, only for 3D curve
    CSG_0.addDAToDOType(bType='INT16U', fc='SP', nameDA='numPts', dchg='true')
    CSG_0.addDAToDOType(bType='Struct', fc='CF', nameDA='xUnits', dchg='true', typeDA='Unit_0')
    CSG_0.addDAToDOType(bType='Struct', fc='CF', nameDA='yUnits', dchg='true', typeDA='Unit_0')
    CSG_0.addDAToDOType(bType='Struct', fc='CF', nameDA='zUnits', dchg='true', typeDA='Unit_0')  # optional, only 3D curve
    CSG_0.addDAToDOType(bType='INT16U', fc='CF', nameDA='maxPts', dchg='true')
    CSG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='xD')
    CSG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='yD')
    CSG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='zD')  # optional DA, only for 3D curve
    CSG_0.organizeDictDO()
    DOTemplates.CSG_0 = CSG_0

    # CUG_0
    CUG_0 = DOType(cdc='CUG')
    CUG_0.createDictDO()
    CUG_0.addDAToDOType(bType='Currency', fc='SP', nameDA='cur', dchg='true')
    CUG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    CUG_0.organizeDictDO()
    DOTemplates.CUG_0 = CUG_0

    # DEL_0
    # note we added several SDO to the DO here, not only DA
    DEL_0 = DOType(cdc='DEL')
    DEL_0.createDictDO()
    DEL_0.addSDOToDOType(nameSDO='phsAB', typeSDO='CMV_0', descSDO='Value of phase A to phase B')
    DEL_0.addSDOToDOType(nameSDO='phsBC', typeSDO='CMV_0', descSDO='Value of phase B to phase C')
    DEL_0.addSDOToDOType(nameSDO='phsCA', typeSDO='CMV_0', descSDO='Value of phase C to phase A')
    DEL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    DEL_0.organizeDictDO()
    DOTemplates.DEL_0 = DEL_0

    # DPL_0
    # unlike other DO, for DPL we include all possible DA, mandatory and optional.
    # Remove the unnecessary DAs on demand later
    DPL_0 = DOType(cdc='DPL')
    DPL_0.createDictDO()
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='vendor')
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='hwRev')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='swRev')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='serNum')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='model')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='location')  # optional DA
    DPL_0.addDAToDOType(bType='VisString64', fc='DC', nameDA='nameDA')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='owner')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='ePSName')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='primeOper')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='secondOper')  # optional DA
    DPL_0.addDAToDOType(bType='FLOAT32', fc='DC', nameDA='latitude')  # optional DA
    DPL_0.addDAToDOType(bType='FLOAT32', fc='DC', nameDA='longitude')  # optional DA
    DPL_0.addDAToDOType(bType='FLOAT32', fc='DC', nameDA='altitude')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='mRID')  # optional DA
    DPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    DPL_0.organizeDictDO()
    DOTemplates.DPL_0 = DPL_0

    # ENC_0
    # This DO template only a reference presenting how an ENC DO is supposed to look like.
    # It does not contain valid information as the Enum Type must be specified for each Enum Kind
    # To use this DO typeDA correctly, always tracking the calling of Enum typeDA DO and initialized explicit
    # DO Template dynamically. Remember not to create duplicated templates for the same EnumKind
    ENC_0 = DOType(cdc='ENC')
    ENC_0.createDictDO()
    ENC_0.addDAToDOType(bType='Struct', fc='ST', nameDA='origin', typeDA='Originator_0')  # optional DA
    ENC_0.addDAToDOType(bType='INT8U', fc='ST', nameDA='ctlNum')  # optional DA
    ENC_0.addDAToDOType(bType='Enum', fc='ST', nameDA='stVal', dchg='true', dupd='true', typeDA='PseudoEnumKind')
    ENC_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    ENC_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    ENC_0.addDAToDOType(bType='Enum', fc='CF', nameDA='ctlModel', typeDA='CtlModelKind')
    ENC_0.addDAToDOType(bType='Enum', fc='CO', nameDA='ctlVal', typeDA='PseudoEnumKind')
    ENC_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ENC_0.organizeDictDO()
    DOTemplates.ENC_0 = ENC_0

    # ENG_0
    # This DO template only a reference presenting how an ENG DO is supposed to look like.
    # It does not contain valid information as the Enum Type must be specified for each Enum Kind
    # To use this DO typeDA correctly, always tracking the calling of Enum typeDA DO and initialized explicit
    # DO Template dynamically. Remember not to create duplicated templates for the same EnumKind
    ENG_0 = DOType(cdc='ENG')
    ENG_0.createDictDO()
    ENG_0.addDAToDOType(bType='Enum', fc='SP', nameDA='setVal', typeDA='PseudoEnumKind')
    ENG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ENG_0.organizeDictDO()
    DOTemplates.ENG_0 = ENG_0

    # ENS_0
    # This DO template only a reference presenting how an ENS DO is supposed to look like.
    # It does not contain valid information as the Enum Type must be specified for each Enum Kind
    # To use this DO typeDA correctly, always tracking the calling of Enum typeDA DO and initialized explicit
    # DO Template dynamically. Remember not to create duplicated templates for the same EnumKind
    ENS_0 = DOType(cdc='ENS')
    ENS_0.createDictDO()
    ENS_0.addDAToDOType(bType='Enum', fc='ST', nameDA='stVal', dchg='true', dupd='true', typeDA='PseudoEnumKind')
    ENS_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    ENS_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    ENS_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ENS_0.organizeDictDO()
    DOTemplates.ENS_0 = ENS_0

    # LPL_0
    LPL_0 = DOType(cdc='LPL')
    LPL_0.createDictDO()
    LPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='vendor')
    LPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='swRev')
    LPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='configRev')  # mandatory in LLN0
    LPL_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    LPL_0.organizeDictDO()
    DOTemplates.LPL_0 = LPL_0

    # INC_0
    INC_0 = DOType(cdc='INC')
    INC_0.createDictDO()
    INC_0.addDAToDOType(bType='Struct', fc='ST', nameDA='origin', typeDA='Originator_0')  # optional DA
    INC_0.addDAToDOType(bType='INT8U', fc='ST', nameDA='ctlNum')  # optional DA
    INC_0.addDAToDOType(bType='INT32', fc='ST', nameDA='stVal', dchg='true', dupd='true')
    INC_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    INC_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    INC_0.addDAToDOType(bType='Enum', fc='CF', nameDA='ctlModel', typeDA='CtlModelKind')
    INC_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    INC_0.addDAToDOType(bType='INT32', fc='CO', nameDA='ctlVal')
    INC_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    INC_0.organizeDictDO()
    DOTemplates.INC_0 = INC_0

    # ING_0
    ING_0 = DOType(cdc='ING')
    ING_0.createDictDO()
    ING_0.addDAToDOType(bType='INT32', fc='SP', nameDA='setVal', dchg='true')
    ING_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    ING_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ING_0.organizeDictDO()
    DOTemplates.ING_0 = ING_0

    # INS_0
    INS_0 = DOType(cdc='INS')
    INS_0.createDictDO()
    INS_0.addDAToDOType(bType='BOOLEAN', fc='ST', nameDA='stVal', dchg='true')
    INS_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    INS_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    INS_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    INS_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    INS_0.organizeDictDO()
    DOTemplates.INS_0 = INS_0

    # MV_0
    # instMag is not included, as we do not calculate deadband
    MV_0 = DOType(cdc='MV')
    MV_0.createDictDO()
    MV_0.addDAToDOType(bType='Struct', fc='MX', nameDA='mag', dchg='true', dupd='true', typeDA='AnalogueValue_0')
    MV_0.addDAToDOType(bType='Quality', fc='MX', nameDA='q', qchg='true')
    MV_0.addDAToDOType(bType='Timestamp', fc='MX', nameDA='t')
    MV_0.addDAToDOType(bType='Struct', fc='CF', nameDA='units', dchg='true', typeDA='Unit_0')  # optional DA
    MV_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    MV_0.organizeDictDO()
    DOTemplates.MV_0 = MV_0

    # ORG_0
    # ObjRef changed to ObjectReference
    ORG_0 = DOType(cdc='ORG')
    ORG_0.createDictDO()
    ORG_0.addDAToDOType(bType='ObjectReference', fc='ST', nameDA='setSrcRef', dchg='true')
    ORG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ORG_0.organizeDictDO()
    DOTemplates.ORG_0 = ORG_0

    # ORS_0
    ORS_0 = DOType(cdc='ORS')
    ORS_0.createDictDO()
    ORS_0.addDAToDOType(bType='ObjectReference', fc='ST', nameDA='stVal', dchg='true')
    ORS_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    ORS_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    ORS_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    ORS_0.organizeDictDO()
    DOTemplates.ORS_0 = ORS_0

    # SPC_0
    SPC_0 = DOType(cdc='SPC')
    SPC_0.createDictDO()
    SPC_0.addDAToDOType(bType='Struct', fc='ST', nameDA='origin', typeDA='Originator_0')  # optional DA
    SPC_0.addDAToDOType(bType='INT8U', fc='ST', nameDA='ctlNum')  # optional DA
    SPC_0.addDAToDOType(bType='BOOLEAN', fc='ST', nameDA='stVal', dchg='true')
    SPC_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    SPC_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    SPC_0.addDAToDOType(bType='Enum', fc='CF', nameDA='ctlModel', typeDA='CtlModelKind')
    SPC_0.addDAToDOType(bType='BOOLEAN', fc='CO', nameDA='ctlVal')
    SPC_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    SPC_0.organizeDictDO()
    DOTemplates.SPC_0 = SPC_0

    # SPG_0
    SPG_0 = DOType(cdc='SPG')
    SPG_0.createDictDO()
    SPG_0.addDAToDOType(bType='BOOLEAN', fc='SP', nameDA='setVal', dchg='true')
    SPG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    SPG_0.organizeDictDO()
    DOTemplates.SPG_0 = SPG_0

    # SPS_0
    SPS_0 = DOType(cdc='SPS')
    SPS_0.createDictDO()
    SPS_0.addDAToDOType(bType='INT32', fc='ST', nameDA='stVal', dchg='true')
    SPS_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    SPS_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    SPS_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    SPS_0.organizeDictDO()
    DOTemplates.SPS_0 = SPS_0

    # TCS_0
    TCS_0 = DOType(cdc='TCS')
    TCS_0.createDictDO()
    TCS_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='stVal', dchg='true', dupd='true')
    TCS_0.addDAToDOType(bType='Quality', fc='ST', nameDA='q', qchg='true')
    TCS_0.addDAToDOType(bType='Timestamp', fc='ST', nameDA='t')
    TCS_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    TCS_0.organizeDictDO()
    DOTemplates.TCS_0 = TCS_0

    # TSG_0
    TSG_0 = DOType(cdc='TSG')
    TSG_0.createDictDO()
    TSG_0.addDAToDOType(bType='Timestamp', fc='SP', nameDA='setTm', dchg='true')
    TSG_0.addDAToDOType(bType='Struct', fc='SP', nameDA='setCal', dchg='true', typeDA='CalendarTime_0')
    TSG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    TSG_0.organizeDictDO()
    DOTemplates.TSG_0 = TSG_0

    # VSG_0
    VSG_0 = DOType(cdc='VSG')
    VSG_0.createDictDO()
    VSG_0.addDAToDOType(bType='VisString255', fc='SP', nameDA='setVal', dchg='true')
    VSG_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    VSG_0.organizeDictDO()
    DOTemplates.VSG_0 = VSG_0

    # WYE_0
    # note we added several SDO to the DO here, not only DA
    WYE_0 = DOType(cdc='WYE')
    WYE_0.createDictDO()
    WYE_0.addSDOToDOType(nameSDO='phsA', typeSDO='CMV_0', descSDO='Value of phase A')
    WYE_0.addSDOToDOType(nameSDO='phsB', typeSDO='CMV_0', descSDO='Value of phase B')
    WYE_0.addSDOToDOType(nameSDO='phsC', typeSDO='CMV_0', descSDO='Value of phase C')
    WYE_0.addSDOToDOType(nameSDO='neut', typeSDO='CMV_0', descSDO='Value of measured phase neutral')
    WYE_0.addSDOToDOType(nameSDO='net', typeSDO='CMV_0', descSDO='net value')
    WYE_0.addSDOToDOType(nameSDO='res', typeSDO='CMV_0', descSDO='residual value')
    WYE_0.addDAToDOType(bType='VisString255', fc='DC', nameDA='d')  # optional DA
    WYE_0.organizeDictDO()
    DOTemplates.WYE_0 = WYE_0

    Config.listTemplateDO = list(DOTemplates.__dict__)

    return DOTemplates


def initLNTemplates():
    """
    Initialize templates for LN Logical Nodes containing DO
    Here are some important notes:
        - LN Templates provides the users LN with all possible DO that are relevant for DER application, this will
            make the scope of the data model kind of out of control
        - A model reduction based on user configuration should be performed later in the main function
        - the usage of _0 for default LNs is inspired by the XML schema in the IEC 61850 engineering tool
            ICD Designer

    Theoretically one can copy all the stuffs here directly from the standard document by hand, well that would take
    quite some time, this approach is not recommended. I noticed that for the parameter mapping, there exists an
    Excel file anyway collecting all the necessary DOs, so a supporting script "templateCodeGenerator.py" to
    automatically generate python codes that initialize essential LN templates. The only thing left is to copy the
    codes from the text file and insert them here.

    Make sure you double-check whether all arguments make sense, while a topology validator will check them anyway.
    """

    LNTemplates = Templates()  # init the template instance for LN

    # TODO: all DOs are added without desc at this stage, consider add them later
    # start initializing templates for LN, alphabetically sorted

    # DCCT_0
    DCCT_0 = LNType(lnClass='DCCT')
    DCCT_0.createDictLN()
    DCCT_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DCCT_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DCCT_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DCCT_0.addDOToLNType(typeDO='CUG_0', nameDO='Ccy')
    DCCT_0.addDOToLNType(typeDO='ASG_0', nameDO='OpCost')
    DCCT_0.addDOToLNType(typeDO='ASG_0', nameDO='OpWhCost')
    DCCT_0.addDOToLNType(typeDO='ASG_0', nameDO='StrCost')
    DCCT_0.addDOToLNType(typeDO='ASG_0', nameDO='StopCost')
    DCCT_0.addDOToLNType(typeDO='ASG_0', nameDO='RampCost')
    DCCT_0.addDOToLNType(typeDO='CSG_0', nameDO='HeatRteCost')
    DCCT_0.addDOToLNType(typeDO='CSG_0', nameDO='CRteCost')
    DCCT_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LNTemplates.DCCT_0 = DCCT_0
    
    # DECP_0
    DECP_0 = LNType(lnClass='DECP')
    DECP_0.createDictLN()
    DECP_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DECP_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DECP_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DECP_0.addDOToLNType(typeDO='ENS_PhaseKind', nameDO='PhsConnTyp')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VRef')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VRefPct')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='WRtg')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VArRtg')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VARtg')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VRtg')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='HzNom')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VMax')
    DECP_0.addDOToLNType(typeDO='ASG_0', nameDO='VMin')
    DECP_0.addDOToLNType(typeDO='VSG_0', nameDO='ElcRefId')
    DECP_0.addDOToLNType(typeDO='SPG_0', nameDO='DERMsIncl')
    DECP_0.addDOToLNType(typeDO='ORG_0', nameDO='ElcMsRef')
    DECP_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LNTemplates.DECP_0 = DECP_0
    
    # DGEN_0
    DGEN_0 = LNType(lnClass='DGEN')
    DGEN_0.createDictLN()
    DGEN_0.addDOToLNType(typeDO='DPL_0', nameDO='EEName')
    DGEN_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DGEN_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DGEN_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DGEN_0.addDOToLNType(typeDO='SPS_0', nameDO='LocKey')
    DGEN_0.addDOToLNType(typeDO='SPS_0', nameDO='Loc')
    DGEN_0.addDOToLNType(typeDO='ENS_DERSynchronizationKind', nameDO='GnSynSt')
    DGEN_0.addDOToLNType(typeDO='ENS_DERStateKind', nameDO='DEROpSt')
    DGEN_0.addDOToLNType(typeDO='INS_0', nameDO='OpTmh')
    DGEN_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='EEHealth')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='CnstWMax')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='GnEnTot')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='GnEnPer')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='RenWPct')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='RenVArPct')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='VArTot')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='AvarTot')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='IvarTot')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='VArAvl')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='AvarAvl')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='IvarAvl')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='SelfSvcWh')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='VAPct')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='AvlUpW')
    DGEN_0.addDOToLNType(typeDO='MV_0', nameDO='AvlDnW')
    DGEN_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DGEN_0.addDOToLNType(typeDO='SPC_0', nameDO='LocSta')
    DGEN_0.addDOToLNType(typeDO='INC_0', nameDO='GnOnCnt')
    DGEN_0.addDOToLNType(typeDO='INC_0', nameDO='TotStrCnt')
    DGEN_0.addDOToLNType(typeDO='INC_0', nameDO='PerStrCnt')
    DGEN_0.addDOToLNType(typeDO='INC_0', nameDO='OpTms')
    DGEN_0.addDOToLNType(typeDO='SPC_0', nameDO='GnEnPerRs')
    DGEN_0.addDOToLNType(typeDO='ENC_DERStateTransitionKind', nameDO='DEROpStCtl')
    DGEN_0.addDOToLNType(typeDO='APC_0', nameDO='WSpt')
    DGEN_0.addDOToLNType(typeDO='APC_0', nameDO='VArSpt')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='OutWSet')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='OutVarSet')
    DGEN_0.addDOToLNType(typeDO='INC_0', nameDO='OpCntRs')
    DGEN_0.addDOToLNType(typeDO='ORG_0', nameDO='InclGn')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='WMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VAMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VArMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='AvarMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='IvarMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='AMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VMinRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='WRpuMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='WRpdMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='CtbWMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='CtbVArMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='WMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='WRmp')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VArMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='AvarMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='IvarMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VMin')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='AMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='VAMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='AvaMax')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='IvaMax')
    DGEN_0.addDOToLNType(typeDO='ENG_ReactivePowerRefParamKind', nameDO='VArSptRef')
    DGEN_0.addDOToLNType(typeDO='ENG_ECPConnKind', nameDO='EcpConnTyp')
    DGEN_0.addDOToLNType(typeDO='ENG_PhaseKind', nameDO='PhsConnTyp')
    DGEN_0.addDOToLNType(typeDO='ENG_DERUnitKind', nameDO='DERTyp')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='TmpMaxRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfWRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfVRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfPFRtg')
    DGEN_0.addDOToLNType(typeDO='SPG_0', nameDO='RvSeq')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfVRngRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='EfcRtgPct')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='HzNomRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='HzMinRtg')
    DGEN_0.addDOToLNType(typeDO='ASG_0', nameDO='HzMaxRtg')
    DGEN_0.addDOToLNType(typeDO='VSG_0', nameDO='DERId')
    LNTemplates.DGEN_0 = DGEN_0
    
    # DINV_0
    DINV_0 = LNType(lnClass='DINV')
    DINV_0.createDictLN()
    DINV_0.addDOToLNType(typeDO='DPL_0', nameDO='EEName')
    DINV_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DINV_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DINV_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DINV_0.addDOToLNType(typeDO='SPS_0', nameDO='LocKey')
    DINV_0.addDOToLNType(typeDO='SPS_0', nameDO='Loc')
    DINV_0.addDOToLNType(typeDO='SPS_0', nameDO='InvACLosAlm')
    DINV_0.addDOToLNType(typeDO='SPS_0', nameDO='InvDCLosAlm')
    DINV_0.addDOToLNType(typeDO='SPS_0', nameDO='InvGriLosAl')
    DINV_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='EEHealth')
    DINV_0.addDOToLNType(typeDO='INS_0', nameDO='OpTmh')
    DINV_0.addDOToLNType(typeDO='APC_0', nameDO='WSpt')
    DINV_0.addDOToLNType(typeDO='APC_0', nameDO='VArSpt')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='OutWSet')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='OutVarSet')
    DINV_0.addDOToLNType(typeDO='ENG_InverterControlSourceKind', nameDO='InvCtlSrc')
    DINV_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DINV_0.addDOToLNType(typeDO='SPC_0', nameDO='LocSta')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='WRtg')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='VARtg')
    DINV_0.addDOToLNType(typeDO='CSG_0', nameDO='WVArVLim')
    DINV_0.addDOToLNType(typeDO='CSG_0', nameDO='WVArVLimSet')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='SwHz')
    DINV_0.addDOToLNType(typeDO='ENG_CoolingMethodKind', nameDO='ClMthTyp')
    DINV_0.addDOToLNType(typeDO='ENG_IsolationKind', nameDO='IsoTyp')
    DINV_0.addDOToLNType(typeDO='ENG_ACSystemKind', nameDO='ACTyp')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='InAMax')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='InVMax')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='VArRtg')
    DINV_0.addDOToLNType(typeDO='ASG_0', nameDO='VRtg')
    LNTemplates.DINV_0 = DINV_0
    
    # DLOD_0
    DLOD_0 = LNType(lnClass='DLOD')
    DLOD_0.createDictLN()
    DLOD_0.addDOToLNType(typeDO='DPL_0', nameDO='EEName')
    DLOD_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DLOD_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DLOD_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DLOD_0.addDOToLNType(typeDO='SPS_0', nameDO='LocKey')
    DLOD_0.addDOToLNType(typeDO='SPS_0', nameDO='Loc')
    DLOD_0.addDOToLNType(typeDO='ENS_DERStateKind', nameDO='DEROpSt')
    DLOD_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='EEHealth')
    DLOD_0.addDOToLNType(typeDO='INS_0', nameDO='OpTmh')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='VArTot')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='AvarTot')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='IvarTot')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='VArAvl')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='AvarAvl')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='IvarAvl')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='SelfSvcWh')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='VAPct')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='AvlUpW')
    DLOD_0.addDOToLNType(typeDO='MV_0', nameDO='AvlDnW')
    DLOD_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DLOD_0.addDOToLNType(typeDO='SPC_0', nameDO='LocSta')
    DLOD_0.addDOToLNType(typeDO='ENC_DERStateTransitionKind', nameDO='DEROpStCtl')
    DLOD_0.addDOToLNType(typeDO='APC_0', nameDO='WSpt')
    DLOD_0.addDOToLNType(typeDO='APC_0', nameDO='VArSpt')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='OutWSet')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='OutVarSet')
    DLOD_0.addDOToLNType(typeDO='INC_0', nameDO='OpCntRs')
    DLOD_0.addDOToLNType(typeDO='ORG_0', nameDO='DERUnit')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='WMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VMinRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='AMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VAMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='WRpuMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='WRpdMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='WMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='WRmp')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VArMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='AvarMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='IvarMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VMin')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='AMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='VAMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='AvaMax')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='IvaMax')
    DLOD_0.addDOToLNType(typeDO='ENG_ReactivePowerRefParamKind', nameDO='VArSptRef')
    DLOD_0.addDOToLNType(typeDO='ORG_0', nameDO='OutEcpRef')
    DLOD_0.addDOToLNType(typeDO='ENG_ECPConnKind', nameDO='EcpConnTyp')
    DLOD_0.addDOToLNType(typeDO='ENG_PhaseKind', nameDO='PhsConnTyp')
    DLOD_0.addDOToLNType(typeDO='ENG_DERUnitKind', nameDO='DERTyp')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='TmpMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='FltRtgPct')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='FltAMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfVRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='FltDurMaxTms')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfWRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfPFRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfVRngRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='EfcRtgPct')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='HzNomRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='HzMinRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='HzMaxRtg')
    DLOD_0.addDOToLNType(typeDO='ASG_0', nameDO='DERId')
    LNTemplates.DLOD_0 = DLOD_0
    
    # DPCC_0
    DPCC_0 = LNType(lnClass='DPCC')
    DPCC_0.createDictLN()
    DPCC_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DPCC_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DPCC_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DPCC_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DPCC_0.addDOToLNType(typeDO='VSG_0', nameDO='AreaEpsEcpId')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='AreaEpsWMax')
    DPCC_0.addDOToLNType(typeDO='ENS_PhaseKind', nameDO='PhsConnTyp')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VRef')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VRefPct')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='WRtg')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VArRtg')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VARtg')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VRtg')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='HzNom')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VMax')
    DPCC_0.addDOToLNType(typeDO='ASG_0', nameDO='VMin')
    DPCC_0.addDOToLNType(typeDO='VSG_0', nameDO='ElcRefId')
    DPCC_0.addDOToLNType(typeDO='SPG_0', nameDO='DERMsIncl')
    DPCC_0.addDOToLNType(typeDO='ORG_0', nameDO='ElcMsRef')
    LNTemplates.DPCC_0 = DPCC_0
    
    # DPMC_0
    DPMC_0 = LNType(lnClass='DPMC')
    DPMC_0.createDictLN()
    DPMC_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DPMC_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DPMC_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DPMC_0.addDOToLNType(typeDO='ORS_0', nameDO='WTopFct')
    DPMC_0.addDOToLNType(typeDO='ORS_0', nameDO='VArTopFct')
    DPMC_0.addDOToLNType(typeDO='SPS_0', nameDO='LocKey')
    DPMC_0.addDOToLNType(typeDO='SPS_0', nameDO='Loc')
    DPMC_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DPMC_0.addDOToLNType(typeDO='SPC_0', nameDO='LocSta')
    DPMC_0.addDOToLNType(typeDO='MV_0', nameDO='ReqTotW')
    DPMC_0.addDOToLNType(typeDO='MV_0', nameDO='ReqTotWMin')
    DPMC_0.addDOToLNType(typeDO='MV_0', nameDO='ReqTotWMax')
    DPMC_0.addDOToLNType(typeDO='APC_0', nameDO='WSpt')
    DPMC_0.addDOToLNType(typeDO='ASG_0', nameDO='OutWSet')
    DPMC_0.addDOToLNType(typeDO='APC_0', nameDO='WMinSpt')
    DPMC_0.addDOToLNType(typeDO='APC_0', nameDO='WMaxSpt')
    LNTemplates.DPMC_0 = DPMC_0
    
    # DCST_0
    DCST_0 = LNType(lnClass='DCST')
    DCST_0.createDictLN()
    DCST_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DCST_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DCST_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DCST_0.addDOToLNType(typeDO='CUG_0', nameDO='Ccy')
    DCST_0.addDOToLNType(typeDO='CSG_0', nameDO='HeatRteAct')
    DCST_0.addDOToLNType(typeDO='CSG_0', nameDO='HeatRteCost')
    DCST_0.addDOToLNType(typeDO='ASG_0', nameDO='StrCost')
    DCST_0.addDOToLNType(typeDO='ASG_0', nameDO='StopCost')
    DCST_0.addDOToLNType(typeDO='ASG_0', nameDO='RampCost')
    DCST_0.addDOToLNType(typeDO='CSG_0', nameDO='CRteCost')
    DCST_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LNTemplates.DCST_0 = DCST_0
    
    # DSTO_0
    DSTO_0 = LNType(lnClass='DSTO')
    DSTO_0.createDictLN()
    DSTO_0.addDOToLNType(typeDO='DPL_0', nameDO='EEName')
    DSTO_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DSTO_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DSTO_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='LocKey')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='Loc')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='SocHiAlm')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='SocHiWrn')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='SocLoAlm')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='SocLoWrn')
    DSTO_0.addDOToLNType(typeDO='SPS_0', nameDO='SohLoAlm')
    DSTO_0.addDOToLNType(typeDO='INS_0', nameDO='ChaCycCnt')
    DSTO_0.addDOToLNType(typeDO='ENS_DERStateKind', nameDO='DEROpSt')
    DSTO_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='EEHealth')
    DSTO_0.addDOToLNType(typeDO='INS_0', nameDO='OpTmh')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='InWh')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='OutWh')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='SocWh')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='UseSocPct')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='SocEffWhPct')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='ChaWhTot')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='DschWhTot')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='AvlDschW')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='AvlChaW')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='ChaVAPct')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='AvlChaWTm')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='AvlDschWTm')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='ChaAvarTot')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='DschAvarTot')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='ChaIvarTot')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='DschIvarTot')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='ChaAvarAvl')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='DschAvarAvl')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='ChaIvarAvl')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='DschIvarAvl')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='EffWh')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='EffWhPct')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='SelfSvcWh')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='VAPct')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='AvlUpW')
    DSTO_0.addDOToLNType(typeDO='MV_0', nameDO='AvlDnW')
    DSTO_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DSTO_0.addDOToLNType(typeDO='SPC_0', nameDO='LocSta')
    DSTO_0.addDOToLNType(typeDO='ENC_DERStateTransitionKind', nameDO='DEROpStCtl')
    DSTO_0.addDOToLNType(typeDO='APC_0', nameDO='WSpt')
    DSTO_0.addDOToLNType(typeDO='APC_0', nameDO='VArSpt')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='OutWSet')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='OutVarSet')
    DSTO_0.addDOToLNType(typeDO='INC_0', nameDO='OpCntRs')
    DSTO_0.addDOToLNType(typeDO='ORG_0', nameDO='EqSto')
    DSTO_0.addDOToLNType(typeDO='ORG_0', nameDO='DERUnit')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='SocHiAlsPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='SocHiWrsPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='SocLoAlsPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='SocLoWrsPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='SohLoAlsPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='RntEffPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaWMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschWMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaWRmpRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschWRmpRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVAMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVAMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaAvarRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschAvarRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaIvarRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschIvarRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVMinRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVMinRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaAMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschAMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='WhRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='WhMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='WhMinRtg')
    DSTO_0.addDOToLNType(typeDO='CSG_0', nameDO='ChaEfcRtg')
    DSTO_0.addDOToLNType(typeDO='CSG_0', nameDO='DschEfcRtg')
    DSTO_0.addDOToLNType(typeDO='ENG_ChargeSourceKind', nameDO='ChaSrcRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaWMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaWRmp')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschWRmp')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschWMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVArMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVArMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVAMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVAMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaAvarMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschAvarMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaIvarMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschIvarMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaVMin')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschVMin')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='ChaAMax')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='DschAMax')
    DSTO_0.addDOToLNType(typeDO='CSG_0', nameDO='ChaEfc')
    DSTO_0.addDOToLNType(typeDO='CSG_0', nameDO='DschEfc')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='UseWhMaxPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='UseWhMinPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='UseWh')
    DSTO_0.addDOToLNType(typeDO='ENG_ChargeSourceKind', nameDO='ChaSrc')
    DSTO_0.addDOToLNType(typeDO='SPG_0', nameDO='RenChaEna')
    DSTO_0.addDOToLNType(typeDO='ORG_0', nameDO='OutEcpRef')
    DSTO_0.addDOToLNType(typeDO='ENG_ECPConnKind', nameDO='EcpConnTyp')
    DSTO_0.addDOToLNType(typeDO='ENG_PhaseKind', nameDO='PhsConnTyp')
    DSTO_0.addDOToLNType(typeDO='ENG_DERUnitKind', nameDO='DERTyp')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='TmpMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='FltRtgPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='FltAMaxRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='SelfVRtg')
    DSTO_0.addDOToLNType(typeDO='ING_0', nameDO='FltDurMaxTms')
    DSTO_0.addDOToLNType(typeDO='ING_0', nameDO='SelfWRtg')
    DSTO_0.addDOToLNType(typeDO='ING_0', nameDO='SelfPFRtg')
    DSTO_0.addDOToLNType(typeDO='ING_0', nameDO='SelfVRngRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='EfcRtgPct')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='HzNomRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='HzMinRtg')
    DSTO_0.addDOToLNType(typeDO='ASG_0', nameDO='HzMaxRtg')
    DSTO_0.addDOToLNType(typeDO='VSG_0', nameDO='DERId')
    LNTemplates.DSTO_0 = DSTO_0
    
    # DVER_0
    DVER_0 = LNType(lnClass='DVER')
    DVER_0.createDictLN()
    DVER_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    DVER_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    DVER_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    DVER_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    DVER_0.addDOToLNType(typeDO='ORG_0', nameDO='InclElcRef')
    DVER_0.addDOToLNType(typeDO='VSG_0', nameDO='ElcRefId')
    DVER_0.addDOToLNType(typeDO='ORG_0', nameDO='ElcMsRef')
    LNTemplates.DVER_0 = DVER_0
    
    # FSCC_INS0
    FSCC_INS0 = LNType(lnClass='FSCC', idLN='FSCC_INS0')
    FSCC_INS0.createDictLN()
    FSCC_INS0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCC_INS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCC_INS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCC_INS0.addDOToLNType(typeDO='ORS_0', nameDO='ActSchdRef')
    FSCC_INS0.addDOToLNType(typeDO='INS_0', nameDO='ValINS')
    FSCC_INS0.addDOToLNType(typeDO='ORG_0', nameDO='CtlEnt')
    FSCC_INS0.addDOToLNType(typeDO='ORG_0', nameDO='Schd')
    FSCC_INS0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCC_INS0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCC_INS0 = FSCC_INS0
    
    # FSCC_SPS0
    FSCC_SPS0 = LNType(lnClass='FSCC', idLN='FSCC_SPS0')
    FSCC_SPS0.createDictLN()
    FSCC_SPS0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCC_SPS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCC_SPS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCC_SPS0.addDOToLNType(typeDO='ORS_0', nameDO='ActSchdRef')
    FSCC_SPS0.addDOToLNType(typeDO='SPS_0', nameDO='ValSPS')
    FSCC_SPS0.addDOToLNType(typeDO='ORG_0', nameDO='CtlEnt')
    FSCC_SPS0.addDOToLNType(typeDO='ORG_0', nameDO='Schd')
    FSCC_SPS0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCC_SPS0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCC_SPS0 = FSCC_SPS0
    
    # FSCC_ENS0
    FSCC_ENS0 = LNType(lnClass='FSCC', idLN='FSCC_ENS0')
    FSCC_ENS0.createDictLN()
    FSCC_ENS0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCC_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCC_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCC_ENS0.addDOToLNType(typeDO='ORS_0', nameDO='ActSchdRef')
    FSCC_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='ValENS')
    FSCC_ENS0.addDOToLNType(typeDO='ORG_0', nameDO='CtlEnt')
    FSCC_ENS0.addDOToLNType(typeDO='ORG_0', nameDO='Schd')
    FSCC_ENS0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCC_ENS0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCC_ENS0 = FSCC_ENS0
    
    # FSCC_MV0
    FSCC_MV0 = LNType(lnClass='FSCC', idLN='FSCC_MV0')
    FSCC_MV0.createDictLN()
    FSCC_MV0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCC_MV0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCC_MV0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCC_MV0.addDOToLNType(typeDO='ORS_0', nameDO='ActSchdRef')
    FSCC_MV0.addDOToLNType(typeDO='MV_0', nameDO='ValMV')
    FSCC_MV0.addDOToLNType(typeDO='ORG_0', nameDO='CtlEnt')
    FSCC_MV0.addDOToLNType(typeDO='ORG_0', nameDO='Schd')
    FSCC_MV0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCC_MV0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCC_MV0 = FSCC_MV0
    
    # FSCH_INS0
    FSCH_INS0 = LNType(lnClass='FSCH', idLN='FSCH_INS0')
    FSCH_INS0.createDictLN()
    FSCH_INS0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCH_INS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCH_INS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCH_INS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdSt')
    FSCH_INS0.addDOToLNType(typeDO='INS_0', nameDO='SchdEntr')
    FSCH_INS0.addDOToLNType(typeDO='INS_0', nameDO='ValINS')
    FSCH_INS0.addDOToLNType(typeDO='TCS_0', nameDO='ActStrTm')
    FSCH_INS0.addDOToLNType(typeDO='TCS_0', nameDO='NxtStrTm')
    FSCH_INS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdEnaErr')
    FSCH_INS0.addDOToLNType(typeDO='SPC_0', nameDO='EnaReq')
    FSCH_INS0.addDOToLNType(typeDO='SPC_0', nameDO='DsaReq')
    FSCH_INS0.addDOToLNType(typeDO='ING_0', nameDO='SchdPrio')
    FSCH_INS0.addDOToLNType(typeDO='ING_0', nameDO='NumEntr')
    FSCH_INS0.addDOToLNType(typeDO='ING_0', nameDO='SchdIntv')
    FSCH_INS0.addDOToLNType(typeDO='ING_0', nameDO='ValING')
    FSCH_INS0.addDOToLNType(typeDO='TSG_0', nameDO='StrTm')
    FSCH_INS0.addDOToLNType(typeDO='SPG_0', nameDO='EvtTrg')
    FSCH_INS0.addDOToLNType(typeDO='ORG_0', nameDO='InSyn')
    FSCH_INS0.addDOToLNType(typeDO='SPG_0', nameDO='SchdReuse')
    FSCH_INS0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCH_INS0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCH_INS0 = FSCH_INS0
    
    # FSCH_SPS0
    FSCH_SPS0 = LNType(lnClass='FSCH', idLN='FSCH_SPS0')
    FSCH_SPS0.createDictLN()
    FSCH_SPS0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCH_SPS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCH_SPS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCH_SPS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdSt')
    FSCH_SPS0.addDOToLNType(typeDO='INS_0', nameDO='SchdEntr')
    FSCH_SPS0.addDOToLNType(typeDO='SPS_0', nameDO='ValSPS')
    FSCH_SPS0.addDOToLNType(typeDO='TCS_0', nameDO='ActStrTm')
    FSCH_SPS0.addDOToLNType(typeDO='TCS_0', nameDO='NxtStrTm')
    FSCH_SPS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdEnaErr')
    FSCH_SPS0.addDOToLNType(typeDO='SPC_0', nameDO='EnaReq')
    FSCH_SPS0.addDOToLNType(typeDO='SPC_0', nameDO='DsaReq')
    FSCH_SPS0.addDOToLNType(typeDO='ING_0', nameDO='SchdPrio')
    FSCH_SPS0.addDOToLNType(typeDO='ING_0', nameDO='NumEntr')
    FSCH_SPS0.addDOToLNType(typeDO='ING_0', nameDO='SchdIntv')
    FSCH_SPS0.addDOToLNType(typeDO='SPG_0', nameDO='ValSPG')
    FSCH_SPS0.addDOToLNType(typeDO='TSG_0', nameDO='StrTm')
    FSCH_SPS0.addDOToLNType(typeDO='SPG_0', nameDO='EvtTrg')
    FSCH_SPS0.addDOToLNType(typeDO='ORG_0', nameDO='InSyn')
    FSCH_SPS0.addDOToLNType(typeDO='SPG_0', nameDO='SchdReuse')
    FSCH_SPS0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCH_SPS0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCH_SPS0 = FSCH_SPS0
    
    # FSCH_ENS0
    FSCH_ENS0 = LNType(lnClass='FSCH', idLN='FSCH_ENS0')
    FSCH_ENS0.createDictLN()
    FSCH_ENS0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCH_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCH_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCH_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdSt')
    FSCH_ENS0.addDOToLNType(typeDO='INS_0', nameDO='SchdEntr')
    FSCH_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='ValENS')
    FSCH_ENS0.addDOToLNType(typeDO='TCS_0', nameDO='ActStrTm')
    FSCH_ENS0.addDOToLNType(typeDO='TCS_0', nameDO='NxtStrTm')
    FSCH_ENS0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdEnaErr')
    FSCH_ENS0.addDOToLNType(typeDO='SPC_0', nameDO='EnaReq')
    FSCH_ENS0.addDOToLNType(typeDO='SPC_0', nameDO='DsaReq')
    FSCH_ENS0.addDOToLNType(typeDO='ING_0', nameDO='SchdPrio')
    FSCH_ENS0.addDOToLNType(typeDO='ING_0', nameDO='NumEntr')
    FSCH_ENS0.addDOToLNType(typeDO='ING_0', nameDO='SchdIntv')
    FSCH_ENS0.addDOToLNType(typeDO='ENG_PseudoEnumKind', nameDO='ValENG')
    FSCH_ENS0.addDOToLNType(typeDO='TSG_0', nameDO='StrTm')
    FSCH_ENS0.addDOToLNType(typeDO='SPG_0', nameDO='EvtTrg')
    FSCH_ENS0.addDOToLNType(typeDO='ORG_0', nameDO='InSyn')
    FSCH_ENS0.addDOToLNType(typeDO='SPG_0', nameDO='SchdReuse')
    FSCH_ENS0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCH_ENS0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCH_ENS0 = FSCH_ENS0
    
    # FSCH_MV0
    FSCH_MV0 = LNType(lnClass='FSCH', idLN='FSCH_MV0')
    FSCH_MV0.createDictLN()
    FSCH_MV0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    FSCH_MV0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Beh')
    FSCH_MV0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='Health')
    FSCH_MV0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdSt')
    FSCH_MV0.addDOToLNType(typeDO='INS_0', nameDO='SchdEntr')
    FSCH_MV0.addDOToLNType(typeDO='TCS_0', nameDO='ActStrTm')
    FSCH_MV0.addDOToLNType(typeDO='TCS_0', nameDO='NxtStrTm')
    FSCH_MV0.addDOToLNType(typeDO='ENS_PseudoEnumKind', nameDO='SchdEnaErr')
    FSCH_MV0.addDOToLNType(typeDO='MV_0', nameDO='ValMV')
    FSCH_MV0.addDOToLNType(typeDO='SPC_0', nameDO='EnaReq')
    FSCH_MV0.addDOToLNType(typeDO='SPC_0', nameDO='DsaReq')
    FSCH_MV0.addDOToLNType(typeDO='ING_0', nameDO='SchdPrio')
    FSCH_MV0.addDOToLNType(typeDO='ING_0', nameDO='NumEntr')
    FSCH_MV0.addDOToLNType(typeDO='ING_0', nameDO='SchdIntv')
    FSCH_MV0.addDOToLNType(typeDO='ASG_0', nameDO='ValASG')
    FSCH_MV0.addDOToLNType(typeDO='TSG_0', nameDO='StrTm')
    FSCH_MV0.addDOToLNType(typeDO='SPG_0', nameDO='EvtTrg')
    FSCH_MV0.addDOToLNType(typeDO='ORG_0', nameDO='InSyn')
    FSCH_MV0.addDOToLNType(typeDO='SPG_0', nameDO='SchdReuse')
    FSCH_MV0.addDOToLNType(typeDO='ORG_0', nameDO='InRef')
    FSCH_MV0.addDOToLNType(typeDO='ENC_PseudoEnumKind', nameDO='Mod')
    LNTemplates.FSCH_MV0 = FSCH_MV0
    
    # LLN0_0
    LLN0_0 = LNType(lnClass='LLN0')
    LLN0_0.createDictLN()
    LLN0_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    LLN0_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    LLN0_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    LLN0_0.addDOToLNType(typeDO='SPS_0', nameDO='LocKey')
    LLN0_0.addDOToLNType(typeDO='SPS_0', nameDO='Loc')
    LLN0_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LLN0_0.addDOToLNType(typeDO='SPC_0', nameDO='LocSta')
    LLN0_0.addDOToLNType(typeDO='SPG_0', nameDO='MltLev')
    LNTemplates.LLN0_0 = LLN0_0
    
    # LPHD_0
    LPHD_0 = LNType(lnClass='LPHD')
    LPHD_0.createDictLN()
    LPHD_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    LPHD_0.addDOToLNType(typeDO='DPL_0', nameDO='PhyNam')
    LPHD_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='PhyHealth')
    LPHD_0.addDOToLNType(typeDO='SPS_0', nameDO='Proxy')
    LNTemplates.LPHD_0 = LPHD_0
    
    # MMET_0
    MMET_0 = LNType(lnClass='MMET')
    MMET_0.createDictLN()
    MMET_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    MMET_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    MMET_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='PoaInsol')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='EnvTmp')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='WetBlbTmp')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='CloudCvr')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='EnvHum')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='DewPt')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='DffInsol')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='DctInsol')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='DlDur')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='HorInsol')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='HorWdDir')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='HorWdSpd')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='VerWdDir')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='VerWdSpd')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='WdGustSpd')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='EnvPres')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='RnFll')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='SnwDen')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='SnwTmp')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='SnwCvr')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='SnwFll')
    MMET_0.addDOToLNType(typeDO='MV_0', nameDO='SnwEq')
    MMET_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LNTemplates.MMET_0 = MMET_0
    
    # MMTR_0
    MMTR_0 = LNType(lnClass='MMTR')
    MMTR_0.createDictLN()
    MMTR_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    MMTR_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    MMTR_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='TotVAh')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='TotWh')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='TotVArh')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='SupWh')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='SupVArh')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='DmdWh')
    MMTR_0.addDOToLNType(typeDO='BCR_0', nameDO='DmdVArh')
    MMTR_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LNTemplates.MMTR_0 = MMTR_0
    
    # MMXU_0
    MMXU_0 = LNType(lnClass='MMXU')
    MMXU_0.createDictLN()
    MMXU_0.addDOToLNType(typeDO='LPL_0', nameDO='NamPlt')
    MMXU_0.addDOToLNType(typeDO='ENS_BehaviourModeKind', nameDO='Beh')
    MMXU_0.addDOToLNType(typeDO='ENS_HealthKind', nameDO='Health')
    MMXU_0.addDOToLNType(typeDO='SPS_0', nameDO='PFExtQud')
    MMXU_0.addDOToLNType(typeDO='ENS_QuadrantRunningStateKind', nameDO='PQSt')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='TotW')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='TotVAr')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='TotVA')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='TotPF')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='Hz')
    MMXU_0.addDOToLNType(typeDO='DEL_0', nameDO='PPV')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='PNV')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='PhV')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='A')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='W')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='VAr')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='VA')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='PF')
    MMXU_0.addDOToLNType(typeDO='WYE_0', nameDO='Z')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvAPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvPPVPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvPhVPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvWPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvVAPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvVArPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvPFPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='AvZPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxAPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxPPVPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxPhVPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxWPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxVAPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxVArPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxPFPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MaxZPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinAPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinPPVPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinPhVPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinWPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinVAPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinVArPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinPFPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='MinZPhs')
    MMXU_0.addDOToLNType(typeDO='MV_0', nameDO='HzRte')
    MMXU_0.addDOToLNType(typeDO='ENC_BehaviourModeKind', nameDO='Mod')
    LNTemplates.MMXU_0 = MMXU_0
    


    Config.listTemplateLN = list(LNTemplates.__dict__)

    return LNTemplates


def validateTemplateNames(Template=None, nameIdentifier=None):
    """
    This function validates the instance names. This validation process is essential, as all instance names
    are manually defined, while some variables in the instance (e.g. "id" or "name") are automatically generated.
    The entire framework is based on interlinks by data class names to preserve the hierarchical structure.

    The logs returned by this validator will give the user some hints on the generated templates,
    errors must be corrected before using the templates in other scripts.
    """

    listNameInstances = list(Template.__dict__.keys())
    for item in listNameInstances:
        nameInInstance = Template.__dict__[item].__dict__[nameIdentifier]
        if item != nameInInstance:
            logger.error('The name of the instance "{}" does not '
                         'match the name "{}" in the instance'.format(item, nameInInstance))
    logger.info('Validation of names in {} finished.'.format(Template))


def checkNumberOfTemplates():
    """ Check whether all the generated templates are added to the master template instance"""
    if Config.nGeneratedEnum != len(EnumTemplates.__dict__.keys()):
        logger.error('Inconsistent template number, {} Enum templates should be generated, {} found, \
                     please check typo in code'.format(Config.nGeneratedEnum, len(EnumTemplates.__dict__.keys())))
    else:
        logger.info('{} Enum templates generated in total, the number matches the items in master EnumTemplates'
                    .format(Config.nGeneratedEnum))

    if Config.nGeneratedDO != len(DOTemplates.__dict__.keys()):
        logger.error('Inconsistent template number, {} DO templates should be generated, {} found, \
                     please check typo in code'.format(Config.nGeneratedDO, len(DOTemplates.__dict__.keys())))
    else:
        logger.info('{} DO templates generated in total, the number matches the items in master DOTemplates'
                    .format(Config.nGeneratedDO))

    if Config.nGeneratedDA != len(DATemplates.__dict__.keys()):
        logger.error('Inconsistent template number, {} DA templates should be generated, {} found, \
                     please check typo in code'.format(Config.nGeneratedDA, len(DATemplates.__dict__.keys())))
    else:
        logger.info('{} DA templates generated in total, the number matches the items in master DATemplates'
                    .format(Config.nGeneratedDA))

    if Config.nGeneratedLN != len(LNTemplates.__dict__.keys()):
        logger.error('Inconsistent template number, {} LN templates should be generated, {} found, \
                     please check typo in code'.format(Config.nGeneratedLN, len(LNTemplates.__dict__.keys())))
    else:
        logger.info('{} LN templates generated in total, the number matches the items in master LNTemplates'
                    .format(Config.nGeneratedLN))

def genIEC61850Templates():
    """ Generate IEC 61850 templates. """

    # TODO: here the templates are declared as global variables to enable crossing use.
    #   Check whether this could be a problem.

    global EnumTemplates, DATemplates, DOTemplates, LNTemplates
    
    EnumTemplates = initEnumTemplates()
    DATemplates = initDATemplates()
    DOTemplates = initDOTemplates()
    LNTemplates = initLNTemplates()

    # Validate Enum templates
    validateTemplateNames(EnumTemplates, 'name')
    validateTemplateNames(DATemplates, 'id')
    validateTemplateNames(DOTemplates, 'id')
    validateTemplateNames(LNTemplates, 'id')

    # check template number
    checkNumberOfTemplates()
    
    return EnumTemplates, DATemplates, DOTemplates, LNTemplates

def test_templateGenerator():
    """ A simply test function to validate the function outputs """

    [EnumTemplates, DATemplates, DOTemplates, LNTemplates] = genIEC61850Templates()

if '__name__' == '__main__':
    test_templateGenerator()
