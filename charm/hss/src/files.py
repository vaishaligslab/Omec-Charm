#!/usr/bin/env python3
# Copyright 2021 root
# See LICENSE file for licensing details.

"""File manipulation."""

import os


def loadfile(file_name: str, namespace: str) -> str:
    """Loads ands returns file content."""
    command = "sed -i 's/NAMESPACE/{1}/' {0}".format(file_name, namespace)
    os.system(command)

    with open(file_name, "r") as f:
        data = f.read()
        f.close()
        return data
