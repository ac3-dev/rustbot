import os
import aiohttp
import discord
from discord.ext import commands, tasks

# ==========================================
# ⚙️ CONFIGURATION & TARGET PLAYERS
# ==========================================

# 1. Alert Channel ID
RUST_ALERT_CHANNEL_ID = 1424585775772602448

# 2. Tracked Players (SteamID64 -> Display Name)
# Rust App ID on Steam is 252490
RUST_APP_ID = "252490"
TRACKED_PLAYERS = {
    "76561199244950673": "Ace",  # Replace PlayerName with your desired display name
}

# 3. Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# Track online state to detect both login and logout events
player_online_status = {steam_id: False for steam_id in TRACKED_PLAYERS}

# ==========================================
# 🤖 BOT SETUP & STEAM API CHECK
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


async def check_steam_status(session: aiohttp.ClientSession, steam_id: str):
  """Checks Steam directly to see if the user is in-game playing Rust."""
  url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"

  try:
    async with session.get(url) as response:
      if response.status == 200:
        data = await response.json()
        players = data.get("response", {}).get("players", [])
        if players:
          player = players[0]
          game_id = str(player.get("gameid", ""))
          game_name = player.get("gameextrainfo", "")
          avatar = player.get("avatarfull", "")

          if game_id == RUST_APP_ID or "rust" in game_name.lower():
            return True, game_name or "Rust", avatar
          return False, None, avatar
      return False, None, None
  except Exception as e:
    print(f"Error checking Steam API for {steam_id}: {e}")
    return False, None, None


# Checks Steam every 60 seconds
@tasks.loop(seconds=60)
async def steam_tracker_loop():
  channel = bot.get_channel(RUST_ALERT_CHANNEL_ID)
  if not channel:
    return

  async with aiohttp.ClientSession() as session:
    for steam_id, player_name in TRACKED_PLAYERS.items():
      is_online, game_name, avatar_url = await check_steam_status(
          session, steam_id
      )
      was_online = player_online_status.get(steam_id, False)

      # 🟢 Player hopped ON Rust
      if is_online and not was_online:
        player_online_status[steam_id] = True

        embed = discord.Embed(
            title="🎮 Rust Activity Alert",
            description=f"**{player_name}** is now playing **{game_name}**!",
            color=discord.Color.green(),
        )
        if avatar_url:
          embed.set_thumbnail(url=avatar_url)
        embed.add_field(
            name="Steam Profile",
            value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
            inline=False,
        )
        await channel.send(embed=embed)

      # 🔴 Player got OFF Rust
      elif not is_online and was_online:
        player_online_status[steam_id] = False

        embed = discord.Embed(
            title="🛑 Rust Activity Alert",
            description=f"**{player_name}** got off **Rust**!",
            color=discord.Color.red(),
        )
        if avatar_url:
          embed.set_thumbnail(url=avatar_url)
        embed.add_field(
            name="Steam Profile",
            value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
            inline=False,
        )
        await channel.send(embed=embed)


@steam_tracker_loop.before_loop
async def before_steam_tracker_loop():
  await bot.wait_until_ready()


@bot.event
async def on_ready():
  print(f"Logged on as {bot.user}!")
  if not steam_tracker_loop.is_running():
    steam_tracker_loop.start()


# Startup validation
if not DISCORD_TOKEN:
  raise ValueError("❌ DISCORD_TOKEN environment variable is missing!")
if not STEAM_API_KEY:
  raise ValueError("❌ STEAM_API_KEY environment variable is missing!")

bot.run(DISCORD_TOKEN)
