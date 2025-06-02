import json
import os
from campaign_repository import insert_campaign

def lambda_handler(event, context):
    for record in event['Records']:
        body = json.loads(record['body'])

        try:
            insert_campaign(body)
        except Exception as e:
            print(f"❌ 저장 실패: {e}")

        return {
            'statusCode': 200,
            'body': 'Data processed successfully'
        }
    