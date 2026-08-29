import os
import aiohttp
import discord
from discord.ext import commands, tasks

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

RUST_ALERT_CHANNEL_ID = 1424585775772602448
RUST_APP_ID = 252490

# Target player mapping (SteamID64 -> Display Name)
TRACKED_PLAYERS = {
    "76561199244950673": "Ace",
    "76561199115906390": "Ziirka",
}

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# State trackers
last_playtime = {steam_id: None for steam_id in TRACKED_PLAYERS}
player_online_status = {steam_id: False for steam_id in TRACKED_PLAYERS}

# ==========================================
# 🤖 BOT SETUP & PLAYTIME TRACKER
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


async def get_rust_playtime_data(session: aiohttp.ClientSession, steam_id: str):
  """Fetches total Rust playtime and recent (past 2 weeks) playtime in minutes."""
  url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"

  try:
    async with session.get(url) as response:
      if response.status == 200:
        data = await response.json()
        games = data.get("response", {}).get("games", [])
        for game in games:
          if game.get("appid") == RUST_APP_ID:
            total_time = game.get("playtime_forever", 0)
            recent_time = game.get("playtime_2weeks", 0)
            return total_time, recent_time
      return None, None
  except Exception as e:
    print(f"Error checking recent games for {steam_id}: {e}")
    return None, None


@tasks.loop(minutes=2)
async def steam_playtime_tracker():
  channel = bot.get_channel(RUST_ALERT_CHANNEL_ID)
  if not channel:
    return

  async with aiohttp.ClientSession() as session:
    for steam_id, player_name in TRACKED_PLAYERS.items():
      current_playtime, recent_playtime = await get_rust_playtime_data(
          session, steam_id
      )

      if current_playtime is None:
        continue

      previous_playtime = last_playtime[steam_id]

      # First run / startup check (handles bot restarting while player is already on)
      if previous_playtime is None:
        last_playtime[steam_id] = current_playtime

        # If they have recent playtime, treat them as currently active
        if recent_playtime and recent_playtime > 0:
          player_online_status[steam_id] = True
          embed = discord.Embed(
              title="🎮 Rust Activity Alert (Bot Initialized)",
              description=(
                  f"**{player_name}** is already actively playing **Rust**!"
              ),
              color=discord.Color.green(),
          )
          embed.add_field(
              name="Recent Activity",
              value=f"`{recent_playtime}` mins logged recently",
              inline=False,
          )
          embed.add_field(
              name="Steam Profile",
              value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
              inline=False,
          )
          await channel.send(embed=embed)
        continue

      was_online = player_online_status[steam_id]

      # 🟢 Playtime increased -> Player is actively in Rust
      if current_playtime > previous_playtime:
        last_playtime[steam_id] = current_playtime

        if not was_online:
          player_online_status[steam_id] = True
          embed = discord.Embed(
              title="🎮 Rust Activity Alert",
              description=f"**{player_name}** is now playing **Rust**!",
              color=discord.Color.green(),
          )
          embed.add_field(
              name="Steam Profile",
              value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
              inline=False,
          )
          await channel.send(embed=embed)

      # 🔴 Playtime stopped increasing -> Player got off Rust
      elif current_playtime == previous_playtime and was_online:
        player_online_status[steam_id] = False
        embed = discord.Embed(
            title="🛑 Rust Activity Alert",
            description=f"**{player_name}** got off **Rust**!",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Steam Profile",
            value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
            inline=False,
        )
        await channel.send(embed=embed)


@steam_playtime_tracker.before_loop
async def before_tracker():
  await bot.wait_until_ready()


@bot.event
async def on_ready():
  print(f"Logged on as {bot.user}!")
  if not steam_playtime_tracker.is_running():
    steam_playtime_tracker.start()


if not DISCORD_TOKEN or not STEAM_API_KEY:
  raise ValueError("Missing environment variables!")

bot.run(DISCORD_TOKEN)
