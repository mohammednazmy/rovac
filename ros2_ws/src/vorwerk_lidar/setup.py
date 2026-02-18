from setuptools import setup

package_name = 'vorwerk_lidar'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='User',
    maintainer_email='user@example.com',
    description='Vorwerk Lidar Driver',
    license='TODO',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'lidar_node = vorwerk_lidar.lidar_node:main',
        ],
    },
)
