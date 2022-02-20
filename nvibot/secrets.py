# coding=utf-8

import os
import json as json_module

import requests
import boto3

from . import __title__


class SecretManager:
    def __init__(self, buyer: str):
        self._buyer = buyer

    def get(self, secret_name: str, json: bool = False) -> str:
        secret = self.get_raw(secret_name)
        if json:
            secret = json_module.loads(secret)
        return secret


class AwsSecretManager(SecretManager):
    def __init__(self, buyer: str, region_name: str):
        super().__init__(buyer)
        self._buyer = buyer
        self._region_name = region_name

    def get_raw(self, secret_name: str) -> str:
        client = boto3.client("ssm", region_name=self._region_name)
        param_name = f"{__title__}/{self._buyer}/{secret_name}"
        param_reply = client.get_parameter(Name=param_name, WithDecryption=True)
        return param_reply["Parameter"]["Value"]


class EnvSecretManager(SecretManager):
    def get_raw(self, secret_name: str) -> str:
        param_name = f"{__title__}_{self._buyer}_{secret_name}".upper()
        return os.environ[param_name]


def get_manager(buyer: str) -> SecretManager:
    try:
        reply = requests.get(
            "http://169.254.169.254/latest/dynamic/instance-identity/document",
            timeout=1,
        )
        region = reply.json()["region"]
        return AwsSecretManager(buyer, region)
    except (requests.ConnectTimeout, requests.ConnectionError):
        return EnvSecretManager(buyer)
