# bot.py
import os
import threading
import time
import discord
from discord.ext import commands
from discord import ButtonStyle
from discord.ui import Button, View
from PokerNightManager import PokerNightManager
from DBManager import DBManager

TOKEN = os.getenv('DISCORD_TOKEN')
# Create a bot instance
intents = discord.Intents.default()
intents.messages = True
intents.members = True
intents.guilds = True    # Necessary for operating within guilds
intents.voice_states = True
intents.message_content = True  # Necessary to access the content of messages

bot = commands.Bot(command_prefix='!', intents=intents, description="This is Poker Night bot", help_command=None)
DB=DBManager()
PNM=PokerNightManager(DB)

# Event listener for when the bot has switched from offline to online.
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

@bot.event
async def on_message(message):
    # Check if the message is from the bot itself or another bot
    if message.author.bot:
        return
    # Check if the message is a command
    if message.content.startswith(bot.command_prefix):
        # Process the command
        await bot.process_commands(message)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.message.delete();
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f'This command is on a cooldown, please wait.')
    else:
        raise error

#Poker Night commands:
class PlayerButton(Button):
    def __init__(self, label, player_name):
        super().__init__(style=ButtonStyle.primary, label=label)
        self.player_name = player_name

    async def callback(self, interaction):
        global PNM
        # Increment the counter for the player
        PNM.active_night_add_buyin(self.player_name)
        self.label = f"{self.player_name}: {PNM.active_night_player_data[self.player_name][0]}"
        await interaction.response.edit_message(view=self.view)


class FinishButton(Button):
    def __init__(self):
        super().__init__(style=ButtonStyle.success, label="FINISH")

    async def callback(self, interaction):
        global PNM
        await interaction.response.defer()
        
        s_name, s_link=PNM.create_new_sheet()
        
        #await interaction.response.send_message(f"{s_name} sheet created: {s_link}")
        await interaction.followup.send(f"{s_name} sheet created: {s_link}", ephemeral=False)

        PNM.finish_active_night()
        
        # Disable all buttons after FINISH
        for item in self.view.children:
            item.disabled = True
            
        await interaction.message.edit(view=self.view)
        self.view.stop()
        
class AbortButton(Button):
    def __init__(self):
        super().__init__(style=ButtonStyle.danger, label="ABORT")

    async def callback(self, interaction):
        global PNM
        await interaction.response.defer()
        await interaction.followup.send("Track Aborted", ephemeral=False)

        PNM.finish_active_night()
        
        # Disable all buttons after FINISH
        for item in self.view.children:
            item.disabled = True
            
        await interaction.message.edit(view=self.view)
        self.view.stop()
        
@bot.command()
async def track(ctx, *, names: str = ""):
    global PNM
    mentions = ctx.message.mentions
    player_names=[]
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        player_names.extend(PNM.dids_to_names([user.name.capitalize() for user in voice_channel.members]))
    if mentions:
        player_names.extend(PNM.dids_to_names([user.name.capitalize() for user in mentions]))
    else:
        normalized_input = names.replace(",", "\n")
        player_names = [name.strip().capitalize() for name in normalized_input.splitlines() if name.strip()]
    
    PNM.init_active_night_players(player_names)
    
    view = View(timeout=None)
    finish_button = FinishButton()
    abort_button = AbortButton()
    view.add_item(finish_button)
    view.add_item(abort_button)

    for _ in range(3):
        view.add_item(Button(label="\u200b", disabled=True, style=ButtonStyle.secondary))
    
    for name in player_names:
        button = PlayerButton(label=f"{name}: 1", player_name=name)
        view.add_item(button)

    message = await ctx.send("Track Buyins. Click button to add 1", view=view)
    PNM.active_night_view=(view, message)

@bot.command()
async def addtotrack(ctx, name):
    global PNM
    # Check if there's an active view in the current channel
    if not (PNM.active_night_view == None):
        view, original_message = PNM.active_night_view
        
        # Add a new button for the specified member
        mentions = ctx.message.mentions
        if mentions:
            name=PNM.dids_to_names([mentions[0].name.capitalize()])[0]
        else:
            name=name.strip().capitalize()
            
        button = PlayerButton(label=f"{name}: 1", player_name=name)
        view.add_item(button)
        PNM.active_night_add_player(name)
        
        # Edit the original message to display the updated view
        await original_message.edit(view=view)
        await ctx.message.delete()
    else:
        await ctx.send("No active tracking session found in this channel.")

@bot.command()
async def gpt_query(ctx):
    global PNM
    # Get the raw message content
    raw_message = ctx.message.content

    # Extract the query part (removes the command prefix and name)
    command_prefix = ctx.prefix
    command_name = ctx.invoked_with
    query = raw_message[len(command_prefix + command_name):].strip()

    # Get the sender's username
    sender_username = ctx.author.name.capitalize()
    sender_player=PNM.did_to_name[sender_username]
    
    # Replace user mentions (formatted as <@user_id>) with their display names and construct the formatted string
    for user in ctx.message.mentions:
        mention_placeholder = f'<@{user.id}>'
        query = query.replace(mention_placeholder, f'player:{PNM.did_to_name[user.name.capitalize()]}')

    # Construct the final formatted query
    formatted_query = f"Query by player:{sender_player} [{query}]"
    output_path=PNM.gpt_query_stats(formatted_query)
    await ctx.send(file=discord.File(output_path))
    os.remove(output_path)

@bot.command()
async def checkdata(ctx):
    global PNM
    await ctx.send(PNM.checkdata())

@bot.command()
async def leaderboard(ctx):
    global PNM
    await ctx.send(PNM.leaderboard())

@bot.command()
async def pokersheet(ctx):
    global PNM
    await ctx.send(PNM.gs_url)
    
@bot.command()
async def reconnect(ctx):
    global PNM
    await ctx.send(PNM.reconnect())

@bot.command()
async def stats(ctx, user: commands.MemberConverter()=None):
    global PNM
    
    name=ctx.author.name
    if user!=None:
        name=user.name
    
    output_path=PNM.personal_stats(name)
    await ctx.send(file=discord.File(output_path))
    os.remove(output_path)

# Start the keep-alive mechanism
PNM.keep_google_connection_alive()
DB.keep_alive_rethinkdb()
bot.run(TOKEN)
