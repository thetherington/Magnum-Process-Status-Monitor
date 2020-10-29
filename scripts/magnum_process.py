import argparse
import importlib
import json
import os
import random
import re
import select
import socket


class processMonitor:
    def __init__(self, **kwargs):

        # RPC-JSON specifics
        self.sock = None
        self.endFrame = (b"\x0d" + b"\x0a").decode("utf-8")
        self.rpc_id = random.randint(1, 10)
        self.magnum_port = 12021

        self.verbose = None

        self.overall = True
        self.systemName = "Magnum"
        self.redundancyStateServices = []
        self.monitor_services = []

        self.substituted = None

        for key, value in kwargs.items():

            if ("address" in key) and (value):
                self.magnum_ip = value

            if ("services" == key) and (value):
                self.monitor_services += value

            if ("verbose" in key) and (value):
                self.verbose = True

            if ("disable_overall" in key) and (value):
                self.overall = None

            if ("subdata" in key) and (value):
                self.substituted = value

            if ("systemName" in key) and (value):
                self.systemName = value

            if ("redundancy_services" in key) and (value):

                self.redundancyStateServices = value

                if "services" in kwargs.keys():
                    self.monitor_services += value

        self.rpc_connect()

    def do_ping(self):

        ping_def = {"id": self.rpcId(), "jsonrpc": "2.0", "method": "ping"}

        ping_payload = json.dumps(ping_def) + self.endFrame

        resp = self.rpc_call(ping_payload)

        try:

            if resp["result"] == "pong":
                return True

        except Exception:
            return None

    def set_version(self):

        version_def = {
            "id": self.rpcId(),
            "jsonrpc": "2.0",
            "method": "health.api.handshake",
            "params": {"client_supported_versions": [2]},
        }

        version_payload = json.dumps(version_def) + self.endFrame

        resp = self.rpc_call(version_payload)

        try:

            if resp["result"]["server_selected_version"] == 2:
                return True

        except Exception:
            return None

    def get_metrics(self):

        metrics_def = {"id": self.rpcId(), "jsonrpc": "2.0", "method": "get.health.metrics"}

        metrics_payload = json.dumps(metrics_def) + self.endFrame

        retries = 2
        while retries > 0:

            if self.do_ping():
                if self.set_version():

                    resp = self.rpc_call(metrics_payload)

                    try:

                        if "result" in resp:
                            return resp["result"]

                    except Exception:
                        pass

            self.rpc_close()
            self.rpc_connect()

            retries -= 1

        return None

    def rpc_call(self, msg):
        def empty_socket(sock):
            """remove the data present on the socket"""
            while True:
                inputready, _, _ = select.select([sock], [], [], 0)
                if len(inputready) == 0:
                    break
                for s in inputready:
                    if not s.recv(1):
                        return

        try:

            empty_socket(self.sock)
            self.sock.send(msg.encode("utf-8"))

            responselist = []

            while True:

                try:
                    data = self.sock.recv(1024).decode("utf-8")
                except socket.timeout:
                    break
                if not data:
                    break

                responselist.append(data)

                if self.endFrame in data:
                    break

            response = json.loads("".join(responselist))

        except Exception:
            return None

        if self.verbose:
            print("-->", msg.strip("\r\n"))
            print("<--", json.dumps(response)[0:300])

        return response

    def rpc_connect(self):

        try:

            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2)
            self.sock.connect((self.magnum_ip, self.magnum_port))

            return True

        except Exception:
            self.rpc_close()

        return None

    def rpc_close(self):

        try:

            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

            return True

        except Exception:
            return None

    def rpcId(self):

        self.rpc_id = random.randint(1, 10) if self.rpc_id > 99 else self.rpc_id + 1

        return self.rpc_id

    def group_metrics(self, metrics):
        def create_service_dict():

            services = {}
            for service in self.monitor_services:
                services.update({service: []})

            return services

        def autogenerate_service_dict(metric_list):

            Services = {}

            for metric in metric_list:

                # next metric if any found service match.
                # saves computing with the re libarary
                if any(service in metric[0] for service in Services.keys()):
                    continue

                else:

                    # access the process name from a string like "Services: magstoresrv Total Resident Memory"
                    labelPattern = re.compile(r"Services:\s([a-zA-Z\-]*)\s.*")
                    matchLabel = labelPattern.finditer(metric[0])

                    for match in matchLabel:
                        Services.update({match.group(1): []})

            return Services

        if metrics:

            process_metrics = {}
            cluster_information = {}

            for _, hostCollection in metrics.items():

                # create initial host trees for process dict and cluster information
                # generate a nested service tree by either the class service list or call the
                # auto generating function to discovery all the services from the metrics list.
                process_metrics.update(
                    {
                        hostCollection["hostname"]: {
                            "processes": create_service_dict()
                            if len(self.monitor_services) > 0
                            else autogenerate_service_dict(hostCollection["health_metrics"]),
                            "overall_health": hostCollection["overall_health"],
                        }
                    }
                )

                cluster_information.update(
                    {hostCollection["hostname"]: {"cluster_information": []}}
                )

                # reference in the process and cluster info lists
                host_processes = process_metrics[hostCollection["hostname"]]["processes"]
                host_cluster = cluster_information[hostCollection["hostname"]][
                    "cluster_information"
                ]

                for metric in hostCollection["health_metrics"]:

                    # check each service to see if it's in the metric desction.
                    # if so add it to the service list
                    for service in host_processes.keys():
                        if service in metric[0]:
                            host_processes[service].append(metric)

                    if "Cluster" in metric[0]:
                        host_cluster.append(metric)

            if self.verbose:
                print(json.dumps(process_metrics, indent=1))
                print(json.dumps(cluster_information, indent=1))

            return process_metrics, cluster_information

        return None, None

    def create_status(self):

        redundancyState = None
        serviceState = None

        if not self.substituted:

            process_metrics, cluster_information = self.group_metrics(self.get_metrics())

        else:

            import api_status

            importlib.reload(api_status)

            try:

                sample_metrics = eval("api_status." + self.substituted)

            except Exception as e:
                print(e)
                quit()

            process_metrics, cluster_information = self.group_metrics(sample_metrics)

        # calculate redundancy status information
        if cluster_information:

            redundancyState = {}

            for host, cluster_collection in cluster_information.items():

                redundancyState.update(
                    {
                        host: {
                            "s_host": host,
                            "s_status": None,
                            "s_maintenance": None,
                            "s_online": None,
                            "i_resources_running": 0,
                            "i_resources_stopped": 0,
                            "s_system": self.systemName,
                            "s_type": "redundancy",
                        }
                    }
                )

                # tokens are the different resource names that control the cluster ip
                # status list is used to store the state of each one to be verified later
                clusterTokens = ["cl-token", "cl-ip1", "db-ip1", "db-token"]
                clusterStatus = []

                for item in cluster_collection["cluster_information"]:

                    if "Cluster: Maintenance mode" in item[0]:
                        redundancyState[host]["s_maintenance"] = item[1]

                    elif "Cluster: Online (%s)" % (host) in item[0]:
                        redundancyState[host]["s_online"] = item[1]

                    elif any(match in item[0] for match in clusterTokens):
                        clusterStatus.append(item[1])

                    if "Cluster: Resource" in item[0]:

                        if any(match in item[1] for match in ["Started", "Slave", "Master"]):
                            redundancyState[host]["i_resources_running"] += 1

                        else:
                            redundancyState[host]["i_resources_stopped"] += 1

                # calculate redundancy status description. if server is offline then punt out a Server Error Offline
                # if both token and ip1 is started or stopped then assume it's working Active or Standby
                # if both do not match than assume there's a server error. probably need to add more combinations in the future.
                if redundancyState[host]["s_online"] == "Yes":

                    if all(status == "Started" for status in clusterStatus):
                        redundancyState[host]["s_status"] = "Server Active/Online"

                    elif all(status == "Stopped" for status in clusterStatus):
                        redundancyState[host]["s_status"] = "Server Standby/Online"

                    else:
                        redundancyState[host]["s_status"] = "Server Error Online"

                else:
                    redundancyState[host]["s_status"] = "Server Error Offline"

            if self.verbose:
                print(json.dumps(redundancyState, indent=1))

        if process_metrics:

            serviceState = {}

            # get all the process state and information
            # iterate through each host branch
            for host, host_collection in process_metrics.items():

                serviceState.update({host: {}})

                for service, metrics in host_collection["processes"].items():

                    # configure a default set of information that is a missing metric for easy fallback
                    serviceState[host].update(
                        {
                            service: {
                                "s_service": service,
                                "s_state": "Not Available",
                                "d_cpu_p": 0,
                                "d_memory_p": 0,
                                "l_memory_b": 0,
                                "i_pid": None,
                                "s_cluster": None,
                                "s_status": None,
                                "s_type": "service",
                            }
                        }
                    )

                    # reference in the service def for easy access
                    service_def = serviceState[host][service]

                    # iterate through each of the list items for a process
                    for metric in metrics:

                        if "State" in metric[0]:

                            # set value as-is
                            service_def["s_state"] = metric[1]

                            # chech if it's "Not Running" while the server redundancy is known to be in a normal Standby/Online state
                            # and the service is known as a redundancy state service, then rewrite the state as "Standby"
                            # otherwise just leave the value as-is.

                            # incase the redundancy state did not complete.
                            try:

                                if (
                                    metric[1] == "Not Running"
                                    and redundancyState[host]["s_status"] == "Server Standby/Online"
                                    and service in self.redundancyStateServices
                                ):
                                    service_def["s_state"] = "Standby"

                            except Exception:
                                pass

                        elif "CPU Usage (%)" in metric[0]:
                            service_def["d_cpu_p"] = round(float(metric[1].strip("%")) / 100, 3)

                        elif "Memory Usage (%)" in metric[0]:
                            service_def["d_memory_p"] = round(float(metric[1].strip("%")) / 100, 3)

                        elif "Total Resident Memory" in metric[0]:

                            try:

                                byte_convert = {
                                    "B": 1,
                                    "K": 1000,
                                    "M": 1000000,
                                    "G": 1000000000,
                                    "T": 1000000000000,
                                }

                                unit = metric[1][-1]
                                value = metric[1].split(unit)[0]

                                service_def["l_memory_b"] = int(float(value) * byte_convert[unit])

                            except Exception:
                                service_def["l_memory_b"] = 0

                        elif "Cluster: Resource" in metric[0]:
                            service_def["s_cluster"] = metric[1]

                        elif "Main PID" in metric[0]:
                            service_def["i_pid"] = metric[1]

                        # set status to value if not set or anytime if value is not "Ok"
                        # trying to get any unkown values to stay set that's worse than "OK"
                        if (metric[2] != "Ok") or not service_def["s_status"]:
                            service_def["s_status"] = metric[2]

                # create overall metrics if the flag is left on
                if self.overall:

                    # create initial default information for overall health
                    # state comes from the magnum overall health state.
                    serviceState[host].update(
                        {
                            "overall_health": {
                                "s_service": "overall_health",
                                "s_state": "Running",
                                "d_cpu_p": 0,
                                "d_memory_p": 0,
                                "l_memory_b": 0,
                                "i_num_services": 0,
                                "i_num_failed": 0,
                                "s_status": host_collection["overall_health"],
                                "s_type": "overall",
                            }
                        }
                    )

                    # create reference for easy access to def
                    overall_health = serviceState[host]["overall_health"]

                    for service, metrics in serviceState[host].items():

                        # don't add the overall health metrics to itself.
                        if service != "overall_health":

                            overall_health["d_cpu_p"] += metrics["d_cpu_p"]
                            overall_health["d_memory_p"] += metrics["d_memory_p"]
                            overall_health["l_memory_b"] += metrics["l_memory_b"]
                            overall_health["i_num_services"] += 1

                            if metrics["s_state"] != "Running" and metrics["s_state"] != "Standby":
                                overall_health["s_state"] = "Not Running"
                                overall_health["i_num_failed"] += 1

            if self.verbose:
                print(json.dumps(serviceState, indent=1))

        return serviceState, redundancyState


