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
import hashlib

conf_dir = os.path.expanduser("~/.spamsabot")
apikey_file = os.path.join(conf_dir, "apikey")
blacklist_file = os.path.join(conf_dir, "blacklist")

banned_users = set()
banned_ids = set()
banned_images = set()
banned_avatars = set()

# In an attempt to reduce the calls to getUserProfilePhotos, it will
# cache the results for each user ID here for 10 minutes. The values
# in the dictionary are a tuple with the time it was requested and the
# result. We don’t want to cache it forever in case the bot
# accidentally blocks a real person and we want to give them a chance
# to change their avatar.
AVATAR_CACHE_TIME = 10 * 60
avatar_cache = {}

# Mapping from file_id to md5 hash to avoid repeatedly downloading
# photos.
file_hash_cache = {}

# Queue of messages to retry. Each element is a tuple of (timestamp,
# retry_count, message)
retry_queue = []

FILTER_URL = r'https?://[\./0-9a-zA-Z]+'
FILTER_URL_RE = re.compile(FILTER_URL)

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
# U+2B55 HEAVY LARGE CIRCLE ⭕
# U+1f493 - U+1f49f various hearts
# They can optionally be followed by a variant selector
# (U+fe00-U+fe0f) and \uff (I’m not really sure why but some messages
# have that). These can be repeated any amount of times and be
# seperated by zero or more whitespace characters.
FILTER_EMOJI = ("(?:[\u2764\U0001f5a4\u2757\u2753\U0001f48b\U0001f46b\U0001f51e"
                "\u25c0\u25b6\u2705\u2747\u26a0\u2b55\U0001f493-\U0001f49f]"
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

come\s+(?:in\s+)?and\s+(?:meet|see)\s+(?:me\s+)?URL\s*

|

EMOJI Relationships\s+For\s+sex,?\s+Here\s*!\s* URL \s+ EMOJI

|

EMOJI Girls\s+are\s+waiting\s+for\s+you,\s+bad\s+guy,\s+
Hot\s+Fast\s+sex\s+100%\s+ URL \s+ EMOJI

|

Here\s+Only\s+Hot\s+Girls\s+for\s+sex\s*>+\s* EMOJI URL \s+ EMOJI

|

Hi\s+I'm\s+[A-Za-z]+,\s* EMOJI I\s+want\s+a\s+bad\s+guy\s+!+\s* URL \s+ EMOJI

|

My\s+name\s+is\s+[A-Za-z]+\.\s+
I\s+want\s+to\s+get\s+acquainted\s+with\s+the\s+guy,\s+
EMOJI my\s+photos\s+on\s+the\s+link\.\s*>+\s* URL \s*

|

EMOJI URL \s+ EMOJI Do\s+you\s+want\s+a\s+beautiful\s+girl\s* EMOJI
Then\s+to\s+you\s+to\s+us\s* EMOJI URL \s+ EMOJI

|

(?:
I\s+would\s+like\s+to\s+drive\s+you\s+wild |
My\s+breast,\s+my\s+neck,\s+my\s+buttocks,\s+my\s+hips |
I\s+find\s+long\s+love\s+play\s+annoying |
I\s+would\s+like\s+to\s+do\s+it\s+gently |
I\s+prefer\s+long,\s+tender\s+uninhibited\s+love\s+making |
I’m\s+here,\s+go\s+to\s+my\s+chat |
sign\s+up\s+for\s+free\s+and\s+see\s+me\s+live\s+here
)
\s+ URL

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
assert(FILTER_RE.match(r"come and see me http://catcut.net/POQv"))
assert(FILTER_RE.match(r"💋 Relationships For sex, Here ! "
                       r"http://bit.ly/2Ij6X9D ❤️❗️"))
assert(FILTER_RE.match(r"💋Girls are waiting for you, bad guy, Hot Fast sex "
                       r"100% http://bit.ly/2K6g2IH ❤️❗️"))
assert(FILTER_RE.match(r"Here Only Hot Girls for sex >>> ❤️❗️ "
                       r"http://bit.ly/2K6g2IH ❤️❗️"))
assert(FILTER_RE.match(r"Hi I'm Barbara, 💋 I want a bad guy !!! "
                       r"http://bit.ly/2K6g2IH ❤️❗️"))
assert(FILTER_RE.match(r"My name is Amanda. I want to get acquainted with the "
                       r"guy, ❤️❗️ my photos on the link. >>> "
                       r"http://bit.ly/2K6g2IH"))
assert(FILTER_RE.match(r"⭕️🔞⭕️ https://bit.ly/2KmrvQm ⚠️  "
                       r"Do you want a beautiful girl❓ Then to you to us❗️ "
                       r"https://bit.ly/2KmrvQm 💋"))
assert(FILTER_RE.match(r"I would like to drive you wild "
                       r"http://catcut.net/4SWv"))
assert(FILTER_RE.match(r"My breast, my neck, my buttocks, my hips "
                       r"http://catcut.net/4SWv"))
assert(FILTER_RE.match(r"I find long love play annoying "
                       r"http://catcut.net/4SWv"))
assert(FILTER_RE.match(r"I would like to do it gently "
                       r"http://catcut.net/4SWv"))
assert(FILTER_RE.match(r"I prefer long, tender uninhibited love making "
                       r"http://catcut.net/4SWv"))
assert(FILTER_RE.match(r"I’m here, go to my chat http://catcut.net/4SWv"))
assert(FILTER_RE.match(r"sign up for free and see me live here "
                       r"http://catcut.net/4SWv"))

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
            md = re.match('^\s*avatar\s+(\S+)\s*$', line)
            if md:
                banned_avatars.add(md.group(1))
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

try:
    with open(os.path.join(conf_dir, "avatar_channel"),
              'r',
              encoding='utf-8') as f:
        avatar_channel = f.read().strip()
        try:
            avatar_channel = int(avatar_channel)
        except ValueError:
            pass
except FileNotFoundError:
    avatar_channel = None

apihost = "https://api.telegram.org/"
urlbase = apihost + "bot" + apikey + "/"
file_urlbase = apihost + "file/bot" + apikey + "/"
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
        for avatar in banned_avatars:
            print("avatar {}".format(avatar), file=f)

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

    timeout = 300
    now = time.monotonic()

    for timestamp, retry_count, message in retry_queue:
        next_time = max(timestamp - now, 0)
        if next_time < timeout:
            timeout = next_time

    args = {
        'allowed_updates': ['message'],
        'timeout': 300
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
        note = repr(e)
        read_op = getattr(e, "read", None)
        if callable(read_op):
            try:
                note = note + ": " + read_op().decode('utf-8')
            except UnicodeDecodeError:
                pass
        raise HandleMessageException("{} while handling {} {}".format(
            note, request, args))
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
        'chat_id': report_channel,
        'parse_mode': 'HTML'
    }

    try:
        send_request('sendMessage', args)
    except HandleMessageException as e:
        print("{}".format(e), file=sys.stderr)

def delete_message(chat_id, message_id):
    args = {
        'chat_id': chat_id,
        'message_id': message_id
    }

    send_request('deleteMessage', args)
    
def kick_user(chat_id, user_id):
    args = {
        'chat_id': chat_id,
        'user_id': user_id
    }

    send_request('kickChatMember', args)

def is_banned_chat(message, forward):
    try:
        if (forward['username'] in banned_users or
            forward['id'] in banned_ids):
            return "plusendaĵo de malpermesita kanalo"
    except KeyError:
        pass

    if ('photo' in message or 'document' in message) and 'caption' in message:
        caption = message['caption']
        if FILTER_RE.match(caption):
            caption = FILTER_URL_RE.sub("<i>ligilo</i>", html.escape(caption))
            return "bildo kun la priskribo «{}»".format(caption)

    return None

def is_banned(message):
    if 'forward_from_chat' in message:
        return is_banned_chat(message, message['forward_from_chat'])

    if 'photo' in message and 'caption' not in message:
        for file in message['photo']:
            if 'file_id' in file and file['file_id'] in banned_images:
                return "malpermesita bildo sen priskribo"

    return None

def send_reply(message, note):
    args = {
        'chat_id' : message['chat']['id'],
        'text' : note,
        'reply_to_message_id' : message['message_id']
    }

    send_request('sendMessage', args)

def add_banned_avatar_photos(message, photos):
    to_ban = []

    for photo in photos:
        try:
            photo_hash = file_id_to_hash(photo['file_id'])
            if photo_hash not in banned_avatars:
                to_ban.append(photo_hash)
        except (KeyError, HandleMessageException) as e:
            print("{}".format(e), file=sys.stderr)

    if len(to_ban) <= 0:
        send_reply(message, "Neniu nova profilbildo estis trovita")
    else:
        banned_avatars.update(to_ban)
        save_blacklist()
        send_reply(message,
                   "Aldonis la jenajn profilbildojn al la nigra listo: " +
                   ", ".join(to_ban))

def add_banned_avatar(message, user_id):
    try:
        photos = get_profile_photo(user_id)
    except HandleMessageException as e:
        print("{}".format(e), file=sys.stderr)
        return

    return add_banned_avatar_photos(message, photos)

def process_command(message, command, args):
    if command == '/start':
        send_reply(message,
                   "Ĉi tiu roboto provas aŭtomate forigi kelkajn tipojn de "
                   "spamo. Aldonu ĝin al grupo kaj administrantigu ĝin se vi "
                   "volas uzi ĝin en via grupo.")
    elif message['from']['id'] == administrator_id:
        if command == '/avatar':
            md = re.match(r'\s*(-?[0-9]+)\s*$', args)
            if md:
                add_banned_avatar(message, int(md.group(1)))

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

def handle_banned_avatar_forward(message):
    try:
        photos = [smallest_sized_photo(message['photo'])]
    except KeyError:
        pass
    else:
        add_banned_avatar_photos(message, photos)

def handle_chat_forward(message):
    global banned_ids, banned_users

    forward = message['forward_from_chat']

    if 'username' in forward:
        username = forward['username']
        if "@{}".format(username) == avatar_channel:
            handle_banned_avatar_forward(message)
            return True
        elif username in banned_users:
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
        if user_id == avatar_channel:
            handle_banned_avatar_forward(message)
            return True
        elif user_id in banned_ids:
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

def username_for_report(user):
    try:
        from_id = user['id']
    except KeyError:
        from_id = '?'

    if 'username' in user:
        username = "{} ({})".format(html.escape(user['username']),
                                    from_id)
    else:
        username = str(from_id)

    return '<a href="tg://user?id={}">{}</a>'.format(from_id, username)

def chat_title_for_report(chat):
    if 'title' in chat:
        title = html.escape(chat['title'])
    else:
        title = str(chat_id)

    return title

def contains_banned_avatar(photos):
    for photo in photos:
        try:
            photo_hash = file_id_to_hash(photo['file_id'])
            if photo_hash in banned_avatars:
                return True
        except (KeyError, HandleMessageException) as e:
            print("{}".format(e), file=sys.stderr)

    return False

def smallest_sized_photo(photo):
    smallest = None
    smallest_size = 0

    for sized_photo in photo:
        size = sized_photo['width'] * sized_photo['height']
        if smallest is None or size < smallest_size:
            smallest_size = size
            smallest = sized_photo

    return smallest

def file_id_to_hash(file_id):
    try:
        return file_hash_cache[file_id]
    except KeyError:
        pass

    rep = send_request('getFile', { 'file_id': file_id  })
    file_url = file_urlbase + rep['result']['file_path']

    try:
        req = urllib.request.Request(file_url)
        data = urllib.request.urlopen(req).read()
    except (urllib.error.URLError, http.client.HTTPException, IOError) as e:
        raise HandleMessageException(e)

    md5 = hashlib.md5()
    md5.update(data)
    res = md5.hexdigest()

    file_hash_cache[file_id] = res
    return res

def get_profile_photo(user_id):
    if user_id in avatar_cache:
        timestamp, res = avatar_cache[user_id]
        if time.monotonic() - timestamp <= AVATAR_CACHE_TIME:
            return res
        del avatar_cache[user_id]

    args = {
        'user_id': user_id,
        'offset': 0,
        'limit': 1
    }
    rep = send_request('getUserProfilePhotos', args)
    try:
        res = [smallest_sized_photo(x) for x in rep['result']['photos']]
    except KeyError:
        raise HandleMessageException("Missing photos in result")

    avatar_cache[user_id] = (time.monotonic(), res)
    return res

def retry_message(message, retry_count):
    retry_queue.append((time.monotonic() + 60 * 2 ** retry_count,
                        retry_count + 1,
                        message))

def check_banned_avatar(message, retry_count):
    try:
        new_members = message['new_chat_members']
    except KeyError:
        return False

    ret = False
    found = False

    for user in new_members:
        try:
            photos = get_profile_photo(user['id'])
        except (KeyError, HandleMessageException) as e:
            print("Error getting photos from {}: {}".format(message, e),
                  file=sys.stderr)
            if retry_count < 3:
                retry_message(message, retry_count)
            else:
                print("giving up on {}".format(message), file=sys.stderr)
            continue

        if contains_banned_avatar(photos):
            try:
                kick_user(message['chat']['id'], user['id'])
            except (KeyError, HandleMessageException) as e:
                  print(("Dum provo forbari {} de {} "
                         "pro malpermesita profilbildo: {}").format(
                             username_for_report(user),
                             chat_title_for_report(message['chat']),
                             e),
                        file=sys.stderr)
            else:
                report("Forbaris {} de {} pro malpermesita profilbildo".format(
                    username_for_report(user),
                    chat_title_for_report(message['chat'])))
                found = True
            ret = True
        elif avatar_channel is not None:
            try:
                photo_id = photos[0]['file_id']
            except (IndexError, KeyError):
                continue

            caption = username_for_report(user)
            try:
                chat_title = html.escape(message['chat']['title'])
                caption = "{} en {}".format(caption, chat_title)
            except KeyError as e:
                pass

            args = {
                'chat_id': avatar_channel,
                'photo': photo_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }

            try:
                send_request('sendPhoto', args)
            except HandleMessageException as e:
                print("{}".format(e), file=sys.stderr)

    if found:
        try:
            delete_message(message['chat']['id'], message['message_id'])
        except (HandleMessageException, KeyError) as e:
            print("{}".format(e), file=sys.stderr)

    return ret

def handle_message(message, retry_count = 0):
    chat = message['chat']

    if 'type' in chat and chat['type'] == 'private':
        if handle_spam_forward(message):
            return
        command = find_command(message)
        if command is not None:
            try:
                process_command(message, command[0], command[1])
            except ProcessCommandException as e:
                print("{}".format(e), file=sys.stderr)
        return

    if check_banned_avatar(message, retry_count):
        return

    if 'id' not in chat:
        return
    chat_id = chat['id']

    if 'message_id' not in message:
        return
    message_id = message['message_id']

    ban_reason = is_banned(message)
    if ban_reason is None:
        return

    if 'from' not in message:
        return
    from_info = message['from']
    if 'id' not in from_info:
        return
    from_id = from_info['id']

    username = username_for_report(from_info)
    title = chat_title_for_report(chat)

    report("Forigos la mesaĝon {} de {} en {} "
           "kaj forbaros rin pro {}".format(
        message_id, username, title, ban_reason))

    try:
        delete_message(chat_id, message_id)
        kick_user(chat_id, from_id)
    except HandleMessageException as e:
        print("{}".format(e), file=sys.stderr)

while True:
    try:
        updates = get_updates()
    except GetUpdatesException as e:
        print("{}".format(e), file=sys.stderr)
        # Delay for a bit before trying again to avoid DOSing the server
        time.sleep(60)
        continue

    if len(retry_queue) > 0:
        messages = retry_queue
        retry_queue = []
        now = time.monotonic()

        for timestamp, retry_count, message in messages:
            if now >= timestamp:
                print("Retrying {}".format(message), file=sys.stderr)
                handle_message(message, retry_count)
            else:
                retry_queue.append((timestamp, retry_count, message))

    for update in updates:
        message = update['message']
        handle_message(message)
