# coding=utf-8
from __future__ import absolute_import
import re
import logging
import threading
import time
import requests
import backoff

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
	def on_after_startup(self):
		self.ensure_storage()

		main_thread = threading.Thread(target=self.poll_loop)
		main_thread.daemon = True
		main_thread.start()


	## Private methods

	def octoprint_data(self):
		data = self._printer.get_current_data()
		data['temperatures'] = self._printer.get_current_temperatures()
		return data

	def ensure_storage(self):
		self._file_manager.add_folder("local", PRINTQ_FOLDER, ignore_existing=True)
		self._g_code_folder = self._file_manager.path_on_disk("local", PRINTQ_FOLDER)

	@backoff.on_exception(backoff.expo, Exception, max_value=240)
	def poll_loop(self):
		while True:
			self.send_printer_status({"octoprint_data": self.octoprint_data()})
			time.sleep(30)

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
		file_name = re.sub(r'[^\w\.]', '_', file_name)

		import os
		r = requests.get(file_url, allow_redirects=True)
		r.raise_for_status()
		target_path = os.path.join(self._g_code_folder, file_name)
		open(target_path, "wb").write(r.content)
		self._printer.select_file(target_path, False, printAfterSelect=True)

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

