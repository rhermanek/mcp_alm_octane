from setuptools import setup

setup(
    name="octane-mcp",
    version="0.1.0",
    py_modules=["octane_client", "server"],
    install_requires=[
        "mcp>=1.0.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "octane-mcp=server:main",
        ],
    },
)
