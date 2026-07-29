from setuptools import setup, find_packages

setup(
    name="realitydb-docs",
    version="0.1.0",
    description="Synthetic financial document generator for IDP/underwriting testing",
    author="Edward Mkwambe",
    packages=find_packages(),
    install_requires=["reportlab>=4.0"],
    python_requires=">=3.9",
)
