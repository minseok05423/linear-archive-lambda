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
        # body can be string in some proxy integrations
        if isinstance(event.get('body'), str):
            body_data = json.loads(event.get('body', '{}'))
        else:
            body_data = event.get('body', {})
            
        # Support both body_data and event-level keys
        task = body_data.get("task", event.get("task", "analysis"))
        
        # Get environment variable
        DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

        if not DEEPSEEK_API_KEY:
            print("ERROR: Missing DEEPSEEK_API_KEY")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing DEEPSEEK_API_KEY'})
            }

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }

        if task == "query_parser":
            print("=== Performing Query Parsing ===")
            user_query = body_data.get("query", "")
            current_date = body_data.get("current_date", "")
            
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": f"""You are a precise query parser. Your job is to extract search filters from the user's natural language query (which may be in Korean or English).
Current Date: {current_date}

Return a JSON object with these fields:
{{
  "startDate": "YYYY-MM-DD" or null,
  "endDate": "YYYY-MM-DD" or null,
  "tags": ["tag1", "tag2"] (empty array if none),
  "keywords": ["word1", "word2"] (empty array if none),
  "daysOfWeek": [0, 1, ...] (integers 0=Sun to 6=Sat, empty if none),
  "hasImage": boolean or null (true/false if explicitly requested, else null),
  "sort": "newest" | "oldest" | "random" | null,
  "limit": integer or null
}}

Rules:
1. Handle date ranges: "1월 1일부터 2월 1일까지" -> startDate: "2024-01-01", endDate: "2024-02-01".
2. Handle relative dates: "지난주", "저번주" -> calculate range. "어제" -> specific date.
3. Handle tags: "운동 태그", "#운동" -> tags: ["운동"].
4. Handle specific text: "코딩 관련 보드" -> keywords: ["코딩"].
5. Days: "월요일에 뭐했지?" -> daysOfWeek: [1]. "주말" -> [0, 6].
6. Images: "사진 보여줘" -> hasImage: true.
7. Sort/Limit: "최근 5개" -> sort: "newest", limit: 5. "랜덤 2개" -> sort: "random", limit: 2.
8. If the user asks for "summary", "analysis", "요약", "분석" without specific constraints, return null for all fields.
9. Return format must be valid JSON."""
                    },
                    {
                        "role": "user",
                        "content": user_query
                    }
                ],
                "model": "deepseek-chat",
                "response_format": {
                    "type": "json_object"
                },
                "temperature": 0.1
            }
            
        elif task == "quick_insight":
            # === QUICK INSIGHT TASK ===
            print("Mode: Quick Insight")
            boards = body_data.get("boards", [])
            stats = body_data.get("stats", {})
            history = body_data.get("history", "")
            action = body_data.get("action", "create")  # create, update, or delete
            target_board_id = body_data.get("target_board_id")  # Specific board to analyze
            related_boards = body_data.get("related_boards", [])  # RAG: Similar historical boards

            # Find the target board
            # 1. Try explicit object passed from frontend
            target_board = body_data.get("target_board")
            
            # 2. Try looking up ID in boards list
            if not target_board and target_board_id:
                target_board = next((b for b in boards if b.get('board_id') == target_board_id), None)

            # 3. Fallback to first board
            if not target_board:
                target_board = boards[0] if boards else {}

            # Context boards are all the others
            context_boards = [b for b in boards if b.get('board_id') != target_board.get('board_id')]

            print(f"Target board description: {target_board.get('description', 'N/A')[:50]}...")

            # Construct context from stats
            stats_context = ""
            if stats:
                habits = stats.get('habits', {})
                counts = stats.get('counts', {})
                stats_context = f"""
                [User Statistics]
                - Most Active Day: {habits.get('mostActiveDay', 'N/A')}
                - Current Streak: {habits.get('currentStreak', 0)} days
                - Total Records: {counts.get('totalBoards', 0)}
                """

            # Add history context
            history_context = ""
            if history:
                history_context = f"\n\n[Long-term History]\n{history}\n"

            # Build RAG context from related boards
            rag_context = ""
            if related_boards:
                rag_context = "\n\n=== RELATED PAST ENTRIES (Pattern Detection) ===\n"
                rag_context += "These are semantically similar entries from the user's history:\n\n"
                for i, rb in enumerate(related_boards[:5], 1):
                    rag_context += f"{i}. [{rb.get('date', 'N/A')}] {rb.get('description', 'No description')}\n"
                    if rb.get('tags'):
                        tag_names = [t.get('tag_name', '') for t in rb.get('tags', [])]
                        rag_context += f"   Tags: {', '.join(tag_names)}\n"
                rag_context += "\n[PATTERN DETECTION INSTRUCTIONS]\n"
                rag_context += "- Compare the TARGET ENTRY to these RELATED PAST ENTRIES\n"
                rag_context += "- Notice patterns: frequency, improvements, consistency, time gaps\n"
                rag_context += "- Examples of pattern-aware responses:\n"
                rag_context += "  ✅ '이번 주만 벌써 3번째네요!' (if similar activity happened 2+ times this week)\n"
                rag_context += "  ✅ '2주 만이네요?' (if last similar entry was 2 weeks ago)\n"
                rag_context += "  ✅ '무게 늘었네요!' (if workout weight increased)\n"
                rag_context += "  ✅ '요즘 자주 하시네요 ㅎㅎ' (if activity is becoming more frequent)\n"

            # Action context
            action_desc = {
                "create": "User just WROTE this new entry.",
                "update": "User just EDITED this entry.",
                "delete": "User just DELETED this entry."
            }.get(action, "User interacted with this entry.")

            # Debug logging
            print(f"Target Board Keys: {list(target_board.keys())}")
            print(f"Target Description (Raw): {target_board.get('description')}")
            
            # Robust extraction
            raw_desc = target_board.get('description')
            if raw_desc is None:
                raw_desc = ""
            target_desc = str(raw_desc).strip()
            
            # Robust tag extraction
            raw_tags = target_board.get('tags', [])
            tag_list = []
            if isinstance(raw_tags, list):
                for t in raw_tags:
                    if isinstance(t, dict):
                        # Try 'tag_name', 'name', or just values
                        t_name = t.get('tag_name') or t.get('name') or str(list(t.values())[0] if t else "Unknown")
                        tag_list.append(t_name)
                    elif isinstance(t, str):
                        # It's already a string!
                        tag_list.append(t)
                    else:
                        tag_list.append(str(t))
            
            target_tags = ", ".join(tag_list) if tag_list else "(No tags)"
            target_date = target_board.get('date', 'Unknown Date')

            # Format as structured JSON for the AI
            ai_input_data = {
                "description": target_desc,
                "tags": tag_list,
                "created_at": target_board.get("created_at", "Unknown"),
                "debug_info": f"Desc length: {len(target_desc)}"
            }

            # Check if we actually have data
            if not target_desc and not tag_list:
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'insight': "⚠️ SYSTEM NOTICE: Data was empty. (Description & Tags missing)",
                        'debug': ai_input_data,
                        'raw_received_target': target_board,
                        'full_body_keys': list(body_data.keys())
                    }, ensure_ascii=False)
                }

            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": f"""You are a witty, observant friend.
