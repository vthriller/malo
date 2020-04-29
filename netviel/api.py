"""Flask web app providing a REST API to notmuch."""

import email
import email.policy
import email.utils
import io
import logging
import os

from itertools import islice
from collections import defaultdict

import bleach
import notmuch
from flask import Flask, current_app, g, send_file, send_from_directory, request, jsonify
from flask_cors import CORS
from flask_restful import Api, Resource

ALLOWED_TAGS = [
    "a",
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "strong",
    "ul",
    "span",
    "p",
    "br",
    "div",

    'table',
    'thead',
    'tbody',
    'tr',
    'td',
    'th',

    'img',

    'style',
]
ALLOWED_ATTRIBUTES = {
    '*': ['style', 'class', 'id', 'title'],

    "a": ["href"],

    'table': 'cellpadding cellspacing width border'.split(),
    'td': ['valign', 'bgcolor'],
    'th': ['valign'],
}
ALLOWED_STYLES = [
    'border',
    'border-collapse',
    'border-radius',

    'color',
    'background-color',

    'font-family',
    'font-size',
    'font-weight',

    'text-align',
    'vertical-align',

    'text-decoration',
    'line-height',

    'margin',
    'padding',

    'width',
    'height',
    'min-width',
    'min-height',
    'max-width',
    'max-height',

    'display',
]

def get_db():
    """Get a new `Database` instance. Called before every request. Cached on first call."""
    if "db" not in g:
        g.db = notmuch.Database(current_app.config["NOTMUCH_PATH"], create=False, mode=notmuch.Database.MODE.READ_WRITE)
    return g.db


def close_db(e=None):
    """Close the Database. Called after every request."""
    pass


def create_app():
    """Flask application factory."""
    app = Flask(__name__, static_folder="js")
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.config["NOTMUCH_PATH"] = os.getenv("NOTMUCH_PATH")
    app.logger.setLevel(logging.INFO)

    CORS(app)

    api = Api(app)

    @app.route("/")
    def send_index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/<path:path>")
    def send_js(path):
        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    @app.before_request
    def before_request():
        get_db()

    app.teardown_appcontext(close_db)

    class Query(Resource):
        def get(self):
            query_string = request.args['q']
            page = int(request.args.get('page', '1'))
            what = request.args.get('what', 'threads')
            per_page = 50

            count = 0
            tags = defaultdict(lambda: [0, 0])

            query = notmuch.Query(get_db(), query_string)
            if what == 'threads':
                threads = iter(query.search_threads())
            elif what == 'messages':
                threads = iter(query.search_messages())
            else:
                return 'Bad request', 400

            # N.B. cannot process pages declaratively via zip(threads, range(…))
            # due to notmuch.errors.NotInitializedError being raised after first StopIteration

            for _ in range((page - 1) * per_page):
                # before current page
                try: t = next(threads)
                except StopIteration:
                    threads = iter([]) # to prevent NotInitializedError
                    break

                count += 1

                thread_tags = list(t.get_tags())
                unread = int('unread' in thread_tags)
                for tag in thread_tags:
                    tags[tag][0] += unread
                    tags[tag][1] += 1

            current = []
            for _ in range(per_page):
                # current page
                try: t = next(threads)
                except StopIteration:
                    threads = iter([]) # to prevent NotInitializedError
                    break

                count += 1

                thread_tags = list(t.get_tags())
                unread = int('unread' in thread_tags)
                for tag in thread_tags:
                    tags[tag][0] += unread
                    tags[tag][1] += 1

                current.append(t)

            while True:
                # after current page
                try: t = next(threads)
                except StopIteration:
                    break

                count += 1

                thread_tags = list(t.get_tags())
                unread = int('unread' in thread_tags)
                for tag in thread_tags:
                    tags[tag][0] += unread
                    tags[tag][1] += 1

            return dict(
                pages = count // per_page + 1,
                tags = [
                    dict(name=name, unread=unread, total=total)
                    for name, (unread, total) in sorted(tags.items())
                ],
                threads = [thread_to_json(t) for t in current] if what == 'threads' else None,
                messages = [message_to_json(t, skip_content=True) for t in current] if what == 'messages' else None,
            )

    class Thread(Resource):
        def get(self, query):
            query = notmuch.Query(get_db(), query)
            query.set_sort(notmuch.Query.SORT.OLDEST_FIRST)
            thread = query.search_messages()
            messages = [message_to_json(m) for m in thread]
            if not messages:
                return 'Not found', 404
            return messages

    api.add_resource(Query, "/api/query")
    api.add_resource(Thread, "/api/thread/<string:query>") # usually thread:012abcdef or mid:20200102@example.com

    @app.route("/api/attachment/<string:message_id>/<int:num>/<string:filename>")
    def download_attachment(message_id, num, filename):
        # filename is unused, only added to url to name saved files appropriately
        msgs = notmuch.Query(get_db(), "mid:{}".format(message_id)).search_messages()
        try:
            msg = next(msgs)  # there can be only 1
        except StopIteration:
            return 'Not found', 404
        d = message_attachment(msg, num)
        if not d:
            return None
        if isinstance(d["content"], str):
            f = io.BytesIO(d["content"].encode())
        else:
            f = io.BytesIO(d["content"])
        f.seek(0)
        return send_file(f, mimetype=d["content_type"])

    @app.route("/api/message/<string:message_id>")
    def fetch_message(message_id):
        msgs = notmuch.Query(get_db(), "mid:{}".format(message_id)).search_messages()
        try:
            msg = next(msgs)  # there can be only 1
        except StopIteration:
            return 'Not found', 404
        return message_to_json(msg)

    @app.route("/api/message/<string:message_id>/raw")
    def download_message(message_id):
        msgs = notmuch.Query(get_db(), "mid:{}".format(message_id)).search_messages()
        try:
            msg = next(msgs)  # there can be only 1
        except StopIteration:
            return 'Not found', 404
        # not message/rfc822: people might want to read it in browser
        return send_file(msg.get_filename(), mimetype="text/plain")

    @app.route('/api/message/<string:message_id>/tag/<string:tag>/add')
    def add_tag(message_id, tag):
        msgs = notmuch.Query(get_db(), "mid:{}".format(message_id)).search_messages()
        try:
            msg = next(msgs)  # there can be only 1
        except StopIteration:
            return 'Not found', 404

        msg.add_tag(tag, sync_maildir_flags=True)

        return jsonify(list(msg.get_tags()))

    @app.route('/api/message/<string:message_id>/tag/<string:tag>/remove')
    def remove_tag(message_id, tag):
        msgs = notmuch.Query(get_db(), "mid:{}".format(message_id)).search_messages()
        try:
            msg = next(msgs)  # there can be only 1
        except StopIteration:
            return 'Not found', 404

        msg.remove_tag(tag, sync_maildir_flags=True)

        return jsonify(list(msg.get_tags()))

    return app




