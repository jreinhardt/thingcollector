# Copyright 2014 Johannes Reinhardt <jreinhardt@ist-dein-freund.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import apscheduler
from apscheduler.scheduler import Scheduler

class NowTrigger:
    def __init__(self):
        self.triggered = False
    def get_next_fire_time(self,start):
        if not self.triggered:
            self.triggered = True
            return start
        else:
            return None

scheduler = Scheduler()
scheduler.start()

