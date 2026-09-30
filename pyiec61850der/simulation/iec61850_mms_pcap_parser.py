# -*- coding: utf-8 -*-
"""
A useful script to parse IEC 61850 MMS related data in a wireshark pcap capture file.

Originally created in 2017-2018 in the scope of German research project CLS-App-BW, AI-assisted refactoring
was conducted in research project MeGA for data evaluation purpose.

PCAP TCP Flags:
    'F': 'FIN'
    'S': 'SYN'
    'R': 'RST'
    'P': 'PSH'
    'A': 'ACK'
    'U': 'URG'
    'E': 'ECE'
    'C': 'CWR'

@author: Chen
"""
import codecs
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import logging
import ctypes
import re
import pandas as pd
from scapy.all import rdpcap, TCP, Raw
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(f"main_logger.{__name__}")

# Bitmask values for IEC 61850 / MMS Report Trigger Options (TrgOps)
TRG_OPS_MAP = {
    0x20: "dchg",  # Data change
    0x10: "qchg",  # Quality change
    0x08: "dupd",  # Data update
    0x04: "period",  # Periodic / Integrity
    0x02: "gi",  # General Interrogation
}


@dataclass
class ParserConfig:
    filepath: Path | str
    name_ied: str = "virtualCLSmini"
    ied_server_port: int = 61850
    ied_client_port: int | None = None  # If specified, restricts control & report parsing to this client port
    target_trg_ops: str = "integrity"  # Filter options: 'integrity' / 'dchg' / 'all'
    t_interval: int = 10
    offset_lat: float = 0.0
    ether_lat: float = 0.0
    merge_pac_number: int | None = 5
    is_integrity: bool = True
    is_report: bool = False
    auto_detect_all: bool = True
    list_rcb: list[str] = field(default_factory=lambda: ["PV1_MX_MMXU1"])
    list_controller: list[str] = field(default_factory=lambda: ["OutWSet"])
    list_controller_type: list[str] = field(default_factory=lambda: ["float"])
    para_target: list[list[str]] = field(default_factory=lambda: [["TotW", "TotVAr", "Hz", "PhV1", "PhV2", "PhV3"]])
    output_excel_path: Path | None = None


def hex_to_float(hex_val: str | int) -> float:
    """Convert hex representation to float using ctypes."""
    val = int(hex_val, 16) if isinstance(hex_val, str) else hex_val
    cp = ctypes.pointer(ctypes.c_longlong(val))
    fp = ctypes.cast(cp, ctypes.POINTER(ctypes.c_float))
    return float(fp.contents.value)


def extract_mms_trg_ops(mms_hex: str) -> str | None:
    """Extract and decode IEC 61850 MMS Trigger Options (TrgOps) byte if present in BER payload."""
    try:
        pos = mms_hex.find("8202")
        if pos == -1:
            pos = mms_hex.find("8302")
        if pos != -1:
            trg_byte = int(mms_hex[pos + 6: pos + 8], 16)
            for mask, name in TRG_OPS_MAP.items():
                if trg_byte & mask:
                    return "integrity" if name == "period" else name
    except Exception:
        pass
    return None


def get_tcp_ack_time(pcaps, packet_idx: int, server_port: int) -> float | None:
    """Find the timestamp of the client's TCP ACK acknowledging this specific packet."""
    pkt = pcaps[packet_idx]
    if not pkt.haslayer(TCP):
        return None

    expected_ack = pkt[TCP].seq + len(pkt[TCP].payload)
    for next_idx in range(packet_idx + 1, min(packet_idx + 200, len(pcaps))):
        next_pkt = pcaps[next_idx]
        if next_pkt.haslayer(TCP):
            if next_pkt[TCP].dport == server_port and next_pkt[TCP].ack == expected_ack:
                return float(next_pkt.time)
    return None


