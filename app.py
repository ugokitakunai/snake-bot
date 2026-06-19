import datetime

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from bot import SnakeBot
from fastapi.responses import HTMLResponse
import time, asyncio, uuid

app = FastAPI()

active_bots = {}

bg_tasks = BackgroundTasks()

async def timeout_bot(bot_id: str, timeout: int = 3600):
    while bot_id in active_bots:
        bot = active_bots[bot_id]
        elapsed_time = (datetime.datetime.now() - bot.last_play_time).total_seconds()
        if elapsed_time > timeout:
            active_bots.pop(bot_id, None)
            break
        await asyncio.sleep(10)

@app.get("/")
async def root():
    domain = "snake-play.ugk.app"
    bot_name = "snake-bot"
    room_code = ""
    bot = SnakeBot(f"wss://{domain}/ws", bot_name)
    bot_id = str(uuid.uuid4())
    active_bots[bot_id] = bot
    asyncio.create_task(bot.start())
    asyncio.create_task(timeout_bot(bot_id))
    await bot.wait_for_room_creation()
    room_code = bot.room_code

    return HTMLResponse(f"""
        <html>
            <body>
                <script>
                    function startGame(botId) {{
                        fetch(`/bot/${{botId}}/start-game`, {{ method: 'GET' }})
                            .then(response => response.json())
                            .then(data => {{
                                console.log(data);
                            }})
                            .catch(error => {{
                                console.error('Error:', error);
                            }});
                    }}
                </script>
                <h1>Snake Bot</h1>
                <p>Room Code: {room_code}</p>
                <a href="https://{domain}/?room={room_code}" target="_blank">参加</a>
                <br>
            <button onclick="startGame('{bot_id}')">ゲームを開始(5秒後)</button>
            </body>
        </html>
    """)

@app.get("/bot/{bot_id}/start-game")
async def start_game(bot_id: str):
    bot = active_bots.get(bot_id)
    if not bot:
        return {"error": "Bot not found."}
    
    await asyncio.sleep(2)
    await bot.start_game()
    return {"message": "Game started."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
