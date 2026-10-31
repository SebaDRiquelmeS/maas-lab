import copy
import importlib.util
import ipaddress
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab', REPO / 'lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((REPO / 'config.example.json').read_text())

    def load(self, config):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            p.write_text(json.dumps(config))
            return lab.configuration(p)

    def test_defaults_valid(self):
        self.assertEqual(self.load(self.config)['prefix'], 'ml')

    def test_rejects_shell_characters(self):
        self.config['prefix'] = 'a;id'
        with self.assertRaises(ValueError):
            self.load(self.config)

    def test_rejects_overlapping_networks(self):
        self.config['nat_cidr'] = self.config['provision_cidr']
        with self.assertRaises(ValueError):
            self.load(self.config)

    def test_rejects_non_private_network(self):
        self.config['nat_cidr'] = '8.8.8.0/24'
        with self.assertRaises(ValueError):
            self.load(self.config)

    def test_rejects_zero_resources(self):
        self.config['node_memory_mib'] = 0
        with self.assertRaises(ValueError):
            self.load(self.config)

    def test_rejects_channel_injection(self):
        self.config['maas_channel'] = '3.7/stable;id'
        with self.assertRaises(ValueError):
            self.load(self.config)

class StateAndNetworkTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((REPO / 'config.example.json').read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lab = lab.Lab(self.config)
        self.lab.state = Path(self.temp.name) / 'state'
        self.lab.prepare()

    def test_preserves_same_configuration(self):
        self.lab.prepare()
        self.assertEqual(json.loads((self.lab.state / 'config.json').read_text()), self.config)

    def test_rejects_changed_state(self):
        self.lab.c = copy.deepcopy(self.config)
        self.lab.c['node_vcpus'] = 3
        with self.assertRaises(RuntimeError):
            self.lab.prepare()

    def test_refuses_overlapping_host_route_without_creating_network(self):
        with patch.object(self.lab, 'virsh', return_value='') as virsh, patch.object(lab, 'run', return_value='[{"dst":"192.168.210.0/24"}]'):
            with self.assertRaises(RuntimeError):
                self.lab.network('ml-nat', 'vb-ml', self.lab.nat, True)
            self.assertFalse(any(c.args[0] == 'net-define' for c in virsh.call_args_list))

    def test_refuses_foreign_network_with_same_name(self):
        xml = '<network><bridge name="wrong"/><ip address="192.168.210.1"/></network>'
        with patch.object(self.lab, 'virsh', side_effect=['ml-nat\n', xml]):
            with self.assertRaises(RuntimeError):
                self.lab.network('ml-nat', 'vb-ml', self.lab.nat, True)

    def test_isolated_network_has_no_dhcp_or_forward(self):
        with patch.object(self.lab, 'virsh', side_effect=['', '', '', '', '']), patch.object(lab, 'run', return_value='[]'):
            self.lab.network('ml-provision', 'vp-ml', self.lab.net, False)
        xml = (self.lab.state / 'ml-provision.xml').read_text()
        self.assertNotIn('<dhcp', xml)
        self.assertNotIn('<forward', xml)

    def test_incomplete_image_prevents_node_registration(self):
        resources = [{'name': 'ubuntu/noble', 'architecture': 'amd64/ga-24.04', 'id': 5}]
        with patch.object(self.lab, 'virsh', return_value=''), patch.object(self.lab, 'cli', side_effect=[resources, {'sets': {'v1': {'complete': False}}}]) as cli:
            with self.assertRaises(RuntimeError):
                self.lab.node_vm()
            self.assertEqual(cli.call_count, 2)
            self.assertFalse((self.lab.state / 'node.json').exists())

if __name__ == '__main__':
    unittest.main()
