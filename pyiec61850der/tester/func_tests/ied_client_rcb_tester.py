# -*- coding: utf-8 -*-
"""
A test script for the testing of subscribing mms RCB reports.

libiec61850 client error code:
ref: https://support.mz-automation.de/doc/libiec61850/net/latest/namespace_i_e_c61850_1_1_client.html
      IedClientError.IED_ERROR_OK = 0
      IedClientError.IED_ERROR_NOT_CONNECTED = 1
      IedClientError.IED_ERROR_ALREADY_CONNECTED = 2
      IedClientError.IED_ERROR_CONNECTION_LOST = 3
      IedClientError.IED_ERROR_SERVICE_NOT_SUPPORTED = 4
      IedClientError.IED_ERROR_CONNECTION_REJECTED = 5
      IedClientError.IED_ERROR_USER_PROVIDED_INVALID_ARGUMENT = 10
      IedClientError.IED_ERROR_ENABLE_REPORT_FAILED_DATASET_MISMATCH = 11
      IedClientError.IED_ERROR_OBJECT_REFERENCE_INVALID = 12
      IedClientError.IED_ERROR_UNEXPECTED_VALUE_RECEIVED = 13
      IedClientError.IED_ERROR_TIMEOUT = 20
      IedClientError.IED_ERROR_ACCESS_DENIED = 21
      IedClientError.IED_ERROR_OBJECT_DOES_NOT_EXIST = 22
      IedClientError.IED_ERROR_OBJECT_EXISTS = 23
      IedClientError.IED_ERROR_OBJECT_ACCESS_UNSUPPORTED = 24
      IedClientError.IED_ERROR_TYPE_INCONSISTENT = 25,
      IedClientError.IED_ERROR_TEMPORARILY_UNAVAILABLE = 26
      IedClientError.IED_ERROR_OBJECT_UNDEFINED = 27
      IedClientError.IED_ERROR_INVALID_ADDRESS = 28
      IedClientError.IED_ERROR_HARDWARE_FAULT = 29
      IedClientError.IED_ERROR_TYPE_UNSUPPORTED = 30
      IedClientError.IED_ERROR_OBJECT_ATTRIBUTE_INCONSISTENT = 31
      IedClientError.IED_ERROR_OBJECT_VALUE_INVALID = 32
      IedClientError.IED_ERROR_OBJECT_INVALIDATED = 33
      IedClientError.IED_ERROR_MALFORMED_MESSAGE = 34
      IedClientError.IED_ERROR_SERVICE_NOT_IMPLEMENTED = 98
      IED_ERROR_UNKNOWN = 99
"""

import sys
import os
import time
from settings import helper
from communication.pyiec61850_client import IedClient

helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()


def init_ied_client(ip_addr: str = "127.0.0.1", port: int = 61850) -> tuple[bool, IedClient | None]:
    try:
        ied_client = IedClient(ip_addr, port)
        return True, ied_client
    except Exception as e:
        print('Can not initialise the IED client object')
        print(e)
        return False, None

def connect_ied_server(ied_client: IedClient) -> bool:
    """
    This test function can be used to test the connection to a single IED server
    """

    try:
        is_connected = ied_client.create_IED_connection()
        return is_connected
    except Exception as e:
        print('Can not connect to the IED server object')
        print(e)
        return False


# 1. Define the handler class using the official RCBHandler wrapper structure
class MyReportHandler(iec61850.RCBHandler):
    def __init__(self):
        super().__init__()

    # The high-level wrapper automatically targets this method name
    def handleReport(self, subscriber, report):
        print(f"\n⚡ --- [New Report from: {subscriber.getRcbReference()}] --- ⚡")

        # Unpack and read dataset values
        dataset_values = iec61850.ClientReport_getDataSetValues(report)
        if dataset_values:
            array_size = iec61850.MmsValue_getArraySize(dataset_values)
            print(f"Dataset contains {array_size} elements:")

            for i in range(array_size):
                element = iec61850.MmsValue_getElement(dataset_values, i)
                mms_type = iec61850.MmsValue_getType(element)

                if mms_type == iec61850.MMS_FLOAT:
                    val = iec61850.MmsValue_toFloat(element)
                    print(f"  [{i}] Float Value: {val}")
                elif mms_type == iec61850.MMS_INTEGER:
                    val = iec61850.MmsValue_toInt32(element)
                    print(f"  [{i}] Integer Value: {val}")
                elif mms_type == iec61850.MMS_DATA_ACCESS_ERROR:
                    print(f"  [{i}] Data access error (Excluded component).")
                else:
                    print(f"  [{i}] Other MMS Type ({mms_type}).")
        else:
            print("Report envelope received, but dataset payload is empty.")

