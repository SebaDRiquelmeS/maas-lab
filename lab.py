#!/usr/bin/env python3
"""Laboratorio MAAS por etapas; no despliega el sistema del nodo automáticamente."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STATE = Path('/var/lib/maas-lab')

def run(args, *, capture=False, data=None, env=None, timeout=None):
    return subprocess.run([str(a) for a in args], check=True, text=True,
                          input=data, stdout=subprocess.PIPE if capture else None,
                          env=env, timeout=timeout).stdout

def configuration(path=None):
    path = Path(path) if path else ROOT / 'config.json'
    c = json.loads((path if path.exists() else ROOT / 'config.example.json').read_text())
    if not re.fullmatch(r'[a-z][a-z0-9]{1,7}', c['prefix']):
        raise ValueError('prefix: 2-8 letras/dígitos, empieza con letra')
    a, b = (ipaddress.ip_network(c[k]) for k in ('nat_cidr', 'provision_cidr'))
    private_blocks = [ipaddress.ip_network(x) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    if (any(n.version != 4 or n.prefixlen != 24 for n in (a, b)) or a.overlaps(b)
            or any(not any(n.subnet_of(block) for block in private_blocks) for n in (a, b))):
        raise ValueError('Se requieren dos redes IPv4 /24 diferentes')
    for k in ('controller_memory_mib', 'controller_vcpus', 'controller_disk_gib',
              'node_memory_mib', 'node_vcpus', 'node_disk_gib'):
        if type(c[k]) is not int or c[k] <= 0:
            raise ValueError(f'{k} debe ser un entero positivo')
    if not re.fullmatch(r'3\.\d+/stable', c['maas_channel']):
        raise ValueError('Canal MAAS inválido')
    if not re.fullmatch(r'\d+\.\d+\.\d+', c['virtualbmc_version']):
        raise ValueError('Versión VirtualBMC inválida')
    if type(c['bmc_server_port']) is not int or not 1024 < c['bmc_server_port'] < 65536:
        raise ValueError('bmc_server_port debe estar entre 1025 y 65535')
    return c

class Lab:
    def __init__(self, c):
        self.c = c
        self.prefix = c['prefix']
        self.state = STATE / self.prefix
        self.nat = ipaddress.ip_network(c['nat_cidr'])
        self.net = ipaddress.ip_network(c['provision_cidr'])
        self.ip = str(self.net[2])
        self.controller = self.prefix + '-controller'
        self.node = self.prefix + '-node01'
        self.natname = self.prefix + '-nat'
        self.netname = self.prefix + '-provision'
        self.bridge = 'vb-' + self.prefix
        self.pbridge = 'vp-' + self.prefix
        self.url = f'http://{self.ip}:5240/MAAS/'
        self.mac1 = '52:54:00:be:00:01'
        self.mac2 = '52:54:00:be:00:02'
        self.macnode = '52:54:00:be:01:01'

    def prepare(self):
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        snapshot = self.state / 'config.json'
        if snapshot.exists() and json.loads(snapshot.read_text()) != self.c:
            raise RuntimeError('La configuración cambió respecto del estado. Use otro prefix para otro laboratorio.')
        snapshot.write_text(json.dumps(self.c, indent=2))

    def virsh(self, *args, capture=False):
        return run(['virsh', '-c', 'qemu:///system', *args], capture=capture)

    def ssh(self, command, *, data=None, capture=False):
        return run(['ssh', '-i', self.state / 'id_ed25519', '-o', 'BatchMode=yes',
                    '-o', 'StrictHostKeyChecking=accept-new', '-o',
                    f'UserKnownHostsFile={self.state}/known_hosts', '-o', 'ConnectTimeout=10',
                    'estudiante@' + self.ip, command], data=data, capture=capture)

    def guest_python(self, code, capture=False):
        return self.ssh('sudo python3 -', data=code, capture=capture)

    def cli(self, *args):
        # json strings form safe shell arguments through shlex.join, never interpolation.
        import shlex
        return json.loads(self.ssh(shlex.join(['sudo', 'maas', 'lab', *args]), capture=True))

    def doctor(self):
        if os.uname().machine != 'x86_64':
            raise RuntimeError('Este laboratorio requiere CPU x86_64')
        if not Path('/dev/kvm').exists():
            raise RuntimeError('No existe /dev/kvm: habilite VT-x/AMD-V en BIOS/UEFI')
        for command in ('virsh', 'virt-install', 'qemu-img', 'curl', 'xorriso', 'ssh-keygen', 'ip'):
            if not shutil.which(command):
                raise RuntimeError(f'Falta {command}; ejecute scripts/bootstrap.sh')
        self.virsh('list', '--all')
        print('KVM y libvirt disponibles. Redes elegidas:', self.nat, self.net)
        print('RAM total GiB:', round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30, 1))
        print('Espacio libre GiB:', round(shutil.disk_usage(self.state).free / 2**30, 1))

    def network(self, name, bridge, network, nat):
        existing = self.virsh('net-list', '--all', '--name', capture=True).split()
        if name in existing:
            # Never adopt an unrelated existing network.
            import xml.etree.ElementTree as ET
            root = ET.fromstring(self.virsh('net-dumpxml', name, capture=True))
            addr = root.find('ip')
            if root.find('bridge').get('name') != bridge or addr is None or addr.get('address') != str(network[1]):
                raise RuntimeError('Colisión con red existente: ' + name)
        else:
            routes = json.loads(run(['ip', '-j', '-4', 'route', 'show', 'table', 'all'], capture=True))
            for route in routes:
                dst = route.get('dst', 'default')
                if dst != 'default' and network.overlaps(ipaddress.ip_network(dst, strict=False)):
                    raise RuntimeError(f'La red {network} se solapa con {dst}; edite config.json antes de crear el lab')
            dhcp = f'<dhcp><range start="{network[100]}" end="{network[199]}"/></dhcp>' if nat else ''
            xml = f'<network><name>{name}</name><bridge name="{bridge}"/>'
            xml += '<forward mode="nat"/>' if nat else ''
            xml += f'<ip address="{network[1]}" netmask="255.255.255.0">{dhcp}</ip></network>'
            path = self.state / (name + '.xml')
            path.write_text(xml)
            self.virsh('net-define', path)
        if name not in self.virsh('net-list', '--name', capture=True).split():
            self.virsh('net-start', name)
        self.virsh('net-autostart', name)

    def firewall(self):
        # Explicit command, documented narrow UFW changes; never disable firewall.
        if not shutil.which('ufw') or 'Status: active' not in run(['ufw', 'status'], capture=True, env={**os.environ, 'LC_ALL': 'C'}):
            print('UFW no está activo; configure su cortafuegos si usa otro. Consulte docs/NETWORKING.md.')
            return
        for port, proto in (('67', 'udp'), ('53', 'udp'), ('53', 'tcp')):
            run(['ufw', 'allow', 'in', 'on', self.bridge, 'to', 'any', 'port', port, 'proto', proto])
        routes = json.loads(run(['ip', '-j', '-4', 'route', 'show', 'default'], capture=True))
        for dev in sorted({r['dev'] for r in routes}):
            run(['ufw', 'route', 'allow', 'in', 'on', self.bridge, 'out', 'on', dev,
                 'from', str(self.nat)])
        run(['ufw', 'allow', 'in', 'on', self.pbridge, 'from', self.ip,
             'to', str(self.net[1]), 'port', '16230', 'proto', 'udp'])

    def controller_vm(self):
        self.doctor()
        if self.controller in self.virsh('list', '--all', '--name', capture=True).split():
            print('La VM ya existe; no se modifica. Continúe con maas cuando SSH responda.')
            return
        self.network(self.natname, self.bridge, self.nat, True)
        self.network(self.netname, self.pbridge, self.net, False)
        key = self.state / 'id_ed25519'
        if not key.exists():
            run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', key])
        image = self.state / 'ubuntu.img'
        sums = self.state / 'SHA256SUMS'
        base = 'https://cloud-images.ubuntu.com/noble/current/'
        if not image.exists():
            run(['curl', '-fL', '--retry', '3', '-o', image, base + 'noble-server-cloudimg-amd64.img'])
            run(['curl', '-fL', '--retry', '3', '-o', sums, base + 'SHA256SUMS'])
        import hashlib
        expected = next(line.split()[0] for line in sums.read_text().splitlines()
                        if line.split()[-1].lstrip('*') == 'noble-server-cloudimg-amd64.img')
        with image.open('rb') as f:
            actual = hashlib.file_digest(f, 'sha256').hexdigest()
        if actual != expected:
            raise RuntimeError('Checksum incorrecto. Elimine ubuntu.img y SHA256SUMS del estado y reintente.')
        public_key = key.with_suffix('.pub').read_text().strip()
        (self.state / 'user-data').write_text('''#cloud-config
hostname: ''' + self.controller + '''
manage_etc_hosts: true
users:
  - name: estudiante
    groups: [sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: true
    ssh_authorized_keys:
      - ''' + public_key + '''
ssh_pwauth: false
packages: [qemu-guest-agent]
runcmd:
  - [systemctl, start, qemu-guest-agent]
''')
        (self.state / 'meta-data').write_text(f'instance-id: {self.controller}-01\nlocal-hostname: {self.controller}\n')
        (self.state / 'network-config').write_text(f'''version: 2
ethernets:
  uplink:
    match:
      macaddress: "{self.mac1}"
    dhcp4: true
  provision:
    match:
      macaddress: "{self.mac2}"
    addresses: [{self.ip}/24]
''')
        seed = self.state / 'seed.iso'
        run(['xorriso', '-as', 'mkisofs', '-output', seed, '-volid', 'cidata', '-joliet', '-rock',
             *[self.state / name for name in ('user-data', 'meta-data', 'network-config')]])
        disks = Path('/var/lib/libvirt/images') / ('maas-lab-' + self.prefix)
        disks.mkdir(parents=True, exist_ok=True)
        disks.chmod(0o755)
        disk = disks / 'controller.qcow2'
        if disk.exists():
            raise RuntimeError('Disco existente sin VM: inspeccione antes de continuar: ' + str(disk))
        run(['cp', '--sparse=always', image, disk])
        run(['cp', seed, disks / 'seed.iso'])
        run(['chmod', '644', disk, disks / 'seed.iso'])
        run(['qemu-img', 'resize', disk, str(self.c['controller_disk_gib']) + 'G'])
        run(['virt-install', '--connect', 'qemu:///system', '--name', self.controller,
             '--memory', self.c['controller_memory_mib'], '--vcpus', self.c['controller_vcpus'],
             '--cpu', 'host-passthrough', '--os-variant', 'ubuntu24.04', '--import',
             '--disk', f'path={disk},format=qcow2,bus=virtio',
             '--disk', f'path={disks}/seed.iso,device=cdrom',
             '--network', f'network={self.natname},model=virtio,mac={self.mac1}',
             '--network', f'network={self.netname},model=virtio,mac={self.mac2}',
             '--graphics', 'spice,listen=127.0.0.1', '--noautoconsole'])
        print('Controlador creado. Aplique firewall y espere 2-5 minutos; después ejecute maas.')

    def maas(self):
        self.ssh('cloud-init status --wait')
        print('Instalando MAAS y PostgreSQL dentro de la VM...')
        self.ssh('sudo systemctl disable --now systemd-timesyncd && '
                 f'(snap list maas >/dev/null 2>&1 || sudo snap install maas --channel={self.c["maas_channel"]}) && '
                 '(snap list postgresql >/dev/null 2>&1 || sudo snap install postgresql --channel=16/stable)')
        code = (ROOT / 'scripts/guest-init.py').read_text()
        self.guest_python('URL=' + repr(self.url) + '\n' + code)
        raw = self.ssh('sudo cat /root/lab-credentials.json', capture=True)
        (self.state / 'credentials.json').write_text(raw)
        print('MAAS inicializado. Credenciales en', self.state / 'credentials.json')

    def configure_maas(self):
        code = (ROOT / 'scripts/guest-configure.py').read_text()
        params = {'cidr': str(self.net), 'ip': self.ip, 'start': str(self.net[100]),
                  'end': str(self.net[199]), 'reserved_start': str(self.net[1]),
                  'reserved_end': str(self.net[9]), 'key': (self.state / 'id_ed25519.pub').read_text().strip()}
        self.guest_python('PARAMS=' + repr(params) + '\n' + code)

    def node_vm(self):
        if self.node in self.virsh('list', '--all', '--name', capture=True).split():
            print('Nodo existente: no se modifica.')
            return
        # Ensure boot resources are actually complete before booting an empty disk.
        resources = self.cli('boot-resources', 'read')
        candidates = [r for r in resources if r['name'] == 'ubuntu/noble' and r['architecture'] == 'amd64/ga-24.04']
        if not candidates:
            raise RuntimeError('Falta la imagen Ubuntu; ejecute configure y espere la importación')
        resource = self.cli('boot-resource', 'read', str(candidates[0]['id']))
        if not any(s.get('complete') for s in resource.get('sets', {}).values()):
            raise RuntimeError('Imagen aún incompleta. Consulte Images en MAAS.')
        record = self.state / 'node.json'
        if record.exists():
            m = self.cli('machine', 'read', json.loads(record.read_text())['system_id'])
            if m['hostname'] != self.node or m['status_name'] != 'New':
                raise RuntimeError('Registro previo no está en New o no corresponde al nodo; revise MAAS')
        else:
            m = self.cli('machines', 'create', 'hostname=' + self.node, 'architecture=amd64/generic',
                         'mac_addresses=' + self.macnode, 'power_type=manual', 'commission=false')
            record.write_text(json.dumps({'system_id': m['system_id']}))
        disks = Path('/var/lib/libvirt/images') / ('maas-lab-' + self.prefix)
        run(['virt-install', '--connect', 'qemu:///system', '--name', self.node,
             '--memory', self.c['node_memory_mib'], '--vcpus', self.c['node_vcpus'], '--cpu', 'host-passthrough',
             '--os-variant', 'ubuntu24.04', '--disk', f'path={disks}/node01.qcow2,size={self.c["node_disk_gib"]},format=qcow2,bus=virtio',
             '--network', f'network={self.netname},model=virtio,mac={self.macnode}',
             '--boot', 'network,hd', '--pxe', '--graphics', 'spice,listen=127.0.0.1', '--noautoconsole'])
        print('Nodo registrado. Espere a que finalice su primer arranque; configure BMC y haga Commission desde la UI.')

    def bmc(self):
        venv = self.state / 'venv'
        if not (venv / 'bin/vbmc').exists():
            run(['python3', '-m', 'venv', '--system-site-packages', venv])
            run([venv / 'bin/pip', 'install', 'virtualbmc==' + self.c['virtualbmc_version']])
        config = self.state / 'virtualbmc.conf'
        config.write_text(f'[default]\nconfig_dir={self.state}/vbmc\npid_file={self.state}/vbmcd.pid\nserver_port={self.c["bmc_server_port"]}\n')
        env = os.environ.copy()
        env['VIRTUALBMC_CONFIG'] = str(config)
        unit = 'maas-lab-' + self.prefix + '-bmc.service'
        unit_path = Path('/etc/systemd/system', unit)
        if not unit_path.exists():
            # Do not accidentally send commands to another vbmcd already running.
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1', self.c['bmc_server_port']))
                except OSError as exc:
                    raise RuntimeError('Puerto de gestión BMC ocupado; elija otro bmc_server_port antes de crear el lab') from exc
        service = f'''[Unit]
Description=VirtualBMC para {self.node}
Requires=libvirtd.service
After=libvirtd.service
[Service]
Environment=VIRTUALBMC_CONFIG={config}
ExecStart={venv}/bin/vbmcd --foreground
Restart=on-failure
RestartSec=10
[Install]
WantedBy=multi-user.target
'''
        run(['install', '-d', '-m', '700', self.state / 'vbmc'])
        if unit_path.exists() and unit_path.read_text() != service:
            raise RuntimeError('Ya existe un servicio diferente con ese nombre; no se reemplaza')
        unit_path.write_text(service)
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', '--now', unit])
        credential = self.state / 'bmc-credentials.json'
        if not credential.exists():
            credential.write_text(json.dumps({'username': 'maas', 'password': secrets.token_hex(8)}))
        c = json.loads(credential.read_text())
        listing = json.loads(run([venv / 'bin/vbmc', 'list', '-f', 'json'], env=env, capture=True))
        if not any(r.get('Domain name') == self.node for r in listing):
            run([venv / 'bin/vbmc', 'add', self.node, '--address', self.net[1], '--port', '16230',
                 '--username', c['username'], '--password', c['password']], env=env)
        run([venv / 'bin/vbmc', 'start', self.node], env=env)
        sid = json.loads((self.state / 'node.json').read_text())['system_id']
        self.cli('machine', 'update', sid, 'power_type=ipmi',
                 'power_parameters_power_address=' + str(self.net[1]) + ':16230',
                 'power_parameters_power_user=' + c['username'], 'power_parameters_power_pass=' + c['password'],
                 'power_parameters_power_driver=LAN_2_0', 'power_parameters_cipher_suite_id=3',
                 'power_parameters_privilege_level=ADMIN', 'power_parameters_power_boot_type=legacy')
        print('Consulta de estado IPMI:', self.cli('machine', 'query-power-state', sid))
        print('BMC listo. Commission y Deploy se realizan desde la interfaz MAAS.')

    def status(self):
        self.virsh('list', '--all')
        print('Interfaz:', self.url)
        print('Credenciales:', self.state / 'credentials.json')
        if (self.state / 'node.json').exists():
            sid = json.loads((self.state / 'node.json').read_text())['system_id']
            m = self.cli('machine', 'read', sid)
            print({k: m.get(k) for k in ('hostname', 'status_name', 'power_state', 'ip_addresses', 'cpu_count', 'memory')})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='Ruta a una configuración JSON')
    parser.add_argument('step', choices=['doctor', 'controller', 'firewall', 'maas', 'configure', 'node', 'bmc', 'status', 'ssh'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Ejecute con sudo python3 lab.py ...')
    os.umask(0o077)
    lab = Lab(configuration(args.config))
    lab.prepare()
    actions = {'controller': lab.controller_vm, 'configure': lab.configure_maas,
               'node': lab.node_vm, 'ssh': lambda: lab.ssh('hostname; ip -brief address; sudo maas status')}
    try:
        actions.get(args.step, getattr(lab, args.step, None))()
    except (subprocess.CalledProcessError, RuntimeError, ValueError, OSError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        print('No se borraron VM ni discos. Revise docs/TROUBLESHOOTING.md.', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
