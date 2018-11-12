# coding=utf-8
from __future__ import absolute_import
import logging
import threading
from stat import S_ISREG, ST_MTIME, ST_MODE
import os, sys, time
import requests
import backoff

from .utils import ip_addr

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import octoprint.plugin

_logger = logging.getLogger(__name__)

PRINTQ_FOLDER = "_printq_"
POLL_INTERVAL = 30  #30 seconds
CLEANUP_DIR_INTERVAL = 60*60  # 1 hour
CLEANUP_AGE = 60*60*24*14     # files older than 2 weeks will be cleaned up

class PrintQueuePlugin(octoprint.plugin.SettingsPlugin,
			octoprint.plugin.StartupPlugin,
			octoprint.plugin.EventHandlerPlugin,
			octoprint.plugin.AssetPlugin,
			octoprint.plugin.TemplatePlugin):

	def get_template_configs(self):
		return [
		    dict(type="settings", custom_bindings=False)
		]

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		return dict(
                        endpoint_prefix="https://app.gofab.xyz/"
		)

	##~~ AssetPlugin mixin

	def get_assets(self):
		# Define your plugin's asset files to automatically include in the
		# core UI here.
		return dict(
			js=["js/PrintQueue.js"],
			css=["css/PrintQueue.css"],
			less=["less/PrintQueue.less"]
		)

	##~~ Softwareupdate hook

	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
		# for details.
		return dict(
			PrintQueue=dict(
				displayName="PrintQueue Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="kennethjiang",
				repo="OctoPrint-PrintQueue",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/kennethjiang/OctoPrint-PrintQueue/archive/{target_version}.zip"
			)
		)


	##~~ Eventhandler mixin

	def on_event(self, event, payload):
		if event.startswith("Print"):
			self.send_printer_status({
				"octoprint_event": {
					"event_type": event,
					"data": payload
					},
				"octoprint_data": self.octoprint_data()
				})

	##~~Startup Plugin
	def on_startup(self, host, port):
		self._octoprint_port = port if port else self._settings.getInt(["server", "port"])
		self._octoprint_ip = ip_addr()

	def on_after_startup(self):
		self.ensure_storage()

		main_thread = threading.Thread(target=self.main_loop)
		main_thread.daemon = True
		main_thread.start()


	## Private methods

	def octoprint_data(self):
		data = self._printer.get_current_data()
		data['temperatures'] = self._printer.get_current_temperatures()
		data['octoprint_port'] = self._octoprint_port
		data['octoprint_ip'] = self._octoprint_ip
		return data

	@backoff.on_exception(backoff.expo, Exception, max_value=240)
	def main_loop(self):
		last_poll = 0
		last_cleanup_dir = 0
		while True:
			if last_poll < time.time() - POLL_INTERVAL:
				last_poll = time.time()
				self.send_printer_status({"octoprint_data": self.octoprint_data()})

			if last_cleanup_dir < time.time() - CLEANUP_DIR_INTERVAL:
				last_cleanup_dir = time.time()
				self.cleanup_data_dir()

			time.sleep(1)

	def send_printer_status(self, json_data):
		combined_token = self._settings.get(["auth_token"])
		if not combined_token:
			_logger.warning("Auth token is not configured.")
			return

		printer_id, printer_token = combined_token.split(";", 1)

		headers = {"X-Printer-Id": printer_id, "X-Printer-Token": printer_token}
		endpoint = self._settings.get(["endpoint_prefix"]) + "api/printer_statuses.json"
		import json
		_logger.debug(json.dumps(json_data))
		resp = requests.post(
			endpoint,
			headers=headers,
			json=json_data
			)
		resp.raise_for_status()
		for command in resp.json():
			if command["command"] == "print":
				self.download_and_print(command["data"]["file_url"], command["data"]["file_name"])
			if command["command"] == "cancel":
				self._printer.cancel_print()
			if command["command"] == "pause":
				self._printer.pause_print()
			if command["command"] == "resume":
				self._printer.resume_print()

	def download_and_print(self, file_url, file_name):
		import os
		r = requests.get(file_url, allow_redirects=True)
		r.raise_for_status()
		target_path = os.path.join(self._g_code_folder, file_name)
		open(target_path, "wb").write(r.content)
		self._printer.select_file(target_path, False, printAfterSelect=True)

	def ensure_storage(self):
		self._file_manager.add_folder("local", PRINTQ_FOLDER, ignore_existing=True)
		self._g_code_folder = self._file_manager.path_on_disk("local", PRINTQ_FOLDER)

	def cleanup_data_dir(self):

		# List all files with modification times: https://stackoverflow.com/questions/168409/how-do-you-get-a-directory-listing-sorted-by-creation-date-in-python
		# get all entries in the directory w/ stats
		entries = [os.path.join(self._g_code_folder, fn) for fn in os.listdir(self._g_code_folder) if not fn.endswith('.json')]
		entries = [(os.stat(path), path) for path in entries]

		# leave only regular files, insert creation date
		entries = [(stat[ST_MTIME], path) for stat, path in entries if S_ISREG(stat[ST_MODE])]

		for entry in entries:
			mtime, path = entry
			if mtime < time.time() - CLEANUP_AGE:
				os.remove(path)

# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "PrintQueue Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = PrintQueuePlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

