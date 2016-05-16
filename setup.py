import io
import re
from setuptools import setup

init_py = io.open('scion/__init__.py').read()
metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", init_py))
metadata['doc'] = re.findall('"""(.+)"""', init_py)[0]

setup(
    name='scion',
    version=metadata['version'],
    description=metadata['doc'],
    url=metadata['url'],
    author=metadata['author'],
    author_email=metadata['email'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
        'Programming Language :: Python :: 3',
    ],
    packages=['scion'],
    install_requires=[],
    license='Mozilla Public License Version 2.0',
    entry_points = {
        'console_scripts': ['scion=scion.scion:main']
    }
)
