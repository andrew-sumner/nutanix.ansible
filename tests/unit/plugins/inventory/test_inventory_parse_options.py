# Copyright: (c) 2026, Nutanix
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import sys

import pytest
from ansible.inventory.data import InventoryData
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import inventory_loader

# Run parse() on the real plugins with the installed ansible-core, stopping at the
# first SDK call to capture the connection parameters it was given.
PLUGINS = [
    "nutanix.ncp.ntnx_prism_vm_inventory_v2",
    "nutanix.ncp.ntnx_prism_host_inventory_v2",
]


class _Captured(Exception):
    pass


def _capture(module):
    raise _Captured(module.params)


def _connection_params(name, tmp_path, monkeypatch, lines, env):
    for key in list(os.environ):
        if key.startswith("NUTANIX") or key in ("VALIDATE_CERTS",):
            monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    plugin = inventory_loader.get(name)
    assert plugin is not None, name
    module = sys.modules[type(plugin).__module__]
    for fn in ("get_vm_api_instance", "get_clusters_api_instance"):
        if hasattr(module, fn):
            monkeypatch.setattr(module, fn, _capture)
    path = tmp_path / "nutanix.yml"
    path.write_text("\n".join(["plugin: " + name] + lines) + "\n")
    with pytest.raises(_Captured) as captured:
        plugin.parse(InventoryData(), DataLoader(), str(path), cache=False)
    return captured.value.args[0]


CREDS = ["nutanix_username: u", "nutanix_password: p"]


@pytest.mark.parametrize("name", PLUGINS)
def test_endpoint_supplies_host_and_port(name, tmp_path, monkeypatch):
    params = _connection_params(
        name,
        tmp_path,
        monkeypatch,
        CREDS,
        {"NUTANIX_ENDPOINT": "https://pc.example.test:9441"},
    )
    assert params["nutanix_host"] == "pc.example.test"
    assert str(params["nutanix_port"]) == "9441"


@pytest.mark.parametrize("name", PLUGINS)
def test_file_port_beats_endpoint_port(name, tmp_path, monkeypatch):
    params = _connection_params(
        name,
        tmp_path,
        monkeypatch,
        CREDS + ['nutanix_port: "9443"'],
        {"NUTANIX_ENDPOINT": "https://pc.example.test:9441"},
    )
    assert str(params["nutanix_port"]) == "9443"


@pytest.mark.parametrize("name", PLUGINS)
def test_env_port_beats_endpoint_port(name, tmp_path, monkeypatch):
    params = _connection_params(
        name,
        tmp_path,
        monkeypatch,
        CREDS,
        {"NUTANIX_ENDPOINT": "https://pc.example.test:9441", "NUTANIX_PORT": "9442"},
    )
    assert str(params["nutanix_port"]) == "9442"


@pytest.mark.parametrize("name", PLUGINS)
def test_host_beats_endpoint(name, tmp_path, monkeypatch):
    params = _connection_params(
        name,
        tmp_path,
        monkeypatch,
        CREDS,
        {
            "NUTANIX_HOST": "h.example.test",
            "NUTANIX_ENDPOINT": "https://pc.example.test:9441",
        },
    )
    assert params["nutanix_host"] == "h.example.test"
    assert str(params["nutanix_port"]) == "9440"


@pytest.mark.parametrize("name", PLUGINS)
def test_templated_api_key_is_plain_str(name, tmp_path, monkeypatch):
    # The SDK's set_api_key silently stores None for a str subclass, which a
    # lookup result (AnsibleUnsafeText) is before ansible-core 2.19.
    params = _connection_params(
        name,
        tmp_path,
        monkeypatch,
        [
            "nutanix_host: pc.example.test",
            "nutanix_api_key: \"{{ lookup('env', 'TEST_KEY') }}\"",
        ],
        {"TEST_KEY": "key"},
    )
    assert params["nutanix_api_key"] == "key"
    # Exactly str: isinstance() would accept the subclass that is the bug.
    assert params["nutanix_api_key"].__class__ is str
