import time
import sys
import os
import ctypes
import time
import datetime
from settings import helper
from communication.pyiec61850_client import IedClient

helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()

import ctypes


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
            try:
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
    tcpPort = 60850
    rcb_ref = 'virtualCLSminiPV1/LLN0$RP$PV1_MX_MMXU1'

    connection = iec61850.IedConnection_create()
    error = iec61850.IedConnection_connect(connection, hostname, tcpPort)
    print(f"Connecting to IED on {hostname}:{tcpPort}...")

    if error != iec61850.IED_ERROR_OK:
        print(f"Connection setup aborted. Error: {error}")
        iec61850.IedConnection_destroy(connection)
        return

    print("Connected successfully.")

    try:
        # Initialize Report Parameters block configuration
        rcb, rcb_err = iec61850.IedConnection_getRCBValues(connection, rcb_ref, None)
        if not rcb:
            print("Target reference node was not resolved.")
            return

        dataset_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
        print(f"DEBUG -> Associated Dataset Reference: '{dataset_ref}'")

        # FETCH TEXT DATASET DIRECTORY MAP ONCE AT STARTUP (Efficient Approach)
        dataSetDirectory, dir_err = iec61850.IedConnection_getDataSetDirectory(connection, dataset_ref, None)
        if not dataSetDirectory:
            print("Could not query model dataset text names directory matrix mapping.")
            return

        # Configure server properties: Integrity trigger tracking rule (0x08)
        iec61850.ClientReportControlBlock_setTrgOps(rcb, 0x08)
        iec61850.ClientReportControlBlock_setIntgPd(rcb, 5000)  # 5 seconds
        iec61850.IedConnection_setRCBValues(connection, rcb, 768, True)

        # Enable report control tracking states on server
        iec61850.ClientReportControlBlock_setRptEna(rcb, True)
        iec61850.IedConnection_setRCBValues(connection, rcb, 2, True)

        print("\nReporting engine live on server. Running state monitor loop safely...")

        last_seen_seq = -1

        while True:
            # Sync the fresh parameters down from the server
            iec61850.IedConnection_getRCBValues(connection, rcb_ref, rcb)

            # FIX: Check the Sequence Number instead of Configuration Revision
            current_seq = iec61850.ClientReportControlBlock_getSqNum(rcb)

            tic = time.perf_counter()
            if current_seq != last_seen_seq:
                # If last_seen_seq is -1, it's just the initial baseline check.
                # Only pull data values if it's an actual update.
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
        if 'rcb' in locals() and rcb:
            iec61850.ClientReportControlBlock_setRptEna(rcb, False)
            iec61850.IedConnection_setRCBValues(connection, rcb, 2, True)
            iec61850.ClientReportControlBlock_destroy(rcb)
        if 'dataSetDirectory' in locals() and dataSetDirectory:
            iec61850.LinkedList_destroy(dataSetDirectory)

        iec61850.IedConnection_close(connection)
        iec61850.IedConnection_destroy(connection)


if __name__ == "__main__":
    main()