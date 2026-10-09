# -*- coding: utf-8 -*-
"""
A test script for structured testing on the IED client side

@author: S. Chen

The test script for pyiec61850 client object was taken from a test framework as described in:

J. Morris, F. Ebe, J. Pichl, S. Chen, G. Heilscher, and J.-G. Leeser, 
‘Implementation of an automated test bench for monitoring and controlling systems of 
decentralized energy systems through Controller Hardware-In-the-Loop and 
Power Hardware-In-the-Loop methodology’, in 2020 5th IEEE Workshop on the Electronic Grid (eGRID), 
Aachen, Germany: IEEE, Nov. 2020, pp. 1–8. doi: 10.1109/eGRID48559.2020.9330636.

The test functions are strongly simplised for easy use.

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

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import os
import time
import numpy as np
from settings import helper

# Initialize library
helper.set_env_libiec61850()
iec61850 = helper.import_libiec61850()

@dataclass
class CycleRecord:
    """Structure to hold telemetry, metadata, and responses for a single cycle."""
    timestamp: str
    target_sp_value: float
    write_success: bool
    read_back_sp_value: float | None
    is_sp_validated: bool
    read_mx_value: float | None  # Derived from .mag.f
    read_mx_quality: int | None  # Derived from .q (bitmask)
    read_mx_timestamp_ms: int | None  # Derived from .t (Unix epoch ms)
    read_mx_success: bool
    execution_time_s: float


def get_left_skewed_value(peak:int=50, bounds=(50,100)) -> float:
    """
    Generates a left-skewed float value between 10 and 100
    with the peak concentration (mode) at exactly 60.
    """
    val = np.random.triangular(left=bounds[0], mode=peak, right=bounds[1])
    return round(np.float64(val), 5)


def establish_connection(connection, hostname: str, tcp_port: int):
    """Handles connection attempts safely."""
    print(f"\nConnecting to IED on {hostname}:{tcp_port}...")
    error = iec61850.IedConnection_connect(connection, hostname, tcp_port)

    if error != iec61850.IED_ERROR_OK:
        print(f"❌ Connection setup failed. Error code: {error}")
        return None

    print("✅ Connected successfully.")
    return error


def write_float_value(connection, obj_ref: str, value: float, fc_type: int = 1) -> bool:
    """Writes a float value to the server using libiec61850."""
    print(f"ObjRef (MMS Write Address): {obj_ref}")
    try:
        code = iec61850.IedConnection_writeFloatValue(connection, obj_ref, fc_type, value)
        if code == 0:
            print(f"Successfully passed control setpoint value: {value}")
            return True
        print(f"Writing setpoint failed for {obj_ref}. Code: {code}")
        return False
    except Exception as e:
        print(f"Writing float function crashed: {e}")
        return False


def read_float_value(connection, obj_ref: str, fc_type: int = 0) -> tuple[bool, float | None]:
    """Fallback / basic read wrapper for verifying specific single float elements (like SP)."""
    try:
        value, code = iec61850.IedConnection_readFloatValue(connection, obj_ref, fc_type)
        if code == 0:
            return True, value
        return False, None
    except Exception as e:
        print(f"Reading float function crashed: {e}")
        return False, None


def read_mx_with_metadata(connection, base_obj_ref: str) -> tuple[
    bool, float | None, int | None, int | None]:
    """
    Reads mag.f, q, and t for an MX data object from an IEC 61850 server.

    :param base_obj_ref: Base string up to the DataObject name, e.g., 'virtualCLSminiPV1/MMXU1.TotW'
    :return: (success_bool, float_val, quality_val, timestamp_ms)
    """
    f_ref = f"{base_obj_ref}.mag.f"
    q_ref = f"{base_obj_ref}.q"
    t_ref = f"{base_obj_ref}.t"

    try:
        # 1. Read Value (Float)
        val_res, val_code = iec61850.IedConnection_readFloatValue(connection, f_ref, iec61850.IEC61850_FC_MX)
        if val_code != 0:
            print(f"❌ Failed to read value at {f_ref}. Code: {val_code}")
            return False, None, None, None

        # 2. Read Quality (Int32 bitmask)
        mms_val, q_code = iec61850.IedConnection_readObject(connection, q_ref, iec61850.IEC61850_FC_MX)
        q_res = None
        if q_code == 0 and mms_val is not None:
            # Converts the raw server timestamp directly to Unix epoch milliseconds
            q_res = iec61850.MmsValue_getBitStringAsInteger(mms_val)
            # Free memory allocations on C side if necessary based on your wrapper layout
            # iec61850.MmsValue_delete(mms_val)
        else:
            print(f"⚠️ Server Quality attribute read failed at {t_ref}. Code: {q_code}")

        # 3. Read Timestamp (Epoch ms)
        mms_val, t_code = iec61850.IedConnection_readObject(connection, t_ref, iec61850.MMS_UTC_TIME)
        t_res = None
        if t_code == 0 and mms_val is not None:
            # Converts the raw server timestamp directly to Unix epoch milliseconds
            t_res = iec61850.MmsValue_toUnixTimestamp(mms_val)
            # Free memory allocations on C side if necessary based on your wrapper layout
            # iec61850.MmsValue_delete(mms_val)
        else:
            print(f"⚠️ Server Timestamp attribute read failed at {t_ref}. Code: {t_code}")

        return True, val_res, q_res, t_res

    except Exception as e:
        print(f"💥 Exception triggered inside metadata tracking call: {e}")
        return False, None, None, None


def append_to_csv(filepath: str, record: CycleRecord):
    """Appends a single structured cycle row to the CSV file incrementally."""
    file_exists = os.path.exists(filepath)
    row_dict = asdict(record)

    with open(filepath, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=row_dict.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_dict)


def main():
    hostname = "192.168.170.83"
    tcp_port = 60850
    t_wait = 60
    t_write_interval = 30

    csv_filename = "iec61850_telemetry_log.csv"

    # Split into clean path structures
    write_obj_sp = 'virtualCLSminiPV1/DGEN1.OutWSet.setMag.f'
    read_obj_base = 'virtualCLSminiPV1/MMXU1.TotW'

    connection = iec61850.IedConnection_create()

    # Initial Connection Loop
    while establish_connection(connection, hostname, tcp_port) is None:
        print(f"Sleeping for {t_wait}s before retrying initial connection...")
        time.sleep(t_wait)

    try:
        while True:
            tic = time.perf_counter()
            current_time = datetime.now().isoformat(timespec='seconds')

            # 1. Connection Health Check
            conn_state = iec61850.IedConnection_getState(connection)
            if conn_state != iec61850.IED_STATE_CONNECTED:
                print(f"\n⚠️ Link lost! State: {conn_state}. Entering reconnect loop...")
                iec61850.IedConnection_close(connection)

                while establish_connection(connection, hostname, tcp_port) is None:
                    print(f"Reconnect failed. Retrying in {t_wait} seconds...")
                    time.sleep(t_wait)
                continue  # Restart loop immediately once physical link is back

            # 2. Control Cycle
            sp_target = get_left_skewed_value(30, (10,100))

            # Write Setpoint (SP)
            write_success = write_float_value(connection, write_obj_sp, sp_target, iec61850.IEC61850_FC_SP)

            # Read-back Verification Step
            time.sleep(5)
            _, read_back_sp = read_float_value(connection, write_obj_sp, iec61850.IEC61850_FC_SP)

            is_sp_validated = False
            if write_success and read_back_sp is not None:
                is_sp_validated = np.isclose(sp_target, read_back_sp)
                if is_sp_validated:
                    print("✅ The expected control setpoint has been validated.")
                else:
                    print(f"⚠️ Setpoint mismatch! Sent: {sp_target}, Server read-back: {read_back_sp}")

            # 3. Read Measurand Value + DA Metadata (MX)
            mx_success, mx_val, mx_qual, mx_time = read_mx_with_metadata(connection, read_obj_base)
            if mx_success:
                print(
                    f"📊 [MX Data Collected] Value: {mx_val} | Quality Bitmask: {mx_qual} | Server Epoch Time: {mx_time}")

            # Calculate actual loop execution overhead
            t_perf = time.perf_counter() - tic

            # 4. Generate Unified Telemetry Object
            record = CycleRecord(
                timestamp=current_time,
                target_sp_value=sp_target,
                write_success=write_success,
                read_back_sp_value=read_back_sp,
                is_sp_validated=is_sp_validated,
                read_mx_value=mx_val,
                read_mx_quality=mx_qual,
                read_mx_timestamp_ms=mx_time,
                read_mx_success=mx_success,
                execution_time_s=round(t_perf, 4)
            )

            # 5. Append Cycle Metrics to disk immediately
            append_to_csv(csv_filename, record)

            # Sleep to match target cycle interval
            if t_write_interval > t_perf:
                time.sleep(t_write_interval - t_perf)

    except KeyboardInterrupt:
        print("\nHalting script loops safely...")
    finally:
        iec61850.IedConnection_close(connection)
        iec61850.IedConnection_destroy(connection)


if __name__ == "__main__":
    main()