def subscribe_rcb(connection, rcb_ref):
    global _active_subscribers

    try:
        rcb = iec61850.ClientReportControlBlock_create(rcb_ref)

        # NOTE: Using direct single-variable unpacking based on previous error fix
        obj, rd_err = iec61850.IedConnection_getRCBValues(connection, rcb_ref, rcb)
        if rd_err != iec61850.IED_ERROR_OK:
            print(f"Failed to read RCB values. Error: {rd_err}")
            return
        else:
            dataset_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
            print(f"DEBUG -> Assigned Dataset Reference: '{dataset_ref}'")
            current_trg = iec61850.ClientReportControlBlock_getTrgOps(rcb)
            print(f"DEBUG -> Server current TrgOps bitmask: {current_trg}")

        # --- Configure Triggers & Integrity (Data Change = 0x40, Integrity = 0x08) ---
        # # Write trigger settings to server (TRG_OPS=16 + INTG_PD=32 -> bitmask 48)
        # wr_err = iec61850.IedConnection_setRCBValues(connection, rcb, 48, True)
        # if wr_err != iec61850.IED_ERROR_OK:
        #     print(f"Failed to set Trigger/Integrity configurations. Error: {wr_err}")
        #     return
        # else:
        #     current_trg = iec61850.ClientReportControlBlock_getTrgOps(rcb)
        #     print(f"DEBUG -> Server current TrgOps bitmask: {current_trg}")

        iec61850.ClientReportControlBlock_setTrgOps(rcb, 0x08)
        iec61850.IedConnection_setRCBValues(connection, rcb, iec61850.RCB_ELEMENT_TRG_OPS, True)
        iec61850.ClientReportControlBlock_setIntgPd(rcb, 5000)
        iec61850.IedConnection_setRCBValues(connection, rcb, iec61850.RCB_ELEMENT_INTG_PD, True)
        current_trg = iec61850.ClientReportControlBlock_getTrgOps(rcb)
        print(f"DEBUG -> Server current TrgOps bitmask: {current_trg}")

        # --- Set up the Asynchronous Subscriber ---
        my_handler = MyReportHandler()

        subscriber = iec61850.RCBSubscriber()

        subscriber.setEventHandler(my_handler)
        subscriber.setIedConnection(connection)
        subscriber.setRcbReference(rcb_ref)
        subscriber.setRcbRptId(iec61850.ClientReportControlBlock_getRptId(rcb))

        # IMPORTANT: Append to a live list so Python never cleans these up!
        subscription = {
            "handler": my_handler,
            "subscriber": subscriber,
            "rcb": rcb,
        }

        _active_subscribers.append(subscription)

        # Subscribes background thread to listen for incoming packets
        subscriber.subscribe()
        print(f"Successfully subscribed to {rcb_ref}")
        print("Is already enabled?:", iec61850.ClientReportControlBlock_getRptEna(rcb))
        print("Is already reserved?:", iec61850.ClientReportControlBlock_getResv(rcb))
        print("Owner string:", iec61850.ClientReportControlBlock_getOwner(rcb))

        # --- Enable Reporting ---
        iec61850.ClientReportControlBlock_setRptEna(rcb, True)
        wr_err = iec61850.IedConnection_setRCBValues(connection, rcb, iec61850.RCB_ELEMENT_RPT_ENA, True)  # RPT_ENA bitmask is 2

        if wr_err != iec61850.IED_ERROR_OK:
            print(f"Failed to enable reporting on server. Error: {wr_err}")
            return
        else:
            print("RPT_ENA write:", wr_err, flush=True)

        print("Reporting live. Periodic updates should stream every 5 seconds...")

        # Keeps the main thread alive so background event thread can print
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting application...")
    finally:
        iec61850.IedConnection_destroy(connection)


class ActiveReportHandler(iec61850.RCBHandler):
    def __init__(self):
        super().__init__()

    # The high-level framework monitors this exact method name
    def handleReport(self, subscriber, report):
        print(f"\n⚡ --- [Event-Driven Report Fired!] --- ⚡")

        # Extract dataset values out of the report envelope
        dataset_values = iec61850.ClientReport_getDataSetValues(report)
        if dataset_values:
            array_size = iec61850.MmsValue_getArraySize(dataset_values)
            print(f"Dataset contains {array_size} structured elements:")

            for i in range(array_size):
                element = iec61850.MmsValue_getElement(dataset_values, i)

                # Unpack standard structural elements (mag.f, q, t)
                if iec61850.MmsValue_getType(element) == iec61850.MMS_STRUCTURE:
                    try:
                        # Extract components by structural layout sequence
                        mag_struct = iec61850.MmsValue_getElement(element, 0)
                        float_element = iec61850.MmsValue_getElement(mag_struct, 0)
                        mag_f = iec61850.MmsValue_toFloat(float_element)

                        q_element = iec61850.MmsValue_getElement(element, 1)
                        q_val = iec61850.MmsValue_getBitStringAsInteger(q_element)

                        t_element = iec61850.MmsValue_getElement(element, 2)
                        t_ms = iec61850.MmsValue_getUtcTimeInMs(t_element)

                        print(f"  [{i}] Value: {mag_f:<8} | Quality: {hex(q_val):<6} | Timestamp: {t_ms} ms")
                    except Exception as e:
                        print(f"  [{i}] Layout variation observed: {e}")
        else:
            print("Report payload is empty.")


