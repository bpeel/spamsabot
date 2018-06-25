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
import itertools
import datetime
import http

conf_dir = os.path.expanduser("~/.spamsabot")
apikey_file = os.path.join(conf_dir, "apikey")
blacklist_file = os.path.join(conf_dir, "blacklist")

banned_users = set()
banned_ids = set()
banned_images = set()

FILTER_URL = r'https?://[\./0-9a-zA-Z]+'
# Matches any of the following emoji:
# U+2764 HEAVY BLACK HEART ❤
# U+1f5a4 BLACK HEART 🖤
# U+2757 HEAVY EXCLAMATION MARK SYMBOL ❗
# U+2753 BLACK QUESTION MARK ORNAMENT ❓
# U+1f48b KISS MARK 💋
# U+1f46b MAN AND WOMAN HOLDING HANDS 👫
# U+1f51e NO ONE UNDER EIGHTEEN SYMBOL 🔞
# U+25c0 BLACK LEFT-POINTING TRIANGLE ◀
# U+25b6 BLACK RIGHT-POINTING TRIANGLE ▶
# U+2705 WHITE HEAVY CHECK MARK ✅
# U+2747 SPARKLE ❇
# U+26A0 WARNING SIGN ⚠
# U+1f493 - U+1f49f various hearts
# They can optionally be followed by a variant selector
# (U+fe00-U+fe0f) and \uff (I’m not really sure why but some messages
# have that). These can be repeated any amount of times and be
# seperated by zero or more whitespace characters.
FILTER_EMOJI = ("(?:[\u2764\U0001f5a4\u2757\u2753\U0001f48b\U0001f46b\U0001f51e"
                "\u25c0\u25b6\u2705\u2747\u26a0\U0001f493-\U0001f49f]"
                "[\ufe00-\ufe0f]?\u00ff?\\s*)+")

FILTER_RE_STRING = r"""
\s*

(?:

H(?:i|ey)\s* EMOJI I(?:\'m|\s+am)\s+[A-Za-z]+\s* EMOJI URL \s+ EMOJI
I(?:\'m|\s+am)\s+[0-9]+\s+years\s+old\s* EMOJI
I(?:\'m|\s+am)\s+looking\s+for\s+a\s+man\s* EMOJI URL \s* EMOJI

|

(?: URL \s* | EMOJI )* You\s+want\s+sex\s* (?: URL \s* | EMOJI )+
We\s+only\s+have\s+free\s+girls\s*
(?: URL \s* | EMOJI )+

|

come\s+in\s+and\s+meet\s+URL\s*

|

EMOJI Relationships\s+For\s+sex,?\s+Here\s*!\s* URL \s+ EMOJI

)

$
"""

FILTER_RE = re.compile(FILTER_RE_STRING.replace("EMOJI", FILTER_EMOJI)
                       .replace("URL", FILTER_URL),
                       re.VERBOSE)

assert(FILTER_RE.match(r"Hey💋 I'm Addison ❤️❗️ http://catcut.net/dlOv  ❗️"
                       r"I am 18 years old👫 I'm looking for a man🔞❗️ "
                       r"http://catcut.net/dlOv  ❗️"))
assert(FILTER_RE.match(r"http://bit.do/enVd4  ◀️ 🖤❤️🖤❤️ You want sex❓"
                       r"We only have free girls⚠️🔞 http://bit.do/enVd4"))
assert(FILTER_RE.match(r"💚💙💜 You want sex❓We only have free girls⚠️🔞 "
                       r"http://bit.do/enVd4"))
assert(FILTER_RE.match(r"come in and meet http://catcut.net/n0Pv"))
assert(FILTER_RE.match(r"💋 Relationships For sex, Here ! "
                       r"http://bit.ly/2Ij6X9D ❤️❗️"))

with open(apikey_file, 'r', encoding='utf-8') as f:
    apikey = f.read().rstrip()

