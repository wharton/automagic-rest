from setuptools import setup, find_packages
setup(
    name='drf-pg-builder',
    version="0.1.0",
    description='Django REST Framework PostgreSQL Builder',
    long_description='',
    author='Timothy Allen',
    author_email='tallen@wharton.upenn.edu',
    url='https://github.com/wharton/drf-pg-builder',
    include_package_data=True,
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        'djangorestframework>=3.7.7,<3.8',
        'inflection==0.3.1',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Framework :: Django',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
