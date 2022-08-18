
from cgitb import text
import os
from slack_bolt import App
from slack_sdk.errors import SlackApiError
import logging
import json
from collections import Counter
from num2words import num2words
from pymongo import MongoClient

#To do

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initializes your app with your bot token and signing secret
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Send initial modal
@app.shortcut("poll")
def open_modal(ack, shortcut, client):
    # Acknowledge the shortcut request
    ack()
    # ask for number of poll questions
    client.views_open(
        trigger_id=shortcut["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "poll",
            "title": {"type": "plain_text", "text": "Create a Poll"},
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Poll Creation Wizard",
                        "emoji": True
                    }
                },
                {
                    "dispatch_action": True,
                    "type": "input",
                    "block_id": "questions",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "pollquestions"
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "How many questions/options in your poll?",
                        "emoji": True
			}
		}
	        ]     
        }
    )
# Update Poll building Modal with questions
@app.action("pollquestions")
def handle_view_events(ack, body, logger, client):
    # Acknowledge the shortcut request
    ack()
    questions = body["view"]["state"]["values"]["questions"]["pollquestions"]["value"]
    viewtoupdate = body["view"]["id"]
    # create title block
    blocks = [
        {
            "type": "input",
            "block_id": "question",
            "element": {
                "type": "plain_text_input",
                "action_id": "plain_text_input-action"
            },
            "label": {
                "type": "plain_text",
                "text": "Enter Poll Question",
                "emoji": True
            }
        },
        # create anonymous section
        {   
			"type": "input",
            "block_id": "anonymous",
			"element": {
				"type": "radio_buttons",
				"options": [
					{
						"text": {
							"type": "plain_text",
							"text": "Yes",
							"emoji": True
						},
						"value": "value-0"
					},
					{
						"text": {
							"type": "plain_text",
							"text": "No",
							"emoji": True
						},
						"value": "value-1"
					}
				],
				"action_id": "radio_buttons-action"
			},
			"label": {
				"type": "plain_text",
				"text": "Anonymous?",
				"emoji": True
			}
		}

    ]
    # build questions section
    for i in range(int(questions)):
        question_Builder = [{
            "type": "input",
            "block_id": f"option{i}",
            "element": {
                "type": "plain_text_input",
                "action_id": "plain_text_input-action"
            },
            "label": {
                "type": "plain_text",
                "text": f"Enter Option {i+1}",
                "emoji": True
            }
        }]
        blocks = blocks + question_Builder
    blocks = json.dumps(blocks)
    client.views_update(
        view_id = viewtoupdate,
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "poll",
            "submit": {
                "type": "plain_text",
                "text": "Submit",
            },
            "title": {"type": "plain_text", "text": "Create a Poll"},
            "close": {"type": "plain_text", "text": "Close"},
            "blocks": blocks
        }
    )

