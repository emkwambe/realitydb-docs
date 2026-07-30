from setuptools import setup, find_packages

setup(
    name="realitydb-docs",
    version="0.1.0",
    description="Synthetic financial document generator for IDP/underwriting testing",
    author="Edward Mkwambe",
    packages=find_packages(),
    install_requires=["reportlab>=4.0", "PyYAML>=6.0"],
    python_requires=">=3.9",
    # NOTE: config/*.yaml sits beside the package, not inside it, so
    # find_packages() does not carry it into a wheel. A source checkout finds
    # it; an installed wheel needs REALITYDB_CONFIG_DIR pointed at a copy.
    # Moving config/ inside realitydb_docs/ would collide with the
    # realitydb_docs/config.py module name, so this is left as-is and the
    # override path is the supported answer. See config.py.
)
