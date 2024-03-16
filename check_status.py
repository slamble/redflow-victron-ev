#!/usr/bin/python3

import time, sys
from pyModbusTCP.client import ModbusClient
from enum import Enum

class LogLevel(int, Enum):
  ERROR = 0
  WARNING = 1
  INFO = 2
  DEBUG = 3

class ZCellStatus(int, Enum):
  SAFE_SHUTDOWN = 700
  BUBBLE_PURGE = 701
  RUN_MODE = 702
  MAINTENANCE_DISCHARGE = 712
  STRIP_RUNNING = 713
  # 715
  PRECHARGE_STANDBY = 720
  # 750
  PRECHARGE = 751
  PRECHARGE_FAIL = 753

ZCellStatusStrings = {
  ZCellStatus.SAFE_SHUTDOWN: "Safe Shutdown - reactions stopped",
  ZCellStatus.BUBBLE_PURGE: "Bubble purge - precharge",
  ZCellStatus.RUN_MODE: "Run mode (standard)",
  ZCellStatus.MAINTENANCE_DISCHARGE: "Maintenance Discharge",
  ZCellStatus.STRIP_RUNNING: "Anode strip in progress",
  ZCellStatus.PRECHARGE_STANDBY: "Standby for precharge",
  ZCellStatus.PRECHARGE: "Precharge",
  ZCellStatus.PRECHARGE_FAIL: "Precharge failed"
}

# ===== User-adjustable parameters start here =====
ZBM_IP = '192.168.50.109'             # The IP address of the Redflow BMS

# ===== User-adjustable parameters end here =====

Reg_ZCell_State = 0x9019
Reg_ZCell_BusVoltage = 0x9018 # times 10
Reg_ZCell_Current = 0x9014 # times 10
Reg_ZCell_Voltage = 0x9013 # times 10
Reg_ZCell_StateOfCharge = 0x9011 # times 100

from datetime import datetime

def log(str):
  now = datetime.now()
  timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
  print(timestamp + ' ' + str)

def log_data(state, bus_voltage, current, voltage, charge_state):
  if (type(state) is list):
    if (len(state) >= 1):
      state = state[0]
    else:
      state = "Unknown"
  else:
    state = "Unknown"
  if (len(bus_voltage) >= 1):
    bus_voltage = bus_voltage[0] / 10
  else:
    bus_voltage = "Unknown"
  if (len(current) >= 1):
    current = current[0]
    if (current > 32767):
      current = current - 65536
    current = current / 10
  else:
    current = "Unknown"
  if (len(voltage) >= 1):
    voltage = voltage[0] / 10
  else:
    voltage = "Unknown"
  if (len(charge_state) >= 1):
    charge_state = charge_state[0] / 100
  else:
    charge_state = "Unknown"

  tail_data = ", {bus_voltage}, {current}, {voltage}, {charge_state}".format(
    bus_voltage = bus_voltage,
    current = current,
    voltage = voltage,
    charge_state = charge_state)
  if state in ZCellStatusStrings:
    log(ZCellStatusStrings[state] + " (" + str(state) + ")" + tail_data)
  else:
    log("Unknown state (" + str(state) + ")" + tail_data)

# Is there any way to get this unit ID programmatically?
zbm_client = ModbusClient(ZBM_IP, unit_id=201)
zcell_client = ModbusClient(ZBM_IP, unit_id = 1)
while True:
  zcell_client.open()
  state = zcell_client.read_holding_registers(Reg_ZCell_State)
  bus_voltage = zcell_client.read_holding_registers(Reg_ZCell_BusVoltage)
  current = zcell_client.read_holding_registers(Reg_ZCell_Current)
  voltage = zcell_client.read_holding_registers(Reg_ZCell_Voltage)
  charge_state = zcell_client.read_holding_registers(Reg_ZCell_StateOfCharge)
  zcell_client.close()
  log_data(state, bus_voltage, current, voltage, charge_state)
  time.sleep(20)
