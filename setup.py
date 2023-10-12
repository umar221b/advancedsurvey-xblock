"""Setup for advancedsurvey XBlock."""


import os

from setuptools import setup


def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}


setup(
    name='advancedsurvey-xblock',
    version='0.1',
    description='Adds advanced surveys that can include sections with headers and multiple questions (Heavily inspired by xblock-poll by OpenCraft)',
    license='AGPL v3',
    packages=[
        'advancedsurvey',
    ],
    install_requires=[
        'XBlock',
        'markdown',
        'bleach'
    ],
    entry_points={
        'xblock.v1': [
            'advancedsurvey = advancedsurvey:AdvancedSurveyXBlock',
        ]
    },
    package_data=package_data("advancedsurvey", ["static", "public", "translations"]),
)
