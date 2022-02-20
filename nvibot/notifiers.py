# coding=utf-8

import requests
import time
import logging
import json

from . import __title__
from nvibot.secrets import SecretManager

logger = logging.getLogger(__title__)


class Notifier:
    def __init__(self):
        self._last_msg_time = {}
        self._pushed_msg = set()

    def humble_push(self, msg, elapsed=60):
        now = time.time()
        last_time = self._last_msg_time.get(msg, 0)
        if now > last_time + elapsed:
            r = self.push(msg)
            self._last_msg_time[msg] = now
            return r

    def push_once(self, msg):
        if msg not in self._pushed_msg:
            r = self.push(msg)
            self._pushed_msg.add(msg)
            return r


class PushoverNotifier(Notifier):
    url = "https://api.pushover.net/1/messages.json"

    def __init__(self, secret_manager: SecretManager):
        super().__init__()
        credentials = secret_manager.get("pushover", json=True)
        self._user = credentials["user"]
        self._token = credentials["token"]

    def push(self, msg):
        logger.info(msg)
        data = {
            "token": self._token,
            "user": self._user,
            "message": msg,
            "priority": 1,
        }
        r = requests.post(self.url, data=data)
        return r


class DiscordNotifier(Notifier):
    url = "https://discord.com/api/channels/{}/messages"

    def __init__(self, secret_manager: SecretManager):
        super().__init__()
        credentials = secret_manager.get("discord", json=True)
        self._token = credentials["token"]
        self.channel = credentials["channel"]

    def push(self, msg):
        logger.info(msg)
        headers = {
            "User-Agent": "DiscordBot",
            "Content-Type": "application/json",
            "Authorization": f"Bot {self._token}",
        }
        data = {"content": msg}
        r = requests.post(
            self.url.format(self.channel), data=json.dumps(data), headers=headers
        )
        return r
