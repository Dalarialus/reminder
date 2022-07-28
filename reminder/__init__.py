from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redbot.core import Red

from .reminder import Reminder

def setup(bot: Red):
    bot.add_cog(Reminder(bot))