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
                    "content": """당신은 누군가의 활동 보드를 분석하는 열정적인 개인 생활 코치입니다. 당신의 역할은 그들이 이룬 것을 자랑스럽게 여기고 진전에 대해 흥분하게 만드는 것입니다.

다음 형식의 JSON 객체로 응답하세요:
{
  "fact1": "최근 활동에 대한 흥미로운 발견 (구체적인 숫자 포함)",
  "fact2": "또 다른 흥미로운 패턴이나 성취 (구체적인 숫자 포함)",
  "analysis": "그들에게 직접 전하는 따뜻하고 격려하는 2-3문장의 메시지"
}

가이드라인:
- 2인칭("당신", "당신의")으로 작성하세요 - 절대 3인칭 사용 금지
- 그들의 활동에 대해 열정적이고 긍정적으로 표현하세요
- 그들이 기록한 것에서 흥미로운 패턴이나 주제를 지적하세요
- 실제 데이터(날짜, 태그, 설명)를 구체적으로 언급하세요
- 로봇이 아닌 지지해주는 친구처럼 말하세요
- 모든 응답은 한국어로 작성하세요""",
                    "role": "system"
                },
                {
                    "content": f"""이 사람이 보드에 기록한 내용을 보고 흥미로운 인사이트를 전해주세요:

{json.dumps(boards, indent=2)}

그들의 활동에 대해 기분 좋게 만들어주세요! 다음에 집중하세요:
- 그들이 작업하거나 경험한 것
- 당신이 발견한 멋진 패턴이나 주제
- 그들이 얼마나 활발하게 활동했는지
- 그들이 포착한 특정 성취나 순간들

따뜻하고, 개인적이며, 열정적으로 작성하세요. 전체적으로 "당신"과 "당신의"를 사용하세요.
오직 유효한 JSON만 반환하고, 마크다운이나 추가 텍스트는 포함하지 마세요.
모든 응답은 한국어로 작성하세요.""",
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