# 2. CRUCIAL: Global lists to prevent object destruction / memory collection
_global_handler = None
_global_subscriber = None


def subscribe_rcb2(connection, rcb_ref):
    global _global_handler, _global_subscriber

    try:
        # Create control block configuration object
        rcb = iec61850.ClientReportControlBlock_create(rcb_ref)

        # Read the current configurations
        obj, rd_err = iec61850.IedConnection_getRCBValues(connection, rcb_ref, rcb)
        if rd_err != iec61850.IED_ERROR_OK:
            print(f"Failed to read initial RCB parameters. Error: {rd_err}")
            return

        # --- Configure Triggers & Timers ---
        # 0x08 strictly isolates the triggers to Integrity (No data changes)
        iec61850.ClientReportControlBlock_setTrgOps(rcb, 0x08)
        iec61850.ClientReportControlBlock_setIntgPd(rcb, 5000)  # 5 seconds

        # Write trigger configurations using official masks: TRG_OPS(256) + INTG_PD(512) = 768
        wr_err = iec61850.IedConnection_setRCBValues(connection, rcb, 768, True)
        if wr_err != iec61850.IED_ERROR_OK:
            print(f"Failed to update parameters on server. Error: {wr_err}")
            return

        # --- Instantiate high-level subscriber layers safely ---
        _global_handler = ActiveReportHandler()
        _global_subscriber = iec61850.RCBSubscriber()

        # Bind the properties to the high-level subscriber object wrapper
        _global_subscriber.setEventHandler(_global_handler)
        _global_subscriber.setIedConnection(connection)
        _global_subscriber.setRcbReference(rcb_ref)
        _global_subscriber.setRcbRptId(iec61850.ClientReportControlBlock_getRptId(rcb))

        # Start the background socket listening thread natively
        _global_subscriber.subscribe()
        print(f"Successfully configured active subscriber to {rcb_ref}")

        # --- Enable Reporting (RPT_ENA mask is 2) ---
        iec61850.ClientReportControlBlock_setRptEna(rcb, True)
        wr_err = iec61850.IedConnection_setRCBValues(connection, rcb, 2, True)
        if wr_err != iec61850.IED_ERROR_OK:
            print(f"Failed to activate Report Enable. Error: {wr_err}")
            return

        print("Reporting live via true RCB listeners. Waiting 5s for data...")

        # Main process loop keeping the thread safe and alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting application...")
    finally:
        # Graceful cleanup to avoid locking the RCB on subsequent executions
        if _global_subscriber:
            _global_subscriber.unsubscribe()
        iec61850.IedConnection_destroy(connection)

