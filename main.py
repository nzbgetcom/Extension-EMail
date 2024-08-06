#
# E-Mail post-processing script for NZBGet
#
# Copyright (C) 2013-2017 Andrey Prygunkov <hugbug@users.sourceforge.net>
# Copyright (C) 2024 Denis <denis@nzbget.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import os
import sys
import datetime
import smtplib

from email.mime.text import MIMEText
from email.header import Header
from urllib.parse import quote
from xmlrpc.client import ServerProxy

# Exit codes used by NZBGet
POSTPROCESS_SUCCESS = 93
POSTPROCESS_ERROR = 94
POSTPROCESS_NONE = 95


print("[DETAIL] Script successfully started")
sys.stdout.flush()

required_options = (
    "NZBPO_FROM",
    "NZBPO_TO",
    "NZBPO_SERVER",
    "NZBPO_PORT",
    "NZBPO_ENCRYPTION",
    "NZBPO_USERNAME",
    "NZBPO_PASSWORD",
)
for optname in required_options:
    if not optname in os.environ:
        print(
            "[ERROR] Option %s is missing in configuration file. Please check script settings"
            % optname[6:]
        )
        sys.exit(POSTPROCESS_ERROR)

# Check if the script is executed from settings page with a custom command
command = os.environ.get("NZBCP_COMMAND")
test_mode = command == "ConnectionTest"
if command != None and not test_mode:
    print("[ERROR] Invalid command " + command)
    sys.exit(POSTPROCESS_ERROR)

status = os.environ.get("NZBPP_STATUS") if not test_mode else "SUCCESS/ALL"
total_status = os.environ.get("NZBPP_TOTALSTATUS") if not test_mode else "SUCCESS"

# If any script fails the status of the item in the history is "WARNING/SCRIPT".
# This status however is not passed to pp-scripts in the env var "NZBPP_STATUS"
# because most scripts are independent of each other and should work even
# if a previous script has failed. But not in the case of E-Mail script,
# which should take the status of the previous scripts into account as well.
if total_status == "SUCCESS" and os.environ.get("NZBPP_SCRIPTSTATUS") == "FAILURE":
    total_status = "WARNING"
    status = "WARNING/SCRIPT"

success = total_status == "SUCCESS"

if success and os.environ.get("NZBPO_SENDMAIL") == "OnFailure" and not test_mode:
    print("[INFO] Skipping sending of message for successful download")
    sys.exit(POSTPROCESS_NONE)

if success:
    subject = 'Success for "%s"' % (os.environ.get("NZBPP_NZBNAME", "Test download"))
    text = 'Download of "%s" has successfully completed.' % (
        os.environ.get("NZBPP_NZBNAME", "Test download")
    )
else:
    subject = 'Failure for "%s"' % (os.environ["NZBPP_NZBNAME"])
    text = 'Download of "%s" has failed.' % (os.environ["NZBPP_NZBNAME"])

text += "\nStatus: %s" % status

if (
    os.environ.get("NZBPO_STATISTICS") == "yes"
    or os.environ.get("NZBPO_NZBLOG") == "Always"
    or (os.environ.get("NZBPO_NZBLOG") == "OnFailure" and not success)
) and not test_mode:
    # To get statistics or the post-processing log we connect to NZBGet via XML-RPC.
    # For more info visit https://nzbget.com/documentation/api/
    # First we need to know connection info: host, port and password of NZBGet server.
    # NZBGet passes all configuration options to post-processing script as
    # environment variables.
    host = os.environ["NZBOP_CONTROLIP"]
    port = os.environ["NZBOP_CONTROLPORT"]
    username = os.environ["NZBOP_CONTROLUSERNAME"]
    password = os.environ["NZBOP_CONTROLPASSWORD"]

    if host == "0.0.0.0":
        host = "127.0.0.1"

    # Build a URL for XML-RPC requests
    rpcUrl = "http://%s:%s@%s:%s/xmlrpc" % (
        quote(username),
        quote(password),
        host,
        port,
    )

    # Create remote server object
    server = ServerProxy(rpcUrl)

