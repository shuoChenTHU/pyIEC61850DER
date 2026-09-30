# -*- coding: utf-8 -*-
"""
A test script for the testing of subscribing MMS RCB reports

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

import time
import sys
import os
import ctypes
import time
import datetime
from settings import helper

helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()

import ctypes


def establish_connection(connection, hostname, tcpPort):
    """Helper function to handle connection attempts and report setup."""
    print(f"\nConnecting to IED on {hostname}:{tcpPort}...")
    error = iec61850.IedConnection_connect(connection, hostname, tcpPort)

    if error != iec61850.IED_ERROR_OK:
        print(f"❌ Connection setup failed. Error code: {error}")
        return None, None

    print("✅ Connected successfully. Configuring reporting states...")
    return error

def get_string_from_node_data(node_data_ptr):
    """Safely extracts a Python string out of an opaque sLinkedList node value address pointer."""
    try:
        if isinstance(node_data_ptr, int):
            mem_address = node_data_ptr
        else:
            mem_address = int(node_data_ptr)

        if mem_address != 0:
            return ctypes.string_at(mem_address).decode('utf-8')
    except Exception as e:
        print(f"Error casting node data pointer to string: {e}")
    return "Unknown_Element"


def parse_and_print_dataset_with_names(dataset_values, data_set_directory):
    """Aligns primitive numbers with text object names using matching positional indexes."""
    if not dataset_values or not data_set_directory:
        print("Data execution vectors are empty.")
        return

    array_size = iec61850.MmsValue_getArraySize(dataset_values)
    print(f"\n📊 --- [Decoded Data Snapshot: {array_size} Elements] --- 📊")

    for i in range(array_size):
        element = iec61850.MmsValue_getElement(dataset_values, i)

        # 1. Fetch the text directory node pointer for this index position
        linked_list_node = iec61850.LinkedList_get(data_set_directory, i)
        raw_void_ptr = linked_list_node.data if hasattr(linked_list_node, 'data') else linked_list_node

        # 2. Convert raw memory reference pointer to a Python text string
        element_name = get_string_from_node_data(raw_void_ptr)

        if iec61850.MmsValue_getType(element) == iec61850.MMS_STRUCTURE:
            struct_size = iec61850.MmsValue_getArraySize(element)
            try:
                if struct_size == 1:
                    setmag_struct = iec61850.MmsValue_getElement(element, 0)
                    float_element = iec61850.MmsValue_getElement(setmag_struct, 0)
                    setmag_f = iec61850.MmsValue_toFloat(float_element)
                    print(f"  [{i}] DO: {do_name:<12} | DA: {da_name:<8} -> Value: {setmag_f:<8}")
                else:

                    # Drill down directly into standard structure layout to read mag.f, q, and t
                    mag_struct = iec61850.MmsValue_getElement(element, 0)
                    float_element = iec61850.MmsValue_getElement(mag_struct, 0)
                    mag_f = iec61850.MmsValue_toFloat(float_element)

                    q_element = iec61850.MmsValue_getElement(element, 1)
                    q_val = iec61850.MmsValue_getBitStringAsInteger(q_element)

                    t_element = iec61850.MmsValue_getElement(element, 2)
                    t_ms = iec61850.MmsValue_getUtcTimeInMs(t_element)

                    # Split strings to extract clean DO and DA handles (e.g. splitting by '$')
                    parts = element_name.split('.')
                    do_name = parts[1] if len(parts) > 1 else "Unknown_DO"
                    da_name = ".".join(parts[2:]) if len(parts) > 2 else "Unknown_DA"

                    print(
                        f"  [{i}] DO: {do_name:<12} | DA: {da_name:<8} -> Value: {mag_f:<8} | Quality: {hex(q_val):<5} | Time: {t_ms} ms")
            except Exception as ex:
                print(f"  [{i}] Error parsing standard layout path: {element_name} -> {ex}")
        else:
            print(f"  [{i}] PATH: {element_name} -> Primitive Type Code: {iec61850.MmsValue_getType(element)}")


def process_report_payload(connection, dataset_ref, data_set_directory):
    """Triggered by main loop to fetch and execute parsing of raw values."""
    # Read fresh numbers from server
    dataset_obj, read_err = iec61850.IedConnection_readDataSetValues(connection, dataset_ref, None)

    if read_err == iec61850.IED_ERROR_OK:
        dataset_values = iec61850.ClientDataSet_getValues(dataset_obj)

        # Connect values and directory data arrays together here
        parse_and_print_dataset_with_names(dataset_values, data_set_directory)

        # Free memory allocation handles cleanly
        iec61850.ClientDataSet_destroy(dataset_obj)
    else:
        print(f"Failed to fetch matching snapshot. Error code: {read_err}")


def main():
    hostname = "127.0.0.1"
    tcpPort = 61850
    INTG_PERIOD = 5000  # ms
    T_WAIT = 30 #s
    rcb_ref = 'virtualCLSminiPV1/LLN0$RP$PV1_MX_MMXU1'
    # rcb_ref = 'demoVirtualCLS_demoProsumerXY/PV1_MMXU0$RP$demoProsumerXY_RP_PV1_MMXU0'

    connection = iec61850.IedConnection_create()

    # Initial Connection
    while establish_connection(connection, hostname, tcpPort) is None:
        print(f"Sleeping for {T_WAIT}s before retrying initial connection...")
        time.sleep(T_WAIT)

    rcb = None
    dataSetDirectory = None
    last_seen_seq = -1
    needs_reconfiguration = True

    try:
        while True:
            # 1. CHECK CONNECTION HEALTH BEFORE EACH RCB QUERY
            # State 1 = IED_STATE_CONNECTED. Any other state means the link is down.
            conn_state = iec61850.IedConnection_getState(connection)

            if conn_state != iec61850.IED_STATE_CONNECTED:
                print(f"\n⚠️ Link lost! (Connection State: {conn_state}). Entering reconnect loop...")

                # Cleanup old local structures to prevent memory leaks during drops
                if rcb:
                    iec61850.ClientReportControlBlock_destroy(rcb)
                    rcb = None
                if dataSetDirectory:
                    iec61850.LinkedList_destroy(dataSetDirectory)
                    dataSetDirectory = None

                iec61850.IedConnection_close(connection)
                needs_reconfiguration = True
                last_seen_seq = -1  # Reset baseline tracker for safe alignment upon recovery

                # Retry loop until server accepts us back
                while True:
                    if establish_connection(connection, hostname, tcpPort) is not None:
                        break  # Break retry loop once physical TCP socket connects
                    print(f"Reconnect failed. Retrying in {T_WAIT} seconds...")
                    time.sleep(T_WAIT)

            # 2. RUN REPORT AND DIRECTORY RE-INITIALIZATION ON RECOVERY
            if needs_reconfiguration:
                try:
                    rcb, rcb_err = iec61850.IedConnection_getRCBValues(connection, rcb_ref, None)
                    if not rcb:
                        print("❌ Error: Target reference node could not be resolved. Retrying layout...")
                        time.sleep(T_WAIT)
                        continue

                    dataset_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
                    print(f"DEBUG -> Associated Dataset Reference: '{dataset_ref}'")

                    dataSetDirectory, dir_err = iec61850.IedConnection_getDataSetDirectory(connection, dataset_ref,
                                                                                           None)
                    if not dataSetDirectory:
                        print("❌ Error: Could not query model dataset text names directory mapping.")
                        time.sleep(T_WAIT)
                        continue

                    # Configure server reporting parameters
                    iec61850.ClientReportControlBlock_setTrgOps(rcb, 0x08)
                    iec61850.ClientReportControlBlock_setIntgPd(rcb, INTG_PERIOD)
                    iec61850.IedConnection_setRCBValues(connection, rcb, 768, True)

                    # Enable report control tracking states on server
                    iec61850.ClientReportControlBlock_setRptEna(rcb, True)
                    iec61850.IedConnection_setRCBValues(connection, rcb, 2, True)

                    print("🎉 Reporting engine successfully restored and live on server!")
                    needs_reconfiguration = False  # Clear configuration flag

                except Exception as config_err:
                    print(f"Error during configuration phase: {config_err}. Retrying sequence...")
                    time.sleep(T_WAIT)
                    continue

            # 3. REPEAT THE RCB INTEGRITY QUERY LOOP SAFE
            # Sync the fresh parameters down from the server
            iec61850.IedConnection_getRCBValues(connection, rcb_ref, rcb)

            # Check the Sequence Number
            current_seq = iec61850.ClientReportControlBlock_getSqNum(rcb)

            if current_seq != last_seen_seq:
                # If last_seen_seq is -1, it's just the initial baseline after (re)connect.
                if last_seen_seq != -1:
                    print(f"\n⚡ --- [New Report Interval Detected! SqNum: {current_seq}] --- ⚡")
                    print(datetime.datetime.now())
                    process_report_payload(connection, dataset_ref, dataSetDirectory)

                # Align our local loop marker flag state
                last_seen_seq = current_seq

            # Poll the lightweight sequence flag quickly (100ms) to detect changes instantly
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nHalting script loops safely...")
    finally:
        # Graceful cleanup to cleanly release report states
        if rcb:
            try:
                iec61850.ClientReportControlBlock_setRptEna(rcb, False)
                iec61850.IedConnection_setRCBValues(connection, rcb, 2, True)
                iec61850.ClientReportControlBlock_destroy(rcb)
            except:
                pass
        if dataSetDirectory:
            try:
                iec61850.LinkedList_destroy(dataSetDirectory)
            except:
                pass

        iec61850.IedConnection_close(connection)
        iec61850.IedConnection_destroy(connection)

if __name__ == "__main__":
    main()