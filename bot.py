import asyncio
import json
import websockets
import datetime

MOVES = {
    'up':    {'x': 0,  'y': -1},
    'down':  {'x': 0,  'y': 1},
    'left':  {'x': -1, 'y': 0},
    'right': {'x': 1,  'y': 0}
}

OPPOSITE_DIR = {
    'up': 'down',
    'down': 'up',
    'left': 'right',
    'right': 'left'
}

class SnakeBot:
    def __init__(self, server_url: str, bot_name: str):
        self.player_id = None
        self.grid = None
        self.server_url = server_url
        self.bot_name = bot_name
        self.last_play_time = datetime.datetime.now()
        self.room_code = None
        self.ws = None
        self.is_first_game = True

    async def start(self):
        try:
            async with websockets.connect(self.server_url) as ws:
                self.ws = ws
                join_message = {
                    "type": "create_room",
                    "name": self.bot_name
                }
                await ws.send(json.dumps(join_message))

                async for message in ws:
                    await self.handle_message(ws, message)

        except Exception as e:
            pass # すべてを握りつぶす
    
    async def start_as_player(self, room_code: str):
        try:
            self.is_first_game = False
            async with websockets.connect(self.server_url) as ws:
                self.ws = ws
                join_message = {
                    "type": "join_room",
                    "code": room_code,
                    "name": self.bot_name
                }
                await ws.send(json.dumps(join_message))

                async for message in ws:
                    await self.handle_message(ws, message)

        except Exception as e:
            pass
    
    async def wait_for_room_creation(self, timeout: int = 10):
        start_time = datetime.datetime.now()
        while self.room_code is None:
            if (datetime.datetime.now() - start_time).total_seconds() > timeout:
                raise TimeoutError("Room creation timed out.")
            await asyncio.sleep(0.1)
        return self.room_code
    
    async def start_game(self):
        if not self.ws:
            return
        if not self.is_first_game:
            await self.ws.send(json.dumps({"type": "restart"}))
            await self.ws.send(json.dumps({"type": "start_game"}))
        else:
            self.is_first_game = False
            await self.ws.send(json.dumps({"type": "start_game"}))
        
    async def handle_message(self, ws, raw_msg):
        msg = json.loads(raw_msg)
        msg_type = msg.get("type")

        if msg_type == "room_joined":
            self.player_id = msg.get("playerId")
            self.room_code = msg.get("code")

        elif msg_type == "game_start":
            self.grid = msg.get("grid")
            self.last_play_time = datetime.datetime.now()

        elif msg_type == "state":
            if not self.player_id or not self.grid:
                return
            
            await self.think(ws, msg)

        elif msg_type == "game_over":
            pass 

        elif msg_type == "error":
            pass

    async def think(self, ws, state):
        snakes = state.get("snakes", [])
        walls = state.get("walls", [])
        foods = state.get("foods", [])

        my_snake = next((s for s in snakes if s.get("playerId") == self.player_id), None)
        if not my_snake or not my_snake.get("alive") or len(my_snake.get("segments", [])) == 0:
            return

        segments = my_snake.get("segments")
        my_length = len(segments)
        my_head = segments[0]
        current_dir = my_snake.get("dir")

        danger_tiles = set()
        for w in walls: 
            danger_tiles.add(f"{w['x']},{w['y']}")
        
        enemy_heads = []
        for snake in snakes:
            for seg in snake.get("segments", []):
                danger_tiles.add(f"{seg['x']},{seg['y']}")

            if not snake.get("alive"):
                continue
            
            if snake.get("playerId") != self.player_id:
                e_segments = snake.get("segments", [None])
                enemy_head = e_segments[0]
                if enemy_head:
                    enemy_heads.append({
                        "head": enemy_head,
                        "length": len(snake.get("segments", [])),
                        "dir": snake.get("dir")
                    })

        current_closest_food_dist = 9999
        if foods:
            for f in foods:
                d = abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y'])
                if d < current_closest_food_dist:
                    current_closest_food_dist = d

        current_closest_enemy_dist = 9999
        for eh_info in enemy_heads:
            eh = eh_info["head"]
            d = abs(my_head['x'] - eh['x']) + abs(my_head['y'] - eh['y'])
            if d < current_closest_enemy_dist:
                current_closest_enemy_dist = d

        is_food_closer = (current_closest_food_dist <= current_closest_enemy_dist)

        best_dir = None
        best_score = -999999

        for direction, vec in MOVES.items():
            if direction == OPPOSITE_DIR.get(current_dir): 
                continue

            next_x = my_head['x'] + vec['x']
            next_y = my_head['y'] + vec['y']

            if next_x < 0 or next_x >= self.grid['w'] or next_y < 0 or next_y >= self.grid['h']: 
                continue
            if f"{next_x},{next_y}" in danger_tiles: 
                continue

            score = 0

            dist_to_left = next_x
            dist_to_right = (self.grid['w'] - 1) - next_x
            dist_to_top = next_y
            dist_to_bottom = (self.grid['h'] - 1) - next_y
            min_wall_dist = min(dist_to_left, dist_to_right, dist_to_top, dist_to_bottom)
            
            if min_wall_dist == 0:   
                score -= 40
            elif min_wall_dist == 1: 
                score -= 15

            if foods:
                next_closest_food_dist = 9999
                for f in foods:
                    d = abs(next_x - f['x']) + abs(next_y - f['y'])
                    if d < next_closest_food_dist:
                        next_closest_food_dist = d
                
                distance_diff = current_closest_food_dist - next_closest_food_dist
                if distance_diff > 0:
                    score += 80 if is_food_closer else 20
                elif distance_diff < 0:
                    score -= 5

            for eh_info in enemy_heads:
                eh = eh_info["head"]
                e_len = eh_info["length"]
                e_dir = eh_info["dir"]

                current_enemy_dist = abs(my_head['x'] - eh['x']) + abs(my_head['y'] - eh['y'])
                next_enemy_dist = abs(next_x - eh['x']) + abs(next_y - eh['y'])
                
                is_i_am_bigger = (my_length >= e_len)

                if next_enemy_dist == 1:
                    if is_i_am_bigger:
                        score += 150
                    else:
                        score -= 50
                elif next_enemy_dist == 2:
                    if is_i_am_bigger:
                        score += 100
                    else:
                        score += 30
                elif 3 <= next_enemy_dist <= 6:
                    if next_enemy_dist < current_enemy_dist:
                        score += 15 if is_food_closer else 60
                    else:
                        score -= 10
                else:
                    if next_enemy_dist < current_enemy_dist:
                        score += 5 if is_food_closer else 15

                if next_enemy_dist <= 4 and min_wall_dist <= 1:
                    if is_i_am_bigger:
                        score += 80
                    else:
                        score -= 100

                if current_dir == e_dir:
                    dir_vec = MOVES[current_dir]
                    dx = eh['x'] - my_head['x']
                    dy = eh['y'] - my_head['y']
                    
                    is_side_by_side = False
                    if dir_vec['x'] == 0:
                        is_side_by_side = (dy == 0) and (abs(dx) == 1 or abs(dx) == 2)
                    else:
                        is_side_by_side = (dx == 0) and (abs(dy) == 1 or abs(dy) == 2)

                    if is_side_by_side:
                        if dir_vec['x'] != 0:
                            is_ahead = (next_x * dir_vec['x'] > eh['x'] * dir_vec['x'])
                            turning_towards_enemy = (next_y == eh['y'])
                        else:
                            is_ahead = (next_y * dir_vec['y'] > eh['y'] * dir_vec['y'])
                            turning_towards_enemy = (next_x == eh['x'])

                        if is_ahead and turning_towards_enemy:
                            score += 300

            if direction == current_dir:
                score += 5

            if score > best_score:
                best_score = score
                best_dir = direction

        if best_dir:
            if best_dir != current_dir:
                action = {"type": "set_direction", "dir": best_dir}
                await ws.send(json.dumps(action))
        else:
            action = {"type": "drop_block"}
            await ws.send(json.dumps(action))