Your goal is to PROVE you read the specific details of the user's entry.

[CORE INSTRUCTION]
Don't just say "Good job". Tell them WHY it's interesting or relatable.
If they say "Ate pizza", don't say "Yum". Say "Pepperoni? Or Hawaiian?"
If they say "Fixed bug", don't say "Good". Say "Finally! That bug was annoying."

[CONTEXT AWARENESS]
- Time: {target_date} (Is it late? Early?)
- Status: This entry was just {action.upper()}D.

[ACTION GUIDES]
- CREATE/UPDATE: React to the content energetically.
- DELETE: "Deleting '{target_desc[:10]}...'? Changed your mind?" or "Cleaning up history?"

[FORMAT]
- Korean (casual 해요체)
- One short sentence (max 60 chars)
- NO quotes.
- NO generic placeholders like "오늘 하루".

[EXAMPLES]
Entry: {{ "description": "Running 5km", "tags": ["Health"] }} 
-> "와 5km... 무릎 괜찮으세요? 대단해요!"

Entry: {{ "description": "Debugging", "tags": ["Work"] }} 
-> "버그와의 전쟁... 승리하셨나요?"

Entry: {{ "description": "", "tags": ["Reading"] }} 
-> "무슨 책이에요? 저도 추천해주세요!"
"""
                    },
                    {
                        "role": "user",
                        "content": f"""User Action: {action.upper()}

TARGET DATA (JSON):
{json.dumps(ai_input_data, ensure_ascii=False, indent=2)}

[RAW DEBUG DUMP]
(If target data seems empty, look here!)
{json.dumps(body_data, ensure_ascii=False, default=str)[:3000]}

