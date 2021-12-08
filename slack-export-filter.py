#!/usr/bin/python

import sys
import os
import re
import datetime
import argparse
import pprint
import json

parser = argparse.ArgumentParser(epilog='Search the chat logs in a Slack history export for messages matching the given query (in the same syntax the official Slack client uses).', usage='slack-export-filter <query> <export-directory>')
parser.add_argument('--users-file')
opts, args = parser.parse_known_args()

decoder = json.JSONDecoder()

def dereference_usernames(users, text):
	for k in users:
		text = text.replace(k, users[k])
	return text

def parse_query(query_string, query=None):
	'''Slack search query format:
in:#?channel_name
from:@?username
"phrase"
search-term
'''
	if query is None:
		query = {
			'channels': set([]),
			'authors': set([]),
			'search_terms': set([]),
		}
	query_string = query_string.strip()
	while query_string:
		if query_string.startswith('in:'):
			try:
				channel_name, query_string = query_string[len('in:'):].split(' ', 1)
			except ValueError:
				channel_name = query_string[len('in:'):]
				query_string = ''
			else:
				query_string = query_string.lstrip()
			channel_name = channel_name.lstrip('#')
			query['channels'].add(channel_name)

		elif query_string.startswith('from:'):
			try:
				author_name, query_string = query_string[len('from:'):].split(' ', 1)
			except ValueError:
				author_name = query_string[len('from:'):]
				query_string = ''
			else:
				query_string = query_string.lstrip()

			author_name = author_name.lstrip('@')
			query['authors'].add(author_name)

		elif query_string.startswith('"'):
			try:
				phrase, query_string = query_string[len('"'):].split('"', 1)
			except ValueError:
				phrase = query_string[len('"'):] # '"foo bar' is a loosely-valid phrase
				query_string = ''
			else:
				query_string = query_string.lstrip()

			query['search_terms'].add(phrase)

		else:
			try:
				phrase, query_string = query_string.split(' ', 1)
			except ValueError:
				phrase = query_string
				query_string = ''
			else:
				query_string = query_string.lstrip()

			query['search_terms'].add(phrase)

	return query

def channel_name_from_relative_path(rel_path):
	"A relative path such as channel/2019-04-01.json can have the channel name extracted from it."
	dir_path, filename = os.path.split(rel_path)
	immediate_parent_dir_name = os.path.basename(dir_path) # For paths like logs/channel/2019-04-01.json
	return immediate_parent_dir_name or '<unknown_channel>'

def generate_channel_log_paths(slack_export_paths, query={ 'channels': set() }, _daily_log_name_exp=re.compile(r'[0-9]{4,}-[0-9]{2}-[0-9]{2}\.json')):
	"Each item in slack_export_paths should be a path to a Slack export directory, containing users.json and zero or more channel directories, each channel directory containing zero or more yyyy-mm-dd.json files."

	# This is a band-aid; the outer loop is iterating over the list of paths and passing each path into where we expect a list of paths and iterate over it. Oops.
	if isinstance(slack_export_paths, basestring):
		slack_export_paths = [ slack_export_paths ]

	for top_dir in slack_export_paths:
		# Read channels.json
		with open(os.path.join(top_dir, 'channels.json'), 'r') as chf:
			channels_info = decoder.decode(chf.read())
			channels = [ ch['name'] for ch in channels_info ]

		only_these_channels = query['channels']

		for ch in channels:
			if (not only_these_channels) or ch in only_these_channels:
				for dir_path, subdir_names, file_names in os.walk(os.path.join(top_dir, ch)):
					for fn in file_names:
						if _daily_log_name_exp.match(fn):
							yield os.path.join(dir_path, fn)

query = parse_query(args.pop(0))

for top_dir_path in args or ['.']:
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
					print message
					raise
				this_message_sender_username = users[this_message_sender]

				matched_channel = True
				# No need to filter by channel because generate_channel_log_paths doesn't visit channels not matching the query.

				matched_author = True
				if query['authors']:
					matched_author = (this_message_sender in query['authors'] or this_message_sender_username in query['authors'])

				if matched_channel and matched_author:
					filtered_text = dereference_usernames(users, message['text'])

					matched_content = True
					if query['search_terms']:
						matched_content = False
						num_terms = len(query['search_terms'])
						num_matched = 0
						for term in query['search_terms']:
							# TODO: This doesn't restrict to word boundaries. Need to fix that with some sort of tokenization/DFA implementation.
							if term in filtered_text:
								num_matched += 1
						matched_content = num_matched // num_terms

					if matched_content:
						when = datetime.datetime.fromtimestamp(float(message['ts']))
						print ('#%s [%s] <%s> %s' % (channel_name, when, this_message_sender_username, filtered_text)).encode('utf-8')
						print '-' * 80
