import sys
import os
import ctypes
import time
from settings import helper
from communication.pyiec61850_client import IedClient

helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()

# 1. Define the exact C-compatible functional prototype using ctypes
# typedef void (*ReportCallbackFunction) (void* parameter, ClientReport report);
# void* maps to c_void_p, ClientReport maps to c_void_p (opaque pointer)
CALLBACK_PROTOTYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

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

# 2. Define your true native Python callback function
def raw_c_report_callback(parameter, report_ptr):
    print("\n⚡ --- [Event-Driven C Callback Triggered Safely] --- ⚡")

    # Cast the raw memory pointer back into a usable SWIG ClientReport handle
    # This allows you to use your standard unpack library calls safely
    report = iec61850.ClientReport_frompointer(report_ptr) if hasattr(iec61850,
                                                                      'ClientReport_frompointer') else report_ptr

    dataset_values = iec61850.ClientReport_getDataSetValues(report)
    if dataset_values:
        array_size = iec61850.MmsValue_getArraySize(dataset_values)
        print(f"Dataset contains {array_size} structured elements:")
        # ... your standard printing loop logic goes here
    else:
        print("Payload empty.")



#
# # --- C reportCallbackFunction translation ---
# class ReportCallback(iec61850.RCBHandler):
#     def __init__(self):
#         super().__init__()
#
#     # SWIG monitors this exact function signature name internally to bridge the C callback
#     def trigger(self):
#         report = self._client_report
#         dataset_values = iec61850.ClientReport_getDataSetValues(report)
#         print(f"received report for {iec61850.ClientReport_getRcbReference(report)}")
#
#         # In this Python wrapper, let's unpack the available elements safely
#         if dataset_values:
#             array_size = iec61850.MmsValue_getArraySize(dataset_values)
#             for i in range(array_size):
#                 reason = iec61850.ClientReport_getReasonForInclusion(report, i)
#                 # 0 maps to IEC61850_REASON_NOT_INCLUDED
#                 if reason != 0:
#                     element = iec61850.MmsValue_getElement(dataset_values, i)
#
#                     # Unpack standard structural elements (mag.f, q, t)
#                     if iec61850.MmsValue_getType(element) == iec61850.MMS_STRUCTURE:
#                         try:
#                             mag_struct = iec61850.MmsValue_getElement(element, 0)
#                             float_element = iec61850.MmsValue_getElement(mag_struct, 0)
#                             mag_f = iec61850.MmsValue_toFloat(float_element)
#
#                             q_element = iec61850.MmsValue_getElement(element, 1)
#                             q_val = iec61850.MmsValue_getBitStringAsInteger(q_element)
#
#                             t_element = iec61850.MmsValue_getElement(element, 2)
#                             t_ms = iec61850.MmsValue_getUtcTimeInMs(t_element)
#
#                             print(
#                                 f"  [{i}] Value (mag.f): {mag_f:<8} | Quality: {hex(q_val)} | Timestamp: {t_ms} ms (reason: {reason})")
#                         except Exception as e:
#                             print(f"  [{i}] Included for reason {reason}, custom parsing required.")
#         else:
#             print("Report payload empty.")
#
#
# # Keep the handler instance in global scope to shield it from Garbage Collection
# _keep_alive_handler = None
#
#
# def main():
#     global _keep_alive_handler
#     hostname = "127.0.0.1"
#     tcpPort = 61852
#
#     # IedConnection con = IedConnection_create();
#     con = iec61850.IedConnection_create()
#
#     # IedConnection_connect(con, &error, hostname, tcpPort);
#     # Note: Python wrapper returns error integer directly instead of utilizing pointers
#     error = iec61850.IedConnection_connect(con, hostname, tcpPort)
#     print(f"Connecting to {hostname}:{tcpPort}")
#
#     rcb_ref = 'virtualCLSminiPV1/LLN0$RP$PV1_MX_MMXU1'
#     ds_ref = 'virtualCLSminiPV1/LLN0$PV1_MX_MMXU1'
#
#     if error == iec61850.IED_ERROR_OK:
#         print("Connected")
#
#         # --- read an analog measurement value from server ---
#         value, read_err = iec61850.IedConnection_readObject(con, "virtualCLSminiPV1/MMXU1.TotW.mag.f",
#                                                             iec61850.IEC61850_FC_MX)
#         if value is not None:
#             if iec61850.MmsValue_getType(value) == iec61850.MMS_FLOAT:
#                 fval = iec61850.MmsValue_toFloat(value)
#                 print(f"read float value: {fval}")
#             elif iec61850.MmsValue_getType(value) == iec61850.MMS_DATA_ACCESS_ERROR:
#                 print(f"Failed to read value (error code: {iec61850.MmsValue_getDataAccessError(value)})")
#             iec61850.MmsValue_delete(value)
#
#         # --- read data set ---
#         clientDataSet, ds_err = iec61850.IedConnection_readDataSetValues(con, ds_ref, None)
#
#         if clientDataSet is None:
#             print("failed to read dataset")
#             iec61850.IedConnection_close(con)
#             iec61850.IedConnection_destroy(con)
#             return
#
#         # --- Read RCB values ---
#         rcb, rcb_err = iec61850.IedConnection_getRCBValues(con, rcb_ref, None)
#
#         if rcb:
#             rptEna = iec61850.ClientReportControlBlock_getRptEna(rcb)
#             print(f"RptEna = {rptEna}")
#
#             # --- Install handler for reports ---
#             _keep_alive_handler = ReportCallback()
#             rpt_id = iec61850.ClientReportControlBlock_getRptId(rcb)
#
#             # SWIG automatically attempts to process an RCBHandler subclass instance
#             iec61850.IedConnection_installReportHandler(con, rcb_ref, rpt_id, _keep_alive_handler, None)
#             print(f"Successfully bound report hook to {rcb_ref}")
#
#             # --- Set trigger options and enable report ---
#             # TRG_OPT_DATA_UPDATE (0x10) | TRG_OPT_INTEGRITY (0x08) | TRG_OPT_GI (0x04) = 0x1C (28)
#             iec61850.ClientReportControlBlock_setTrgOps(rcb, 0x1C)
#             iec61850.ClientReportControlBlock_setRptEna(rcb, True)
#             iec61850.ClientReportControlBlock_setIntgPd(rcb, 5000)
#
#             # Re-writing values using the explicit C library parameter bitmasks:
#             # RPT_ENA (2) | TRG_OPS (256) | INTG_PD (512) = 770
#             error = iec61850.IedConnection_setRCBValues(con, rcb, 770, True)
#             if error != iec61850.IED_ERROR_OK:
#                 print(f"report activation failed (code: {error})")
#
#             time.sleep(1)
#
#             # --- trigger GI report ---
#             iec61850.ClientReportControlBlock_setGI(rcb, True)
#             # RCB_ELEMENT_GI bitmask code is 1024
#             error = iec61850.IedConnection_setRCBValues(con, rcb, 1024, True)
#             if error != iec61850.IED_ERROR_OK:
#                 print(f"Error triggering a GI report (code: {error})")
#
#             print("Reporting live. Listening for updates...")
#
#             # Thread execution delay matching the C example's Thread_sleep(60000)
#             time.sleep(60)
#
#             # --- disable reporting ---
#             iec61850.ClientReportControlBlock_setRptEna(rcb, False)
#             error = iec61850.IedConnection_setRCBValues(con, rcb, 2, True)
#             if error != iec61850.IED_ERROR_OK:
#                 print(f"disable reporting failed (code: {error})")
#
#             iec61850.ClientDataSet_destroy(clientDataSet)
#             iec61850.ClientReportControlBlock_destroy(rcb)
#
#         iec61850.IedConnection_close(con)
#     else:
#         print(f"Failed to connect to {hostname}:{tcpPort}")
#         time.sleep(5)
#
#     iec61850.IedConnection_destroy(con)

