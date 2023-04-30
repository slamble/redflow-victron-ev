# What is it?

A utility to encourage Redflow batteries to discharge into an electric car, rather than the grid.

# What do I need?

* A Redflow zinc bromide flow battery module (Redflow ZBM) with the Redflow Battery Management System (BMS)
* A Victron energy storage system, using a Cerbo GX communication centre
* A Victron EV charging station
* An electric car that can charge from the EV charging station (any vehicle with a Type 2 plug will work.)
* An always on system on the same LAN as the EV charging station and the Redflow BMS

# Why do I want to use this?

Because of the way zinc tends to form dendrites when it is electroplated onto an anode, Redflow batteries undergo a maintenance cycle every three days. This maintenance cycle involves fully discharging all stored energy from the battery, followed by a chemical strip of the battery anodes to remove all electroplated material.

If you have only one Redflow battery, it will generally discharge to the grid. This script monitors the Redflow battery to determine when it is about to start a maintenance discharge, and tells the Victron EV charger to start charging the car at 6 amps (approximately 1.4 kW on a 230 volt system). This will, assuming a properly configured system, encourage the battery to discharge at a higher rate, with most of the discharged energy going into the EV rather than being sent to the electrical grid.

The value in this script is mostly for those who have a single Redflow ZBM, and a relatively low (less than 1 kW) typical overnight load. It will reduce the time required for the maintenance discharge (a big plus in summer, when the time available is often too short for maintenance to finish before the sun rises again), increase the energy efficiency of the battery (as there is a constant ~70 watt load for the battery pumps that becomes significant for low load levels), and increase the personal energy return from the solar system.

Note that this script is untested in systems running multiple ZBMs.

# Known limitations

* Written and tested specifically in a Victron ESS with a Cerbo GX communication centre. It can probably be adapted for other systems, but this is the one I have.
* Explicitly only looks at the L1 AC load - meaning it is not suited to systems configured for three phase operation. (For now.)
