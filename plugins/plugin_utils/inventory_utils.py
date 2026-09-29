# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Nutanix
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.module_utils._text import to_text

try:  # ansible-core 2.19+
    from ansible.parsing.vault import VaultHelper
except ImportError:
    VaultHelper = None


def is_vault_encrypted(value):
    """
    Whether a value loaded from an inventory file was vault-encrypted.
    Before ansible-core 2.19 the loader returns AnsibleVaultEncryptedUnicode,
    marked __ENCRYPTED__; from 2.19 it returns an EncryptedString, whose
    ciphertext VaultHelper can recover.
    """
    if getattr(value, "__ENCRYPTED__", False):
        return True
    if VaultHelper is not None:
        return VaultHelper.get_ciphertext(value, with_tags=False) is not None
    return False


def template_file_option(templar, file_config, option_name, value):
    """
    Template an inventory option's value if, and only if, it was given as plain
    text in the inventory file, so it can use lookups for secrets.

    Values from environment variables or defaults (a key absent or empty in the
    file) and vault-encrypted values are returned as-is: a secret that happens to
    contain template syntax must never be evaluated. Before ansible-core 2.19,
    get_option() returns vaulted values already decrypted, so this is decided
    from the loaded file (file_config), not from the value. For a dict option
    (custom_headers), each value is decided separately.

    A templating error names the option but not its value, which may be a secret.
    """
    raw = file_config.get(option_name)
    if not value or templar is None or raw is None:
        return value

    def render(text):
        try:
            return templar.template(text)
        except Exception:
            raise AnsibleError(
                "Could not template the inventory option '%s'. Check its Jinja2 "
                "syntax, or mark a literal value !unsafe." % option_name
            ) from None

    if isinstance(value, dict):
        raw_items = raw if isinstance(raw, dict) else {}
        return dict(
            (k, v if is_vault_encrypted(raw_items.get(k)) else render(v))
            for k, v in value.items()
        )
    if is_vault_encrypted(raw):
        return value
    return render(value)


def get_hostname(compose_func, host_vars, hostnames, default_name, strict=False):
    """
    Evaluate Jinja2 hostname expressions against host_vars.
    Returns the first non-empty result, or default_name as fallback.
    """
    for preference in hostnames:
        try:
            hostname = compose_func(preference, host_vars)
        except Exception as e:
            if strict:
                raise AnsibleError(
                    "Could not compose '%s' as hostname - %s" % (preference, to_text(e))
                )
            continue
        if hostname:
            return to_text(hostname)
    return default_name
