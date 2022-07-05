from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()

setup(
    name="automagic-rest",
    description="Automagic REST: Django REST Framework PostgreSQL Builder",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Timothy Allen",
    author_email="tallen@wharton.upenn.edu",
    url="https://github.com/wharton/automagic-rest",
    include_package_data=True,
    packages=find_packages(),
    zip_safe=False,
    setup_requires=['setuptools_scm'],
    use_scm_version=True,
    install_requires=[
        "djangorestframework>=3.9",
        "djangorestframework-filters==1.0.0.dev2",
        "django-filter==21.1",  # last release to support DRF-filters 1.0.0.dev2
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
        "Framework :: Django",
        "Framework :: Django :: 3",
        "Framework :: Django :: 4",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
)
