# Copyright 2018 Rackspace, US Inc.
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

import time

from octavia_lib.api.drivers import exceptions as driver_exceptions
from octavia_lib.common import constants as lib_consts
from oslo_log import log as logging
from oslo_utils import excutils

from octavia.common import constants as consts
from octavia.common import data_models
from octavia.common import utils
from octavia.db import api as db_apis
from octavia.db import repositories as repo
from octavia.statistics import stats_base

LOG = logging.getLogger(__name__)


class DriverUpdater:

    def __init__(self, **kwargs):
        self.repos = repo.Repositories()
        self.loadbalancer_repo = repo.LoadBalancerRepository()
        self.listener_repo = repo.ListenerRepository()
        self.pool_repo = repo.PoolRepository()
        self.health_mon_repo = repo.HealthMonitorRepository()
        self.member_repo = repo.MemberRepository()
        self.l7policy_repo = repo.L7PolicyRepository()
        self.l7rule_repo = repo.L7RuleRepository()
        self.listener_stats_repo = repo.ListenerStatisticsRepository()

        self.db_session = db_apis.get_session()
        super().__init__(**kwargs)

    def _check_for_lb_vip_deallocate(self, repo, lb_id):
        with self.db_session.begin():
            lb = repo.get(self.db_session, id=lb_id)
        if lb.vip.octavia_owned:
            vip = lb.vip
            # We need a backreference
            vip.load_balancer = lb
            # Only lookup the network driver if we have a VIP to deallocate
            network_driver = utils.get_network_driver()
            network_driver.deallocate_vip(vip)

    def _decrement_quota(self, repo, object_name, record_id):
        lock_session = self.db_session
        lock_session.begin()
        db_object = repo.get(lock_session, id=record_id)
        if db_object is None:
            lock_session.rollback()
            msg = ('{} with ID of {} is not present in the '
                   'database, it might have already been deleted. '
                   'Skipping quota update.'.format(
                       object_name, record_id))
            raise driver_exceptions.NotFound(msg)
        try:
            if db_object.provisioning_status == consts.DELETED:
                LOG.info('%(name)s with ID of %(id)s is already in the '
                         'DELETED state. Skipping quota update.',
                         {'name': object_name, 'id': record_id})
                lock_session.rollback()
                return
            self.repos.decrement_quota(lock_session,
                                       repo.model_class.__data_model__,
                                       db_object.project_id)
            lock_session.commit()
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error('Failed to decrement %(name)s quota for '
                          'project: %(proj)s the project may have excess '
                          'quota in use.', {'proj': db_object.project_id,
                                            'name': object_name})
                lock_session.rollback()

    def _process_status_update(self, repo, object_name, record,
                               delete_record=False):
        # Zero it out so that if the ID is missing from a record we do not
        # report the last LB as the failed record in the exception
        record_id = None
        try:
            record_id = record['id']
            record_kwargs = {}
            prov_status = record.get(consts.PROVISIONING_STATUS, None)
            if prov_status:
                if prov_status == consts.DELETED:
                    if object_name == consts.LOADBALANCERS:
                        self._check_for_lb_vip_deallocate(repo, record_id)

                    try:
                        self._decrement_quota(repo, object_name, record_id)
                    except driver_exceptions.NotFound:
                        # prov_status is DELETED and the object no longer
                        # exists in the DB, ignore the update.
                        return

                    if delete_record and object_name != consts.LOADBALANCERS:
                        with self.db_session.begin():
                            repo.delete(self.db_session, id=record_id)
                        return

                record_kwargs[consts.PROVISIONING_STATUS] = prov_status
            op_status = record.get(consts.OPERATING_STATUS, None)
            if op_status:
                record_kwargs[consts.OPERATING_STATUS] = op_status
            if prov_status or op_status:
                with self.db_session.begin():
                    repo.update(self.db_session, record_id, **record_kwargs)
        except Exception as e:
            # We need to raise a failure here to notify the driver it is
            # sending bad status data.
            raise driver_exceptions.UpdateStatusError(
                fault_string=str(e), status_object_id=record_id,
                status_object=object_name)

    def update_loadbalancer_status(self, status):
        """Update load balancer status.

        :param status: dictionary defining the provisioning status and
            operating status for load balancer objects, including pools,
            members, listeners, L7 policies, and L7 rules.
            iod (string): ID for the object.
            provisioning_status (string): Provisioning status for the object.
            operating_status (string): Operating status for the object.
        :type status: dict
        :raises: UpdateStatusError
        :returns: None
        """
        try:
            members = status.pop(consts.MEMBERS, [])
            for member in members:
                self._process_status_update(self.member_repo, consts.MEMBERS,
                                            member, delete_record=True)

            health_mons = status.pop(consts.HEALTHMONITORS, [])
            for health_mon in health_mons:
                self._process_status_update(
                    self.health_mon_repo, consts.HEALTHMONITORS, health_mon,
                    delete_record=True)

            pools = status.pop(consts.POOLS, [])
            for pool in pools:
                self._process_status_update(self.pool_repo, consts.POOLS,
                                            pool, delete_record=True)

            l7rules = status.pop(consts.L7RULES, [])
            for l7rule in l7rules:
                self._process_status_update(self.l7rule_repo, consts.L7RULES,
                                            l7rule, delete_record=True)

            l7policies = status.pop(consts.L7POLICIES, [])
            for l7policy in l7policies:
                self._process_status_update(
                    self.l7policy_repo, consts.L7POLICIES, l7policy,
                    delete_record=True)

            listeners = status.pop(lib_consts.LISTENERS, [])
            for listener in listeners:
                self._process_status_update(
                    self.listener_repo, lib_consts.LISTENERS, listener,
                    delete_record=True)

            lbs = status.pop(consts.LOADBALANCERS, [])
            for lb in lbs:
                self._process_status_update(self.loadbalancer_repo,
                                            consts.LOADBALANCERS, lb)
        except driver_exceptions.UpdateStatusError as e:
            return {lib_consts.STATUS_CODE: lib_consts.DRVR_STATUS_CODE_FAILED,
                    lib_consts.FAULT_STRING: e.fault_string,
                    lib_consts.STATUS_OBJECT: e.status_object,
                    lib_consts.STATUS_OBJECT_ID: e.status_object_id}
        except Exception as e:
            return {lib_consts.STATUS_CODE: lib_consts.DRVR_STATUS_CODE_FAILED,
                    lib_consts.FAULT_STRING: str(e)}
        return {lib_consts.STATUS_CODE: lib_consts.DRVR_STATUS_CODE_OK}

    def update_listener_statistics(self, statistics):
        """Update listener statistics.

        :param statistics: Statistics for listeners:
              id (string): ID for listener.
              active_connections (int): Number of currently active connections.
              bytes_in (int): Total bytes received.
              bytes_out (int): Total bytes sent.
              request_errors (int): Total requests not fulfilled.
              total_connections (int): The total connections handled.
        :type statistics: dict
        :raises: UpdateStatisticsError
        :returns: None
        """
        listener_stats = statistics.get(lib_consts.LISTENERS, [])
        stats_objects = []
        for stat in listener_stats:
            try:
                stats_obj = data_models.ListenerStatistics(
                    listener_id=stat['id'],
                    bytes_in=stat['bytes_in'],
                    bytes_out=stat['bytes_out'],
                    active_connections=stat['active_connections'],
                    total_connections=stat['total_connections'],
                    request_errors=stat['request_errors'],
                    received_time=time.time()
                )
                stats_objects.append(stats_obj)
            except Exception as e:
                return {
                    lib_consts.STATUS_CODE: lib_consts.DRVR_STATUS_CODE_FAILED,
                    lib_consts.FAULT_STRING: str(e),
                    lib_consts.STATS_OBJECT: lib_consts.LISTENERS}

        # Provider drivers other than the amphora driver do not have
        # an amphora ID, use the listener ID again here to meet the
        # constraint requirement.
        try:
            if stats_objects:
                stats_base.update_stats_via_driver(stats_objects)
        except Exception as e:
            return {
                lib_consts.STATUS_CODE: lib_consts.DRVR_STATUS_CODE_FAILED,
                lib_consts.FAULT_STRING: str(e),
                lib_consts.STATS_OBJECT: lib_consts.LISTENERS}
        return {lib_consts.STATUS_CODE: lib_consts.DRVR_STATUS_CODE_OK}