if os.environ.get("NZBPO_STATISTICS") == "yes" and not test_mode:
    # Find correct nzb in method listgroups
    groups = server.listgroups(0)
    nzbID = int(os.environ["NZBPP_NZBID"])
    for nzbGroup in groups:
        if nzbGroup["NZBID"] == nzbID:
            break

    text += "\n\nStatistics:"

    # add download size
    DownloadedSize = float(nzbGroup["DownloadedSizeMB"])
    unit = " MB"
    if DownloadedSize > 1024:
        DownloadedSize = DownloadedSize / 1024  # GB
        unit = " GB"
    text += "\nDownloaded size: %.2f" % (DownloadedSize) + unit

    # add average download speed
    DownloadedSizeMB = float(nzbGroup["DownloadedSizeMB"])
    DownloadTimeSec = float(nzbGroup["DownloadTimeSec"])
    if DownloadTimeSec > 0:  # check x/0 errors
        avespeed = DownloadedSizeMB / DownloadTimeSec  # MB/s
        unit = " MB/s"
        if avespeed < 1:
            avespeed = avespeed * 1024  # KB/s
            unit = " KB/s"
        text += "\nAverage download speed: %.2f" % (avespeed) + unit

    def format_time_sec(sec):
        Hour = sec / 3600
        Min = (sec % 3600) / 60
        Sec = sec % 60
        return "%d:%02d:%02d" % (Hour, Min, Sec)

    # add times
    text += "\nTotal time: " + format_time_sec(
        int(nzbGroup["DownloadTimeSec"]) + int(nzbGroup["PostTotalTimeSec"])
    )
    text += "\nDownload time: " + format_time_sec(int(nzbGroup["DownloadTimeSec"]))
    text += "\nVerification time: " + format_time_sec(
        int(nzbGroup["ParTimeSec"]) - int(nzbGroup["RepairTimeSec"])
    )
    text += "\nRepair time: " + format_time_sec(int(nzbGroup["RepairTimeSec"]))
    text += "\nUnpack time: " + format_time_sec(int(nzbGroup["UnpackTimeSec"]))

# add list of downloaded files
files = False
if os.environ.get("NZBPO_FILELIST") == "yes" and not test_mode:
    text += "\n\nFiles:"
    for dirname, dirnames, filenames in os.walk(os.environ["NZBPP_DIRECTORY"]):
        for filename in filenames:
            text += (
                "\n"
                + os.path.join(dirname, filename)[
                    len(os.environ["NZBPP_DIRECTORY"]) + 1 :
                ]
            )
            files = True
    if not files:
        text += "\n<no files found in the destination directory (moved by a script?)>"

# add _brokenlog.txt (if exists)
if os.environ.get("NZBPO_BROKENLOG") == "yes" and not test_mode:
    brokenlog = "%s/_brokenlog.txt" % os.environ["NZBPP_DIRECTORY"]
    if os.path.exists(brokenlog):
        text += "\n\nBrokenlog:\n" + open(brokenlog, "r").read().strip()

# add post-processing log
if (
    os.environ.get("NZBPO_NZBLOG") == "Always"
    or (os.environ.get("NZBPO_NZBLOG") == "OnFailure" and not success)
) and not test_mode:

    # To get the item log we connect to NZBGet via XML-RPC and call
    # method "loadlog", which returns the log for a given nzb item.
    # For more info visit https://nzbget.com/documentation/api/

    # Call remote method 'loadlog'
    nzbid = int(os.environ["NZBPP_NZBID"])
    log = server.loadlog(nzbid, 0, 10000)

    # Now iterate through entries and save them to message text
    if len(log) > 0:
        text += "\n\nNzb-log:"
        for entry in log:
            text += "\n%s\t%s\t%s" % (
                entry["Kind"],
                datetime.datetime.fromtimestamp(int(entry["Time"])),
                entry["Text"],
            )

# Create message
print("[DETAIL] Creating Email")
msg = MIMEText(text.encode("utf-8"), "plain", "utf-8")
msg["Subject"] = Header(subject, "utf-8")
msg["From"] = os.environ["NZBPO_FROM"]
msg["To"] = os.environ["NZBPO_TO"]
msg["Date"] = datetime.datetime.now(datetime.timezone.utc).strftime(
    "%a, %d %b %Y %H:%M:%S +0000"
)
msg["X-Application"] = "NZBGet"

# Send message
print("[DETAIL] Sending E-Mail")
sys.stdout.flush()
try:
    if os.environ["NZBPO_ENCRYPTION"] == "force":
        smtp = smtplib.SMTP_SSL(os.environ["NZBPO_SERVER"], os.environ["NZBPO_PORT"])
    else:
        smtp = smtplib.SMTP(os.environ["NZBPO_SERVER"], os.environ["NZBPO_PORT"])

    if os.environ["NZBPO_ENCRYPTION"] == "yes":
        smtp.starttls()

    if os.environ["NZBPO_USERNAME"] != "" and os.environ["NZBPO_PASSWORD"] != "":
        smtp.login(os.environ["NZBPO_USERNAME"], os.environ["NZBPO_PASSWORD"])

    smtp.sendmail(
        os.environ["NZBPO_FROM"], os.environ["NZBPO_TO"].split(","), msg.as_string()
    )

    smtp.quit()
except Exception as err:
    print("[ERROR] %s" % err)
    sys.exit(POSTPROCESS_ERROR)

# All OK, returning exit status 'POSTPROCESS_SUCCESS' (int <93>) to let NZBGet know
# that our script has successfully completed.
sys.exit(POSTPROCESS_SUCCESS)
