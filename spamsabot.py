#!/usr/bin/python3

# Spamsabot - Telegrama roboto por malhelpi (saboti) spamon
# Copyright (C) 2018  Neil Roberts
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import urllib.request
import json
import io
import html
import sys
import time
import os
import random
import re

conf_dir = os.path.expanduser("~/.spamsabot")
update_id_file = os.path.join(conf_dir, "update_id")
apikey_file = os.path.join(conf_dir, "apikey")

banned_users = ['SexGirlsAnalMature']

with open(apikey_file, 'r', encoding='utf-8') as f:
    apikey = f.read().rstrip()

urlbase = "https://api.telegram.org/bot" + apikey + "/"
get_updates_url = urlbase + "getUpdates"

try:
    with open(update_id_file, 'r', encoding='utf-8') as f:
        last_update_id = int(f.read().rstrip())
except FileNotFoundError:
    last_update_id = None

class GetUpdatesException(Exception):
    pass

class HandleMessageException(Exception):
    pass

def save_last_update_id(last_update_id):
    with open(update_id_file, 'w', encoding='utf-8') as f:
        print(last_update_id, file=f)

def is_valid_update(update, last_update_id):
    try:
        update_id = update["update_id"]
        if not isinstance(update_id, int):
            raise GetUpdatesException("Unexpected response from getUpdates "
                                      "request")
        if last_update_id is not None and update_id <= last_update_id:
            return False

        if 'message' not in update:
            return False

        message = update['message']

        if 'chat' not in message:
            return False
    except KeyError as e:
        raise GetUpdatesException(e)

    return True

def get_updates(last_update_id):
    args = {
        'allowed_updates': ['message']
    }

    if last_update_id is not None:
        args['offset'] = last_update_id + 1

    try:
        req = urllib.request.Request(get_updates_url,
                                     json.dumps(args).encode('utf-8'))
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        rep = json.load(io.TextIOWrapper(urllib.request.urlopen(req), 'utf-8'))
    except urllib.error.URLError as e:
        raise GetUpdatesException(e)
    except json.JSONDecodeError as e:
        raise GetUpdatesException(e)

    try:
        if rep['ok'] is not True or not isinstance(rep['result'], list):
            raise GetUpdatesException("Unexpected response from getUpdates "
                                      "request")
    except KeyError as e:
        raise GetUpdatesException(e)
        
    updates = [x for x in rep['result'] if is_valid_update(x, last_update_id)]
    updates.sort(key = lambda x: x['update_id'])
    return updates

def send_request(request, args):
    try:
        req = urllib.request.Request(urlbase + request,
                                     json.dumps(args).encode('utf-8'))
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        rep = json.load(io.TextIOWrapper(urllib.request.urlopen(req), 'utf-8'))
    except urllib.error.URLError as e:
        raise HandleMessageException(e)
    except json.JSONDecodeError as e:
        raise HandleMessageException(e)

    try:
        if rep['ok'] is not True:
            raise HandleMessageException("Unexpected response from "
                                          "{} request".format(request))
    except KeyError as e:
        raise HandleMessageException(e)

    return rep

def delete_message(chat_id, message_id):
    args = {
        'chat_id': chat_id,
        'message_id': message_id
    }

    print("Removing message {} from {}".format(message_id, chat_id))

    send_request('deleteMessage', args)
    
def kick_user(chat_id, user_id):
    args = {
        'chat_id': chat_id,
        'user_id': user_id
    }

    print("Kicking {} from {}".format(user_id, chat_id))

    send_request('kickChatMember', args)
    
while True:
    now = int(time.time())

    try:
        updates = get_updates(last_update_id)

    except GetUpdatesException as e:
        print("{}".format(e), file=sys.stderr)
        # Delay for a bit before trying again to avoid DOSing the server
        time.sleep(60)
        continue

    for update in updates:
        last_update_id = update['update_id']
        save_last_update_id(last_update_id)

        message = update['message']
        chat = message['chat']

        if 'id' not in chat:
            continue
        chat_id = chat['id']

        if 'message_id' not in message:
            continue
        message_id = message['message_id']

        if 'forward_from_chat' not in message:
            continue
        forward = message['forward_from_chat']

        if 'username' not in forward:
            continue
        username = forward['username']

        if 'from' not in message:
            continue
        from_info = message['from']
        if 'id' not in from_info:
            continue
        from_id = from_info['id']

        if username not in banned_users:
            continue

        try:
            delete_message(chat_id, message_id)
            kick_user(chat_id, from_id)
        except HandleMessageException as e:
            print("{}".format(e), file=sys.stderr)