try:
    with open(blacklist_file, 'r', encoding='utf-8') as f:
        for line in f:
            md = re.match('\s*#', line)
            if md:
                continue
            md = re.match('^\s*image\s+(\S+)\s*$', line)
            if md:
                banned_images.add(md.group(1))
                continue
            md = re.match('^\s*(-?[0-9]+)\s*$', line)
            if md:
                banned_ids.add(int(md.group(1)))
                continue
            md = re.match('\s*(\S+)\s*$', line)
            if md:
                banned_users.add(md.group(1))
                continue
except FileNotFoundError:
    pass

try:
    with open(os.path.join(conf_dir, "admin"), 'r', encoding='utf-8') as f:
        administrator_id = int(f.read().strip())
except FileNotFoundError:
    administrator_id = None

try:
    with open(os.path.join(conf_dir, "report_channel"),
              'r',
              encoding='utf-8') as f:
        report_channel = f.read().strip()
except FileNotFoundError:
    report_channel = None

urlbase = "https://api.telegram.org/bot" + apikey + "/"
get_updates_url = urlbase + "getUpdates"

last_update_id = None

class GetUpdatesException(Exception):
    pass

class HandleMessageException(Exception):
    pass

class ProcessCommandException(Exception):
    pass

def save_blacklist():
    global banned_ids, banned_users, banned_images

    today = datetime.date.today()
    backup_file = "{}-{}".format(blacklist_file, today.isoformat())
    try:
        os.rename(blacklist_file, backup_file)
    except FileNotFoundError:
        pass

    with open(blacklist_file, 'w', encoding='utf-8') as f:
        for user in itertools.chain(banned_users, banned_ids):
            print(user, file=f)
        for image in banned_images:
            print("image {}".format(image), file=f)

def is_valid_update(update):
    try:
        if 'message' not in update:
            return False

        message = update['message']

        if 'chat' not in message:
            return False
    except KeyError as e:
        raise GetUpdatesException(e)

    return True

def get_updates():
    global last_update_id

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
    except (urllib.error.URLError, http.client.HTTPException) as e:
        raise GetUpdatesException(e)
    except json.JSONDecodeError as e:
        raise GetUpdatesException(e)

    try:
        if rep['ok'] is not True or not isinstance(rep['result'], list):
            raise GetUpdatesException("Unexpected response from getUpdates "
                                      "request")
    except KeyError as e:
        raise GetUpdatesException(e)

    last_update_id = None
    for update in rep['result']:
        if 'update_id' in update:
            update_id = update['update_id']
            if isinstance(update_id, int):
                if last_update_id is None or update_id > last_update_id:
                    last_update_id = update_id
        
    updates = [x for x in rep['result'] if is_valid_update(x)]
    return updates

def send_request(request, args):
    try:
        req = urllib.request.Request(urlbase + request,
                                     json.dumps(args).encode('utf-8'))
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        rep = json.load(io.TextIOWrapper(urllib.request.urlopen(req), 'utf-8'))
    except (urllib.error.URLError, http.client.HTTPException) as e:
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

def report(message):
    print(message)

    if report_channel is None:
        return

    args = {
        'text': message,
        'chat_id': report_channel
    }

    try:
        send_request('sendMessage', args)
    except HandleMessageException as e:
        print("{}".format(e), file=sys.stderr)

def delete_message(chat_id, message_id, username, title):
    args = {
        'chat_id': chat_id,
        'message_id': message_id
    }

    report("Forigos la mesaĝon {} de {} en {}".format(
        message_id, username, title))

    send_request('deleteMessage', args)
    
def kick_user(chat_id, user_id, username, title):
    args = {
        'chat_id': chat_id,
        'user_id': user_id
    }

    report("Forbaros {} de {}".format(username, title))

    send_request('kickChatMember', args)

def is_banned_chat(message, forward):
    if 'username' in forward:
        if forward['username'] in banned_users:
            return True

    if 'id' in forward:
        if forward['id'] in banned_ids:
            return True

    if ('photo' in message or 'document' in message) and 'caption' in message:
        caption = message['caption']
        if FILTER_RE.match(caption):
            return True

    return False

def is_banned(message):
    if 'forward_from_chat' in message:
        return is_banned_chat(message, message['forward_from_chat'])

    if 'photo' in message and 'caption' not in message:
        for file in message['photo']:
            if 'file_id' in file and file['file_id'] in banned_images:
                return True

    return False

