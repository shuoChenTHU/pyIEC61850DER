# -*- coding: utf-8 -*-
"""
A tester script for elementary sunspec functions.
"""

import sunspec2.modbus.client as client
import time
from datetime import datetime, timezone
import pytz
import pandas as pd
import random

def sunspec_full_scan(d):
    d.scan()
    print(d.models)
    if len(d.models) != 0 or d.models is not None:
        model_names = [key for key, obj in d.models.items() if type(key) is str]
        model_ids = [key for key, obj in d.models.items() if type(key) is int]
        print(f'List of sunspec model names: {model_names}')
        print(f'List of sunspec model ID: {model_ids}')
        for key, obj in d.models.items():
            if type(key) is int:
                print(f'Found Sunspec model {key}')
                model_id = key
                points = getattr(d.models[model_id][0], 'points')
                for name, val in points.items():
                    val = getattr(d.models[model_id][0], name).cvalue
                    print(f'Parameter name {name}, value: {val}')


def periodic_model_reading(d, model_ids):

    d.scan()
    for i in range(999999999):
        print("=" * 120)
        t_read = 0
        for model_id in model_ids:
            print(f'Model scan index {i}, model id {model_id}')
            model_list = d.models.get(model_id)
            tic = time.perf_counter()
            model_list[0].read()
            toc = time.perf_counter()
            t_read += toc - tic
            points = getattr(d.models[model_id][0], 'points')
            for name, val in points.items():
                val = getattr(d.models[model_id][0], name).cvalue
                print(f'Parameter name {name}, value: {val}')
            time.sleep(1.0)
        print(f'Total model read time: {t_read}')
        time.sleep(5)

def write_value(d, model_id, para, val):

    obj = getattr(d.models[model_id][0], para)
    obj.read()
    obj.cvalue
    obj.cvalue = val
    obj.write()
    obj.read()
    obj.cvalue

    # obj = getattr(d.models[model_id][0], para)
    # obj.cvalue = 100
    # obj.write()
    # obj.read()
    # obj.cvalue
    #
    # model_id = 704
    # obj = getattr(d.models[model_id][0], 'WMaxLimPctEna')
    # obj.read()
    # obj.cvalue
    # obj.cvalue = 1
    # obj.write()
    # obj.read()
    # obj.cvalue
    #
    # obj = getattr(d.models[model_id][0], 'WMaxLimPct')
    # obj.cvalue = 100  # Attention: the scale factor is probaly not working properly!
    # obj.write()
    # obj.read()
    # obj.cvalue


def pool_model_points(d, model_ids, interval=10, export_csv=True):
    """
    Connects to a SunSpec device, dynamically reads all points from the requested
    model IDs without relying on df_mapping, and exports the raw snapshot to a CSV.
    """
    # 1. Perform initial full scan to populate device model structures
    d.scan()

    counter = 0
    csv_filename = f'./tester/func_tests/data_recording_{ip_addr.replace(".", "_")}.csv'
    all_recorded_rows = []

    print(f"Starting generic monitoring loop for models: {model_ids}. Press Ctrl+C to stop.")
    try:
        while True:
            time_start = time.perf_counter()

            ctime_utc = datetime.now(timezone.utc)
            ctime_local = ctime_utc.astimezone(pytz.timezone('Europe/Berlin'))
            ctime_local_unix = time.mktime(ctime_local.timetuple())

            row_data = {
                'tstmp': ctime_local,
                'Unix': ctime_local_unix
            }

            # 2. Iterate through requested model IDs
            for model_id in model_ids:
                model_list = d.models.get(model_id)
                if not model_list:
                    print(f"Warning: Model {model_id} not found on device.")
                    continue

                try:
                    # Read the model block over Modbus
                    model_list[0].read()
                    time.sleep(1.0)

                    # Dynamically extract every point and its scaled client value (.cvalue)
                    if hasattr(model_list[0], 'points') and model_list[0].points:
                        for pt_name, pt in model_list[0].points.items():
                            column_key = f"M{model_id}_{pt_name}"
                            row_data[column_key] = getattr(pt, 'cvalue', None)

                except Exception as err:
                    print(f"Warning: Modbus read failed for Model {model_id}: {err}")
                    # If a timeout occurs, proactively null out the socket to prevent offset shifting
                    try:
                        if hasattr(d, 'socket') and d.socket:
                            d.socket = None
                    except Exception:
                        pass
                    break

            all_recorded_rows.append(row_data)
            df_data = pd.DataFrame(all_recorded_rows)
            counter += 1

            print(f"[{ctime_local}] Iteration {counter} recorded {len(row_data)} data points.")

            # Periodic CSV Export
            if export_csv and counter % 6 == 0:
                df_data.to_csv(csv_filename, index=False)
                print(f"Data successfully exported to {csv_filename}")

            time_end = time.perf_counter()
            processing_time = time_end - time_start

            # Maintain strict loop interval timing
            sleep_duration = max(0, interval - processing_time)
            time.sleep(sleep_duration)

    except KeyboardInterrupt:
        print("Monitoring stopped by user. Saving final logs...")
        if export_csv and all_recorded_rows:
            pd.DataFrame(all_recorded_rows).to_csv(csv_filename, index=False)
            print(f"Final data exported to {csv_filename}")

def periodic_pv_curtailment(d) -> None:
    """
    Polls WMaxLimPct from a SunSpec inverter every 10 s.
    This function is not particularly useful because the cvalue always gets written to the point object immediately.
    """
    INTERVAL = 1.0

    print(f"Connecting to SunSpec inverter at {ip_addr}:{port} (Unit ID: {slave_id})...")
    d.scan()
    model_id = 123

    time.sleep(3.0)

    try:
        model = d.models[model_id][0]
        obj = getattr(d.models[model_id][0], 'WMaxLimPct')
        obj.read()
        print(obj.cvalue)
        time.sleep(2.0)

        t = 0
        for i in range(99999):
            tic = time.perf_counter()
            try:
                model.read()
                time.sleep(0.5)
                obj.read()
                # Extract WMaxLimPct point value
                print(f"t={t}: WMaxLimPct: {obj.cvalue}%")

                if i%10 ==0:
                    val = random.randint(0,100)
                    obj.cvalue = val
                    obj.write()
                    print(f'writing {val}')
            except client.SunSpecModbusClientError as err:
                print(f"Modbus communication error at {t:.4f}s: {err}")
            except Exception as err:
                print(f"Unexpected error during read: {err}")
            t_perf = time.perf_counter() - tic

            # Precise cadence control: compensate for execution time
            t += INTERVAL
            sleep_time = INTERVAL - (t_perf - 0.5)
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Execution + network RT spent > 10 ms; skip missed ticks to prevent cumulative delay
                print(f"timing overrun! Loop took {(INTERVAL - sleep_time):.2f} ms")

    finally:
        d.close()
        print("Inverter connection closed.")

# # SMA inverter
# slave_id = 126
# ip_addr = '192.168.170.85'
# port = 502

# Kostal Inverter
slave_id = 71
ip_addr = '192.168.170.88'
port = 1502

d = client.SunSpecModbusClientDeviceTCP(slave_id, ip_addr, port)

model_ids = [103, 120, 123]
# sunspec_full_scan(d)
# periodic_model_reading(d, model_ids)
# write_value(d, 123, 'WMaxLimPct_Ena', 1)
# write_value(d, 123, 'WMaxLimPct', 100)
# write_value(d, 704, 'WMaxLimPct_Ena', 1)
# write_value(d, 704, 'WMaxLimPct', 100)

pool_model_points(d, model_ids, interval=10, export_csv=True)

# periodic_pv_curtailment(d)