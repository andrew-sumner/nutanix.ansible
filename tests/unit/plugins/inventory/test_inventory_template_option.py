# Copyright: (c) 2026, Nutanix
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest
from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.vault import VaultLib, VaultSecret
from ansible.plugins.loader import inventory_loader
from ansible.template import Templar
from ansible_collections.nutanix.ncp.plugins.module_utils.utils import (
    get_custom_headers,
)

# These use the real plugin loader and config manager of the installed
# ansible-core, so they cover how it reports inventory file values.
PLUGINS = [
    "nutanix.ncp.ntnx_prism_vm_inventory_v2",
    "nutanix.ncp.ntnx_prism_host_inventory_v2",
]

# A fake vault password, for encrypting test values only.
VAULT_SECRETS = [("default", VaultSecret(b"fake-vault-password"))]

try:  # ansible-core 2.19+ decrypts through an active secrets context
    from ansible.parsing.vault import VaultSecretsContext

    try:
        VaultSecretsContext.initialize(VaultSecretsContext(secrets=VAULT_SECRETS))
    except Exception:  # already initialised in this process
        pass
except ImportError:
    pass


def _vaulted(plaintext, indent):
    """YAML for a !vault value encrypted with the fake password."""
    cipher = VaultLib(VAULT_SECRETS).encrypt(plaintext).decode()
    pad = " " * indent
    return "!vault |\n" + "\n".join(pad + line for line in cipher.splitlines())


def _plugin_from_file(name, tmp_path, lines):
    """Load an inventory file through the plugin's own config reading."""
    path = tmp_path / "nutanix.yml"
    path.write_text("\n".join(["plugin: " + name] + lines) + "\n")
    plugin = inventory_loader.get(name)
    assert plugin is not None, name
    plugin.loader = DataLoader()
    plugin.loader.set_vault_secrets(VAULT_SECRETS)
    plugin.templar = Templar(loader=plugin.loader)
    plugin._file_config = plugin._read_config_data(str(path)) or {}
    return plugin


@pytest.mark.parametrize("name", PLUGINS)
def test_template_option_templates_inventory_file_values(name, tmp_path):
    plugin = _plugin_from_file(
        name, tmp_path, ["nutanix_password: \"{{ 'pw' ~ '1' }}\""]
    )
    assert plugin._template_option("nutanix_password") == "pw1"


@pytest.mark.parametrize("name", PLUGINS)
def test_template_option_leaves_env_values(name, tmp_path, monkeypatch):
    # A secret containing template syntax must not be evaluated or break parsing.
    monkeypatch.setenv("NUTANIX_PASSWORD", "ab{{cd")
    plugin = _plugin_from_file(name, tmp_path, [])
    assert plugin._template_option("nutanix_password") == "ab{{cd"


@pytest.mark.parametrize("name", PLUGINS)
def test_file_values_seen_before_env(name, tmp_path, monkeypatch):
    # The inventory file's value wins over the environment, and is found on every
    # supported ansible-core (get_option_and_origin misses it before 2.18).
    monkeypatch.setenv("NUTANIX_PASSWORD", "envpw")
    plugin = _plugin_from_file(name, tmp_path, ["nutanix_password: filepw"])
    assert plugin._template_option("nutanix_password") == "filepw"
    assert "nutanix_password" in plugin._file_config


@pytest.mark.parametrize("name", PLUGINS)
def test_empty_file_key_leaves_env_value(name, tmp_path, monkeypatch):
    # A key left empty in the file falls through to the environment; that value
    # must still be used as-is, not templated.
    monkeypatch.setenv("NUTANIX_PASSWORD", "ab{{ 6 * 7 }}")
    plugin = _plugin_from_file(name, tmp_path, ["nutanix_password:"])
    assert plugin._template_option("nutanix_password") == "ab{{ 6 * 7 }}"


@pytest.mark.parametrize("name", PLUGINS)
def test_vaulted_file_value_not_templated(name, tmp_path):
    # Before ansible-core 2.19, get_option() returns vaulted values already
    # decrypted; a vaulted secret containing template syntax must not change.
    plugin = _plugin_from_file(
        name, tmp_path, ["nutanix_password: " + _vaulted("ab{#x#}cd", 4)]
    )
    assert str(plugin._template_option("nutanix_password")) == "ab{#x#}cd"


@pytest.mark.parametrize("name", PLUGINS)
def test_vaulted_custom_header_not_templated(name, tmp_path):
    # Each custom_headers value is decided separately: plain ones are templated,
    # vaulted ones are left as they are.
    plugin = _plugin_from_file(
        name,
        tmp_path,
        [
            "custom_headers:",
            "  X-Plain: \"{{ 'h' ~ '1' }}\"",
            "  X-Secret: " + _vaulted("s{{ecret", 4),
        ],
    )
    headers = plugin._template_option("custom_headers")
    assert headers["X-Plain"] == "h1"
    # What reaches the SDK must be text: it cannot send a vault object.
    sent = get_custom_headers({"custom_headers": headers})
    assert sent["X-Secret"] == "s{{ecret"
    assert isinstance(sent["X-Secret"], str)


@pytest.mark.parametrize("name", PLUGINS)
def test_template_error_does_not_show_value(name, tmp_path):
    # A plain file value with broken template syntax fails, naming the option
    # but not echoing the value, which may be a secret.
    plugin = _plugin_from_file(name, tmp_path, ['nutanix_password: "S3cr{#tPw"'])
    with pytest.raises(AnsibleError) as err:
        plugin._template_option("nutanix_password")
    assert "nutanix_password" in str(err.value)
    assert "S3cr" not in str(err.value)
