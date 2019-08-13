#!/usr/bin/python

import sys
import os
import re
import datetime
import argparse
import pprint
import json

parser = argparse.ArgumentParser()
parser.add_argument('--users-file')
parser.add_argument('--username', action='append', default=[])
opts, args = parser.parse_known_args()

decoder = json.JSONDecoder()

users = { 'USLACKBOT': 'slackbot' } #user ID to username
if opts.users_file:
	user_records = decoder.decode(open(opts.users_file, 'r').read())
	for u in user_records:
		users[u['id']] = u['name']

def dereference_usernames(users, text):
	for k in users:
		text = text.replace(k, users[k])
	return text

in_files = [open(path, 'r') for path in args] if args else [sys.stdin]
for f in in_files:
	log = decoder.decode(f.read())
	for message in log:
		this_message_sender = message['user']
		this_message_sender_username = users[this_message_sender]

		if (not opts.username) or (this_message_sender in opts.username or this_message_sender_username in opts.username):
			when = datetime.datetime.fromtimestamp(float(message['ts']))
			filtered_text = dereference_usernames(users, message['text'])
			print ('[%s] <%s> %s' % (when, this_message_sender_username, filtered_text)).encode('utf-8')
			print
