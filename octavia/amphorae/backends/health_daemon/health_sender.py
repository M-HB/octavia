#    Copyright 2014 Hewlett-Packard Development Company, L.P.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import socket

from oslo_config import cfg
from oslo_log import log as logging

from octavia.amphorae.backends.health_daemon import status_message

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def round_robin_addr(addrinfo_list):
    if not addrinfo_list:
        return None
    addrinfo = addrinfo_list.pop(0)
    addrinfo_list.append(addrinfo)
    return addrinfo


class UDPStatusSender:
    def __init__(self):
        self._update_dests()
        self.v4sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.v6sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

    def update(self, dest, port):
        addrlist = socket.getaddrinfo(dest, port, 0, socket.SOCK_DGRAM)
        # addrlist = [(family, socktype, proto, canonname, sockaddr) ...]
        # e.g. 4 = sockaddr - what we actually need
        for addr in addrlist:
            self.dests.append(addr)  # Just grab the first match
            break

    def _send_msg(self, dest, msg):
        # Note: heartbeat_key is mutable and must be looked up for each call
        envelope_str = status_message.wrap_envelope(
            msg, str(CONF.health_manager.heartbeat_key))
        # dest = (family, socktype, proto, canonname, sockaddr)
        # e.g. 0 = sock family, 4 = sockaddr - what we actually need
        try:
            if dest[0] == socket.AF_INET:
                self.v4sock.sendto(envelope_str, dest[4])
            elif dest[0] == socket.AF_INET6:
                self.v6sock.sendto(envelope_str, dest[4])
        except OSError:
            # Pass here as on amp boot it will get one or more
            # error: [Errno 101] Network is unreachable
            # while the networks are coming up
            # No harm in trying to send as it will still failover
            # if the message isn't received
            pass

    # The controller_ip_port_list configuration has mutated, reload it.
    def _update_dests(self):
        self.dests = []
        for ipport in CONF.health_manager.controller_ip_port_list:
            try:
                ip, port = ipport.rsplit(':', 1)
                if ip and ip[0] == '[' and ip[-1] == ']':
                    ip = ip[1:-1]
            except ValueError:
                LOG.error("Invalid ip and port '%s' in health_manager "
                          "controller_ip_port_list", ipport)
                break
            self.update(ip, port)
        self.current_controller_ip_port_list = (
            CONF.health_manager.controller_ip_port_list)

    def dosend(self, obj):
        # Check for controller_ip_port_list mutation
        if not (self.current_controller_ip_port_list ==
                CONF.health_manager.controller_ip_port_list):
            self._update_dests()
        dest = round_robin_addr(self.dests)
        if dest is None:
            LOG.error('No controller address found. Unable to send heartbeat.')
            return
        self._send_msg(dest, obj)
