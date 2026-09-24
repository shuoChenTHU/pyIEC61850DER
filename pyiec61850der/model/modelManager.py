# -*- coding: utf-8 -*-
"""
@author: chen
"""

# standard python libs
import xmltodict
from collections import OrderedDict
import sys
import os
import uuid
import pandas as pd
import os
import numpy as np

# project relevant libs
import model.iec61850DataTemplates as iec61850DataTemplates

def updateEnumInSP5(filename='config_SP5_Enum.xml'):
    """
    This script can be used to update the XML file that reflects the Enum definitions in the Siemens SCADA system of
    type Spectrum Power 5 v5.40.
    It takes the filename of the Enum XML as the single input, update the content of it and returns the updated
    XML file, to avoid issues due to filename change, the original file will be overwritten. So careful when using this
    script, run it only when you know the contents of the original XML well.
    """

    """ read the xml config file """
    pathXML = './model/{}'.format(filename) # for debugger: this fixed working dir could be a bug maker
    with open(pathXML, 'r', encoding='utf-8') as fo:
        dictEnum = xmltodict.parse(fo.read())
    dictEnumExisting = dictEnum['XDF']['Instances']['Parent']['ValueAliasSets']['ValueAliasSet']
    listEnumExisting = [item['@Name'] for item in dictEnumExisting] 
    dictEnumUpdated = dictEnum.copy()
        
    """ get Enum Template list """
    [EnumTemplates, DATemplates, DOTemplates, LNTemplates] = iec61850DataTemplates.genIEC61850Templates()

    """ update the XML dictionary """
    for enum in EnumTemplates.__dict__:
        dictThisEnum = EnumTemplates.__dict__[enum].dict
        nameThisEnum = dictThisEnum['@id']
        if nameThisEnum in listEnumExisting:
            print('{} already exists in the Enum list, check if it is necessary to update it manually'.format(nameThisEnum))
        else:
            listValueToAlias = []
            for pair in dictThisEnum['EnumVal']:
                if '/' in pair['#text']:
                    valText = pair['#text'].replace('/', '-') ## special char / not allowed
                    valName = pair['#text'].replace('/', '-') ## special char / not allowed
                elif len(pair['#text']) >=33:
                    valText = pair['#text'][0:32]
                    valName = pair['#text']
                elif pair['#text'] == '':
                    valText = 'None'
                    valName = 'None'
                else:
                    valText = pair['#text']
                    valName = pair['#text']
                dictValueToAlias = OrderedDict({('@Name', valName),
                                                ('@Guid', '{' + str(uuid.uuid4()) + '}'),
                                                ('@ValueCode', pair['@ord']),
                                                ('@ValidForManualUpdate', 'true'),
                                                ('@ValidForControl', 'true'),
                                                ('@TextString', valText),
                                                ('@IsAlarmState', 'false'),
                                                ('@pathName', None),
                                                ('@mRID', None),
                                                ('@localName', None),
                                                ('@Description', None),
                                                ('@aliasName', None),
                                                })
                listValueToAlias.append(dictValueToAlias)
    
            dictValueAliasSet = OrderedDict([('@Name', nameThisEnum),
                                             ('@Guid', '{' + str(uuid.uuid4()) + '}'),
                                             ('@DisplayUnit', 'false'),
                                             ('@DecimalPlaces', 0),
                                             ('@pathName', ''),
                                             ('@mRID', None),
                                             ('@localName', None),
                                             ('@Description', None),
                                             ('@aliasName', None),
                                             ('ValueToAlias', listValueToAlias),
                                             ])
            dictEnum['XDF']['Instances']['Parent']['ValueAliasSets']['ValueAliasSet'].append(dictValueAliasSet)
            print('{} successfully added to the Enum Kind list'.format(nameThisEnum))
        
    """ Export the dictionary into an XML file """
    with open(pathXML, 'wt', encoding='utf-8') as fo:
        xmltodict.unparse(dictEnumUpdated, fo, pretty=True)


