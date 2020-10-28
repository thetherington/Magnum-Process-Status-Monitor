import socket
import json
import argparse
import json
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
        self.systemName = None
        self.redundancyStateServices = None
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
                self.monitor_services += value

            if ("legacy" in key) and (value):
                self.legacy = True

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

        if not self.substituted:

            process_metrics, cluster_information = self.group_metrics(self.get_metrics())

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
                            service_def["s_state"] = metric[1]

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

                            if metrics["s_state"] != "Running":
                                overall_health["s_state"] = "Not Running"
                                overall_health["i_num_failed"] += 1

            print(json.dumps(serviceState, indent=1))


def main():
    pass


if __name__ == "__main__":

    main()