def main():

    parser = argparse.ArgumentParser(
        description="Magnum RPC-JSON API Poller program for service health status "
    )

    sub = parser.add_subparsers(dest="manual or auto")
    sub.required = True

    sub_manual = sub.add_parser("manual", help="generate command manually")
    sub_manual.set_defaults(which="manual")
    sub_manual.add_argument(
        "-IP", "--address", metavar="172.16.112.20", required=True, help="Magnum Cluster IP Address"
    )
    sub_manual.add_argument(
        "-S",
        "--services",
        metavar="nginx mysql triton",
        required=False,
        nargs="+",
        help="Services to monitor from Magnum. If not used then all services are monitored",
    )
    sub_manual.add_argument(
        "-R",
        "--redundancyservices",
        metavar="eventd magnum-web-config",
        required=False,
        nargs="+",
        help="Redundancy state services which will depend on the redundancy which use Standy",
    )
    sub_manual.add_argument(
        "-N", "--system", metavar="SDVN", required=False, help="System Redundancy Group Name",
    )
    sub_manual.add_argument(
        "-no-overall",
        "--overall_disable",
        action="store_true",
        required=False,
        help="Disable the overall status",
    )
    sub_manual.add_argument(
        "-z",
        "--fakeit",
        metavar="sdvn_status",
        required=False,
        help="supplement some fake data from api_status file",
    )
    sub_manual.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        required=False,
        help="enable a more detailed output for troubleshooting",
    )

    sub_auto = sub.add_parser(
        "auto", help="generate command automatically from external file or from inside the script"
    )
    sub_auto.set_defaults(which="auto")
    group = sub_auto.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-F",
        "--file",
        metavar="file",
        required=False,
        help="File containing parameter options (should be in dictionary format)",
    )
    group.add_argument(
        "-D",
        "--dump",
        required=False,
        metavar="clienthost / sdvn",
        help="Dump a sample json file to use to test with. sample data can be 'clienthost' or 'sdvn'",
    )
    group.add_argument(
        "-S",
        "--script",
        required=False,
        metavar="clienthost / sdvn",
        help="Use the dictionary in the script to feed the arguments either 'clienthost' or 'sdvn'",
    )

    args = parser.parse_args()  # (["auto", "-S"])

    # args = parser.parse_args(["manual", "-IP", "10.9.1.24", "-N", "ClientHost"])

    if args.which == "manual":

        params = {
            "address": args.address,
            "services": args.services,
            "redundancy_services": args.redundancyservices,
            "systemName": args.system,
            "verbose": args.verbose,
            "subdata": args.fakeit,
            "disable_overall": args.overall_disable,
        }

        mag = processMonitor(**params)

    if args.which == "auto":

        sdvn = {
            "address": "10.9.1.31",
            "services": [
                "magsysmgr",
                "magsigmonsrv",
                "magwampsrv",
                "magrtrsrv",
                "magbackupsrv",
                "magdrvsrv",
                "magquartz",
                "magep3srv",
                "magcfgsrv",
                "triton",
                "zeus",
                "pacemaker",
                "magwebcfgmgt",
                "postgres",
                "magselfmonsrv",
                "magstoresrv",
                "nginx",
                "magwebcfgmgt",
                "corosync",
            ],
            "redundancy_services": ["eventd", "magnum-web-config"],
            "systemName": "Magnum-SDVN",
        }

        clienthost = {
            "address": "10.9.1.24",
            "services": ["nginx", "mysql", "zeus", "triton"],
            "redundancy_services": ["eventd", "magnum-web-config", "nundina"],
            "systemName": "Magnum-CH",
        }

        if args.file:

            try:

                with open(os.getcwd() + "\\" + args.file, "r") as f:
                    mon_args = json.loads(f.read())

                mag = processMonitor(**mon_args)

            except Exception as e:
                print(e)

        if args.script or args.dump:

            if (
                args.script == "clienthost"
                or args.script == "sdvn"
                or args.dump == "clienthost"
                or args.dump == "sdvn"
            ):

                params = {
                    "verbose": None,
                    "subdata": None,
                    "disable_overall": None,
                }

                if args.script:

                    params.update(eval(args.script))
                    mag = processMonitor(**params)

                elif args.dump:

                    params.update(eval(args.dump))

                    try:

                        with open(os.getcwd() + "\\json_file.json", "w") as f:
                            f.write(json.dumps(params, indent=3))

                    except Exception as e:
                        print(e)

                    quit()

            else:
                print("Choose either 'clienthost' or 'sdvn'...")
                quit()

    if not mag.verbose:

        input_quit = False
        while input_quit is not "q":

            services, redundancy = mag.create_status()

            if services:

                for host, processes in services.items():

                    print(host)

                    for process, metrics in processes.items():
                        print(process, metrics)

                    print("\n")

            if redundancy:

                for host, items in redundancy.items():
                    print(host, items)

            input_quit = input("\nType q to quit or just hit enter: ")

    else:
        mag.create_status()


if __name__ == "__main__":

    main()
