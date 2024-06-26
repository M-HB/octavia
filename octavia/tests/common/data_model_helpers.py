#    Copyright 2014 Rackspace
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

from octavia.common import constants
from octavia.common import data_models
from octavia.tests.common import constants as ut_constants


def generate_load_balancer_tree(additional_vips=None):
    vip = generate_vip()
    amps = [generate_amphora(), generate_amphora()]
    lb = generate_load_balancer(vip=vip, amphorae=amps,
                                additional_vips=additional_vips)
    return lb


LB_SEED = 0


def generate_load_balancer(vip=None, amphorae=None,
                           topology=constants.TOPOLOGY_SINGLE,
                           additional_vips=None):
    amphorae = amphorae or []
    additional_vips = additional_vips or []
    global LB_SEED
    LB_SEED += 1
    lb = data_models.LoadBalancer(id=f'lb{LB_SEED}-id',
                                  project_id='2',
                                  name=f'lb{LB_SEED}',
                                  description=f'lb{LB_SEED}',
                                  vip=vip,
                                  topology=topology,
                                  amphorae=amphorae)
    for amp in lb.amphorae:
        amp.load_balancer = lb
        amp.load_balancer_id = lb.id
        amp.status = constants.AMPHORA_ALLOCATED
    if vip:
        vip.load_balancer = lb
        vip.load_balancer_id = lb.id
    for add_vip in additional_vips:
        add_vip_obj = data_models.AdditionalVip(
            load_balancer_id=lb.id,
            ip_address=add_vip.get('ip_address'),
            subnet_id=add_vip.get('subnet_id'),
            network_id=vip.network_id,
            port_id=vip.port_id,
            load_balancer=lb
        )
        lb.additional_vips.append(add_vip_obj)
    return lb


VIP_SEED = 0


def generate_vip(load_balancer=None):
    global VIP_SEED
    VIP_SEED += 1
    vip = data_models.Vip(ip_address=f'10.0.0.{VIP_SEED}',
                          subnet_id=ut_constants.MOCK_VIP_SUBNET_ID,
                          port_id=f'vrrp-port-{VIP_SEED}',
                          load_balancer=load_balancer)
    if load_balancer:
        vip.load_balancer_id = load_balancer.id
    return vip


AMP_SEED = 0


def generate_amphora(load_balancer=None):
    global AMP_SEED
    AMP_SEED += 1
    amp = data_models.Amphora(id=f'amp{AMP_SEED}-id',
                              compute_id=f'amp{AMP_SEED}-compute-id',
                              status='ACTIVE',
                              lb_network_ip=f'99.99.99.{AMP_SEED}',
                              vrrp_ip=f'55.55.55.{AMP_SEED}',
                              vrrp_port_id=f'vrrp_port-{AMP_SEED}-id',
                              load_balancer=load_balancer)
    if load_balancer:
        amp.load_balancer_id = load_balancer.id
    return amp
