# -*- coding: utf-8 -*-

"""
A deprecated testing script for some core functions, no longer in deployment.

This testing script is consisted of several basic tests of the IEC 61850 data modelling,
IED server and virtual CLS functions.

List of available test cases:
    1 - Configurator tester
    2 - Model Generator tester
    3 - IED server tester
    4 - Initialising CLS application tester (static test server)
    5 - Initialising CLS application tester (dynamic customized server)
    6 - IEC 61850 IED client tester (deprecated, use the separat test script iedClientTester)


Attention: this testing script has no error handler, if a test failed, one should execute
the code in the test directly to locate the error.
"""



##############################################################################
######################   defining test cases  ################################
##############################################################################

def runTests(listTests=None):
    '''
    Init test cases and run tests based on user selection.
    To determine the tests for execution, either pass a list of integers as input variable listTests,
    or add them one by one using keyboard. 

    '''
    
    
    dictTests = {0: '0 - Set environment tester',
                 1: '1 - Configurator tester',
                 2: '2 - Model Generator tester',
                 3: '3 - IED server tester',
                 4: '4 - Initialising CLS application tester (dynamic customized server)',
                 }
    
    
    print('Pyiec61850der tester is ready for use, list of testers:')
    for key, value in dictTests.items():
        print(value)
    
    print('\n')
    
    if not listTests:
        try:
            listTests = []
            print('Add new test case by entering the integer index.')
            print('0 for all tests, non-int input (e.q. q) to terminate selection adn start test.')
            while True:
                newTest = input()
                listTests.append(int(newTest))
        except:
            print('The following test cases have been selected:')
            for idx in listTests:
                print(dictTests[idx])
    
    nTest = len(listTests)
    nPass = 0
    
    if -1 in listTests:
        # just a place_holder for systematical module test.
        pass
    
    else:
        if 0 in listTests:
            isPass = testEnvSetter()
            nPass += int(isPass)
        if 1 in listTests:
            [isPass, instConfig] = testConfigurator()
            nPass += int(isPass)
        if 2 in listTests:
            isPass = testModelGenerator()
            nPass += int(isPass)
        if 3 in listTests:
            isPass = testIEDServer(instConfig)
            nPass += int(isPass)
        if 4 in listTests:
            isPass = testInitDynamicCLS()
            nPass += int(isPass)
    
    print(f'{nTest} tests conducted in total, {nPass} passed.')


##############################################################################
######################   set up os environment variable  #####################
##############################################################################

def testEnvSetter():
    try:
        '''
        test setting env
        '''
        
        print('Start the test for the environment setup')
        from settings import config, helper, logger
        helper.set_env_libiec61850()
        
        isPass = True
        print('Test of environment setup has passed.')
    except:
        isPass = False
        print('Test of environment setup has failed.')

    return isPass

##############################################################################
######################   define other test cases     #########################
##############################################################################

def testConfigurator():
    '''
    test settings
    '''
    
    print('Start the test for the settings')
    try:
        from settings import config, helper, logger
        helper.set_env_libiec61850()
        
        from logging import rotating_logger
        logger = rotating_logger('testLogger', 'testLogger')
        
        PATH_CONFIG = './tester/func_tests/configTester.yaml'
        
        instConfig = config.IedConfig()
        instConfig.update_config(PATH_CONFIG)
        config.display_config_info(instConfig)
        config.init_container_time(instConfig)
        
        isPass = True
        print('Test of settings has passed.')
    except:
        isPass = False
        instConfig = None
        print('Test of settings has failed.')

    return isPass, instConfig


def testModelGenerator():
    '''
    Test model generator
    '''
    
    print('Start the test for the IEC 61850 data model generator')
    try:
        import model.iec61850DataModelGenerator as modelGenerator
        import model.iec61850DataTemplates as iec61850DataTemplates
        import model.modelManager as modelManager
        
        # test model template
        [EnumTemplates, DATemplates, DOTemplates, LNTemplates] = iec61850DataTemplates.genIEC61850Templates()
        
        # test model manager
        
        ## generate IEC 61850 data model templates
        configFilename = 'config_IEC61850_LN_DA.xlsx'
        modelManager.templateCodeGenerator(configFilename)
        
        # ## update Enum list for SCADA data interface
        # configFilename = 'config_SP5_Enum.xml'
        # modelManager.updateEnumInSP5(configFilename)
        
        # test data model generator
        pathConfigFile = './model/config_IEC61850_model.xlsx'
        dmGen = modelGenerator.IEC61850DataModelGenerator(pathConfigFile, nameIED='CLS_tester')
        [pathOutputSCL, dictOutputSCL] = dmGen.main()

        isPass = True
        print('Test of IEC 61850 data model generator has passed.')
    except:
        isPass = False
        print('Test of IEC 61850 data model generator has failed.')

    return isPass