def thread_to_json(thread):
    """Converts a `notmuch.threads.Thread` instance to a JSON object."""
    return {
        "authors": thread.get_authors(),
        "matched_messages": thread.get_matched_messages(),
        "newest_date": thread.get_newest_date(),
        "oldest_date": thread.get_oldest_date(),
        "subject": thread.get_subject(),
        "tags": list(thread.get_tags()),
        "thread_id": thread.get_thread_id(),
        "total_messages": thread.get_total_messages(),
    }

def message_to_json(message, skip_content=False):
    """Converts a `notmuch.message.Message` instance to a JSON object."""
    with open(message.get_filename(), "rb") as f:
        email_msg = email.message_from_binary_file(f, policy=email.policy.default)
    if not skip_content:
        attachments = []
        for part in email_msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                attachments.append(
                    {
                        "filename": part.get_filename(),
                        "content_type": part.get_content_type(),
                    }
                )
        msg_body = email_msg.get_body(preferencelist=("html", "plain"))
        content_type = msg_body.get_content_type()
        if content_type == "text/html":
            content = bleach.clean(
                msg_body.get_content(),
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                styles=ALLOWED_STYLES,
                strip=True,
            )
        else:
            content = msg_body.get_content()
    return {
        "from": email_msg["From"],
        "from_name_addr": email.utils.parseaddr(email_msg["From"]),
        "to": email_msg["To"],
        "cc": email_msg["CC"],
        "bcc": email_msg["BCC"],
        "date": email_msg["Date"],
        "timestamp": email.utils.parsedate_to_datetime(email_msg["Date"]).timestamp(),
        "subject": email_msg["Subject"],
        "content": content if not skip_content else None,
        "content_type": content_type if not skip_content else None,
        "attachments": attachments if not skip_content else None,
        "message_id": message.get_message_id(),
        "tags": list(message.get_tags()),
    }

def message_attachment(message, num):
    """Returns attachment no. `num` of a `notmuch.message.Message` instance."""
    with open(message.get_filename(), "rb") as f:
        email_msg = email.message_from_binary_file(f, policy=email.policy.default)
    attachments = []
    for part in email_msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_disposition() == "attachment":
            attachments.append(part)
    if not attachments:
        return {}
    attachment = attachments[num]
    return {
        "content_type": attachment.get_content_type(),
        "content": attachment.get_content(),
    }
