#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from setuptools import find_packages, setup

MAIN_REQUIREMENTS = ["estuary-airbyte-cdk~=0.1", "stripe==2.56.0", "pendulum==1.2.0"]

TEST_REQUIREMENTS = [
    "pytest~=6.1",
    "requests-mock",
    "requests_mock~=1.8",
]

setup(
    name="source_stripe",
    description="Source implementation for Stripe.",
    author="Airbyte",
    author_email="contact@airbyte.io",
    packages=find_packages(),
    install_requires=MAIN_REQUIREMENTS,
    package_data={"": ["*.json", "*.yaml", "schemas/*.json", "schemas/shared/*.json"]},
    extras_require={
        "tests": TEST_REQUIREMENTS,
    },
)
