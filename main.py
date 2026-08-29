import os
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

player_online_status = {steam_id: False for steam_id in TRACKED_PLAYERS}

# ==========================================
# 🤖 BOT SETUP & STEAM TRACKER
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def check_player_live_status(session: aiohttp.ClientSession, steam_id: str):
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

                    # Returns True if either Rust or Crosshair X is running
                    if game_id in TRACKED_APP_IDS or "rust" in game_name.lower() or "crosshair" in game_name.lower():
                        return True, "Rust", avatar
                    return False, None, avatar
            return False, None, None
    except Exception as e:
        print(f"Error checking Steam status for {steam_id}: {e}")
        return False, None, None

@tasks.loop(seconds=60)
async def steam_tracker_loop():
    channel = bot.get_channel(RUST_ALERT_CHANNEL_ID)
    if not channel:
        return

    async with aiohttp.ClientSession() as session:
        for steam_id, player_name in TRACKED_PLAYERS.items():
            is_online, game_name, avatar_url = await check_player_live_status(session, steam_id)
            was_online = player_online_status.get(steam_id, False)

            # 🟢 Player is detected in Rust / Companion
            if is_online and not was_online:
                player_online_status[steam_id] = True
                embed = discord.Embed(
                    title="🎮 Rust Activity Alert",
                    description=f"**{player_name}** is now playing **Rust**!",
                    color=discord.Color.green()
                )
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Steam Profile", value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})", inline=False)
                await channel.send(embed=embed)

            # 🔴 Player closed Rust / Companion
            elif not is_online and was_online:
                player_online_status[steam_id] = False
                embed = discord.Embed(
                    title="🛑 Rust Activity Alert",
                    description=f"**{player_name}** got off **Rust**!",
                    color=discord.Color.red()
                )
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Steam Profile", value=f"[View Profile](https://steamcommunity.com/profiles/{steam_id})", inline=False)
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
    raise ValueError("Missing DISCORD_TOKEN or STEAM_API_KEY environment variables!")

bot.run(DISCORD_TOKEN)
