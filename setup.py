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
    author=metadata['author'],
    author_email=metadata['email'],
    url=metadata['url'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
        'Programming Language :: Python :: 3',
    ],
    packages=['scion'],
    install_requires=io.open('requirements.txt').readlines(),
    entry_points={
        'console_scripts': [
            'scion = scion-py3:main',
        ],
    },
    license=open('LICENSE').read(),
)
