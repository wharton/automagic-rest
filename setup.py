from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()

setup(
    name="automagic-rest",
    version="0.2.1",
    description="Automagic REST: Django REST Framework PostgreSQL Builder",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Timothy Allen",
    author_email="tallen@wharton.upenn.edu",
    url="https://github.com/wharton/automagic-rest",
    include_package_data=True,
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        "djangorestframework>=3.7.7",
        "djangorestframework-filters==1.0.0.dev0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Framework :: Django",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
)