def testIEDServer(instConfig):
    '''
    Test IED server using a single SCL file as input.
    There are currently 3 IEC 61850 data models available, with different sizes.
        1 - demoCLS.cid (A tiny CLS demo data model)
        2 - IEC61850_DER_v1.cid (A comprehensive large DER data model)
        3 - IEC61850_DER_v1_slim.cid (A slim comprehensive DER data model)
    
    Attention: testers read SCL data model in the sub-folder "./tester", while the real application
    expects SCL data model to be stored in "./model/IEC61850_dataModel"
    '''
    
    print('Start the test for the virtual IEC 61850 server')
    try:
        import communication.pyiec61850_server as iedServer
                
        PATH_SCL = './tester/func_tests/IEC61850_DER_v1_slim.cid'
        
        instConfig.interface.path_scl = PATH_SCL
        iec61850ServerMMS = iedServer.run_ied_server_mms(instConfig)
        dataModel = iec61850ServerMMS.data_model
        iec61850Server = iec61850ServerMMS.ied_server

        isPass = True
        print('Test of virtual IEC 61850 server has passed.')
    except:
        isPass = False
        print('Test of virtual IEC 61850 server has failed.')

    return isPass
   

def testInitDynamicCLS():
    '''
    test cls with user customized dynamic server
    Similar to the tester of IED server, for the CLS tester the also these 3 data models
    can be used:
        1 - demoCLS.cid (A tiny CLS demo data model)
        2 - IEC61850_DER_v1.cid (A comprehensive large DER data model)
        3 - IEC61850_DER_v1_slim.cid (A slim comprehensive DER data model)
    
    Attention: testers read SCL data model in the sub-folder "./tester", while the real application
    expects SCL data model to be stored in "./model/IEC61850_dataModel"
    
    Currently the CLS tester uses the similar config file compared to the real-time application,
    but with some tiny changes. The test CLS server starts with simulated time and stops in 3 minutes.
    Therefore, this use case is only suitable for server initialisation test, not for Long-term tests.
    
    User can change the DA settings directly in the lookup table (a CSV file) configured in the configTester.yaml
    For example, for the test with SCL IEC61850_DER_v1_slim.cid, only 1 monitor DA and 1 control DA is activated,
    accordingly, in the CSV file IEC61850_DA_lookup_tester_DER_slim.csv:
            - on line 350, demoVirtualCLS_PV1/MMXU1.TotW, interface "local", is_monitor "True", is_control "False"
            - on line 304, demoVirtualCLS_PV1/DGEN1.OutWSet, interface "disabled", is_monitor "True", is_control "True"
    
    '''
    
    print('Start the test for initialising the IEC 61850 compliant virtual CLS controller')
    try:
        import importlib.util
        ifExist = importlib.util.find_spec("pylibiec61850")
        if not ifExist:
            print("""The local module pyiec61850der is not configured properly!! \n
            A essential lib pylibiec61850 can not be found in current working dir!! \n
            Please check the structure of the working directory!! \n """)
        else:
            from settings.helper import rotating_logger
            nameLogger = 'testLogger'
            nameLogfile = 'testLogger'   
            logger = rotating_logger(nameLogger, nameLogfile)
            
            import simulation.virtual_ied as pyiec61850cls
            
            PATH_CONFIG = './tester/func_tests/configTester.yaml'
    
            ied_manager = pyiec61850cls.run_virtual_ied(path_config=PATH_CONFIG)

        isPass = True
        print('Test of initialising virtual CLS controller has passed.')
    except:
        isPass = False
        print('Test of initialising virtual CLS controller has failed.')

    return isPass


##############################################################################
###########################   run test cases  ################################
##############################################################################

#listTests = None
# listTests = [0, 1, 2, 3, 5,]
listTests = [0, 5,]
runTests(listTests)