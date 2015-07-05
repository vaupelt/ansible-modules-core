#!/usr/bin/python
#coding: utf-8 -*-

# (c) 2013, Benno Joy <benno@ansible.com>
#
# This module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.

try:
    import shade
    HAS_SHADE = True
except ImportError:
    HAS_SHADE = False


DOCUMENTATION = '''
---
module: os_subnet
short_description: Add/Remove subnet to an OpenStack network
extends_documentation_fragment: openstack
version_added: "2.0"
author: "Monty Taylor (@emonty)"
description:
   - Add or Remove a subnet to an OpenStack network
options:
   state:
     description:
        - Indicate desired state of the resource
     choices: ['present', 'absent']
     required: false
     default: present
   network_name:
     description:
        - Name of the network to which the subnet should be attached
     required: true when state is 'present'
   name:
     description:
       - The name of the subnet that should be created. Although Neutron
         allows for non-unique subnet names, this module enforces subnet
         name uniqueness.
     required: true
   cidr:
     description:
        - The CIDR representation of the subnet that should be assigned to
          the subnet.
     required: true when state is 'present'
     default: None
   ip_version:
     description:
        - The IP version of the subnet 4 or 6
     required: false
     default: 4
   enable_dhcp:
     description:
        - Whether DHCP should be enabled for this subnet.
     required: false
     default: true
   gateway_ip:
     description:
        - The ip that would be assigned to the gateway for this subnet
     required: false
     default: None
   dns_nameservers:
     description:
        - List of DNS nameservers for this subnet.
     required: false
     default: None
   allocation_pool_start:
     description:
        - From the subnet pool the starting address from which the IP should
          be allocated.
     required: false
     default: None
   allocation_pool_end:
     description:
        - From the subnet pool the last IP that should be assigned to the
          virtual machines.
     required: false
     default: None
   host_routes:
     description:
        - A list of host route dictionaries for the subnet.
     required: false
     default: None
requirements:
    - "python >= 2.6"
    - "shade"
'''

EXAMPLES = '''
# Create a new (or update an existing) subnet on the specified network
- os_subnet:
    state=present
    network_name=network1
    name=net1subnet
    cidr=192.168.0.0/24
    dns_nameservers:
       - 8.8.8.7
       - 8.8.8.8
    host_routes:
       - destination: 0.0.0.0/0
         nexthop: 123.456.78.9
       - destination: 192.168.0.0/24
         nexthop: 192.168.0.1

# Delete a subnet
- os_subnet:
    state=absent
    name=net1subnet
'''


def _needs_update(subnet, module):
    """Check for differences in the updatable values."""
    enable_dhcp = module.params['enable_dhcp']
    subnet_name = module.params['name']
    pool_start = module.params['allocation_pool_start']
    pool_end = module.params['allocation_pool_end']
    gateway_ip = module.params['gateway_ip']
    dns = module.params['dns_nameservers']
    host_routes = module.params['host_routes']
    curr_pool = subnet['allocation_pools'][0]

    if subnet['enable_dhcp'] != enable_dhcp:
        return True
    if subnet_name and subnet['name'] != subnet_name:
        return True
    if pool_start and curr_pool['start'] != pool_start:
        return True
    if pool_end and curr_pool['end'] != pool_end:
        return True
    if gateway_ip and subnet['gateway_ip'] != gateway_ip:
        return True
    if dns and sorted(subnet['dns_nameservers']) != sorted(dns):
        return True
    if host_routes:
        curr_hr = sorted(subnet['host_routes'], key=lambda t: t.keys())
        new_hr = sorted(host_routes, key=lambda t: t.keys())
        if sorted(curr_hr) != sorted(new_hr):
            return True
    return False


def _system_state_change(module, subnet):
    state = module.params['state']
    if state == 'present':
        if not subnet:
            return True
        return _needs_update(subnet, module)
    if state == 'absent' and subnet:
        return True
    return False


def main():
    argument_spec = openstack_full_argument_spec(
        name=dict(required=True),
        network_name=dict(default=None),
        cidr=dict(default=None),
        ip_version=dict(default='4', choices=['4', '6']),
        enable_dhcp=dict(default='true', type='bool'),
        gateway_ip=dict(default=None),
        dns_nameservers=dict(default=None, type='list'),
        allocation_pool_start=dict(default=None),
        allocation_pool_end=dict(default=None),
        host_routes=dict(default=None, type='list'),
        state=dict(default='present', choices=['absent', 'present']),
    )

    module_kwargs = openstack_module_kwargs()
    module = AnsibleModule(argument_spec,
                           supports_check_mode=True,
                           **module_kwargs)

    if not HAS_SHADE:
        module.fail_json(msg='shade is required for this module')

    state = module.params['state']
    network_name = module.params['network_name']
    cidr = module.params['cidr']
    ip_version = module.params['ip_version']
    enable_dhcp = module.params['enable_dhcp']
    subnet_name = module.params['name']
    gateway_ip = module.params['gateway_ip']
    dns = module.params['dns_nameservers']
    pool_start = module.params['allocation_pool_start']
    pool_end = module.params['allocation_pool_end']
    host_routes = module.params['host_routes']

    # Check for required parameters when state == 'present'
    if state == 'present':
        for p in ['network_name', 'cidr']:
            if not module.params[p]:
                module.fail_json(msg='%s required with present state' % p)

    if pool_start and pool_end:
        pool = [dict(start=pool_start, end=pool_end)]
    elif pool_start or pool_end:
        module.fail_json(msg='allocation pool requires start and end values')
    else:
        pool = None

    try:
        cloud = shade.openstack_cloud(**module.params)
        subnet = cloud.get_subnet(subnet_name)

        if module.check_mode:
            module.exit_json(changed=_system_state_change(module, subnet))

        if state == 'present':
            if not subnet:
                subnet = cloud.create_subnet(network_name, cidr,
                                             ip_version=ip_version,
                                             enable_dhcp=enable_dhcp,
                                             subnet_name=subnet_name,
                                             gateway_ip=gateway_ip,
                                             dns_nameservers=dns,
                                             allocation_pools=pool,
                                             host_routes=host_routes)
                changed = True
            else:
                if _needs_update(subnet, module):
                    cloud.update_subnet(subnet['id'],
                                        subnet_name=subnet_name,
                                        enable_dhcp=enable_dhcp,
                                        gateway_ip=gateway_ip,
                                        dns_nameservers=dns,
                                        allocation_pools=pool,
                                        host_routes=host_routes)
                    changed = True
                else:
                    changed = False
            module.exit_json(changed=changed)

        elif state == 'absent':
            if not subnet:
                changed = False
            else:
                changed = True
                cloud.delete_subnet(subnet_name)
            module.exit_json(changed=changed)

    except shade.OpenStackCloudException as e:
        module.fail_json(msg=e.message)


# this is magic, see lib/ansible/module_common.py
from ansible.module_utils.basic import *
from ansible.module_utils.openstack import *
if __name__ == '__main__':
    main()
