"""Executed inside the controller. PARAMS is injected by lab.py."""
import json
import subprocess

def cli(*args):
    raw = subprocess.check_output(['maas', 'lab', *args], text=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw

subnet = next(s for s in cli('subnets', 'read') if s['cidr'] == PARAMS['cidr'])
vlan = subnet['vlan']
rack = next(r for r in cli('rack-controllers', 'read')
            if any(i['vlan']['id'] == vlan['id'] for i in r['interface_set']))
ranges = cli('ipranges', 'read')
for kind, start, end in [('reserved', PARAMS['reserved_start'], PARAMS['reserved_end']),
                         ('dynamic', PARAMS['start'], PARAMS['end'])]:
    if not any(r['start_ip'] == start and r['end_ip'] == end and r['type'] == kind for r in ranges):
        cli('ipranges', 'create', 'subnet=' + str(subnet['id']), 'type=' + kind,
            'start_ip=' + start, 'end_ip=' + end)
cli('subnet', 'update', str(subnet['id']), 'dns_servers=' + PARAMS['ip'])
cli('vlan', 'update', str(vlan['fabric_id']), str(vlan['vid']),
    'dhcp_on=True', 'primary_rack=' + rack['system_id'])
cli('maas', 'set-config', 'name=upstream_dns', 'value=1.1.1.1')
cli('maas', 'set-config', 'name=default_distro_series', 'value=noble')
keys = cli('sshkeys', 'read')
if not any(k['key'].split()[:2] == PARAMS['key'].split()[:2] for k in keys):
    cli('sshkeys', 'create', 'key=' + PARAMS['key'])
sources = cli('boot-sources', 'read')
source = next((s for s in sources if 'images.maas.io' in s['url']), None)
if source is None:
    source = cli('boot-sources', 'create', 'url=https://images.maas.io/ephemeral-v3/stable/',
                 'keyring_filename=/snap/maas/current/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg')
sid = str(source['id'])
# Keep downloaded resources; only choose the needed kernel for future imports.
selections = cli('boot-source-selections', 'read', sid)
selection = next((s for s in selections if s['os'] == 'ubuntu' and s['release'] == 'noble'), None)
if selection:
    cli('boot-source-selection', 'update', sid, str(selection['id']), 'arches=amd64', 'subarches=ga-24.04', 'labels=*')
else:
    cli('boot-source-selections', 'create', sid, 'os=ubuntu', 'release=noble',
        'arches=amd64', 'subarches=ga-24.04', 'labels=*')
cli('boot-resources', 'import')
print('DHCP privado configurado. Importación iniciada; espere a que Images muestre Synced.')
