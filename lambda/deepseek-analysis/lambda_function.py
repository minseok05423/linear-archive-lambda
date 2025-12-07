import json
import os
import requests

def lambda_handler(event, context):
    # CORS headers for all responses
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }

    # Handle OPTIONS preflight request
    if event.get('httpMethod') == 'OPTIONS' or event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        print("Handling OPTIONS preflight request")
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }

    try:
        print("=== Deepseek Analysis Lambda started ===")
        print(f"Received event: {json.dumps(event)}")

        # Get environment variable
        DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

        if not DEEPSEEK_API_KEY:
            print("ERROR: Missing DEEPSEEK_API_KEY")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing DEEPSEEK_API_KEY'})
            }

        # Parse boards data from request body
        boards = event.get("boards", [])

        if not boards:
            print("ERROR: No boards data provided")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No boards data provided'})
            }

        print(f"Received {len(boards)} boards for analysis")

        # Prepare Deepseek API request
        payload = {
            "messages": [
                {
                    "content": """You are an enthusiastic personal life coach analyzing someone's activity boards. Your job is to make them feel proud of what they've accomplished and excited about their progress.

Respond with a JSON object in this format:
{
  "fact1": "An exciting discovery about their recent activities (with specific numbers)",
  "fact2": "Another interesting pattern or achievement (with specific numbers)",
  "analysis": "A warm, encouraging 2-3 sentence message directly to them"
}

Guidelines:
- Write in second person ("you", "your") - never third person
- Be enthusiastic and positive about their activities
- Point out interesting patterns or themes in what they're documenting
- Make specific references to their actual data (dates, tags, descriptions)
- Sound like a supportive friend, not a robot""",
                    "role": "system"
                },
                {
                    "content": f"""Look at what this person has been documenting on their boards and give them some exciting insights:

{json.dumps(boards, indent=2)}

Make them feel good about their activities! Focus on:
- What they've been working on or experiencing
- Any cool patterns or themes you notice
- How active they've been
- Specific accomplishments or moments they've captured

Be warm, personal, and enthusiastic. Use "you" and "your" throughout.
Return ONLY valid JSON, no markdown or extra text.""",
                    "role": "user"
                }
            ],
            "model": "deepseek-chat",
            "response_format": {
                "type": "json_object"
            },
            "thinking": {
                "type": "disabled"
            },
            "max_tokens": 1024,
            "temperature": 1,
            "top_p": 1
        }

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }

        print("Calling Deepseek API for analysis...")
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"Deepseek API responded with status: {response.status_code}")

        if not response.ok:
            error_text = response.text
            print(f"ERROR: Deepseek API error: {error_text}")
            raise Exception(f"Deepseek API error {response.status_code}: {error_text}")

        completion = response.json()
        print(f"Deepseek response: {json.dumps(completion)}")

        # Extract the analysis from the response
        analysis_content = completion['choices'][0]['message']['content']
        print(f"Analysis content (raw): {analysis_content}")

        # Parse the JSON string to an object
        try:
            analysis_json = json.loads(analysis_content)
            print(f"Analysis content (parsed): {json.dumps(analysis_json)}")
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse analysis JSON: {str(e)}")
            analysis_json = {
                "fact1": "Unable to parse analysis",
                "fact2": "Unable to parse analysis",
                "analysis": analysis_content
            }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'analysis': analysis_json,
                'raw_response': completion
            })
        }

    except Exception as error:
        print(f"Analysis error: {str(error)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'error': f'Analysis failed: {str(error)}'
            })
        }
