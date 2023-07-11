#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import datetime
import argparse
import pprint
import json
import pathlib

parser = argparse.ArgumentParser(epilog='Search the chat logs in a Slack history export for messages matching the given query (in the same syntax the official Slack client uses).')
parser.add_argument('--users-file', type=pathlib.Path)
parser.add_argument('query_string', help='The query to search for, in the same syntax Slack uses')
parser.add_argument('export_dir_path', type=pathlib.Path, metavar='path_to_export_dir', help='The path to the unzipped export archive')
opts = parser.parse_args()

decoder = json.JSONDecoder()

def dereference_usernames(users, text):
	for k in users:
		text = text.replace(k, users[k])
	return text

def parse_query(query_string, query=None):
	'''Slack search query format:
in:#?channel_name
from:@?username
is:thread
"phrase"
search-term
'''
	if query is None:
		query = {
			'channels_yes': set([]),
			'authors_yes': set([]),
			'search_terms_yes': set([]),
			'is': set([]),

			'channels_no': set([]),
			'authors_no': set([]),
			'search_terms_no': set([]),
			'is_not': set([]),
		}
	query_string = query_string.strip()
	while query_string:
		negative = query_string.startswith('-')
		if negative:
			query_string = query_string[len('-'):]
			if not query_string: continue

		if query_string.startswith('in:'):
			try:
				channel_name, query_string = query_string[len('in:'):].split(' ', 1)
			except ValueError:
				channel_name = query_string[len('in:'):]
				query_string = ''
			else:
				query_string = query_string.lstrip()
			channel_name = channel_name.lstrip('#')
			query['channels_no' if negative else 'channels_yes'].add(channel_name)

		elif query_string.startswith('from:'):
			try:
				author_name, query_string = query_string[len('from:'):].split(' ', 1)
			except ValueError:
				author_name = query_string[len('from:'):]
				query_string = ''
			else:
				query_string = query_string.lstrip()

			author_name = author_name.lstrip('@')
			query['authors_no' if negative else 'authors_yes'].add(author_name)

		elif query_string.startswith('is:'):
			try:
				thing_that_it_is, query_string = query_string[len('is:'):].split(' ', 1)
			except ValueError:
				thing_that_it_is = query_string[len('is:'):]
				query_string = ''
			else:
				query_string = query_string.lstrip()

			query['is not' if negative else 'is'].add(thing_that_it_is)

		elif query_string.startswith('"'):
			try:
				phrase, query_string = query_string[len('"'):].split('"', 1)
			except ValueError:
				phrase = query_string[len('"'):] # '"foo bar' is a loosely-valid phrase
				query_string = ''
			else:
				query_string = query_string.lstrip()

			query['search_terms_no' if negative else 'search_terms_yes'].add(phrase)

		else:
			try:
				phrase, query_string = query_string.split(' ', 1)
			except ValueError:
				phrase = query_string
				query_string = ''
			else:
				query_string = query_string.lstrip()

			query['search_terms_no' if negative else 'search_terms_yes'].add(phrase)

	return query

def channel_name_from_relative_path(rel_path):
	"A relative path such as channel/2019-04-01.json can have the channel name extracted from it."
	dir_path, filename = os.path.split(rel_path)
	immediate_parent_dir_name = os.path.basename(dir_path) # For paths like logs/channel/2019-04-01.json
	return immediate_parent_dir_name or '<unknown_channel>'

def generate_channel_log_paths(slack_export_paths, query={ 'channels': set() }, _daily_log_name_exp=re.compile(r'[0-9]{4,}-[0-9]{2}-[0-9]{2}\.json')):
	"Each item in slack_export_paths should be a path to a Slack export directory, containing users.json and zero or more channel directories, each channel directory containing zero or more yyyy-mm-dd.json files."

	# This is a band-aid; the outer loop is iterating over the list of paths and passing each path into where we expect a list of paths and iterate over it. Oops.
	if isinstance(slack_export_paths, str) or isinstance(slack_export_paths, pathlib.Path):
		slack_export_paths = [ slack_export_paths ]

	for top_dir in slack_export_paths:
		# Read channels.json
		with open(os.path.join(top_dir, 'channels.json'), 'r') as chf:
			channels_info = decoder.decode(chf.read())
			channels = [ ch['name'] for ch in channels_info ]

		only_these_channels = query['channels_yes']
		not_these_channels = query['channels_no']

		for ch in channels:
			if not_these_channels and ch in not_these_channels:
				continue
			if (not only_these_channels) or ch in only_these_channels:
				for dir_path, subdir_names, file_names in os.walk(os.path.join(top_dir, ch)):
					for fn in file_names:
						if _daily_log_name_exp.match(fn):
							yield os.path.join(dir_path, fn)

