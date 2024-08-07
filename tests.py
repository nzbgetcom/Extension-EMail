#
# This file is part of nzbget. See <https://nzbget.com>.
#
# Copyright (C) 2024 Denis <denis@nzbget.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


from os.path import dirname
import unittest
import json

ROOT_DIR = dirname(__file__)


class Tests(unittest.TestCase):

    def test_manifest(self):
        with open(ROOT_DIR + "/manifest.json", encoding="utf-8") as file:
            try:
                json.loads(file.read())
            except ValueError as e:
                self.fail(f"manifest.json is not valid: {e}")


if __name__ == "__main__":
    unittest.main()