class SafeReportCallback(iec61850.RCBHandler):
    def __init__(self):
        # We explicitly invoke the C++ base class constructor mapping via SWIG
        iec61850.RCBHandler.__init__(self)

    # Use 'handleReport' to match the official high-level subscriber interface hook
    def handleReport(self, subscriber, report):
        print(f"\n⚡ --- [Event-Driven Report Received via RCB!] --- ⚡")

        # Unpack dataset values
        dataset_values = iec61850.ClientReport_getDataSetValues(report)
        if dataset_values:
            array_size = iec61850.MmsValue_getArraySize(dataset_values)
            print(f"Dataset contains {array_size} elements:")

            for i in range(array_size):
                element = iec61850.MmsValue_getElement(dataset_values, i)

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
                        print(f"  [{i}] Error parsing: {e}")
        else:
            print("Report envelope received, but payload is empty.")


# Use a module-level global list so Python's Garbage Collector never cleans up the background hook
_keep_alive_context = []


def subscribe_rcb(connection, rcb_ref):
    global _keep_alive_context
    try:
        # Create control block configuration object
        rcb, rcb_err = iec61850.IedConnection_getRCBValues(connection, rcb_ref, None)
        if not rcb:
            print("Failed to query target RCB configuration values.")
            return

        dataset_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
        print(f"DEBUG -> Linked to Dataset: '{dataset_ref}'")

        # --- Configure Triggers & Period on Server ---
        # 0x08 strictly configures the server block for Integrity-only triggers
        iec61850.ClientReportControlBlock_setTrgOps(rcb, 0x08)
        iec61850.ClientReportControlBlock_setIntgPd(rcb, 5000)  # 5 seconds

        # Write trigger configurations using official masks: TRG_OPS(256) + INTG_PD(512) = 768
        wr_err = iec61850.IedConnection_setRCBValues(connection, rcb, 768, True)
        if wr_err != iec61850.IED_ERROR_OK:
            print(f"Failed to apply server configurations. Error code: {wr_err}")
            return

        # --- Initialize high-level wrapper object layer ---
        my_handler = SafeReportCallback()
        subscriber = iec61850.RCBSubscriber()

        # Bind properties to the subscriber wrapper object
        subscriber.setEventHandler(my_handler)
        subscriber.setIedConnection(connection)
        subscriber.setRcbReference(rcb_ref)
        subscriber.setRcbRptId(iec61850.ClientReportControlBlock_getRptId(rcb))

        # Append BOTH targets into the global reference block
        _keep_alive_context.append(my_handler)
        _keep_alive_context.append(subscriber)

        # Start listening natively inside the wrapper's managed thread context
        subscriber.subscribe()
        print(f"Successfully configured active subscriber to {rcb_ref}")

        # Enable Reporting (RPT_ENA bitmask flag is 2)
        iec61850.ClientReportControlBlock_setRptEna(rcb, True)
        wr_err = iec61850.IedConnection_setRCBValues(connection, rcb, 2, True)
        if wr_err != iec61850.IED_ERROR_OK:
            print(f"Failed to turn on Report Enable parameter. Error: {wr_err}")
            return

        print("Reporting active. True asynchronous listener thread running stably...")

        # Main execution keep-alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting application...")
    finally:
        if 'subscriber' in locals():
            subscriber.unsubscribe()
        iec61850.IedConnection_destroy(connection)

# do a MMS RCB subscribe test
_active_subscribers = []

ip_addr = "127.0.0.1"
port =61852
rcb_ref = 'virtualCLSminiPV1/LLN0$RP$PV1_MX_MMXU1'
[flag, ied_client] = init_ied_client(ip_addr=ip_addr, port=port)
if flag:
    flag = connect_ied_server(ied_client)
    if flag:
        connection = ied_client.connection
        # subscribe_rcb(connection, rcb_ref)
        subscribe_rcb(connection, rcb_ref)