def templateCodeGenerator(filename='config_IEC61850_LN_DA.xlsx'):
    """
    This function can help to generate codes that initialize LNTemplate, therefore manual work for copy-paste could
    be saved. It takes a XLSX file with lists of DO and cdc type, pass the path of this file as the only input arg,
    then the code would generate a text file with the expected codes for you!
    """
    # TODO: implement a method to eliminate duplicated DO

    LINE_ADD = "<nameLN>_0.addDOToLNType(typeDO='<cdcType>_0', nameDO='<nameDO>')\n"
    LINE_ENUM = "<nameLN>_0.addDOToLNType(typeDO='<cdcType>_<EnumKind>', nameDO='<nameDO>')\n"

    LINE_ADD_SCHD = "<nameLN>.addDOToLNType(typeDO='<cdcType>_0', nameDO='<nameDO>')\n"
    LINE_ENUM_SCHD = "<nameLN>.addDOToLNType(typeDO='<cdcType>_<EnumKind>', nameDO='<nameDO>')\n"

    LINE_0 = "# <nameLN>_0\n"
    LINE_1 = "<nameLN>_0 = LNType(lnClass='<nameLN>')\n"
    LINE_2 = "<nameLN>_0.createDictLN()\n"
    LINE_END = "LNTemplates.<nameLN>_0 = <nameLN>_0\n"

    LINE_0_SCHD = "# <nameLN>\n"
    LINE_1_SCHD = "<nameLN> = LNType(lnClass='<classLN>', idLN='<idLN>')\n"
    LINE_2_SCHD = "<nameLN>.createDictLN()\n"
    LINE_END_SCHD = "LNTemplates.<nameLN> = <nameLN>\n"
    
    listText = []
    filepath = f'./model/{filename}'  # for debugger: this fixed working dir could be a bug maker
    filepathOutput =  './model/autoGenCode.txt'  # for debugger: this fixed working dir could be a bug maker
    
    # get sheet names
    excelFile = pd.ExcelFile(filepath)
    listDF = excelFile.sheet_names
    listDF.sort()
    if 'Note' in listDF:
        listDF.remove('Note')
    
    # iterate through all sheets and generate codes
    for sheet in listDF:
        dfSheet = excelFile.parse(sheet)
        dtSheet = dict(dfSheet)
        listCDC = dtSheet['cdc'].to_list()
        listDO = dtSheet['IEC 61850 DO'].to_list()
        listEnumKind = dtSheet['EnumKind'].to_list()
        nDO = min(len(listCDC), len(listDO), len(listEnumKind))
        
        # append header lines to the list
        # build a special case for Scheduling FSCC and FSCH
        if sheet in ['FSCC', 'FSCH']:
            # The scheduled value should be one of the following
            # monitoring value ['ValINS', 'ValSPS', 'ValENS', 'ValMV']
            # control value ['ValING', 'ValSPG', 'ValENG', 'ValASG']
            # corresponding to the cdc Type ['INS', 'SPS', 'ENS', 'MV'], max one is allowed
            # so there should be 4 templates representing the 4 types of scheduling
            schdType = ['INS', 'SPS', 'ENS', 'MV']
            valTypeMon = ['ValINS', 'ValSPS', 'ValENS', 'ValMV']
            valTypeCtl = ['ValING', 'ValSPG', 'ValENG', 'ValASG']
            
            for idxDA, schd in enumerate(schdType):
                nameLN = '{}_{}0'.format(sheet, schd)  # get cdc type of the scheduled parameter
                valTypeMonDump = valTypeMon.copy()
                valTypeMonDump.pop(idxDA)
                valTypeCtlDump = valTypeCtl.copy()
                valTypeCtlDump.pop(idxDA)
                listDump = valTypeMonDump + valTypeCtlDump  # prepare a list to remove other DAs
                listText.append(LINE_0_SCHD.replace('<nameLN>', nameLN))
                listText.append(LINE_1_SCHD.replace('<nameLN>', nameLN).replace('<classLN>', sheet).replace('<idLN>', nameLN))
                listText.append(LINE_2_SCHD.replace('<nameLN>', nameLN))
                for idx in range(nDO):
                    if listDO[idx] in listDump:
                        continue  # if a DA in the dump list occurs, skip it
                    elif listCDC[idx][0] == 'E':  # detect Enum type
                        # TODO: here "PseudoEnumKind" is used instead of "EnumDA", it is only a place holder
                        listText.append(LINE_ENUM_SCHD.replace('<nameLN>', nameLN).replace('<cdcType>', listCDC[idx]).
                                        replace('<EnumKind>', 'PseudoEnumKind').replace('<nameDO>', listDO[idx]))
                    else:
                        listText.append(LINE_ADD_SCHD.replace('<nameLN>', nameLN).replace('<cdcType>', listCDC[idx]).
                                        replace('<nameDO>', listDO[idx]))          
                listText.append(LINE_END_SCHD.replace('<nameLN>', nameLN))
                listText.append('\n')
                
        else:  # all other LN are considered as normal cases
            listText.append(LINE_0.replace('<nameLN>', sheet))
            listText.append(LINE_1.replace('<nameLN>', sheet))
            listText.append(LINE_2.replace('<nameLN>', sheet))
            for idx in range(nDO):
                if listCDC[idx][0] == 'E':  # detect Enum type
                # TODO: use nan check to detect non-specified Enum type. come up with a better idea.
                    if type(listEnumKind[idx]) is float:
                        if np.isnan(listEnumKind[idx]):
                            print(f'Warning - EnumKind is empty, skip this DO {listDO[idx]}')
                            continue
                        else:
                            listEnumKind[idx] = str(listEnumKind[idx])
                    listText.append(LINE_ENUM.replace('<nameLN>', sheet).replace('<cdcType>', listCDC[idx]).
                                    replace('<EnumKind>', listEnumKind[idx]).replace('<nameDO>', listDO[idx]))
                else:
                    listText.append(LINE_ADD.replace('<nameLN>', sheet).replace('<cdcType>', listCDC[idx]).
                                    replace('<nameDO>', listDO[idx]))
            listText.append(LINE_END.replace('<nameLN>', sheet))                
            listText.append('\n')
    
    # write the codes into a text file
    with open(filepathOutput, 'w') as f:
        f.writelines(listText)
        f.close()
    
    excelFile.close()