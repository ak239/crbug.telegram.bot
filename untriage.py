from collections import defaultdict
import csv
import json
from time import sleep
import urllib
import urllib2
import datetime

__author__ = 'kozyatinskiy'


def send_request(request):
    print 'debug: request: {0}'.format(request)
    raw_response = urllib2.urlopen(REQUEST_URL + request)
    response = json.loads(raw_response.read())
    if response['ok']:
        return response['result']
    raise Exception('error:' + raw_response)


def get_me():
    return send_request('getMe')


def get_updates(offset, limit=100, timeout=0):
    request = 'getUpdates?offset={0}&limit={1}&timeout={2}'.format(offset, limit, timeout)
    return send_request(request)


def send_message(user_id, message):
    request = 'sendMessage?chat_id={0}&{1}'.format(user_id, urllib.urlencode({'text': message}))
    return send_request(request)


def subscribe_custom_updates(user, query):
    subscriptions[query][user['id']]


def subscribe_me(user, query):
    subscribe_custom_updates(user, 'owner:{0}'.format(query))


def subscribe_untriage(user):
    subscribe_custom_updates(user, 'Platform-DevTools -status:Assigned -status:Started -status:Available -Needs=Feedback -status:ExternalDependency')


def to_int(s):
    if len(s):
        return int(s)
    return 0


def get_issues(query, offset=0):
    CRBUG_REQUEST = 'https://code.google.com/p/chromium/issues/csv?{0}&colspec=ID%20Pri%20ReleaseBlock%20Cr%20Status%20Owner%20Summary%20Modified&sort=-modified%20-id&start={1}'
    raw_response = urllib2.urlopen(CRBUG_REQUEST.format(urllib.urlencode({'q': query}), offset))
    response = raw_response.read()
    lines = response.split('\n')
    has_more = False
    if lines[-2].startswith('This file is truncated'):
        lines = lines[1:-2]
        has_more = True
    else:
        lines = lines[1:-1]

    reader = csv.reader(lines, delimiter=',', quotechar='"')
    issues = []
    for row in reader:
        if row:
            issues.append(
                dict(ID=int(row[0]), Pri=to_int(row[1]), ReleaseBlock=row[2], Cr=row[3], Status=row[4], Owner=row[5],
                     Summary=row[6], ModifiedTimestamp=int(row[9])))
    return dict(issues=issues, has_more=has_more)


def issue_to_string(issue):
    issue_time = datetime.datetime.fromtimestamp(issue['ModifiedTimestamp']).strftime("%c")
    return '{1}\nhttp://crbug.com/{0}\nModified:{2}'.format(issue['ID'], issue['Summary'], issue_time)

def send_issue(user, issue):
    send_message(user, issue_to_string(issue))


state_file = open('state.txt', 'r')
state = json.load(state_file)
state_file.close()

# query -> user -> last modified
subscriptions = defaultdict(lambda: defaultdict(int))
for query in state['subscriptions']:
    for user in state['subscriptions'][query]:
        subscriptions[query][user] = state['subscriptions'][query][user]
last_update_id = state['last_update']
TOKEN = state['token']
REQUEST_URL = 'https://api.telegram.org/bot' + TOKEN + '/'

print get_me()
while True:
    updates = get_updates(last_update_id)
    for update in updates:
        message = update['message']
        if message['text'].startswith('/custom '):
            subscribe_custom_updates(message['from'], message['text'].split(' ', 1)[1])
        if message['text'].startswith('/me '):
            subscribe_me(message['from'], message['text'].split(' ')[1])
        if message['text'].startswith('/untriage'):
            subscribe_untriage(message['from'])
        last_update_id = update['update_id'] + 1
        print last_update_id

    bad_queries = []
    for query in subscriptions:
        # try:
        all_issues = []
        issues = {'has_more': True}
        offset = 0
        while issues['has_more']:
            issues = get_issues(query, offset)
            all_issues += issues['issues']
            offset += 100
        for issue in reversed(all_issues):
            for user in subscriptions[query]:
                last_modified = subscriptions[query][user]
                if issue['ModifiedTimestamp'] > last_modified:
                    last_modified = issue['ModifiedTimestamp']
                    subscriptions[query][user] = last_modified
                    send_issue(user, issue)
                    # except:
                    #     bad_queries.append(query)
    for query in bad_queries:
        del subscriptions[query]

    state_file = open('state.txt', 'w')
    state_file.write(json.dumps({'subscriptions': subscriptions, 'last_update': last_update_id, 'token': TOKEN}))
    state_file.close()

    sleep(1)
