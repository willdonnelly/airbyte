#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from setuptools import find_packages, setup

MAIN_REQUIREMENTS = [
    "estuary-airbyte-cdk~=0.1",
    "pendulum~=2.1",
]

TEST_REQUIREMENTS = [
    "pytest~=6.1",
    "source-acceptance-test",
    "requests-mock",
]

setup(
    name="source_linkedin_ads",
    description="Source implementation for Linkedin Ads.",
    author="Airbyte",
    author_email="contact@airbyte.io",
    packages=find_packages(),
    install_requires=MAIN_REQUIREMENTS,
    package_data={"": ["*.json", "schemas/*.json", "schemas/shared/*.json"]},
    extras_require={
        "tests": TEST_REQUIREMENTS,
    },
)
