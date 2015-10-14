#!flask/bin/python
from flask import Flask
from isarestapi import config
from isarestapi.rest_api import app

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