def parse_rcb_packets(pcaps, config: ParserConfig, rcb_name: str, target_params: list[str]) -> pd.DataFrame:
    """Parse Report Control Block (RCB) packets with port filtering, deduplication, and ACK latency."""
    rcb_hex = rcb_name.encode("utf-8").hex()
    ied_hex = config.name_ied.encode("utf-8").hex()

    timestamps_unix_all = [float(pkt.time) for pkt in pcaps]
    start_unix = timestamps_unix_all[0] if timestamps_unix_all else 0.0

    seen_tcp_seqs = set()
    records = []

    for idx_pac, packet in enumerate(pcaps):
        if not packet.haslayer(TCP):
            continue

        # 1. Filter Port: Sent from IED Server Port
        if packet[TCP].sport != config.ied_server_port:
            continue
        if config.ied_client_port and packet[TCP].dport != config.ied_client_port:
            continue

        # 2. Retransmission / Duplicate Packet Elimination
        seq_ack_key = (packet[TCP].seq, packet[TCP].ack)
        if seq_ack_key in seen_tcp_seqs:
            continue
        seen_tcp_seqs.add(seq_ack_key)

        raw_payload = bytes(packet[Raw]) if Raw in packet else bytes(packet[TCP].payload)
        mms_hex = raw_payload.hex()
        if not mms_hex or rcb_hex not in mms_hex:
            continue

        # Check Trigger Option Filter if available
        trg_op = extract_mms_trg_ops(mms_hex)
        if trg_op and config.target_trg_ops != "all" and trg_op != config.target_trg_ops:
            continue

        # Find MMS Report PDU (`a382`)
        pos_rcb = [m.start() for m in re.finditer("a382", mms_hex)]
        if not pos_rcb:
            continue

        found_rcb = False
        str_rcb = ""
        for p in pos_rcb:
            try:
                len_rcb = int(mms_hex[p + 4: p + 8], 16) * 2
                str_rcb = mms_hex[p: p + len_rcb + 8]
                if rcb_hex in str_rcb:
                    found_rcb = True
                    break
            except Exception:
                continue

        if not found_rcb:
            continue

        extracted_params = []
        if ied_hex in str_rcb:
            idx_flag = [m.start() for m in re.finditer(ied_hex, str_rcb)]
            for flg in idx_flag:
                try:
                    len_para = int(str_rcb[flg - 2: flg], 16) * 2
                    str_para = str_rcb[flg: flg + len_para]
                    para_name = bytes.fromhex(str_para).decode("utf-8", errors="ignore").split("$")[-1]

                    if para_name == "PhV":
                        extracted_params.extend(["PhV1", "PhV2", "PhV3"])
                    elif para_name and "_" not in para_name:
                        extracted_params.append(para_name)
                except Exception:
                    continue

        current_targets = extracted_params if config.auto_detect_all else target_params

        pos_val = [i for i in range(0, len(str_rcb), 2) if str_rcb[i: i + 3] in ("870", "850")]
        if not pos_val:
            continue

        str_val = [str_rcb[pos_val[i]: pos_val[i + 1]] for i in range(len(pos_val) - 1)]
        str_val.append(str_rcb[pos_val[-1]:])

        pkt_time = timestamps_unix_all[idx_pac]
        row_data = {
            "Packet Index": idx_pac,
            "Absolute Time": datetime.fromtimestamp(pkt_time),
            "Relative Time in [s]": round(pkt_time - start_unix, 3),
            "Unix Time": pkt_time,
            "Trigger Reason": trg_op if trg_op else "N/A",
        }

        # Measure Latency via TCP ACK
        ack_time = get_tcp_ack_time(pcaps, idx_pac, config.ied_server_port)
        if ack_time:
            row_data["Absolute Time IED client"] = datetime.fromtimestamp(ack_time)
            row_data["Unix Time IED client"] = ack_time
            row_data["Latency in [s]"] = round(ack_time - pkt_time, 4)
        else:
            row_data["Absolute Time IED client"] = "N/A"
            row_data["Unix Time IED client"] = "N/A"
            row_data["Latency in [s]"] = "N/A"

        for v_idx, st in enumerate(str_val):
            par = current_targets[v_idx] if v_idx < len(current_targets) else f"Param_{v_idx}"
            try:
                if st.startswith("87"):
                    len_st = int(st[3], 16) * 2
                    hex_st = hex(int(st[4: 4 + len_st], 16) + 0x200)
                    row_data[par] = hex_to_float(hex_st)
                elif st.startswith("85"):
                    len_st = int(st[3], 16) * 2
                    row_data[par] = int(st[4: 4 + len_st], 16)

                if "8403" in st:
                    pos_q = st.index("8403")
                    row_data[f"{par}_q"] = "good" if st[pos_q + 6: pos_q + 10] == "0000" else "Invalid"
            except Exception:
                continue

        records.append(row_data)

    return pd.DataFrame(records)


