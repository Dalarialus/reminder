from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Pattern, Union

if TYPE_CHECKING:
    from redbot.core import Red

import asyncio
import discord
import re

from redbot.core import commands, Config

from datetime import datetime, timedelta
from dateutil.parser import parse, ParserError

from .model import ReminderModel

REGEX: Pattern = re.compile(r"(?P<before><@)(?P<id>!*&*[0-9]+)(?P<after>>)")
REGEX_TEXT: Pattern = re.compile(r"(?P<to>to)\s(?P<text>.+)", re.I)

class Reminder(commands.Cog):
    """
    Reminder Cog.
    """
    def __init__(self, bot: Red) -> None:
        self.bot: Red = bot
        self.config: Config = Config.get_conf(self, 201724124124, force_registration=True)
        default_member: dict = {
            "timers": [],
        }
        default_guild: dict = {
            "reminders": {},
        }
        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)
        self._timers_check: asyncio.Task = self.bot.loop.create_task(self._timers())
        self._repeat_tasks: list[asyncio.Task] = []
    
    def cog_unload(self) -> None:
        self._timers_check.cancel()
        for task in self._repeat_tasks:
            task.cancel()

    def cog_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        return True
    
    async def _timers(self) -> None:
        await self.bot.wait_until_ready()

        guilds: dict = await self.config.all_guilds()
        guilds: list = [self.bot.get_guild(guild) for guild in guilds if self.bot.get_guild(guild)]
        
        if not guilds:
            return

        for guild in guilds:
            reminders: dict
            if reminders := await self.config.guild(guild).reminders.all():
                for id in reminders:
                    data: dict = reminders[id]
                    data["author"] = guild.get_member(data["author"])

                    if not (channel := guild.get_channel(data["channel"])):
                        return
                    data["channel"] = channel
                    
                    if not (message := await channel.fetch_message(data["message"])):
                        return
                    data["message"] = message

                    if not (tagged := guild.get_member(data["tagged"])):
                        return
                    data["tagged"] = tagged

                    ReminderModel(self, id, **data)

    @commands.command()
    async def remind(self, ctx: commands.Context, *, text: Optional[str]) -> None:
        """
        Set up a reminder for you or a member.
        The text, if any, must follow the "to" keyword. See examples below.
        
        Usage examples
        --------------------------
        `(Omitting timezone will use the bot's timezone)`

        [p]remind @member at 8PM on 26/07/2022 to dance
        [p]remind at 8:00PM on 26/07/2022 to dance
        [p]remind @member at 8PM GMT+1 26/07/2022 to dance
        [p]remind at 8:00PM GMT+1 to dance
        """

        member: discord.Member = ctx.author
        match: Optional[re.Match]
        if match := REGEX.match(text):
            text = text.replace(text[match.start():match.end()], "")
            try:
                member = ctx.guild.get_member(int(match.groupdict()["id"]))
            except commands.MemberNotFound:
                member = ctx.author

        match: Optional[re.Match]
        if match := REGEX_TEXT.search(text):
            match_text: str = match.groupdict()["text"]
        else:
            match_text = None

        if text.startswith("in"):
            time_text: str = text.lstrip("in ")

            if match_text:
                time_text = time_text.split(f" to {match.groupdict()['text']}")[0]

            time: Optional[timedelta]
            if not (time := commands.converter.parse_timedelta(time_text)):
                await ctx.send("Wrong given time, please check the command's example.", delete_after=5)
                return
        else:
            time: tuple[datetime, tuple[str]]
            try:
                time = parse(text, fuzzy=True)
            except ParserError:
                await ctx.send("Wrong given time, please check the command's example.", delete_after=5)
                return
        
        channel: discord.TextChannel = ctx.channel
        
        async with self.config.guild(ctx.guild).reminders() as reminders:
            _id: int = int(max(reminders.keys())) + 1 if reminders else 1

            if isinstance(time, timedelta):
                remaining: int = int(time.total_seconds())
            else:
                remaining: int = int(time.timestamp() - datetime.now().timestamp())

            reminders[str(_id)] = {
                "author": None if member == ctx.author else ctx.author.id,
                "message": ctx.message.id,
                "channel": channel.id,
                "tagged": member.id,
                "remaining": remaining,
                "text": match_text,
                "repeating": False,
                "snoozing": False
            }
        
        async with self.config.member(member).timers() as timers:
            timers.append(_id)

        reminder: ReminderModel = ReminderModel(**{
                "cog": self,
                "id": str(_id),
                "author": None if member == ctx.author else ctx.author,
                "message": ctx.message,
                "channel": channel,
                "tagged": member,
                "remaining": remaining,
                "text": match_text,
        })
        
        await ctx.send(
            "Successfully created a timer with the following informations:" \
                f"\nID: {reminder.id}\nNotify: {member.mention}\nEnds: <t:{int(datetime.now().timestamp() + reminder.remaining)}:R>",
                allowed_mentions=discord.AllowedMentions.none(),
                delete_after=10
            )
    
    @commands.group()
    async def timer(self, ctx: commands.Context) -> None:
        "Commands group for reminder."
        ...

    @timer.command()
    async def list(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """List your reminders or an user's reminder if you are mod."""

        if member and not (await self.bot.is_mod(ctx.author) or await self.bot.is_admin(ctx.author)):
            await ctx.send("You require a mod level to check an user's reminders list.", delete_after=5)
            return

        member = member or ctx.author

        timers: dict 
        if not (timers := await self.config.member(member).timers()):
            await ctx.send(f"No reminders for {member.mention}", allowed_mentions=discord.AllowedMentions.none(), delete_after=5)
            return

        _reminders: dict = await self.config.guild(ctx.guild).reminders.all()
        reminders: dict = {k:v for k, v in _reminders.items() if int(k) in timers}

        msg: str = f"{member.mention}'s Reminders"
        for index, reminder in enumerate(reminders, start=1):
            if index == 11:
                break
            msg += f"\n{index}. " \
            f"Text: `{reminders[reminder]['text'][:30] + '[...]' if len(reminders[reminder]['text'][:30]) > 30 else reminders[reminder]['text']}`" \
            f"\n    Snooze: `{reminders[reminder]['snoozing']}`" \
            f"\n    Repeating: `{reminders[reminder]['repeating']}`" \
            f"\n    Ends: <t:{reminders[reminder]['endtime']}:R>"
        
        try:
            await ctx.author.send(msg)
        except discord.Forbidden:
            await ctx.send(msg, allowed_mentions=discord.AllowedMentions.none())
    
    @timer.command()
    async def snooze(self, ctx: commands.Context, reminder_id: int) -> None:
        """Enable snooze for a reminder."""

        reminders: list = await self.config.member(ctx.author).timers()
        if reminder_id not in reminders:
            await ctx.send(f"You do not own a reminder with id `{reminder_id}`", delete_after=5)
            return
        
        async with self.config.guild(ctx.guild).reminders() as reminders:
            reminders[str(reminder_id)]["snoozing"] = True
        
        await ctx.send(f"Changed reminder setting\nID: {reminder_id}\nSnoozing: True", delete_after=5)

    @timer.command()
    async def unsnooze(self, ctx: commands.Context, reminder_id: int) -> None:
        """Disable snooze for a reminder."""

        reminders: list = await self.config.member(ctx.author).timers()
        if reminder_id not in reminders:
            await ctx.send(f"You do not own a reminder with id `{reminder_id}`", delete_after=5)
            return
        
        async with self.config.guild(ctx.guild).reminders() as reminders:
            reminders[str(reminder_id)]["snoozing"] = False
        
        await ctx.send(f"Changed reminder setting\nID: {reminder_id}\nSnoozing: False", delete_after=5)

    @timer.command()
    async def repeat(self, ctx: commands.Context, reminder_id: int) -> None:
        """
        Enable repeating for a reminder.
        `Repeating will use the same reminder creation time lapse`
        """

        reminders: list = await self.config.member(ctx.author).timers()
        if reminder_id not in reminders:
            await ctx.send(f"You do not own a reminder with id `{reminder_id}`", delete_after=5)
            return
        
        async with self.config.guild(ctx.guild).reminders() as reminders:
            reminders[str(reminder_id)]["repeating"] = True
        
        await ctx.send(f"Changed reminder setting\nID: {reminder_id}\nRepeating: True", delete_after=5)

    @timer.command()
    async def unrepeat(self, ctx: commands.Context, reminder_id: int) -> None:
        """Disable repeating for a reminder."""

        reminders: list = await self.config.member(ctx.author).timers()
        if reminder_id not in reminders:
            await ctx.send(f"You do not own a reminder with id `{reminder_id}`", delete_after=5)
            return
        
        async with self.config.guild(ctx.guild).reminders() as reminders:
            reminders[str(reminder_id)]["repeating"] = False
        
        await ctx.send(f"Changed reminder setting\nID: {reminder_id}\nRepeating: False", delete_after=5)