import time
import logging
import sunspec2.modbus.client as client
import random

logger = logging.getLogger(__name__)


def poll_wmaxlimpct_10ms(
        ip_addr: str,
        port: int,
        slave_id: int,
        timeout_sec: float = 0.008,
        duration_sec: float | None = None
) -> None:
    """
    Polls WMaxLimPct from a SunSpec inverter every 10 ms.

    Parameters
    ----------
    ip_addr : str
        IP address of the Modbus/TCP gateway or inverter.
    port : int
        Modbus TCP port (typically 502).
    slave_id : int
        Modbus Slave Unit ID.
    timeout_sec : float, default=0.008
        Socket timeout in seconds (must be < 0.010s to preserve 10ms cadence).
    duration_sec : float, optional
        Total polling duration in seconds. Runs indefinitely if None.
    """
    INTERVAL = 0.1  # 10 milliseconds

    logger.info(f"Connecting to SunSpec inverter at {ip_addr}:{port} (Unit ID: {slave_id})...")
    d = client.SunSpecModbusClientDeviceTCP(slave_id, ip_addr, port)
    d.scan()
    model_id = 123

    try:
        obj = getattr(d.models[model_id][0], 'WMaxLimPct')
        obj.read()
        print(obj.cvalue)

        t = 0
        for i in range(99999):
            tic = time.perf_counter()
            try:
                obj.read()
                # Extract WMaxLimPct point value
                print(f"t={t}: WMaxLimPct: {obj.cvalue}%")

                if i%10 ==0:
                    val = random.randint(0,100)
                    obj.cvalue = val
                    obj.write()
                    print(f'writing {val}')
            except client.SunSpecModbusClientError as err:
                logger.warning(f"Modbus communication error at {t:.4f}s: {err}")
            except Exception as err:
                logger.error(f"Unexpected error during read: {err}")
            t_perf = time.perf_counter() - tic

            # Precise cadence control: compensate for execution time
            t += INTERVAL
            sleep_time = INTERVAL - t_perf
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Execution + network RT spent > 10 ms; skip missed ticks to prevent cumulative delay
                logger.warning(f"10ms timing overrun! Loop took {(INTERVAL - sleep_time):.2f} ms")

    finally:
        d.close()
        logger.info("Inverter connection closed.")

slave_id = 126
ip_addr = '192.168.170.76'
port = 502
poll_wmaxlimpct_10ms(ip_addr, port, slave_id)