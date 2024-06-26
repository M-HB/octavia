# Copyright 2018 Rackspace, US Inc.
# Copyright 2019 Red Hat, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import errno
import os
import socketserver
import threading

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils

from octavia.api.drivers.driver_agent import driver_get
from octavia.api.drivers.driver_agent import driver_updater


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def _recv(recv_socket):
    size_str = b''
    char = recv_socket.recv(1)
    while char != b'\n':
        size_str += char
        char = recv_socket.recv(1)
    payload_size = int(size_str)
    mv_buffer = memoryview(bytearray(payload_size))
    next_offset = 0
    while payload_size - next_offset > 0:
        recv_size = recv_socket.recv_into(mv_buffer[next_offset:],
                                          payload_size - next_offset)
        next_offset += recv_size
    return jsonutils.loads(mv_buffer.tobytes())


class StatusRequestHandler(socketserver.BaseRequestHandler):

    def handle(self):
        # Get the update data
        try:
            status = _recv(self.request)
        except Exception:
            LOG.exception("Error while receiving data.")
            return

        # Process the update
        updater = driver_updater.DriverUpdater()
        response = updater.update_loadbalancer_status(status)

        # Send the response
        json_data = jsonutils.dump_as_bytes(response)
        len_str = f'{len(json_data)}\n'.encode()
        try:
            self.request.send(len_str)
            self.request.sendall(json_data)
        except Exception:
            LOG.exception("Error while sending data.")


class StatsRequestHandler(socketserver.BaseRequestHandler):

    def handle(self):
        # Get the update data
        try:
            stats = _recv(self.request)
        except Exception:
            LOG.exception("Error while receiving data.")
            return

        # Process the update
        updater = driver_updater.DriverUpdater()
        response = updater.update_listener_statistics(stats)

        # Send the response
        json_data = jsonutils.dump_as_bytes(response)
        len_str = f'{len(json_data)}\n'.encode()
        try:
            self.request.send(len_str)
            self.request.sendall(json_data)
        except Exception:
            LOG.exception("Error while sending data.")


class GetRequestHandler(socketserver.BaseRequestHandler):

    def handle(self):
        # Get the data request
        try:
            get_data = _recv(self.request)
        except Exception:
            LOG.exception("Error while receiving data.")
            return

        # Process the get
        response = driver_get.process_get(get_data)

        # Send the response
        json_data = jsonutils.dump_as_bytes(response)
        len_str = f'{len(json_data)}\n'.encode()
        try:
            self.request.send(len_str)
            self.request.sendall(json_data)
        except Exception:
            LOG.exception("Error while sending data.")


class ForkingUDSServer(socketserver.ForkingMixIn,
                       socketserver.UnixStreamServer):
    pass


def _cleanup_socket_file(filename):
    # Remove the socket file if it already exists
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def status_listener(exit_event):
    _cleanup_socket_file(CONF.driver_agent.status_socket_path)

    with ForkingUDSServer(CONF.driver_agent.status_socket_path,
                          StatusRequestHandler) as server:
        server.timeout = CONF.driver_agent.status_request_timeout
        server.max_children = CONF.driver_agent.status_max_processes

        threading.Thread(target=server.serve_forever).start()

        exit_event.wait()

        LOG.info('Waiting for driver status listener to shutdown...')
        server.shutdown()
        LOG.info('Driver status listener shutdown finished.')
    _cleanup_socket_file(CONF.driver_agent.status_socket_path)


def stats_listener(exit_event):
    _cleanup_socket_file(CONF.driver_agent.stats_socket_path)

    with ForkingUDSServer(CONF.driver_agent.stats_socket_path,
                          StatsRequestHandler) as server:
        server.timeout = CONF.driver_agent.stats_request_timeout
        server.max_children = CONF.driver_agent.stats_max_processes

        threading.Thread(target=server.serve_forever).start()

        exit_event.wait()

        LOG.info('Waiting for driver statistics listener to shutdown...')
        server.shutdown()
        LOG.info('Driver statistics listener shutdown finished.')
    _cleanup_socket_file(CONF.driver_agent.stats_socket_path)


def get_listener(exit_event):
    _cleanup_socket_file(CONF.driver_agent.get_socket_path)

    with ForkingUDSServer(CONF.driver_agent.get_socket_path,
                          GetRequestHandler) as server:
        server.timeout = CONF.driver_agent.get_request_timeout
        server.max_children = CONF.driver_agent.get_max_processes

        threading.Thread(target=server.serve_forever).start()

        exit_event.wait()

        LOG.info('Waiting for driver get listener to shutdown...')
        server.shutdown()
        LOG.info('Driver get listener shutdown finished.')
    _cleanup_socket_file(CONF.driver_agent.get_socket_path)
    LOG.info("UDS server was closed and socket was cleaned up.")