(React specifically to the description and tags above.)"""
                    }
                ],
                "model": "deepseek-chat",
                "max_tokens": 150,
                "temperature": 1.1
            }

            response = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload,
                timeout=10
            )

            if not response.ok:
                 raise Exception(f"DeepSeek API Error: {response.text}")

            result = response.json()
            insight = result['choices'][0]['message']['content'].strip().replace('"', '')

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({'insight': insight})
            }
        
        else:
            # === ANALYSIS TASK (Default) ===
            print("Mode: Analysis")
            # Try getting boards from body_data first, then fallback to event
            boards = body_data.get("boards") or event.get("boards", [])
    
            if not boards:
                print("ERROR: No boards data provided")
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'No boards data provided'})
                }
    
            print(f"Received {len(boards)} boards for analysis")
            
            # Extract History
            history = body_data.get("history") or event.get("history", "")
            history_context = ""
            if history:
                 history_context = f"\n\n=== 사용자의 장기 기록 (참고용) ===\n{history}\n\n(이 기록은 장기적인 성장을 이해하는 데 참고하되, 아래의 새로운 활동 보드에 집중해서 피드백을 주세요.)"

            # Extract Metrics
            metrics = body_data.get("metrics") or event.get("metrics", [])
            metrics_context = ""
            if metrics:
                metrics_list = "\n".join([f"- {m.get('label', 'Metric')}: {m.get('value', 'N/A')}" for m in metrics])
                metrics_context = f"\n\n=== 주요 하이라이트 (랜덤 선택됨) ===\n{metrics_list}\n\n(이 수치들을 자연스럽게 이야기에 녹여내어 데이터에 기반한 칭찬을 해주세요.)"

            # Prepare Deepseek API request for Analysis
            payload = {
                "messages": [
                    {
                        "content": f"""당신은 열정적인 퍼스널 라이프 코치이자 데이터 스토리텔러입니다.
    {history_context}
    {metrics_context}
    
    Respond with a JSON object containing a SINGLE field "analysis":
    {{
      "analysis": "사용자의 최근 활동을 요약하는 따뜻하고 격려가 담긴 3-5문장의 하나의 완성된 문단 (한국어)."
    }}
    
    Guidelines:
    - **반드시 한국어로 작성하세요.**
    - 사용자에게 직접 말하듯이 ("해요체" 사용, 예: "했어요", "좋네요") 친근하게 작성하세요.
    - 위에 제공된 **주요 하이라이트(Metrics)**를 자연스럽게 이야기에 포함시키세요. 단순히 나열하지 말고, 이것이 왜 멋진지 설명하세요.
    - 활동 보드에서 발견된 패턴을 요약하세요.
    - 열정적이고 전문적인 톤을 유지하세요.
    - "Fact 1", "Fact 2" 등으로 나누지 말고, 하나의 흐르는 문단으로 작성하세요.
    
    CRITICAL:
    - Return ONLY valid JSON.
    - The "analysis" field must contain the ENTIRE message string in Korean.
    - Do not hallucinate data not present in Boards or Highlights.""",
                        "role": "system"
                    },
                    {
                        "content": f"""최근 활동 보드 데이터입니다:
    
    {json.dumps(boards, indent=2)}
    
    데이터를 분석하고 격려의 메시지를 한국어로 작성해주세요.""",
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

        print(f"Calling Deepseek API for {task}...")
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

        # Extract the content from the response
        content = completion['choices'][0]['message']['content']
        print(f"Content (raw): {content}")

        # Choose result key
        if task == "query_parser":
            try:
                parsed_json = json.loads(content)
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({'filters': parsed_json})
                }
            except json.JSONDecodeError:
                return {
                    'statusCode': 422,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'Failed to parse filters'})
                }
        else:
            # Analysis
            try:
                parsed_json = json.loads(content)
                parsed_content = parsed_json.get('analysis', content) # Handle if analysis key exists or flat string
                if isinstance(parsed_json, dict) and 'analysis' in parsed_json:
                     parsed_content = parsed_json['analysis']
                elif isinstance(parsed_json, dict):
                    # fallback if json but strictly no analysis key? or use whole json?
                    # The prompt asks for { analysis: ... }
                    pass
                
                # Check guidelines again, previously it returned object { analysis: ... }
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({'analysis': parsed_content})
                }

            except json.JSONDecodeError:
                 # If LLM returned plain text despite instructions
                 return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({'analysis': content})
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
