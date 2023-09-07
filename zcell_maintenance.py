#!/usr/bin/python3

import time
from pyModbusTCP.client import ModbusClient
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
AC_voltage = 230                      # Nominal voltage in your region.
LoggingLevel = LogLevel.INFO

# ===== User-adjustable parameters end here =====

# ===== Modbus registers for manipulating the EV charger, and reading data from the Cerbo GX.
Reg_VictronEVSetChargingMode = 5009   # Register for setting the charger mode
Reg_VictronEVStartStopCharging = 5010 # Start/stop charging
Reg_VictronEVChargerState = 5015      # Register for the EV charger state
Reg_VictronEVChargeCurrent = 5016     # Set the charging current
Reg_CerboACLoadL1 = 817               # Load on first phase (watts)
Reg_CerboACLoadL2 = 818               # Load on second phase (watts)
Reg_CerboACLoadL3 = 819               # Load on third phase (watts)
Reg_ZCell_InternalStatus1 = 0x2051    # First of ZCell internal flag registers
                                      # (we don't use the others.)
Reg_ZCell_SOC = 0x0200                # State of charge (list of all ZCell units)

# ===== ZCell internal status flag bitmasks =====
# Only FLAG_STRIPPING and FLAG_STRIP_REQUIRED are used by this code; the
# others are here for completeness.
FLAG_HIGH_TEMPERATURE = 1
FLAG_HIGH_CURRENT = 2
FLAG_LEAK_SENSOR_1_TRIPPED = 4
FLAG_LEAK_SENSOR_2_TRIPPED = 8
FLAG_BUS_TRIPPED = 16
FLAG_FLAT = 32
FLAG_STRIP_REQUIRED = 64
FLAG_STRIPPING = 128
FLAG_CHARGE_END = 256
FLAG_DISCHARGE_END = 512
FLAG_BUS_VOLTAGE_LOCKOUT = 1024
FLAG_CURRENT_TRIPPED_LOCKOUT = 2048
FLAG_CONFIGURATION_DATA_INVALID = 4096
FLAG_PAUSE = 8192
FLAG_STANDBY = 16384
FLAG_REST = 32768

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


charger_client = ModbusClient(VictronEVChargerIP)
cerbo_client = ModbusClient(VictronCerboIP, unit_id=100)
zbm_client = ModbusClient(ZBM_IP, unit_id=201)

def enable_charging():
  charger_client.open()
  charger_client.write_single_register(Reg_VictronEVSetChargingMode, EVChargingState.MANUAL)
  charger_client.write_single_register(Reg_VictronEVChargeCurrent, ChargeCurrent)
  charger_client.write_single_register(Reg_VictronEVStartStopCharging, EVStartStopCharging.START)
  charger_client.close()

def disable_charging():
  charger_client.open()
  charger_client.write_single_register(Reg_VictronEVStartStopCharging, EVStartStopCharging.STOP)
  charger_client.write_single_register(Reg_VictronEVSetChargingMode, EVChargingState.AUTO)
  # Once we're in auto mode, "start" means "whenever there's excess solar,
  # charge the car", which is what we generally want.
  charger_client.write_single_register(Reg_VictronEVStartStopCharging, EVStartStopCharging.START)
  charger_client.close()

def get_current_load():
  cerbo_client.open()
  data = cerbo_client.read_holding_registers(Reg_CerboACLoadL1)
  cerbo_client.close()
  return data[0]

def get_current_charge_level():
  zbm_client.open()
  data = zbm_client.read_holding_registers(Reg_ZCell_SOC)
  zbm_client.close()
  # XXX: This is specific to the first ZBM, and probably should be adjusted to handle multiple ZBMs.
  return data[0]/10

# - When is_stripping becomes true, start the charging.
# - If the ZBM charge level is below min discharge level, stop the charging.
# - If the AC load gets above 2.5 kW, stop the charging.
# - If the AC load drops below 1 kW, start the charging.

# AC load - Cerbo GX register 817 (via read_holding_registers)
# Strictly speaking, that's L1; L2 and 3 are on 818 and 819. Arguably should
# check the load on all three and sum them.

def is_stripping():
  # XXX: unit_id is the zcell RTU unit number. Should make this generic
  # for multi-cell installations.
  zcell_client = ModbusClient(ZBM_IP, unit_id = 1)
  zcell_client.open()
  data = zcell_client.read_holding_registers(Reg_ZCell_InternalStatus1)
  is_stripping_flag = data[0] & (FLAG_STRIPPING | FLAG_STRIP_REQUIRED)
  if is_stripping_flag != 0:
    return True
  else:
    return False

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
  charger_client.open()
  state = charger_client.read_holding_registers(Reg_VictronEVChargerState)
  charger_client.close()
  data = state[0]
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
        time.sleep(300) # Nothing we can do if the car isn't plugged in.
      else:
        charger_client.open()
        current_charging_mode = charger_client.read_holding_registers(Reg_VictronEVSetChargingMode)
        if current_charging_mode[0] == EVChargingState.MANUAL:
          # The car's already charging. Check the draw and reduce it from current load.
          current_charge_current = charger_client.read_holding_registers(Reg_VictronEVChargeCurrent)
          current_charge_current = current_charge_current[0]
          log("Currently charging with current " +str(current_charge_current), LogLevel.WARNING)
          charge_load = current_charge_current * AC_voltage
          current_load = current_load - charge_load
        charger_client.close()
        if current_load < AC_load_min_discharge:
          log("Low AC load. Starting charging.", LogLevel.INFO)
          # Load is too low. Start EV charging and check for the conditions to stop charging.
          enable_charging()
          poll_for_charge_stop()
          disable_charging()
        else:
          log("Load is too high. Waiting for load to drop.", LogLevel.INFO)
          time.sleep(300) # Load is too high, don't enable charging.
