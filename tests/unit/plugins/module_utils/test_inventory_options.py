# Copyright: (c) 2026, Nutanix
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest
from ansible_collections.nutanix.ncp.plugins.module_utils.utils import (
    parse_nutanix_endpoint,
)


@pytest.mark.parametrize(
    "endpoint, expected",
    [
        ("prism.example.com", ("prism.example.com", None)),
        ("prism.example.com:9440", ("prism.example.com", 9440)),
        ("10.0.0.1:9440", ("10.0.0.1", 9440)),
        ("https://prism.example.com:9440", ("prism.example.com", 9440)),
        ("https://prism.example.com", ("prism.example.com", None)),
        # IPv6 hosts come back bracketed, so the SDK can build a URL from them.
        ("[fd00::1]:9440", ("[fd00::1]", 9440)),
        ("[fd00::1]", ("[fd00::1]", None)),
        ("https://[fd00::1]:9440", ("[fd00::1]", 9440)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_nutanix_endpoint(endpoint, expected):
    assert parse_nutanix_endpoint(endpoint) == expected


@pytest.mark.parametrize(
    "endpoint",
    [
        "fd00::1",
        "fd00::1:9440",
        "prism.example.com:notaport",
        "prism.example.com:99999",
        "prism.example.com:0",
        "prism.example.com:",
    ],
)
def test_parse_nutanix_endpoint_rejects_ambiguous_values(endpoint):
    with pytest.raises(ValueError):
        parse_nutanix_endpoint(endpoint)