# FIXME: reading data set is not convenient and error-prone
# def parse_and_print_dataset(dataset_values):
#     """Safely reads and prints out the numerical entries inside the dataset matching any shape"""
#     if not dataset_values:
#         print("Dataset payload is empty.")
#         return
#
#     # 1. Determine structural nature of the dataset layout,
#
#     mms_container_type = iec61850.MmsValue_getType(dataset_values)
#     if mms_container_type == iec61850.MMS_ARRAY:
#         size = iec61850.MmsValue_getArraySize(dataset_values)
#     elif mms_container_type == iec61850.MMS_STRUCTURE:
#         size = iec61850.MmsValue_getStructureSize(dataset_values)
#     else:
#         # Fallback if it's just a single primitive data attribute item directly
#         size = 1
#
#     print(f"\n📊 --- [Dataset Snapshot: {size} elements, Type Code: {mms_container_type}] --- 📊")
#
#     # 2. Iterate safely using the common element extraction patterns
#     for i in range(size):
#         if mms_container_type in (iec61850.MMS_ARRAY, iec61850.MMS_STRUCTURE):
#             element = iec61850.MmsValue_getElement(dataset_values, i)
#         else:
#             element = dataset_values  # Single standalone data node
#
#         mms_type = iec61850.MmsValue_getType(element)
#
#         if mms_type == iec61850.MMS_FLOAT:
#             val = iec61850.MmsValue_toFloat(element)
#             print(f"  [{i}] Float Value: {val}")
#         elif mms_type == iec61850.MMS_INTEGER:
#             val = iec61850.MmsValue_toInt32(element)
#             print(f"  [{i}] Integer Value: {val}")
#         elif mms_type == iec61850.MMS_DATA_ACCESS_ERROR:
#             print(f"  [{i}] Data access error (Excluded component).")
#         elif mms_type == iec61850.MMS_STRUCTURE:
#             try:
#                 # 1. Extract mag.f (mag structure is at index 0, f float is index 0 inside mag)
#                 mag_struct = iec61850.MmsValue_getElement(element, 0)
#                 float_element = iec61850.MmsValue_getElement(mag_struct, 0)
#                 mag_f = iec61850.MmsValue_toFloat(float_element)
#
#                 # 2. Extract q (Quality Bit String is at index 1)
#                 q_element = iec61850.MmsValue_getElement(element, 1)
#                 if q_element is not None:
#                     q_val = iec61850.MmsValue_getBitStringAsInteger(q_element)
#                 else:
#                     q_val = None
#                 # 3. Extract t (Timestamp UTC Time is at index 2)
#                 t_element = iec61850.MmsValue_getElement(element, 2)
#                 if t_element is not None:
#                     t_ms = iec61850.MmsValue_getUtcTimeInMs(t_element)
#                 else:
#                     t_ms = None
#
#                 print(f"  [{i}] Value (mag.f): {mag_f:<8} | Quality (q): {q_val} | Timestamp (t): {t_ms} ms")
#
#             except Exception as ex:
#                 print(f"  [{i}] Parsing error on standard layout: {ex}")
#                 # Fallback check: If the layout is a simple structure (just stVal, q, t without mag)
#                 try:
#                     val_element = iec61850.MmsValue_getElement(element, 0)
#                     print(f"    └─ Alternate type index 0: {iec61850.MmsValue_getType(val_element)}")
#                 except:
#                     pass
#         else:
#             print(f"  [{i}] Unexpected flat type code: {mms_type}")
#
#
# def subscribe_rcb_by_ds(connection, rcb_ref):
#     try:
#         # 1. Read the RCB configuration to discover the target dataset name automatically
#         rcb = iec61850.ClientReportControlBlock_create(rcb_ref)
#         obj, rd_err = iec61850.IedConnection_getRCBValues(connection, rcb_ref, rcb)
#
#         if rd_err != iec61850.IED_ERROR_OK:
#             print(f"Failed to read RCB values. Error: {rd_err}")
#             return
#
#         # Dynamically fetch the dataset path mapped to this report block
#         dataset_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
#         print(f"DEBUG -> Targets Dataset Reference: '{dataset_ref}'")
#
#         if not dataset_ref:
#             print("Error: No dataset reference found mapped to this RCB.")
#             return
#
#         print("Starting stable synchronous polling loop (Every 5 seconds)...")
#
#         # 2. Synchronous Polling Loop
#         while True:
#             # This returns a tuple: (sClientDataSet SWIG pointer, error_code)
#             dataset_obj, read_err = iec61850.IedConnection_readDataSetValues(connection, dataset_ref, None)
#
#             if read_err == iec61850.IED_ERROR_OK:
#                 # CRUCIAL STEP: Unpack the MmsValue object out of the sClientDataSet structure
#                 dataset_values = iec61850.ClientDataSet_getValues(dataset_obj)
#
#                 # Now pass the true underlying values to get printed safely
#                 parse_and_print_dataset(dataset_values)
#
#                 # Free memory allocated for the requested dataset wrapper container safely
#                 iec61850.ClientDataSet_destroy(dataset_obj)
#             else:
#                 print(f"Failed to read dataset from server. Error code: {read_err}")
#
#             time.sleep(5)
#     except KeyboardInterrupt:
#         print("\nExiting application...")
#     finally:
#         iec61850.IedConnection_destroy(connection)
#

#

# do a MMS RCB subscribe test
_active_subscribers = []

ip_addr = "127.0.0.1"
port =61852
rcb_ref = 'virtualCLSminiPV1/LLN0$RP$PV1_SP_DINV1'
[flag, ied_client] = init_ied_client(ip_addr=ip_addr, port=port)
if flag:
    flag = connect_ied_server(ied_client)
    if flag:
        connection = ied_client.connection
        # subscribe_rcb(connection, rcb_ref)
        subscribe_rcb2(connection, rcb_ref)