def parse_control_packets(pcaps, config: ParserConfig) -> pd.DataFrame:
    """Parse control write requests & responses matching exact MMS write PDU structure."""
    timestamps_unix_all = [float(pkt.time) for pkt in pcaps]
    start_unix = timestamps_unix_all[0] if timestamps_unix_all else 0.0

    idx_req = []
    list_req = []
    list_type = []

    # Phase 1: Request Packet Identification
    for i in range(len(pcaps)):
        packet = pcaps[i]
        try:
            # Port check for request: must be directed TO ied_server_port
            if packet.haslayer(TCP) and packet[TCP].dport != config.ied_server_port:
                continue
            if config.ied_client_port and packet.haslayer(TCP) and packet[TCP].sport != config.ied_client_port:
                continue

            # Length filter matching legacy logic
            if len(packet) < 100 or len(packet) > 200:
                continue

            RAW = packet[0]
            MMS_hex = codecs.getencoder("hex_codec")(bytes(RAW))[0].decode()

            # Strictly verify MMS Confirmed Write Request PDU tag structure:
            # Must contain 'a5' as the request tag following 'a0' (Invoke ID)
            # This explicitly filters out Read/GetVariableAccessAttributes requests ('a4')
            has_valid_write_pdu = False
            for pos in range(len(MMS_hex) - 6):
                if MMS_hex[pos : pos + 2] == "a5" and MMS_hex[pos + 4 : pos + 6] == "a0":
                    has_valid_write_pdu = True
                    break

            if not has_valid_write_pdu:
                continue

            # Check controller variable string presence
            for controller, ctlType in zip(config.list_controller, config.list_controller_type):
                if f"${controller}$" in str(bytes(packet[0])):
                    idx_req.append(i)
                    list_req.append(controller)
                    list_type.append(ctlType)
                    break
        except (IndexError, Exception):
            continue

    records = []

    # Phase 2: Iterate identified requests and track matching responses
    for idx in range(len(idx_req)):
        req_idx = idx_req[idx]
        packet_request = pcaps[req_idx]

        RAW = packet_request[0]
        MMS_hex = codecs.getencoder("hex_codec")(bytes(RAW))[0].decode()

        req_time = float(packet_request.time)
        ctl_type = list_type[idx]

        # Read Value
        if ctl_type == "float":
            val_hex_str = MMS_hex[-10:]
            val_hex = hex(int(val_hex_str, 16))
            val = hex_to_float(val_hex)
        elif ctl_type == "int":
            val_hex_str = MMS_hex[-2:]
            val = int(val_hex_str, 16)
        else:
            val = "unknown type"

        # Read Invoke ID (Legacy backtracking algorithm)
        invokeID = None
        invokeIdFlag = None
        for i in range(len(MMS_hex)):
            if MMS_hex[i : i + 2] == "a5" and MMS_hex[i + 4 : i + 6] == "a0":
                invokeIdFlag = i
                break

        if invokeIdFlag is not None:
            for j in range(16):
                if MMS_hex[invokeIdFlag - j : invokeIdFlag - j + 2] == "a0" and MMS_hex[invokeIdFlag - j + 4 : invokeIdFlag - j + 6] == "02":
                    invokeID = MMS_hex[invokeIdFlag - j + 8 : invokeIdFlag]
                    break

        invoke_id_int = int(invokeID, 16) if invokeID is not None else "N/A"

        # Track Response (look forward up to 1000 packets)
        isFoundRes = False
        idx_res = None
        invoke_res = None
        flag_track = None
        MMS_res = ""

        for track in range(1, 1000):
            idx_track = req_idx + track
            if idx_track >= len(pcaps):
                break

            packet_track = pcaps[idx_track]
            if not packet_track.haslayer(TCP):
                continue

            # Response Port Filter: FLIPPED direction (From Server to Client)
            if packet_track[TCP].sport != config.ied_server_port:
                continue
            if config.ied_client_port and packet_track[TCP].dport != config.ied_client_port:
                continue

            MMS_track = codecs.getencoder("hex_codec")(bytes(packet_track[0]))[0].decode()

            for i in range(len(MMS_track)):
                if MMS_track[i : i + 2] == "a1" and MMS_track[i + 4 : i + 6] == "02" and "a5" in MMS_track[i + 8 :]:
                    posInvoke = MMS_track[i + 8 :].index("a5")
                    invoke_res = MMS_track[i + 8 : i + 8 + posInvoke]
                    flag_track = i + 10 + posInvoke
                    break

            if invoke_res is not None and invokeID is not None and invoke_res == invokeID:
                idx_res = idx_track
                isFoundRes = True
                MMS_res = MMS_track
                break

        # Populate output row structure
        if isFoundRes and idx_res is not None:
            packet_response = pcaps[idx_res]
            res_time = float(packet_response.time)

            if MMS_res[flag_track : flag_track + 6] == "028100":
                response_status = "success"
            elif MMS_res[flag_track : flag_track + 8] == "0380010b":
                response_status = "invalid input"
            else:
                response_status = "unknow"

            records.append({
                "Request Index": req_idx,
                "Control Parameter": list_req[idx],
                "Request Absolute Time": datetime.fromtimestamp(req_time),
                "Request Unix Time": req_time,
                "Relative Time in [s]": round(req_time - start_unix),
                "Value": val,
                "Invoke ID": invoke_id_int,
                "Response Index": idx_res,
                "Response Absolute Time": datetime.fromtimestamp(res_time),
                "Response Unix Time": res_time,
                "RTT in [s]": round(res_time - req_time, 6),
                "Response": response_status,
            })
        else:
            records.append({
                "Request Index": req_idx,
                "Control Parameter": list_req[idx],
                "Request Absolute Time": datetime.fromtimestamp(req_time),
                "Request Unix Time": req_time,
                "Relative Time in [s]": round(req_time - start_unix),
                "Value": val,
                "Invoke ID": invoke_id_int,
                "Response Index": "N/A",
                "Response Absolute Time": "N/A",
                "Response Unix Time": "N/A",
                "RTT in [s]": "N/A",
                "Response": "no Response",
            })

    return pd.DataFrame(records)


