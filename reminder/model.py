from __future__ import annotations
from typing import Optional, TYPE_CHECKING, Union

import asyncio
import attr
import discord

from datetime import datetime

if TYPE_CHECKING:
    from .reminder import Reminder

@attr.s(slots=True)
class ReminderModel:
    cog: Reminder = attr.field()
    id: str = attr.field()
    author: Optional[discord.Member] = attr.field()
    tagged: discord.Member = attr.field()
    message: discord.Message = attr.field()
    channel: discord.TextChannel = attr.field()
    repeating: bool = attr.field(default=False)
    snoozing: bool = attr.field(default=False)
    text: str = attr.field(default=None)
    remaining: int = attr.field(default=0)
    task: asyncio.Task = attr.field(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        asyncio.create_task(self.start())

    async def start(self) -> None:
        if self.remaining > 0:
            await asyncio.sleep(self.remaining)

        async with self.cog.config.guild(self.channel.guild).reminders() as reminders:
            try:
                reminders[self.id]
            except KeyError:
                return
            
            self.repeating = reminders[self.id]["repeating"]
            self.snoozing = reminders[self.id]["snoozing"]

            if not self.repeating:
                async with self.cog.config.member(self.tagged).timers() as timers:
                    try:
                        timers.remove(int(self.id))
                    except ValueError:
                        pass

                del reminders[self.id]

        if not self.snoozing:
            if self.author:
                msg: str = f"{self.tagged.mention}, a reminder from {self.author.mention} appeared:"
            else:
                msg: str = f"{self.tagged.mention}, a reminder appeared:"

            msg = f"{msg}\n" \
                f"```\n{self.text}```\n"

            try:
                if self.message:
                    await self.message.reply(msg)
                else:
                    await self.channel.send(msg)
            except:
                return
        
        if self.repeating:
            if self.task:
                self.task.cancel()
                self.cog._repeat_tasks.remove(self.task)
            
            self.task = asyncio.create_task(self.start())
            self.cog._repeat_tasks.append(self.task)