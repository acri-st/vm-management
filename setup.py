"""setup"""

from setuptools import find_packages, setup

print("Found packages:", find_packages())  # noqa: T201

setup(name="vm_management", version="0.1", description="Manage the VM", packages=find_packages())
