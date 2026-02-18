from setuptools import setup
import os
from glob import glob

package_name = 'tank_description'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'urdf'), glob('urdf/*.urdf')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='User',
    maintainer_email='user@example.com',
    description='Tank Description',
    license='TODO',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'tank_motor_driver = tank_description.tank_motor_driver:main',
            'cmd_vel_mux = tank_description.cmd_vel_mux:main',
            'http_bridge = tank_description.http_bridge:main',
        ],
    },
)