# send formatted survey to channel
@app.view("poll")
def handle_view_events(ack, body, logger, client):
    ack()
    questions = body["view"]["state"]["values"]
    mongoclient = MongoClient("mongodb+srv://unfo33:peaches123@cluster0.deaag.mongodb.net/?retryWrites=true&w=majority")
    logger.info(questions)
    title = body["view"]["state"]["values"]["question"]["plain_text_input-action"]["value"]
    anonymous = questions["anonymous"]["radio_buttons-action"]["selected_option"]["text"]["text"]
    submitter = body["user"]["id"]
    blocks = []
    title_block=[
        {
            "type": "header",
            "block_id": "title",
            "text": {
                "type": "plain_text",
                "text": f"{title}",
                "emoji": True
            }
        }
    ]
    anonymous_block = [
        {
			"type": "context",
			"elements": [
				{
					"type": "plain_text",
					"text": ":bust_in_silhouette: This poll is anoymous. The identity of all respondents will be hidden",
					"emoji": True
				}
			]
		},

    ]
    index = 1
    text_Values = {}
    if anonymous == "Yes":
        blocks = blocks + anonymous_block + title_block
    else:
        blocks = blocks + title_block
    for question in questions:
        if question == "question":
            pass
        elif question == "anonymous":
            pass
        else:
            written_Number = num2words(index)
            option = questions[question]["plain_text_input-action"]["value"]
            block_id = question
            question_Builder = [
                {
                    "type": "section",
                    "block_id": f"{block_id}",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{option}",
                    },
                    "accessory": {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": f":{written_Number}:",
                            "emoji": True
                        },
                        "value": f"{block_id}",
                        "action_id": "vote"
                    }
                }]
            index +=1
            text_Values.update({block_id: option})
            blocks = blocks + question_Builder
    final_block = [{
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"Created by <@{submitter}> with VentureWell Poll"
				}
			]
		}]
    blocks = blocks + final_block
    blocks = json.dumps(blocks)
    db = mongoclient.poll
    try:
        result = client.chat_postMessage(
            channel="C03MZFXBXSQ", 
            blocks=blocks
        )
        time = result["message"]["ts"]
        db[time].insert_one(text_Values)
        logger.info(time)
        db[time].insert_one({"anonymous": anonymous})
        return time
    except SlackApiError as e:
        logger.exception(f"Error posting message error: {e}")

def store_Vote(body, client):
    logger.info("storing vote")
    db=client.poll
    ts = body["message"]["ts"]
    voter = body["user"]["id"]
    vote = body["actions"][0]["value"]
    document = db[ts].find_one({"id": voter})
    # determine if poll already created in db
    if document:
        oldvote = document["vote"]
        # determine if person already voted
        if oldvote == vote:
            db[ts].delete_one({"id": voter})
        else:
            db[ts].delete_one({"id": voter})
            db[ts].insert_one({"id": voter, "vote": vote})
    else:
        db[ts].insert_one({"id": voter, "vote": vote})

def retrieve_Vote(client, body):
    logger.info("retrieving vote")
    db=client.poll
    blocks = body["message"]["blocks"]
    ts = body["message"]["ts"]
    document = db[ts].find({})
    # check if anonymous - shouldn't there be any easier way to query the db?
    for i in document:
        if "anonymous" in i:
            anonymous = i["anonymous"]
    # rebuild message for Slack channel
    for block in blocks:
        # skip first section which doesn't change
        if block["type"] != "section":
            pass
        else:
            count_Cursor = db[ts].find({"vote": block["block_id"]})
            # need to pull this from DB again for some reason
            document = db[ts].find({})
            count = len(list(count_Cursor))
            text = document[0][block["block_id"]]
            user_list = []
            user_list_Pretty = []
            if anonymous == "No":
                # logic to grab all users who voted
                for i in document:
                    if "id" in i:
                        if i["vote"] == block["block_id"]:
                            user = i["id"]
                            user_list.append(f"<@{user}>")
                            user_list_Pretty = ", ".join(user_list)
                        else:
                            user_list = []
                            user_list_Pretty = []
                # check if list is empty so it doesn't post empty list []
                if user_list_Pretty:
                    block["text"].update({"text": f"{text}\n`{count}` {user_list_Pretty}"})
                else:
                    block["text"].update({"text": f"{text}\n`{count}`"})
            else:
                block["text"].update({"text": f"{text}\n`{count}`"})
    try:
        logger.info(blocks)
        app.client.chat_update(channel="C03MZFXBXSQ", ts=ts, blocks=blocks)
        logger.info("action item updated")
    except Exception as e:
        logger.exception(f"Failed to update message error: {e}")


# action taken when someone votes
@app.action("vote")
def handle_some_action(ack, body, logger):
    ack()
    dbpass = os.environ.get("DB_PASS")
    client = MongoClient(f"mongodb+srv://unfo33:{dbpass}@cluster0.deaag.mongodb.net/?retryWrites=true&w=majority")
    store_Vote(body, client)
    retrieve_Vote(client, body)

# Start your app
if __name__ == "__main__":
    app.start(3000)