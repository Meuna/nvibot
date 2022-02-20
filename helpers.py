# coding=utf-8
import os
import requests
import time
import json


if os.name == 'nt':
    import threading
    import winsound

    def get_secrets():
        ldlc_user = os.environ['LDLC_USER']
        ldlc_password = os.environ['LDLC_PASSWORD']
        cc = json.loads(os.environ['CC'])
        return ldlc_user, ldlc_password, cc

    def play_sound():
        sound = f'C:/Windows/Media/Alarm01.wav'
        target = lambda:winsound.PlaySound(sound, winsound.SND_FILENAME)
        threading.Thread(target=target).start()
else:
    import boto3

    def get_secrets():
        client = boto3.client('ssm', region_name='eu-west-3')

        ldlc_user = client.get_parameter(Name='LDLC_USER', WithDecryption=True)['Parameter']['Value']
        ldlc_password = client.get_parameter(Name='LDLC_PASSWORD', WithDecryption=True)['Parameter']['Value']
        cc = json.loads(client.get_parameter(Name='CC', WithDecryption=True)['Parameter']['Value'])
        return ldlc_user, ldlc_password, cc

    def play_sound():
        pass

def push_msg(msg, with_sound=False):
    if with_sound:
        play_sound()
    url = 'https://api.pushover.net/1/messages.json'
    app_token = '****'
    user = '****'
    data = {
        'token': app_token,
        'user': user,
        'message': msg,
        'priority': 1,
    }
    r = requests.post(url, data=data)

_last_msg_time = {}
def push_msg_no_spam(msg, with_sound=False, elapsed=60):
    now = time.time()
    if (msg not in _last_msg_time) or (now - _last_msg_time[msg] > elapsed):
        push_msg(msg, with_sound)
        _last_msg_time[msg] = now

_pushed_msg = set()
def push_msg_once(msg, with_sound=False):
    if msg not in _pushed_msg:
        push_msg(msg, with_sound)
        _pushed_msg.add(msg)

