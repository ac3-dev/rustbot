import os
import time
import aiohttp
import discord
from discord.ext import commands, tasks

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

RUST_ALERT_CHANNEL_ID = 1424585775772602448

# Target player mapping (SteamID64 -> Display Name)
TRACKED_PLAYERS = {
    "76561199244950673": "Ace",
    "76561199115906390": "Ziirka",
}

# Rust (252490) + Crosshair X (1366800)
TRACKED_APP_IDS = ["252490", "1366800"]

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# State trackers
player_online_status = {steam_id: False for steam_id in TRACKED_PLAYERS}
player_start_time = {steam_id: None for steam_id in TRACKED_PLAYERS}

# ==========================================
# 🤖 BOT SETUP & HELPER FUNCTIONS
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def format_duration(seconds: int) -> str:
  """Formats seconds into hours, minutes, and seconds."""
  hours, remainder = divmod(seconds, 3600)
  minutes, secs = divmod(remainder, 60)
  parts = []
  if hours > 0:
    parts.append(f"{int(hours)}h")
  if minutes > 0:
    parts.append(f"{int(minutes)}m")
  if secs > 0 or not parts:
    parts.append(f"{int(secs)}s")
  return " ".join(parts)


async def check_player_live_status(
    session: aiohttp.ClientSession, steam_id: str
):
  """Checks Steam live summaries to see if Rust or its companion overlay is running."""
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

          if (
              game_id in TRACKED_APP_IDS
              or "rust" in game_name.lower()
              or "crosshair" in game_name.lower()
          ):
            return True, "Rust", avatar
          return False, None, avatar
      return False, None, None
  except Exception as e:
    print(f"Error checking Steam status for {steam_id}: {e}")
    return False, None, None


# ==========================================
# 🔄 TRACKER LOOP
# ==========================================


@tasks.loop(seconds=60)
async def steam_tracker_loop():
  channel = bot.get_channel(RUST_ALERT_CHANNEL_ID)
  if not channel:
    return

  current_unix = int(time.time())

  async with aiohttp.ClientSession() as session:
    for steam_id, player_name in TRACKED_PLAYERS.items():
      is_online, game_name, avatar_url = await check_player_live_status(
          session, steam_id
      )
      was_online = player_online_status.get(steam_id, False)

      # 🟢 Player hopped ON Rust
      if is_online and not was_online:
        player_online_status[steam_id] = True
        player_start_time[steam_id] = current_unix

        embed = discord.Embed(
            title="🎮 Rust Activity Alert",
            description=f"**{player_name}** is now playing **Rust**!",
            color=discord.Color.green(),
        )
        if avatar_url:
          embed.set_thumbnail(url=avatar_url)

        # Discord dynamic timestamp: <t:UNIX:t> shows exact local time, <t:UNIX:R> shows dynamic elapsed time
        embed.add_field(
            name="Started At",
            value=f"<t:{current_unix}:t> (<t:{current_unix}:R>)",
            inline=True,
        )
        embed.add_field(
            name="Steam Profile",
            value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
            inline=False,
        )
        await channel.send(embed=embed)

      # 🔴 Player got OFF Rust
      elif not is_online and was_online:
        player_online_status[steam_id] = False
        start_unix = player_start_time.get(steam_id, current_unix)

        # Calculate session duration
        elapsed_seconds = max(0, current_unix - start_unix)
        duration_str = format_duration(elapsed_seconds)

        embed = discord.Embed(
            title="🛑 Rust Activity Alert",
            description=f"**{player_name}** got off **Rust**!",
            color=discord.Color.red(),
        )
        if avatar_url:
          embed.set_thumbnail(url=avatar_url)

        embed.add_field(
            name="Started At", value=f"<t:{start_unix}:t>", inline=True
        )
        embed.add_field(
            name="Ended At", value=f"<t:{current_unix}:t>", inline=True
        )
        embed.add_field(
            name="Session Length", value=f"`{duration_str}`", inline=False
        )
        embed.add_field(
            name="Steam Profile",
            value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})",
            inline=False,
        )

        player_start_time[steam_id] = None
        await channel.send(embed=embed)


@steam_tracker_loop.before_loop
async def before_tracker():
  await bot.wait_until_ready()


@bot.event
async def on_ready():
  print(f"Logged on as {bot.user}!")
  if not steam_tracker_loop.is_running():
    steam_tracker_loop.start()


if not DISCORD_TOKEN or not STEAM_API_KEY:
  raise ValueError(
      "Missing DISCORD_TOKEN or STEAM_API_KEY environment variables!"
  )

bot.run(DISCORD_TOKEN)
