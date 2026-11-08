from setuptools import setup, find_packages

setup(
    name="animetui",
    version="0.1.0",
    packages=find_packages(),
    py_modules=["app"],
    install_requires=[
        "textual>=0.40.0",
        "httpx>=0.25.0",
        "beautifulsoup4>=4.12.0",
    ],
    entry_points={
        "console_scripts": [
            "animetui=app:main",
        ],
    },
    python_requires=">=3.10",
)