def print_parsing_statistics(parsed_data: dict[str, pd.DataFrame]):
    """Print detailed summary statistics to console before exporting to Excel."""
    print("\n" + "=" * 60)
    print("                PARSING STATISTICS SUMMARY               ")
    print("=" * 60)
    for sheet_name, df in parsed_data.items():
        print(f"\n Sheet / Group: [{sheet_name}]")
        print(f"  • Total Valid Records: {len(df)}")
        if not df.empty:
            print(f"  • Columns ({len(df.columns)}): {', '.join(df.columns[:8])}...")
            if "RTT in [s]" in df.columns:
                valid_rtt = pd.to_numeric(df["RTT in [s]"], errors="coerce").dropna()
                if not valid_rtt.empty:
                    print(f"  • Avg Control RTT: {valid_rtt.mean():.4f} s | Max: {valid_rtt.max():.4f} s")
            if "Latency in [s]" in df.columns:
                valid_lat = pd.to_numeric(df["Latency in [s]"], errors="coerce").dropna()
                if not valid_lat.empty:
                    print(f"  • Avg Network Latency (ACK): {valid_lat.mean():.4f} s | Max: {valid_lat.max():.4f} s")
        else:
            print("  ⚠️ WARNING: No matching records found after filtering.")
    print("\n" + "=" * 60 + "\n")


def generate_reports(config: ParserConfig):
    logger.info("Starting PCAP analysis with port filtering & deduplication...")
    filepath = Path(config.filepath)
    if not filepath.exists():
        logger.error(f"PCAP File not found: {filepath}")
        return

    pcaps = rdpcap(str(filepath))
    logger.info(f"Loaded {len(pcaps)} packets.")

    parsed_data = {}

    # 1. Parse RCB Sheets
    for idx, rcb_name in enumerate(config.list_rcb):
        target_params = config.para_target[idx] if idx < len(config.para_target) else []
        df_rcb = parse_rcb_packets(pcaps, config, rcb_name, target_params)
        parsed_data[rcb_name[:31]] = df_rcb

    # 2. Parse Controlling Sheet
    df_ctrl = parse_control_packets(pcaps, config)
    parsed_data["Controlling"] = df_ctrl

    # 3. Print Console Statistics
    print_parsing_statistics(parsed_data)

    # 4. Export Excel
    suffix = "_integrity.xlsx" if config.is_integrity else "_all.xlsx"
    output_path = config.output_excel_path or filepath.with_name(filepath.stem + suffix)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in parsed_data.items():
            if df.empty:
                df = pd.DataFrame({"Info": ["No valid non-duplicate packets found."]})
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    logger.info(f"Excel report saved to: {output_path}")


if __name__ == "__main__":

    folder = r'C:\DATA\vIED_logs'
    files = [file for file in os.listdir(folder) if '.pcap' in file or '.pcapng' in file]
    for file in files:
        filepath = f'{folder}\{file}'
        cfg = ParserConfig(
            filepath=filepath,
            name_ied="virtualCLSmini",
            ied_server_port=61850,
            ied_client_port=None,
            target_trg_ops="integrity",
            merge_pac_number=5,
            t_interval=10,
            is_integrity=True,
            auto_detect_all=True,
            list_rcb=["PV1_MX_MMXU1"],
            list_controller=["OutWSet"],
            list_controller_type=["float"],
            para_target=[["TotW", "TotVAr", "Hz", "PhV1", "PhV2", "PhV3"]],
        )
        generate_reports(cfg)