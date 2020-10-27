## Magnum Process Status Monitor

Process status collector module for the Magnum RPC-JSON API interface which collects magnum process status, process cpu, process memory, pid and process cluster information.  Module is used by the inSITE Poller program

The Process status collector module has the below distinct abilities and features:

1. Collect the process state, along with CPU, Memory and PID information
2. Generates Magnum Server Redundancy status and state information
3. Ability to mark process state information into "Standby" mode for processes which do not run on a Magnum Server in Standby mode.
4. Auto discovers process to monitor, or from a supplied list.
5. Auto discovers all magnum servers in a system via Cluster IP

## Minimum Requirements:

- inSITE Version 10.3 and service pack 6
- Python3.7 (_already installed on inSITE machine_)

## Installation: