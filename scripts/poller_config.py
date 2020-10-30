import json
from insite_plugin import InsitePlugin
from magnum_process import processMonitor


class Plugin(InsitePlugin):
    def can_group(self):
        return False

    def fetch(self, hosts):

        host = hosts[-1]

        try:

            self.monitor

        except Exception:

            params = {
                "address": host,
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
                "verbose": None,
                "subdata": None,
                "disable_overall": None,
            }

            self.monitor = processMonitor(**params)

        documents = []

        services, redundancy = self.monitor.create_status()

        if services:

            for server, processes in services.items():

                for _, metrics in processes.items():

                    # remove None values so it doesn't break
                    for key, value in list(metrics.items()):
                        if value is None:
                            metrics.pop(key, None)

                    document = {"fields": metrics, "host": server, "name": "service"}

                    documents.append(document)

        if redundancy:

            for server, info in redundancy.items():

                # remove None values so it doesn't break
                for key, value in list(metrics.items()):
                    if value is None:
                        metrics.pop(key, None)

                document = {"fields": info, "host": server, "name": "redundancy"}

                documents.append(document)

        return json.dumps(documents)

    def dispose(self):

        try:

            self.monitor.rpc_close()

        except Exception:
            pass