query = parse_query(opts.query_string)

def search_export(query, top_dir_path):
	"Yields (channel_name, timestamp_string, sender_username, filtered_text, message) for each message matched by the query. The last item, message, is a dictionary containing all of the message properties."
	users = { 'USLACKBOT': 'slackbot' } #user ID to username
	users_file_path = opts.users_file or (os.path.join(top_dir_path, 'users.json') if os.path.exists(os.path.join(top_dir_path, 'users.json')) else None)
	if users_file_path:
		user_records = decoder.decode(open(users_file_path, 'r').read())
		for u in user_records:
			users[u['id']] = u['name']

	for channel_log_path in generate_channel_log_paths(top_dir_path, query):
		channel_name = channel_name_from_relative_path(channel_log_path)
		with open(channel_log_path, 'r') as f:
			log = decoder.decode(f.read())
			for message in log:
				try:
					this_message_sender = message['user']
				except KeyError:
					try:
						this_message_sender = message['bot_id']
					except KeyError:
						print("Couldn't get bot_id from message:", message, file=sys.stderr)
						raise
					else:
						try:
						this_message_sender_username = message['username']
						except KeyError:
							# So we have a bot_id but no username. That's just going to have to do. Mark it with a prefix to distinguish it from a regular username.
							this_message_sender_username = '$bot_' + this_message_sender
				else:
					try:
					this_message_sender_username = users[this_message_sender]
					except KeyError:
						# So we have a user ID but no username. That's just going to have to do. Mark it with a prefix to distinguish it from a regular username.
						this_message_sender_username = '$unknown_' + this_message_sender

				matched_channel = True
				# No need to filter by channel because generate_channel_log_paths doesn't visit channels not matching the query.

				matched_thread = True
				# Slack doesn't support -is:thread at all, so it's no great loss to treat these as mutually exclusive and not handle a nonsense query like “is:thread -is:thread”.
				if 'thread' in query['is']:
					matched_thread = bool(message.get('thread_ts', False))
				elif 'thread' in query['is_not']:
					matched_thread = not message.get('thread_ts', False)

				matched_author = True
				if query['authors_yes']:
					matched_author = (this_message_sender in query['authors_yes'] or this_message_sender_username in query['authors_yes'])
				if query['authors_no']:
					matched_author = matched_author and (this_message_sender not in query['authors_no'] and this_message_sender_username not in query['authors_no'])

				if matched_channel and matched_thread and matched_author:
					filtered_text = dereference_usernames(users, message['text'])

					matched_content = True
					for term in query['search_terms_no']:
						if term in filtered_text:
							matched_content = False
							break
					if matched_content and query['search_terms_yes']:
						matched_content = False
						num_terms = len(query['search_terms_yes'])
						num_matched = 0
						for term in query['search_terms_yes']:
							# TODO: This doesn't restrict to word boundaries. Need to fix that with some sort of tokenization/DFA implementation.
							if term in filtered_text:
								num_matched += 1
						matched_content = num_matched // num_terms

					if matched_content:
						when = datetime.datetime.fromtimestamp(float(message['ts']))
						yield (channel_name, when, this_message_sender_username, filtered_text, message)

matches = list(search_export(query, opts.export_dir_path or '.'))
matches.sort() # Sorts by channel and then chronologically

for (channel_name, when, this_message_sender_username, filtered_text, message) in matches:
	print('#%s [%s] <%s> %s' % (channel_name, when, this_message_sender_username, filtered_text))
	print('-' * 80)