def send_reply(message, note):
    args = {
        'chat_id' : message['chat']['id'],
        'text' : note,
        'reply_to_message_id' : message['message_id']
    }

    send_request('sendMessage', args)

def process_command(message, command, args):
    if command == '/start':
        send_reply(message,
                   "Ĉi tiu roboto provas aŭtomate forigi kelkajn tipojn de "
                   "spamo. Aldonu ĝin al grupo kaj administrantigu ĝin se vi "
                   "volas uzi ĝin en via grupo.")

def find_command(message):
    if 'entities' not in message or 'text' not in message:
        return None

    for entity in message['entities']:
        if 'type' not in entity or entity['type'] != 'bot_command':
            continue

        start = entity['offset']
        length = entity['length']
        # For some reason the offsets are in UTF-16 code points
        text_utf16 = message['text'].encode('utf-16-le')
        command_utf16 = text_utf16[start * 2 : (start + length) * 2]
        command = command_utf16.decode('utf-16-le')
        remainder_utf16 = text_utf16[(start + length) * 2 :]
        remainder = remainder_utf16.decode('utf-16-le')

        return (command, remainder)

    return None

def handle_chat_forward(message):
    global banned_ids, banned_users

    forward = message['forward_from_chat']

    if 'username' in forward:
        username = forward['username']
        if username in banned_users:
            send_reply(message,
                       "La uzantonomo {} jam estas en la nigra listo".format(
                           username))
        else:
            banned_users.add(username)
            send_reply(message,
                       "Aldonis la uzantnomon {} al la nigra listo".format(
                           username))
    elif 'id' in forward:
        user_id = forward['id']
        if user_id in banned_ids:
            send_reply(message,
                       "La uzantonumero {} jam estas en la nigra listo".format(
                           user_id))
        else:
            banned_ids.add(user_id)
            send_reply(message,
                       "Aldonis la uzantnumeron {} al la nigra listo".format(
                           user_id))
    else:
        send_reply(message, "Neniu uzanto trovita en la mesaĝo")
        return True

    save_blacklist()
    return True

def handle_photo_forward(message):
    global banned_images

    photo = message['photo']
    to_add = list()

    for file in photo:
        if 'file_id' not in file:
            continue

        to_add.append(file['file_id'])

    if len(to_add) > 0:
        banned_images.update(to_add)
        save_blacklist()

        send_reply(message,
                   "Added {} to the image blacklist".format(
                       ", ".join(to_add)))

        return True

    return False

def handle_spam_forward(message):
    try:
        from_id = message['from']['id']
    except KeyError:
        return False

    if from_id != administrator_id:
        return False

    if 'forward_from_chat' in message:
        return handle_chat_forward(message)

    if 'photo' in message and 'caption' not in message:
        return handle_photo_forward(message)
    
while True:
    now = int(time.time())

    try:
        updates = get_updates()

    except GetUpdatesException as e:
        print("{}".format(e), file=sys.stderr)
        # Delay for a bit before trying again to avoid DOSing the server
        time.sleep(60)
        continue

    for update in updates:
        message = update['message']
        chat = message['chat']

        if 'type' in chat and chat['type'] == 'private':
            if handle_spam_forward(message):
                continue
            command = find_command(message)
            if command is not None:
                try:
                    process_command(message, command[0], command[1])
                except ProcessCommandException as e:
                    print("{}".format(e), file=sys.stderr)
            continue

        if 'id' not in chat:
            continue
        chat_id = chat['id']

        if 'message_id' not in message:
            continue
        message_id = message['message_id']

        if not is_banned(message):
            continue

        if 'from' not in message:
            continue
        from_info = message['from']
        if 'id' not in from_info:
            continue
        from_id = from_info['id']

        if 'title' in chat:
            title = chat['title']
        else:
            title = str(chat_id)

        if 'username' in from_info:
            username = "{} ({})".format(from_info['username'], from_id)
        else:
            username = str(from_id)

        try:
            delete_message(chat_id, message_id, username, title)
            kick_user(chat_id, from_id, username, title)
        except HandleMessageException as e:
            print("{}".format(e), file=sys.stderr)
