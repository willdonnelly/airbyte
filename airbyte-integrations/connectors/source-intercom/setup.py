#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from setuptools import find_packages, setup

MAIN_REQUIREMENTS = [
    "estuary-airbyte-cdk~=0.1",
]

TEST_REQUIREMENTS = [
    "pytest~=6.1",
    "requests-mock",
    "source-acceptance-test",
]

setup(
    name="source_intercom",
    description="Source implementation for Intercom.",
    author="Airbyte",
    author_email="contact@airbyte.io",
    packages=find_packages(),
    install_requires=MAIN_REQUIREMENTS,
    package_data={"": ["*.json", "schemas/*.json", "schemas/shared/*.json"]},
    extras_require={
        "tests": TEST_REQUIREMENTS,
    },
)
