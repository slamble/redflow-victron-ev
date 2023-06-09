#!/usr/bin/python3

import pymodbus
import requests
import time
from pymodbus.client import ModbusTcpClient
from enum import Enum

class LogLevel(int, Enum):
  ERROR = 0
  WARNING = 1
  INFO = 2
  DEBUG = 3

# ===== User-adjustable parameters start here =====
VictronEVChargerIP = '192.168.50.229' # The IP address of your EV charger
VictronCerboIP = '192.168.50.206'     # The IP address of the Cerbo GX
ZBM_IP = '192.168.50.109'             # The IP address of the Redflow BMS
ZBM_min_discharge_level = 10 	      # Minimum percentage capacity for EV charging. Below this, the charger is turned off.
AC_load_max_discharge = 2500          # Watts - the maximum load before the charger is turned off
AC_load_min_discharge = 1000          # Watts - the minimum load; if the load is below that mark, the charger is turned on.
ChargeCurrent = 6                     # Amps. Multiply by your voltage to get the watts (230*6 = 1380 watts in Australia.)
LoggingLevel = LogLevel.INFO

# ===== User-adjustable parameters end here =====

# ===== Modbus registers for manipulating the EV charger, and reading data from the Cerbo GX.
Reg_VictronEVSetChargingMode = 5009 # Register for setting the charger mode
Reg_VictronEVStartStopCharging = 5010 # Start/stop charging
Reg_VictronEVChargerState = 5015 # Register for the EV charger state
Reg_VictronEVChargeCurrent = 5016 # Set the charging current
Reg_CerboACLoadL1 = 817 # Load on first phase (watts)
Reg_CerboACLoadL2 = 818 # Load on second phase (watts)
Reg_CerboACLoadL3 = 819 # Load on third phase (watts)

from datetime import datetime

def log(str, level):
  if level <= LoggingLevel:
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    print(timestamp + ' ' + str)

class EVChargerState(int, Enum):  # For register 5015
  DISCONNECTED = 0
  CONNECTED = 1
  CHARGING = 2
  CHARGED = 3
  WAITING_FOR_SUN = 4
  WAITING_FOR_START = 6

class EVChargingState(int, Enum): # For register 5009
  MANUAL = 0
  AUTO = 1
  SCHEDULED = 2

class EVStartStopCharging(int, Enum): # For register 5010
  STOP = 0
  START = 1


charger_client = ModbusTcpClient(VictronEVChargerIP)
charger_client.connect()

cerbo_client = ModbusTcpClient(VictronCerboIP)
cerbo_client.connect()

def get_zbm_status():
  data = requests.get('http://' + ZBM_IP + ':3000/rest/1.0/status')
  json = data.json()
  return json

def enable_charging():
  charger_client.write_register(Reg_VictronEVSetChargingMode, EVChargingState.MANUAL)
  charger_client.write_register(Reg_VictronEVChargeCurrent, ChargeCurrent)
  charger_client.write_register(Reg_VictronEVStartStopCharging, EVStartStopCharging.START)

def disable_charging():
  charger_client.write_register(Reg_VictronEVStartStopCharging, EVStartStopCharging.STOP)
  charger_client.write_register(Reg_VictronEVSetChargingMode, EVChargingState.AUTO)

def get_current_load():
  data = cerbo_client.read_holding_registers(Reg_CerboACLoadL1)
  return data.registers[0]

def get_current_charge_level():
  data = get_zbm_status()
  # XXX: This is specific to the first ZBM, and probably should be adjusted to handle multiple ZBMs.
  data = data["list"][0]["state_of_charge"]
  return data

# - When is_stripping becomes true, start the charging.
# - If the ZBM charge level is below min discharge level, stop the charging.
# - If the AC load gets above 2.5 kW, stop the charging.
# - If the AC load drops below 1 kW, start the charging.

# AC load - Cerbo GX register 817 (via read_holding_registers)
# Strictly speaking, that's L1; L2 and 3 are on 818 and 819. Arguably should
# check the load on all three and sum them.

def is_stripping():
  # XXX: Specific to the first ZBM.
  data = get_zbm_status()
  return data["list"][0]["is_stripping"]

def poll_for_strip():
  while not is_stripping():
    log("Not stripping, sleeping for five minutes.", LogLevel.INFO)
    time.sleep(300) # Wait five minutes.

def poll_for_charge_stop():
  current_charge = get_current_charge_level()
  current_load = get_current_load()
  log("Current charge level is " + str(current_charge) + ", current load is " + str(current_load), LogLevel.INFO)
  while (current_charge >= ZBM_min_discharge_level) and (current_load <= AC_load_max_discharge):
    time.sleep(300)
    current_charge = get_current_charge_level()
    current_load = get_current_load()
    log("Current charge level is " + str(current_charge) + ", current load is " + str(current_load), LogLevel.INFO)

def is_ev_plugged_in():
  state = charger_client.read_holding_registers(Reg_VictronEVChargerState)
  data = state.registers[0]
  valid_states = [ EVChargerState.CONNECTED, EVChargerState.CHARGING, EVChargerState.WAITING_FOR_SUN, EVChargerState.WAITING_FOR_START ]
  if data in valid_states:
    return True
  return False

# Not stripping -> wait for strip
# Stripping ->
#   Not charging.
#     Car plugged in;
#     Load below required discharge level;
#     Charge above required level
#       -> start charging
#   Charging.
#     Load above max discharge level or
#     Charge below required level
#       -> stop charging

log("Initiating poll for maintenance cycle.", LogLevel.INFO)
while True:
  poll_for_strip()
  log("Maintenance time has arrived; checking for valid charging conditions.", LogLevel.INFO)
  while is_stripping():
    current_charge = get_current_charge_level()
    current_load = get_current_load()
    if current_charge < ZBM_min_discharge_level:
      log("Battery level has dropped below threshold. Waiting for maintenance to finish.", LogLevel.INFO)
      while is_stripping():
        # We could just sleep and leave the is_stripping() check to the outer loop, but we know the battery
        # has dropped to a low level of charge. Loop here until maintenance finishes. One hour sleep is a good
        # compromise here.
        time.sleep(3600)
    else:
      # Maintenance is on, and the battery has enough charge.
      if not is_ev_plugged_in():
        log("EV is not plugged in.", LogLevel.WARNING)
        time.sleep(300) # Nothing we can do if the battery isn't plugged in.
      else:
        # We assume we're not charging unless we're polling for the conditions to stop charging.
        if current_load < AC_load_min_discharge:
          log("Low AC load. Starting charging.", LogLevel.INFO)
          # Load is too low. Start EV charging and check for the conditions to stop charging.
          enable_charging()
          poll_for_charge_stop()
          disable_charging()
        else:
          log("Load is too high. Waiting for load to drop.", LogLevel.INFO)
          time.sleep(300) # Load is too high, don't enable charging.
