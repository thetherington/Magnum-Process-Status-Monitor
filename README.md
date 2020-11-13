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

Installation of the status monitoring module requires copying two scripts into the poller modules folder:

1. Copy __magnum_process.py__ script to the poller python modules folder:
   ```
    cp scripts/magnum_process.py /opt/evertz/insite/parasite/applications/pll-1/data/python/modules/
   ```
2. Restart the poller application

## Configuration:

To configure a poller to use the module start a new python poller configuration outlined below

1. Click the create a custom poller from the poller application settings page.
2. Enter a Name, Summary and Description information.
3. Enter the cluster ip address of the Magnum system in the _Hosts_ tab.
4. From the _Input_ tab change the _Type_ to __Python__
5. From the _Input_ tab change the _Metric Set Name_ field to __magnum__
6. From the _Python_ tab select the _Advanced_ tab and enable the __CPython Bindings__ option
7. Select the _Script_ tab, then paste the contents of __scripts/poller_config.py__ into the script panel.
8. Save changes, then restart the poller program.

## Testing:

The magnum_process script can be ran manually from the shell using the following command:

```
python magnum_process.py
```

Below is the _help_ output:

```
python magnum_process.py -h
```

```
usage: magnum_process.py [-h] {manual,auto} ...

Magnum RPC-JSON API Poller program for service health status

positional arguments:
  {manual,auto}
    manual       generate command manually
    auto         generate command automatically from external file or from
                 inside the script

optional arguments:
  -h, --help     show this help message and exit
```